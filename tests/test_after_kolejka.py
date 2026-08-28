#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`safe-run --after`: a wrapper that is still waiting counts as a live job.

Reported from an omniai queue (20.08): 3d chained `--after 3c` started alongside 3b,
because 3c was only waiting for 3b and had nothing in managed/ yet. Everything runs in
an isolated TG_BASE; live pids come from short sleep children and threads, never from
real jobs. Run with: python3 tests/test_after_kolejka.py
"""
import importlib.machinery
import json
import os
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="after_")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
os.environ["SAFE_RUN_AFTER_POLL"] = "0.02"

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


def reg(pid, name, cores=4):
    with open(os.path.join(MANAGED, "%d.json" % pid), "w") as f:
        json.dump({"pid": pid, "name": name, "started": time.time(), "cores": cores}, f)


def clean():
    for fn in os.listdir(MANAGED):
        os.unlink(os.path.join(MANAGED, fn))


def opt(name, after=None, cores=4):
    return {"name": name, "after": after, "cores": cores, "priority": 5}


WAITER = r"""
import importlib.machinery, os, sys, time
sr = importlib.machinery.SourceFileLoader("sr", sys.argv[1]).load_module()
opt = {"name": sys.argv[2], "after": sys.argv[3], "cores": 4, "priority": 5}
p = sr.register_waiting(opt, sys.argv[3])
print("waiting", flush=True)
sr.wait_for_job(sys.argv[3])
sr.drop_registration(p)
print("done", flush=True)
"""


def spawn_waiter(name, after):
    """A real wrapper process blocked in --after: job_named_alive ignores its OWN pid,
    so the waiting side of a chain must be another process, as in life."""
    p = subprocess.Popen([sys.executable, "-c", WAITER, os.path.join(SRC, "safe-run"),
                          name, after], stdout=subprocess.PIPE, text=True)
    children.append(p)
    line = p.stdout.readline().strip()
    assert line == "waiting", line
    return p


def finished(p, timeout=5.0):
    try:
        p.wait(timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


print("1. a waiting wrapper is visible by name")
clean()
a = child_pid()
reg(a, "a")
b = spawn_waiter("b", "a")
path = os.path.join(MANAGED, "%d.json" % b.pid)
test("placeholder written under the wrapper pid", os.path.exists(path), path)
d = json.load(open(path))
test("placeholder is queued, names its predecessor, carries a birth stamp",
     d.get("queued") is True and d.get("waiting_for") == "a"
     and abs(d.get("started", 0) - time.time()) < 30, d)
test("job_named_alive sees the waiting wrapper", sr.job_named_alive("b"))
test("the predecessor is still live", sr.job_named_alive("a"))
test("the wrapper is still blocked", not finished(b, 0.3))
children[0].kill()
children[0].wait()
os.unlink(os.path.join(MANAGED, "%d.json" % a))
test("predecessor gone: the wrapper finishes", finished(b))
test("dropped placeholder disappears", not sr.job_named_alive("b") and not os.path.exists(path))
me = sr.register_waiting(opt("x", after="a"), "a")
sr.drop_registration(me)
sr.drop_registration(me)
test("dropping twice is harmless", not os.path.exists(me))

print("\n2. the arbiter ignores a waiting wrapper: it asks for no cores yet")
clean()
a = child_pid()
reg(a, "a", cores=6)
b = spawn_waiter("b", "a")
running, queued = g._admission_entries()
test("running lists only the real job", [e["name"] for e in running] == ["a"], running)
test("queued does not list the waiting wrapper", queued == [], queued)
b.kill()
b.wait()

print("\n3. the omniai chain: C --after B must wait while B waits for A")
clean()
reg(a, "a")
b = spawn_waiter("b", "a")
c = spawn_waiter("c", "b")
test("C is still blocked while A runs", not finished(c, 0.3))
test("B is still blocked while A runs", not finished(b, 0.1))
proc_a = next(p for p in children if p.pid == a)
proc_a.kill()
proc_a.wait()
os.unlink(os.path.join(MANAGED, "%d.json" % a))
test("B finishes once A is gone", finished(b))
test("C finishes only after B", finished(c) and c.stdout.read().strip().endswith("done"))

# Control for the regression: a wrapper that waits WITHOUT registering (the code
# before this fix) is invisible, and C sails past it while A is still running.
clean()
a = child_pid()             # A from section 3 is dead by now; the control needs a live one
reg(a, "a")
legacy = subprocess.Popen([sys.executable, "-c", WAITER.replace(
    "p = sr.register_waiting(opt, sys.argv[3])", "p = None"),
    os.path.join(SRC, "safe-run"), "b", "a"], stdout=subprocess.PIPE, text=True)
children.append(legacy)
assert legacy.stdout.readline().strip() == "waiting"
c = spawn_waiter("c", "b")
test("(control) without the placeholder C slips through at once", finished(c, 1.0))
test("(control) while B is in fact still waiting", not finished(legacy, 0.1))
legacy.kill()
legacy.wait()

print("\n4. the guard's sweeper drops a stale waiting placeholder (dead wrapper)")
clean()
dead = child_pid()
children[-1].kill()
children[-1].wait()
with open(os.path.join(MANAGED, "%d.json" % dead), "w") as f:
    json.dump({"pid": dead, "name": "ghost", "queued": True, "waiting_for": "a",
               "started": time.time()}, f)
g.managed_pids_from_saferun()
test("dead wrapper's placeholder unlinked",
     not os.path.exists(os.path.join(MANAGED, "%d.json" % dead)))
test("a ghost never blocks a chain", not sr.job_named_alive("ghost"))

print("\n5. a placeholder written long after the wrapper's birth still passes identity")
clean()
me = os.getpid()
with open(os.path.join(MANAGED, "%d.json" % me), "w") as f:
    json.dump({"pid": me, "name": "late", "queued": True, "cores": 2,
               "started": sr.WRAPPER_STARTED - 3600}, f)   # simulate an hour of --after
g.managed_pids_from_saferun()
test("(control) a wrong birth stamp IS dropped as a recycled pid",
     not os.path.exists(os.path.join(MANAGED, "%d.json" % me)))
with open(os.path.join(MANAGED, "%d.json" % me), "w") as f:
    json.dump({"pid": me, "name": "late", "queued": True, "cores": 2,
               "started": sr.WRAPPER_STARTED}, f)
g.managed_pids_from_saferun()
test("the wrapper's real birth survives the sweep",
     os.path.exists(os.path.join(MANAGED, "%d.json" % me)))

for p in children:
    try:
        p.kill()
        p.wait()
    except Exception:
        pass
print("\n%d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
