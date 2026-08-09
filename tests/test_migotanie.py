#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify fixes for pause flapping, false fan alarms, and duplicate CPU candidates.

1. Pause flapping. Chip thresholds have hysteresis (pause 95 / resume 87), but the
   system thermal-state trigger is binary and has no hysteresis. Six pause/resume pairs
   in 15 s cycles at chip 84-85 C made the job jump without cooling anything. The fix
   is a minimum pause duration.
2. False cooling alarm. A reading of "chip 75.9 C, both fans 0 rpm" can be fan spin-up,
   not failure, if fans report 2300-2900 rpm moments later. The condition must hold for
   several readings.
3. Duplicate CPU counting. The same processor used to appear twice in candidates: as
   a parent with subtree CPU and as a child with own CPU, for example "bash 276%" next
   to "ffmpeg 276%" while `ps` showed bash at 0.0%. The displayed list keeps the highest
   ancestor.

Run with:  python3 tests/test_migotanie.py
"""
import importlib.machinery
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


print("1. minimum pause time ends oscillation")
cfg = g.load_cfg()
test("min_pause_seconds is in the config", cfg.get("min_pause_seconds", 0) >= 30,
     "value: %s" % cfg.get("min_pause_seconds"))

mono = time.monotonic()
for description, entry, may_resume in [
    ("pause from 5 s ago - do NOT resume (this caused flicker)",
     {"since": g.now() - 5, "since_mono": mono - 5, "mono_id": g._MONO_ID}, False),
    ("pause from 59 s ago - do NOT resume",
     {"since": g.now() - 59, "since_mono": mono - 59, "mono_id": g._MONO_ID}, False),
    ("pause from 120 s ago - resume",
     {"since": g.now() - 120, "since_mono": mono - 120, "mono_id": g._MONO_ID}, True),
    ("pause from previous daemon, 10 min by wall clock - resume",
     {"since": g.now() - 600, "since_mono": mono + 5000, "mono_id": "999:1"}, True),
]:
    age = g._pause_age(entry)
    test(description, (age >= cfg.get("min_pause_seconds", 60)) is may_resume,
         "age=%.0f s, threshold=%s" % (age, cfg.get("min_pause_seconds")))

print("\n2. cooling alarm requires a sustained condition")
test("fan_alert_polls is in the config and greater than 1",
     cfg.get("fan_alert_polls", 1) > 1, "value: %s" % cfg.get("fan_alert_polls"))

st = {}
cold_soc = {"cpu": 50.0, "fans": [0, 0]}
hot_soc = {"cpu": 80.0, "fans": [0, 0]}
alerts = []
_write = g.record_event
g.record_event = lambda *a, **k: alerts.append(a[0] if a else "?")
try:
    # One "hot + zero rpm" reading means spin-up, not failure.
    g.fan_alarm(cfg, hot_soc, 80.0, st)
    test("first reading does NOT alarm (fan spin-up)", not alerts,
         "alarms: %d" % len(alerts))
    g.fan_alarm(cfg, hot_soc, 80.0, st)
    test("second reading does not either", not alerts, "alarms: %d" % len(alerts))
    g.fan_alarm(cfg, hot_soc, 80.0, st)
    test("third consecutive reading ALARMS (now it is a failure)", len(alerts) == 1,
         "alarms: %d" % len(alerts))
    # Spin-up: fans moved, so the counter must reset.
    st2 = {}
    g.fan_alarm(cfg, hot_soc, 80.0, st2)
    g.fan_alarm(cfg, {"cpu": 80.0, "fans": [2300, 2900]}, 80.0, st2)
    test("fan movement resets the counter", st2.get("_fan_zero_polls") == 0,
         "counter: %s" % st2.get("_fan_zero_polls"))
finally:
    g.record_event = _write

print("\n3. the same processor cannot be a candidate twice")
# bash (parent) uses no CPU itself; all CPU belongs to child ffmpeg.
procs = [(100, 1, 0.0, "bash"), (200, 100, 280.0, "ffmpeg"), (300, 1, 90.0, "python3")]
cfg2 = dict(cfg)
cfg2["count_children"] = True
cfg2["managed_patterns"] = ["bash", "ffmpeg", "python3"]
cfg2["never_patterns"] = []
cfg2["never_extra"] = []
targets = g.pick_targets(cfg2, procs, {})
pidy = [t[0] for t in targets]
# Most important: the target list must include children. If this list is pruned,
# `pgid` is known only for safe-run jobs, so SIGSTOP goes to one process while
# children keep running behind a "paused" log entry.
test("child STAYS on target list (otherwise it will not get SIGSTOP)", 200 in pidy,
     "targets: %s" % pidy)
test("parent is also a target", 100 in pidy, "targets: %s" % pidy)
test("parent CPU carries subtree sum",
     any(t[0] == 100 and t[1] >= 280 for t in targets), "targets: %s" % targets)

# Only the display list is pruned, so the counter does not lie twice.
shown = [t[0] for t in g.without_descendants(targets, procs)]
test("child is no longer on the display list", 200 not in shown, "display: %s" % shown)
test("topmost ancestor remains", 100 in shown, "display: %s" % shown)
test("independent process remains", 300 in shown, "display: %s" % shown)

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
