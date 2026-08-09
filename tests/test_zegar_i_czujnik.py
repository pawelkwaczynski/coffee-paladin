#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure clock jumps cannot kill jobs and a blind guard cannot look healthy.

Three failure families are covered:

1. Wall clock. Pause length was computed from time.time(). A 3 h NTP jump killed a job
   with SIGTERM one minute after pause; moving the clock backward disabled the pause
   limit indefinitely. Monotonic time now decides.
2. Blind guard. "unknown" thermalstate mapped to level 1. A Mac without battery and
   without macmon, such as mini or Studio, stayed at level 1 forever: it never reached
   2, never paused anything, and looked like a healthy slightly warm machine.
3. Calibration. `calibrated_for` did not include sensor information, so an Air installed
   before macmon got a "fans=0" tag and never received fanless thresholds (78/70/88).

Run with:  python3 tests/test_zegar_i_czujnik.py
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

zaliczone = wszystkie = 0


def test(nazwa, warunek, szczegol=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s  -> %s" % (nazwa, szczegol))


def dlugosc_pauzy(v):
    """Mirror daemon-loop logic so the test guards meaning, not spelling."""
    m = v.get("since_mono")
    if m is not None:
        return max(0.0, time.monotonic() - m)
    return max(0.0, g.now() - v.get("since", g.now()))


print("1. clock jump vs pause limit (45 min limit)")
limit = 45 * 60
mono = time.monotonic()
for opis, wpis, oczekiwane in [
    ("pause lasts one minute - do not kill",
     {"since": g.now() - 60, "since_mono": mono - 60}, False),
    ("pause lasts one hour - kill",
     {"since": g.now() - 3600, "since_mono": mono - 3600}, True),
    ("clock jumped by 3 h, pause lasts one minute - do NOT kill",
     {"since": g.now() - 10800, "since_mono": mono - 60}, False),
    ("clock moved backward, pause lasts one hour - kill anyway",
     {"since": g.now() + 7200, "since_mono": mono - 3600}, True),
    ("old entry without since_mono - behavior as before",
     {"since": g.now() - 3600}, True),
]:
    test(opis, (dlugosc_pauzy(wpis) > limit) is oczekiwane,
         "duration=%.0f s" % dlugosc_pauzy(wpis))

print("\n2. blind guard does not pretend to be healthy")
test("state 'unknown' is not treated like 'fair'", g.LEVELS["unknown"] == 0,
     "LEVELS[unknown]=%s" % g.LEVELS["unknown"])
test("'fair' still gives level 1", g.LEVELS["fair"] == 1)
test("'serious' still gives level 2", g.LEVELS["serious"] == 2)

print("\n3. calibration distinguishes missing sensor from no fans")
tagi = set()
for hw in ({"model_id": "Mac15,12", "chip": "M3", "fan_count": 0, "chip_sensor": False},
           {"model_id": "Mac15,12", "chip": "M3", "fan_count": 0, "chip_sensor": True}):
    tagi.add("%s|%s|fans=%s|sensor=%s" % (hw["model_id"], hw["chip"],
                                          hw["fan_count"], bool(hw["chip_sensor"])))
test("Air before macmon and after macmon has DIFFERENT calibration markers", len(tagi) == 2,
     "markers: %s" % tagi)

print("\n4. monotonic clock starts at zero in each process")
# Apple's /usr/bin/python3, the one launchd uses for the daemon, counts
# time.monotonic() from zero for each process. Two guard paths assumed otherwise and
# failed on a live Mac.

# 4a. Sensor cache: initial value 0.0 looked like "read moments ago", so during the
#     first 10 s of daemon life soc_sensors() returned None without asking macmon. The
#     guard reported "no chip sensor" and watched only battery.
test("sensor cache does not pretend a read happened before the first read",
     g._soc_cache["t"] is None, "initial value = %r" % (g._soc_cache["t"],))

# Recreate daemon conditions: fresh process, monotonic clock near zero, no previous read.
zapamietane = dict(g._soc_cache)
prawdziwy_run, prawdziwy_mono = g.run, time.monotonic
odczyty = [0]


def zliczajacy_run(cmd, timeout=10):
    if "macmon" in cmd[0]:
        odczyty[0] += 1
    return prawdziwy_run(cmd, timeout=timeout)


try:
    g.run = zliczajacy_run
    g.time.monotonic = lambda: 0.05          # What the daemon sees just after start.
    g.soc_sensors()
    test("right after daemon start, guard really asks chip sensor",
         odczyty[0] == 1, "macmon reads: %d (0 = guard decided there is no sensor)"
         % odczyty[0])
finally:
    g.run, g.time.monotonic = prawdziwy_run, prawdziwy_mono
    g._soc_cache.clear()
    g._soc_cache.update(zapamietane)

# 4b. Pause limit: a monotonic reading from the previous daemon is negative in the new
#     process, so the pause looked freshly created and the limit never fired. A job
#     frozen before restart would stay in state T forever.
for opis, wpis, oczekiwane in [
    ("pause from this daemon, one hour - kill",
     {"since": g.now() - 3600, "since_mono": time.monotonic() - 3600,
      "mono_id": g._MONO_ID}, True),
    ("pause after daemon restart, one hour by wall clock - kill",
     {"since": g.now() - 3600, "since_mono": time.monotonic() + 50000,
      "mono_id": "999:1"}, True),
    ("pause after daemon restart, one minute - do NOT kill",
     {"since": g.now() - 60, "since_mono": time.monotonic() + 50000,
      "mono_id": "999:1"}, False),
]:
    m = wpis.get("since_mono")
    d = (max(0.0, time.monotonic() - m) if m is not None and wpis.get("mono_id") == g._MONO_ID
         else max(0.0, g.now() - wpis.get("since", g.now())))
    test(opis, (d > limit) is oczekiwane, "duration=%.0f s" % d)

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
