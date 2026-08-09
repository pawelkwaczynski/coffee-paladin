#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Treat display wake as separate from system wake, with the same thermal guardrail.

`caffeinate -is` keeps the system awake but lets the display sleep. Presentations,
dashboards, and render previews need `-d`. A lit panel uses more power and heat, so
it is off by default and must be released with the rest of keep-awake on a hot Mac.

The test does not start real `caffeinate`; it replaces `subprocess.Popen` and verifies
the daemon's argv. It also covers countercases: switching modes in flight must replace
the process because caffeinate flags cannot be changed, and thermal level 2 must stop
keep-awake regardless of the display setting.

Run with:  python3 tests/test_awake_ekran.py
"""
import importlib.machinery
import io
import os
import shutil
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-awake-ekran-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

passed = total = 0
CALLS = []


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


class FakeProcess:
    """Pretend to be a live caffeinate process; `poll()` returns None while running."""

    def __init__(self, argv):
        self.argv = argv
        self.alive = True
        self.killed = False
        self.reaped = False

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.alive = False
        self.killed = True

    def wait(self, timeout=None):
        self.alive = False
        self.reaped = True          # Without wait(), a zombie remains; this is asserted.
        return 0

    def kill(self):
        self.alive = False
        self.killed = True


def fake_popen(argv, **kw):
    CALLS.append(list(argv))
    return FakeProcess(list(argv))


g.subprocess.Popen = fake_popen
g.play_sound = lambda *a, **k: None          # Keep tests silent.


def reset():
    CALLS.clear()
    g._caff["proc"] = None
    g._caff.pop("display", None)


HEAVY_JOBS = [(123, 500.0, "ffmpeg", None)]     # Anything that looks like heavy work.


def cfg(**k):
    c = dict(g.DEFAULTS)
    c["keep_awake_auto"] = True
    c.update(k)
    return c


print("1. by default the display sleeps (caffeinate -is)")
reset()
g.keep_awake_update(cfg(), HEAVY_JOBS, 0, {})
test("caffeinate called exactly once", len(CALLS) == 1, CALLS)
test("without the -d flag", CALLS and CALLS[0] == ["caffeinate", "-is"], CALLS)

print("\n2. keep_awake_display=true -> display is also kept awake (-isd)")
reset()
g.keep_awake_update(cfg(keep_awake_display=True), HEAVY_JOBS, 0, {})
test("-d flag present", CALLS and CALLS[0] == ["caffeinate", "-isd"], CALLS)

print("\n3. live switching replaces the process")
reset()
g.keep_awake_update(cfg(), HEAVY_JOBS, 0, {})                       # Start without display wake.
pierwszy = g._caff["proc"]
g.keep_awake_update(cfg(keep_awake_display=True), HEAVY_JOBS, 0, {})  # User enables display wake.
test("old process was killed", pierwszy.killed, "old caffeinate survived the change")
test("...and REAPED by wait (otherwise it stays a zombie)", pierwszy.reaped,
     "terminate without wait - review gap from 04.08")
test("new process called with -isd", len(CALLS) == 2 and CALLS[1] == ["caffeinate", "-isd"],
     CALLS)
test("and that new process is alive",
     g.keep_awake_update(cfg(keep_awake_display=True), HEAVY_JOBS, 0, {}) is True)

print("\n4. WITHOUT a setting change the process is NOT replaced")
reset()
g.keep_awake_update(cfg(keep_awake_display=True), HEAVY_JOBS, 0, {})
g.keep_awake_update(cfg(keep_awake_display=True), HEAVY_JOBS, 0, {})
g.keep_awake_update(cfg(keep_awake_display=True), HEAVY_JOBS, 0, {})
test("one call despite three loop passes", len(CALLS) == 1,
     "%d calls - daemon replaces caffeinate every cycle" % len(CALLS))

print("\n5. OPPOSITE CASE: hot machine = display sleeps together with idle sleep")
reset()
g.keep_awake_update(cfg(keep_awake_display=True), HEAVY_JOBS, 0, {})
proc = g._caff["proc"]
result = g.keep_awake_update(cfg(keep_awake_display=True), HEAVY_JOBS, 2, {})   # Level 2 = pause.
test("wake lock released at level 2", result is False, result)
test("caffeinate really killed", proc.killed, "process survived overheating")
test("...and reaped on thermal stop", proc.reaped, "zombie left after overheating")
test("and not started again", len(CALLS) == 1, CALLS)

print("\n6. OPPOSITE CASE: no heavy jobs = no wake lock")
reset()
result = g.keep_awake_update(cfg(keep_awake_display=True), [], 0, {})
test("nothing started", len(CALLS) == 0 and result is False, CALLS)

print("\n7. COUNTERS: distinguish 'job ended' from 'too hot'")
reset()
st = {}
g.keep_awake_update(cfg(), HEAVY_JOBS, 0, st)          # Start.
g.keep_awake_update(cfg(), HEAVY_JOBS, 2, st)          # Thermal stop.
test("thermal wake-release counter = 1",
     st.get("stats", {}).get("awake_released_hot") == 1, st.get("stats"))

reset()
st2 = {}
g.keep_awake_update(cfg(), HEAVY_JOBS, 0, st2)         # Start.
g.keep_awake_update(cfg(), [], 0, st2)              # Stop because the job ended.
test("job completion does NOT count as a guard intervention",
     "awake_released_hot" not in st2.get("stats", {}), st2.get("stats"))

print("\n8. counter() by itself")
st3 = {}
g.licznik(st3, "pauses")
g.licznik(st3, "pauses")
g.licznik(st3, "kills")
test("counts cumulatively", st3["stats"]["pauses"] == 2 and st3["stats"]["kills"] == 1, st3)
test("records when counting started", isinstance(st3["stats"].get("since"), (int, float)),
     st3["stats"].get("since"))
test("does not crash on broken state", (g.licznik(None, "pauses") or True))

print("\n9. MOST IMPORTANT: MANUAL sessions also yield to the guard")
# Earlier sections checked hot handling only for automatic mode. The mutation
# `(auto and lvl < 2) or manual` let manual sessions bypass the thermal guard.
# That is the highest-risk failure mode for this feature.
import json
reset()
with io.open(os.path.join(BASE, "awake.json"), "w", encoding="utf-8") as f:
    json.dump({"mode": "forever"}, f)          # A human enabled keep-awake indefinitely.
c = dict(g.DEFAULTS)                            # Note: keep_awake_auto is off.
c["keep_awake_auto"] = False
result = g.keep_awake_update(c, [], 0, {})       # Cool Mac: keep-awake must work.
test("manual session keeps wake lock while cool", result is True and len(CALLS) == 1, CALLS)
proc = g._caff["proc"]
result = g.keep_awake_update(c, [], 2, {})       # Hot Mac: it must yield.
test("manual session YIELDS at level 2", result is False, result)
test("manual-session caffeinate really killed", proc.killed, "survived overheating")
try:
    os.remove(os.path.join(BASE, "awake.json"))
except OSError:
    pass

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
