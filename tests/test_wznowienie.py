#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify three resume defects found on a live Mac.

A bad day had 15 pauses, zero resumes, and four jobs killed by SIGTERM. Existing tests
missed it because each mechanism looked correct in isolation.

1. Resume gate took a hostage. Any sensor could trigger pause, but every sensor could
   block resume. Battery cools over minutes and can sit around ~37 C during long encodes,
   so with chip thresholds 95/87 a chip-triggered pause never ended: chip dropped to 71 C
   in 20 seconds, while battery, three degrees below its own 40 C pause threshold that it
   never crossed, kept the job in state T until termination. Fix: latch per sensor, set at
   its own pause threshold and clear at its own resume threshold.

2. Guard trusted its note, not the system. A `paused` entry only says SIGSTOP was sent
   at some point. A process manually resumed with `kill -CONT` or resumed by safe-run's
   duty limiter could run at full power while its entry kept aging, then receive SIGTERM
   mid-job after 45 minutes. Fix: terminate only what `ps` shows as stopped, and delete
   the other entries.

3. Limiter lock checked the wrong pid. `guard_paused(proc.pid)` asked about the group
   leader, while the guard freezes the process producing heat, often child ffmpeg. The
   answer was "no, guard did not pause this", so the limiter's micro-pause ended with
   `killpg(SIGCONT)` and woke the whole group, including what the guard had just frozen.
   Fix: ask about the whole process group, not a bare pid.

Run with:  python3 tests/test_wznowienie.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import importlib.machinery
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()
sr = importlib.machinery.SourceFileLoader("sr", os.path.join(SRC, "safe-run")).load_module()

passed = total = 0
cleanup_items = []


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


def group_with_child():
    """Start a leader plus child in one process group, matching safe-run jobs.

    Two Popen calls cannot assemble this: a process can only join a group from its own
    session, while `start_new_session` gives each one a separate session. The shell is
    the session and group leader, and its children inherit the group.
    """
    lider = subprocess.Popen(["bash", "-c", "sleep 600 & sleep 600"],
                             start_new_session=True)
    cleanup_items.append(lider)
    time.sleep(0.5)
    pgid = os.getpgid(lider.pid)
    children = []
    for line in subprocess.run(["ps", "-Ao", "pid=,pgid="],
                                capture_output=True, text=True).stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and int(parts[1]) == pgid and int(parts[0]) != lider.pid:
            children.append(int(parts[0]))
    return lider, pgid, children


def cleanup():
    """Leave no process after the test, including children of the shell leader.

    Killing only the leader leaves orphaned `sleep` processes because children have
    their own pids. Signal the whole group, preceded by SIGCONT: a stopped process will
    not handle SIGTERM, so without resume it could remain forever.
    """
    own_group = os.getpgid(0)
    for p in cleanup_items:
        try:
            pgid = os.getpgid(p.pid)
        except OSError:
            pgid = None
        # Never signal our own group. Processes started without `start_new_session`
        # sit in the test group, so killpg would also kill the test itself. That is
        # exactly the class of bug this file tests: group signals reach wider than
        # they seem.
        if pgid is not None and pgid != own_group:
            for sig in (signal.SIGCONT, signal.SIGKILL):
                try:
                    os.killpg(pgid, sig)
                except OSError:
                    pass
        try:
            p.send_signal(signal.SIGCONT)
        except Exception:
            pass
        try:
            p.kill()
            p.wait(timeout=5)
        except Exception:
            pass
    shutil.rmtree(BASE, ignore_errors=True)


# ---------------------------------------------------------------- 1. sensor latch
print("1. sensor blocks resume only when it caused the pause")
PAUSE_B, RESUME_B = 40.0, 36.0          # Battery thresholds.
PAUSE_C, RESUME_C = 95.0, 87.0          # Chip thresholds for compression queue.

st = {}
test("battery 36.7 C (below its own threshold 40) does NOT block - this is the defect",
     g.sensor_latch(st, "_batt_hot", 36.7, PAUSE_B, RESUME_B) is False,
     "latch: %s" % st.get("_batt_hot"))
test("battery 37.9 C (today's peak) also does not block",
     g.sensor_latch(st, "_batt_hot", 37.9, PAUSE_B, RESUME_B) is False)
test("battery 39.9 C - still below threshold, still does not block",
     g.sensor_latch(st, "_batt_hot", 39.9, PAUSE_B, RESUME_B) is False)

# But when battery really crosses its threshold, hysteresis must work as before.
st = {}
test("battery 41 C lights the latch",
     g.sensor_latch(st, "_batt_hot", 41.0, PAUSE_B, RESUME_B) is True)
test("battery 39 C: latch STILL holds (hysteresis, no threshold bouncing)",
     g.sensor_latch(st, "_batt_hot", 39.0, PAUSE_B, RESUME_B) is True)
test("battery 36.5 C: still holds, because resume threshold is 36",
     g.sensor_latch(st, "_batt_hot", 36.5, PAUSE_B, RESUME_B) is True)
test("battery 36 C: latch turns off",
     g.sensor_latch(st, "_batt_hot", 36.0, PAUSE_B, RESUME_B) is False)

st = {"_batt_hot": True, "_batt_hot_prog": [45.0, 36.0]}
test("live threshold change (calibration/slider) clears latch from before the change",
     g.sensor_latch(st, "_batt_hot", 37.0, PAUSE_B, RESUME_B) is False,
     "latch lit against OLD threshold pair means nothing against the new one")

st = {}
g.sensor_latch(st, "_batt_hot", 41.0, PAUSE_B, RESUME_B)
test("missing battery reading turns latch off (as before the change: None = no block)",
     g.sensor_latch(st, "_batt_hot", None, PAUSE_B, RESUME_B) is False)


# The whole gate goes through `resume_gate()`, exactly the function the daemon
# executes. A local copy of this condition would pass even if the loop's original broke.
CFG = {"batt_pause_c": PAUSE_B, "batt_resume_c": RESUME_B,
       "soc_pause_c": PAUSE_C, "soc_resume_c": RESUME_C}

st = {}
test("chip 94 C blocks resume even when pause was caused by system state",
     g.resume_gate(CFG, st, 30.0, 94.0, "nominal") is False,
     "chip latch would let this through - hence the strict threshold")
test("chip 88 C still blocks (chip hysteresis untouched)",
     g.resume_gate(CFG, st, 30.0, 88.0, "nominal") is False)
test("chip 71.2 C with cool battery - RESUME",
     g.resume_gate(CFG, st, 30.0, 71.2, "nominal") is True)
test("missing chip sensor does not block resume",
     g.resume_gate(CFG, st, 30.0, None, "nominal") is True)
test("system state 'serious' blocks regardless of temperatures",
     g.resume_gate(CFG, st, 30.0, 50.0, "serious") is False)

# Exact 19:42:38 -> 19:43 situation.
st = {}
test("at pause time (chip 95.2 / battery 36.7) do NOT resume",
     g.resume_gate(CFG, st, 36.7, 95.2, "nominal") is False)
test("20 seconds later (chip 71.2 / battery 36.6) RESUME - before fix it did NOT",
     g.resume_gate(CFG, st, 36.6, 71.2, "nominal") is True)
# When battery really overheats, the gate must hold as before.
test("battery 41 C with cold chip HOLDS resume (cell protection remains)",
     g.resume_gate(CFG, st, 41.0, 60.0, "nominal") is False)
test("battery 37 C after overheating STILL holds (latch, resume threshold is 36)",
     g.resume_gate(CFG, st, 37.0, 60.0, "nominal") is False)
test("battery 35.5 C turns latch off and resumes",
     g.resume_gate(CFG, st, 35.5, 60.0, "nominal") is True)

# ------------------------------------------------------- 2. terminate only stopped processes
print("\n2. SIGTERM after time limit goes only to a process that is really stopped")
p = subprocess.Popen(["sleep", "600"])
cleanup_items.append(p)
time.sleep(0.3)
entry = {"comm": "Python", "manual": False}


def is_stopped(pid, info=None):
    return g.entry_stopped(str(pid), info if info is not None else entry, *g.stopped_now())


test("running process: entry_stopped() = False", is_stopped(p.pid) is False)
os.kill(p.pid, signal.SIGSTOP)
time.sleep(0.3)
test("after SIGSTOP: entry_stopped() = True", is_stopped(p.pid) is True)
os.kill(p.pid, signal.SIGCONT)
time.sleep(0.3)
test("after SIGCONT (Pawel's manual resume at 20:02): entry_stopped() = False",
     is_stopped(p.pid) is False)
test("dead pid does not count as stopped", is_stopped(999999) is False)

# Group case: leader runs, but a child in its group is stopped. Do not delete the
# entry, because it is the only note anyone can use to resume that child.
lider2, pgid2, children2 = group_with_child()
test("test group has a child (otherwise this scenario checks nothing)",
     len(children2) >= 1, "children: %s" % children2)
if children2:
    child = children2[0]
    os.kill(child, signal.SIGSTOP)
    time.sleep(0.3)
    group_entry = {"comm": "ffmpeg", "manual": False, "pgid": pgid2}
    test("leader runs, child in group is stopped -> entry STAYS (otherwise child remains T)",
         is_stopped(lider2.pid, group_entry) is True)
    os.kill(child, signal.SIGCONT)
    time.sleep(0.3)
    test("whole group runs -> entry to delete",
         is_stopped(lider2.pid, group_entry) is False)

# Expired filter: same arithmetic as the loop.
old = {"since": g.now() - 60 * 60, "since_mono": time.monotonic() - 60 * 60,
         "mono_id": g._MONO_ID, "comm": "Python", "manual": False}
paused = {str(p.pid): old}
limit_seconds = 45 * 60


def to_kill():
    return g.expired_entries(paused, limit_seconds, g.stopped_now())


test("entry older than 45 min, but process RUNS - do not kill (this killed 20:27 measurement)",
     to_kill() == [], "to kill: %s" % to_kill())
test("...and same entry IS on deletion list as woken outside guard",
     g.stale_entries(paused, g.stopped_now()) == [str(p.pid)])
os.kill(p.pid, signal.SIGSTOP)
time.sleep(0.3)
test("same entry when process REALLY is stopped - kill (guard still works)",
     to_kill() == [str(p.pid)], "to kill: %s" % to_kill())
test("...and then do NOT delete it as stale",
     g.stale_entries(paused, g.stopped_now()) == [])
os.kill(p.pid, signal.SIGCONT)

# A failed `ps` measurement (None) must not trigger either execution path. Empty output
# used to mean "nothing is stopped", so the guard would delete a frozen job's entry and
# leave it in state T without a note.
os.kill(p.pid, signal.SIGSTOP)
time.sleep(0.3)
test("ps unavailable -> do not delete any entry", g.stale_entries(paused, None) == [])
test("ps unavailable -> do not kill anything", g.expired_entries(paused, limit_seconds, None) == [])
_old_run = g.run
g.run = lambda *a, **k: ""
try:
    test("stopped_now() with empty ps output returns None, not 'nothing is stopped'",
         g.stopped_now() is None)
finally:
    g.run = _old_run
os.kill(p.pid, signal.SIGCONT)

# ------------------------------------------------- 3. limiter lock knows the whole group
print("\n3. limiter does not wake a group where guard froze something")
lider, group, children = group_with_child()
test("test group has a child (this is what ffmpeg under safe-run looks like)", len(children) >= 1,
     "children: %s" % children)
CHILD = children[0] if children else lider.pid

state = os.path.join(BASE, "state.json")
json.dump({"paused": {str(CHILD): {"pgid": group, "comm": "ffmpeg"}}},
          open(state, "w"))
test("guard froze CHILD from our group -> limiter sees pause and does NOT wake",
     sr.guard_paused(lider.pid) is True,
     "before fix this was False and limiter did killpg(SIGCONT)")

json.dump({"paused": {str(CHILD): {"pgid": group + 4242, "comm": "ffmpeg"}}},
          open(state, "w"))
test("foreign group does not block our limiter", sr.guard_paused(lider.pid) is False)

json.dump({"paused": {str(lider.pid): {"pgid": group, "comm": "sleep"}}}, open(state, "w"))
test("guard froze leader directly - still works as before",
     sr.guard_paused(lider.pid) is True)

# Live foreign process with a recorded pgid equal to ours: the note lies, the system
# tells the truth. Without checking `os.getpgid(entry)`, the limiter would wait forever
# for an unrelated guard decision and leave its own job in state T.
foreign_process = subprocess.Popen(["sleep", "600"], start_new_session=True)
cleanup_items.append(foreign_process)
time.sleep(0.3)
json.dump({"paused": {str(foreign_process.pid): {"pgid": group, "comm": "ffmpeg"}}}, open(state, "w"))
test("live foreign process with foreign recorded pgid does not block limiter",
     sr.guard_paused(lider.pid) is False)

json.dump({"paused": {}}, open(state, "w"))
test("nothing frozen - limiter works normally",
     sr.guard_paused(lider.pid) is False)

# Dead entry plus recycled group number cannot hang the limiter forever.
json.dump({"paused": {"999999": {"pgid": group, "comm": "ffmpeg"}}}, open(state, "w"))
test("entry for nonexistent process does not block limiter (pgid recycling)",
     sr.guard_paused(lider.pid) is False)

# Stale snapshot means "nobody can decide"; keep that rule intact.
json.dump({"paused": {str(CHILD): {"pgid": group}}}, open(state, "w"))
os.utime(state, (time.time() - 600, time.time() - 600))
test("dead daemon (snapshot from 10 min ago) does not keep job frozen",
     sr.guard_paused(lider.pid) is False)

cleanup()
print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
