#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the predictor-training event stream (history_events.jsonl).

Contract: one JSON line per event, written by the guard (pause/resume/terminate/
demote) and by safe-run (job_start/job_end); never a command line or a path in
the record; nothing written in dry-run; rotation via the guard's generation
scheme; and heat must NOT pick the file up as measurement history.

Run with:  python3 tests/test_events_jsonl.py
Uses live processes in a temporary TG_BASE; does not touch ~/.coffee-paladin.
"""
import importlib.machinery
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-events-")
os.environ["TG_BASE"] = BASE
os.environ.setdefault("TG_LANG", "en")

g = importlib.machinery.SourceFileLoader("ev_guard", os.path.join(SRC, "guard.py")).load_module()
g.notify = lambda *a, **k: None

# Shadow launchctl: TG_BASE does not isolate it, and safe-run kickstarts the
# daemon when it looks dead. The test must never touch the real service.
FAKE_BIN = os.path.join(BASE, "bin")
os.makedirs(FAKE_BIN)
with open(os.path.join(FAKE_BIN, "launchctl"), "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(os.path.join(FAKE_BIN, "launchctl"), 0o755)
SR_ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en",
              PATH=FAKE_BIN + os.pathsep + os.environ.get("PATH", ""))

passed = 0
total = 0
CHILDREN = []


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def events():
    p = g.ML_EVENTS_PATH
    if not os.path.exists(p):
        return []
    return [json.loads(line) for line in open(p) if line.strip()]


def launch():
    p = subprocess.Popen(["yes"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    CHILDREN.append(p)
    time.sleep(0.25)
    return p


CFG = g.load_cfg()
CFG["dry_run"] = False

print("=== event_jsonl(): record shape ===")
g.event_jsonl("pause_start", name="demo", pid=1234, pgid=None, cpu_pct=88)
e = events()[-1]
test("1. valid JSON with the contract keys",
     e["type"] == "pause_start" and e["source"] == "guard"
     and "time" in e and "epoch" in e and e["name"] == "demo")
test("2. None fields are dropped", "pgid" not in e, str(e))

print("=== guard call sites on a live process ===")
before = len(events())
p1 = launch()
st = {"paused": {}, "reczna_pauza": False}
g.do_pause(CFG, st, [(p1.pid, 95.0, "yes", os.getpgid(p1.pid))], "test heat")
time.sleep(0.25)
ev = events()
# Since 3.2.7 a thermal pause is followed by demote_start for the same pid (throttle at
# pause), so the pause event is found by type, not as the last line.
new_ev = ev[before:]
pause_ev = [e for e in new_ev if e["type"] == "pause_start"]
test("3. do_pause wrote pause_start", len(pause_ev) == 1 and pause_ev[0]["pid"] == p1.pid
     and [e["type"] for e in new_ev] == ["pause_start", "demote_start"], str(new_ev))
test("4. reason_code recorded", pause_ev[0].get("reason_code") == "termika", str(pause_ev))
g.do_resume(CFG, st, "test cooled", after_cooling=True)
time.sleep(0.25)
ev = events()
test("5. do_resume wrote pause_end with pause_s",
     ev[-1]["type"] == "pause_end" and isinstance(ev[-1].get("pause_s"), int), str(ev[-1]))

dry_cfg = dict(CFG)
dry_cfg["dry_run"] = True
before = len(events())
p2 = launch()
g.do_pause(dry_cfg, {"paused": {}, "reczna_pauza": False},
           [(p2.pid, 95.0, "yes", os.getpgid(p2.pid))], "test")
test("6. dry_run writes NO event", len(events()) == before)

print("=== safe-run: job_start / job_end ===")
r = subprocess.run([sys.executable, os.path.join(SRC, "safe-run"), "--allow-hot",
                    "--name", "ev-test", "--hours", "1", "--cores", "2", "--",
                    "sleep", "0.2"], env=SR_ENV, capture_output=True, text=True, timeout=60)
ev = events()
kinds = [x["type"] for x in ev if x.get("name") == "ev-test"]
test("7. job_start and job_end present", kinds == ["job_start", "job_end"], str(kinds))
end = [x for x in ev if x.get("name") == "ev-test" and x["type"] == "job_end"][0]
test("8. job_end carries exit_code 0 and duration", end.get("exit_code") == 0
     and isinstance(end.get("duration_s"), int), str(end))
start = [x for x in ev if x.get("name") == "ev-test" and x["type"] == "job_start"][0]
test("9. job_start declares cores and cpu limit",
     "cores" in start and "cpu_limit_pct" in start, str(start))

print("=== privacy: no command line, no paths ===")
raw = open(g.ML_EVENTS_PATH).read()
test("10. no cmd key and no path leaks in the stream",
     '"cmd"' not in raw and "/Users/" not in raw and "sleep 0.2" not in raw)

print("=== registration carries cpu_limit_pct (status groundwork) ===")
regs = os.listdir(os.path.join(BASE, "managed")) if os.path.isdir(os.path.join(BASE, "managed")) else []
# The job has exited and unregistered; re-run a longer one and peek mid-flight.
p3 = subprocess.Popen([sys.executable, os.path.join(SRC, "safe-run"), "--allow-hot",
                       "--name", "ev-reg", "--hours", "1", "--cpu-limit", "80", "--",
                       "sleep", "8"], env=SR_ENV, start_new_session=True,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CHILDREN.append(p3)
reg = None
for _ in range(40):
    time.sleep(0.25)
    files = [f for f in os.listdir(os.path.join(BASE, "managed"))
             if f.endswith(".json")] if os.path.isdir(os.path.join(BASE, "managed")) else []
    for fn in files:
        try:
            data = json.load(open(os.path.join(BASE, "managed", fn)))
        except Exception:
            continue
        if data.get("name") == "ev-reg":
            reg = data
            break
    if reg:
        break
test("11. managed entry has cpu_limit_pct", bool(reg) and reg.get("cpu_limit_pct") == 80,
     str(reg))

print("=== rotation: guard's generation scheme kicks in ===")
with open(g.ML_EVENTS_PATH, "a") as f:
    f.write("x" * (g.MAX_LOG_BYTES + 1024) + "\n")
g.event_jsonl("pause_start", name="rot", pid=1)
test("12. oversized stream rotated to .1", os.path.exists(g.ML_EVENTS_PATH + ".1"))
test("13. fresh stream starts with the new event",
     events()[-1].get("name") == "rot", str(events()[-3:]))

print("=== safe-run alone must also rotate, and must sanitise names ===")
sr = importlib.machinery.SourceFileLoader("ev_sr", os.path.join(SRC, "safe-run")).load_module()
test("15. a path passed as --name is reduced to its basename",
     sr.event_name("/Users/someone/clients/acme/render") == "render"
     and sr.event_name("") == "?" and sr.event_name("ok-name") == "ok-name"
     and "\n" not in sr.event_name("a\nb"), sr.event_name("/x/y"))
with open(g.ML_EVENTS_PATH, "a") as f:
    f.write("y" * (sr.ML_EVENTS_MAX_BYTES + 1024) + "\n")
old_gen1 = os.path.getsize(g.ML_EVENTS_PATH + ".1")
sr.event_jsonl("job_start", name="rot-sr", pid=2)
test("16. oversized stream is rotated by safe-run itself (generations shift)",
     os.path.exists(g.ML_EVENTS_PATH + ".2")
     and os.path.getsize(g.ML_EVENTS_PATH + ".1") != old_gen1
     and events()[-1].get("name") == "rot-sr", str(events()[-1:]))

print("=== heat ignores the file as history ===")
hout = subprocess.run([sys.executable, os.path.join(SRC, "heat"), "--profile"],
                      env=SR_ENV, capture_output=True, text=True, timeout=30)
test("14. heat --profile does not crash next to the jsonl", hout.returncode in (0, 1, 2),
     hout.stderr[-200:])

# Never killpg our own group: a supervisor started without start_new_session
# would take the test and its shell down with it, output and all.
me = os.getpgid(0)
for p in CHILDREN:
    try:
        pg = os.getpgid(p.pid)
        if pg != me:
            os.killpg(pg, signal.SIGKILL)
        else:
            p.kill()
    except Exception:
        try:
            p.kill()
        except Exception:
            pass

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
