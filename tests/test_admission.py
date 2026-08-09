#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Admission control: thermal core budget, queue order, and the wrapper side.

Everything runs in an isolated TG_BASE. Live pids come from short sleep
children, never from real jobs. Run with: python3 tests/test_admission.py
"""
import importlib.machinery
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="admission_")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
os.environ["SAFE_RUN_ADMIT_POLL"] = "0.02"
os.environ["SAFE_RUN_AFTER_POLL"] = "0.02"
os.environ["SAFE_RUN_ADMIT_GRACE"] = "0.1"

g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()
sr = importlib.machinery.SourceFileLoader("sr", os.path.join(SRC, "safe-run")).load_module()

MANAGED = os.path.join(BASE, "managed")
os.makedirs(MANAGED, exist_ok=True)
json.dump({"p_cores": 10}, open(os.path.join(BASE, "hardware.json"), "w"))

passed = total = 0
children = []


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


def child_pid():
    p = subprocess.Popen(["sleep", "60"])
    children.append(p)
    return p.pid


def reg(pid, name="job", cores=None, queued=False, priority=5, since=None):
    d = {"pid": pid, "name": name, "started": time.time()}
    if cores is not None:
        d["cores"] = cores
    if queued:
        d.update({"queued": True, "priority": priority,
                  "since": since if since is not None else time.time()})
    with open(os.path.join(MANAGED, "%d.json" % pid), "w") as f:
        json.dump(d, f)


def clean():
    for fn in os.listdir(MANAGED):
        os.unlink(os.path.join(MANAGED, fn))


CFG = {"soc_pause_c": 85.0, "soc_resume_c": 76.0, "admission_control": True}

print("1. thermal core budget")
a = g.admission_update(CFG, 60.0, 0, 0.0)
test("cool chip: full P-core budget", a["budget_cores"] == 10, a)
a = g.admission_update(CFG, 80.0, 1, 0.0)
test("between resume and pause: half the pool", a["budget_cores"] == 5, a)
a = g.admission_update(CFG, 90.0, 2, 0.0)
test("at or above pause: zero admissions", a["budget_cores"] == 0, a)
a = g.admission_update(CFG, 60.0, 2, 0.0)
test("guard level >= 2 wins even with a cool chip", a["budget_cores"] == 0, a)
a = g.admission_update(CFG, None, 0, 0.0)
test("no chip sensor: full budget (admission still serializes)",
     a["budget_cores"] == 10, a)

print("\n2. admission math with running jobs and queue")
clean()
running = child_pid()
reg(running, name="big", cores=6)
q_small = child_pid()
reg(q_small, name="small", cores=4, queued=True)
a = g.admission_update(CFG, 60.0, 0, 0.0)
test("used counts the running declaration", a["used_cores"] == 6, a)
test("4-core job fits into the remaining 4", q_small in a["admitted"], a)

clean()
reg(running, name="big", cores=6)
q_big = child_pid()
reg(q_big, name="huge", cores=6, queued=True, since=1.0)
q_tail = child_pid()
reg(q_tail, name="tiny", cores=1, queued=True, since=2.0)
a = g.admission_update(CFG, 60.0, 0, 0.0)
test("head of line blocks: 6 > 4 free, so nothing is admitted",
     a["admitted"] == [], a)
test("a small job must NOT overtake the head", q_tail not in a["admitted"], a)

print("\n3. priority and arrival order")
clean()
q_late_important = child_pid()
reg(q_late_important, name="vip", cores=2, queued=True, priority=1, since=100.0)
q_early_normal = child_pid()
reg(q_early_normal, name="norm", cores=2, queued=True, priority=5, since=1.0)
a = g.admission_update(CFG, 60.0, 0, 0.0)
test("lower priority value is admitted first",
     a["admitted"][:1] == [q_late_important], a)
test("both fit, both admitted", set(a["admitted"]) == {q_late_important, q_early_normal}, a)

print("\n4. safety of the unknown")
clean()
undeclared = child_pid()
reg(undeclared, name="legacy")                      # no cores field
a = g.admission_update(CFG, 60.0, 0, 0.0)
test("undeclared running job counts as the FULL P-core pool",
     a["used_cores"] == 10, a)

clean()
q1 = child_pid()
reg(q1, name="q1", cores=2, queued=True)
a = g.admission_update(CFG, 60.0, 0, 9.0)
test("foreign load is not billed to admission when nothing is declared",
     a["foreign_load"] == 9, a)
test("foreign load shrinks the budget below the head's cores",
     a["admitted"] == [], a)

print("\n5. fail-open on arbiter error")


class BrokenCfg(dict):
    def get(self, *a, **k):
        raise RuntimeError("boom")


clean()
qx = child_pid()
reg(qx, name="qx", cores=2, queued=True)
a = g.admission_update(BrokenCfg(), 60.0, 0, 0.0)
test("arbiter error admits everyone (must not become a second kill switch)",
     a.get("error") is True and qx in a["admitted"], a)

print("\n6. queued wrapper is never a signal target")
clean()
qp = child_pid()
reg(qp, name="waiting", cores=2, queued=True)
pids, _normal = g.managed_pids_from_saferun()
test("queued pre-registration excluded from pause targeting", qp not in pids, pids)
test("its registration file survives the scan",
     os.path.exists(os.path.join(MANAGED, "%d.json" % qp)), "unlinked")

print("\n7. wrapper: admission_wait")


def snapshot(admission):
    p = os.path.join(BASE, "status.json")
    d = {"level": 0, "chip_c": 60.0}
    if admission is not None:
        d["admission"] = admission
    json.dump(d, open(p, "w"))
    os.utime(p)


clean()
opt = {"name": "me", "cores": 3, "priority": 5}
snapshot(None)
test("daemon without admission support: no waiting",
     sr.admission_wait(opt) is None, "hung or returned a path")
test("placeholder removed after the no-support path",
     not os.listdir(MANAGED), os.listdir(MANAGED))

snapshot({"admitted": [], "queued": []})


def admit_soon():
    time.sleep(0.15)
    snapshot({"admitted": [os.getpid()], "queued": []})


t = threading.Thread(target=admit_soon)
t.start()
t0 = time.time()
placeholder = sr.admission_wait(opt)
t.join()
test("waits until admitted, then returns the placeholder path",
     placeholder is not None and time.time() - t0 >= 0.1, placeholder)
held = json.load(open(placeholder)) if placeholder else {}
test("placeholder flips to queued=false and keeps the declared cores",
     held.get("queued") is False and held.get("cores") == 3, held)
if placeholder:
    os.unlink(placeholder)

p = os.path.join(BASE, "status.json")
os.utime(p, (time.time() - 500, time.time() - 500))
test("stale snapshot: start without admission, not a trap",
     sr.admission_wait(opt) is None, "hung")
test("placeholder removed after the stale path", not os.listdir(MANAGED),
     os.listdir(MANAGED))

print("\n8. wrapper: --after")
clean()
holder = child_pid()
reg(holder, name="pred", cores=1)
test("job_named_alive sees the live predecessor", sr.job_named_alive("pred"), "blind")


def release_soon():
    time.sleep(0.15)
    clean()


t = threading.Thread(target=release_soon)
t.start()
t0 = time.time()
sr.wait_for_job("pred")
t.join()
test("wait_for_job returns once the predecessor is gone",
     time.time() - t0 >= 0.1, "%.3f s" % (time.time() - t0))
test("no live registration means no waiting at all",
     (lambda s: (sr.wait_for_job("pred"), time.time() - s)[1])(time.time()) < 0.1,
     "waited despite empty managed/")

print("\n9. defaults and clamps")
argv0 = sys.argv
sys.argv = ["safe-run", "--cores", "0", "--queue-priority", "99", "--", "true"]
opt2, _ = sr.parse()
sys.argv = argv0
test("cores clamps up to 1", opt2["cores"] == 1, opt2["cores"])
test("priority clamps down to 9", opt2["priority"] == 9, opt2["priority"])
test("declared-core default equals hardware p_cores", sr.default_cores() == 10,
     sr.default_cores())

print("\n10. review fixes (adversarial round)")
clean()
over = child_pid()
reg(over, name="greedy", cores=14)                  # above the 10-core pool
a = g.admission_update(CFG, 60.0, 0, 0.0)
test("running declaration is capped at the P-core pool", a["used_cores"] == 10, a)
clean()
q_over = child_pid()
reg(q_over, name="greedy_q", cores=14, queued=True)
a = g.admission_update(CFG, 60.0, 0, 0.0)
test("over-declared queued job is admissible on a free machine (capped)",
     q_over in a["admitted"], a)

clean()
reg(os.getpid(), name="self")
test("--after never waits for our own pid (recycled-pid self-deadlock)",
     not sr.job_named_alive("self"), "sees itself")

clean()
dead = subprocess.Popen(["sleep", "0.01"])
dead.wait()
reg(dead.pid, name="ghost", cores=10, queued=True)
g.managed_pids_from_saferun()
test("dead queued placeholder is unlinked by the managed scan",
     not os.path.exists(os.path.join(MANAGED, "%d.json" % dead.pid)),
     os.listdir(MANAGED))

clean()
loose = child_pid()
reg(loose, name="planted", cores=8)
os.chmod(os.path.join(MANAGED, "%d.json" % loose), 0o666)
a = g.admission_update(CFG, 60.0, 0, 0.0)
test("group/other-writable registration cannot consume the budget",
     a["used_cores"] == 0, a)

clean()
snapshot({"admitted": [], "queued": []})
json.dump({"level": 0, "chip_c": 60.0}, open(os.path.join(BASE, "status.json"), "w"))
t0 = time.time()
r = sr.admission_wait({"name": "x", "cores": 1, "priority": 5})
test("fresh snapshot without the block: bounded grace, then start",
     r is None and time.time() - t0 >= 0.1, "%.3f s" % (time.time() - t0))

for p_ in children:
    p_.kill()
print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
