#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`heat --profile`: does the machine profile say true things, and do the rails hold?

The advice is only advice, but a person may follow it, so every claim here is
one a wrong number could turn into a hotter Mac:
  A. reading the history (rotated generations, junk rows, empty file),
  B. the measurements (percentiles, idle and load bands, fan spin-up),
  C. the rails on advice (kill never raised, distance to kill, gap to resume,
     thin data gives no advice, a throttled machine is never pushed higher).

Run with:  python3 tests/test_profil.py
Does not touch the real ~/.coffee-paladin.
"""
import importlib.machinery
import io
import os
import shutil
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
heat = importlib.machinery.SourceFileLoader("heat_mod", os.path.join(SRC, "heat")).load_module()

HEADER = ("time,thermal_state,chip_C,gpu_C,battery_C,fan_rpm,watts,battery_pct,"
          "on_ac,cpu_limit,load1,level,top_proc,top_cpu\n")
ok = fail = 0


def check(name, condition, detail=""):
    global ok, fail
    if condition:
        ok += 1
        print("  [PASS] %s" % name)
    else:
        fail += 1
        print("  [FAIL] %s %s" % (name, detail))


def row(day, hour, chip, rpm=0, watts=5.0, top_cpu=10, cpu_limit=100, minute=0):
    return ("2026-08-%02d %02d:%02d:00+0200,nominal,%.1f,70.0,33.0,%d,%.1f,80,1,%d,3.0,0,x,%d\n"
            % (day, hour, minute, chip, rpm, watts, cpu_limit, top_cpu))


def write(path, rows):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(HEADER)
        for r in rows:
            f.write(r)


def busy(chip, n, **kw):
    """n samples of real work at `chip` degrees, spread over 10 days."""
    return [row(1 + (i % 10), i % 24, chip, watts=30.0, top_cpu=600, **kw) for i in range(n)]


def quiet(chip, n):
    # Minute-spaced runs on days AFTER every busy() row: settled idle must
    # observe stability over consecutive minutes, and a quiet row stamped
    # earlier than the last work row counts as "just after work" and is skipped.
    return [row(11 + (i // 60) % 10, 12 + (i // 600) % 12, chip, watts=4.0, top_cpu=5,
                minute=i % 60) for i in range(n)]


CFG = {"soc_pause_c": 95.0, "soc_resume_c": 86.0, "soc_kill_c": 100.0}

print("=" * 78)
print("A. READING THE HISTORY")
print("=" * 78)

write(os.path.join(BASE, "history.csv"), quiet(40.0, 5))
write(os.path.join(BASE, "history.csv.1"), quiet(41.0, 7))
write(os.path.join(BASE, "history.csv.2"), quiet(42.0, 3))
rows = heat.read_history()
check("1. rotated generations are read, not only the current file",
      len(rows) == 15, "got %d" % len(rows))

with io.open(os.path.join(BASE, "history.csv"), "a", encoding="utf-8") as f:
    f.write("2026-08-01 10:00:00+0200,nominal,,,,,,,,,,,,\n")   # guard starting up
    f.write("2026-08-01 10:00:00+0200,nominal,not-a-number,")   # truncated by a hard shutdown
check("2. rows without a chip reading are skipped, the reader does not crash",
      len(heat.read_history()) == 15)

write(os.path.join(BASE, "history.csv"), [])
for extra in ("history.csv.1", "history.csv.2"):
    os.remove(os.path.join(BASE, extra))
check("3. an empty history is empty, not an exception", heat.read_history() == [])

print("=" * 78)
print("B. WHAT THE PROFILE MEASURES")
print("=" * 78)

check("4. percentile picks the value, not the average",
      heat.pct([1, 2, 3, 4, 100], 0.5) == 3 and heat.pct([1, 2, 3, 4, 100], 0.9) == 100)
check("4b. percentile survives its edges (one value, q=0, q=1)",
      heat.pct([7], 0.5) == 7 and heat.pct([1, 2, 3], 0) == 1 and heat.pct([1, 2, 3], 1) == 3)
check("4c. NaN and infinity never become measurements",
      heat.cell({"x": "nan"}, "x") is None and heat.cell({"x": "inf"}, "x") is None
      and heat.cell({"x": "42.5"}, "x") == 42.5)

# Fans keep running while the chip cools down, so the LOWEST temperature seen
# with the fans on is an idle reading. Only the transition means anything.
cooling = [row(1, 1, 50.0, rpm=0, minute=0), row(1, 1, 80.0, rpm=0, minute=5),
           row(1, 1, 82.0, rpm=3000, minute=10), row(1, 1, 60.0, rpm=2500, minute=15),
           row(1, 1, 35.0, rpm=2000, minute=20), row(1, 1, 34.0, rpm=0, minute=25)]
write(os.path.join(BASE, "history.csv"), cooling)
prof = heat.thermal_profile(heat.read_history())
check("5. fan spin-up is read from the transition (82 °C), not from the coldest spinning row",
      prof["fan_start_c"] == 82.0, "got %s" % prof["fan_start_c"])
check("6. a machine whose fans ever ran is not reported as fanless", prof["has_fans"] is True)

write(os.path.join(BASE, "history.csv"), quiet(45.0, 300))
prof = heat.thermal_profile(heat.read_history())
check("7. a Mac that never spun a fan is reported as fanless",
      prof["has_fans"] is False and prof["fan_start_c"] is None)
check("8. idle band comes from the quiet samples", prof["idle_median_c"] == 45.0)
check("9. no heavy work means no plateau, not a plateau of zero",
      prof["plateau_c"] is None and prof["load_samples"] == 0)

write(os.path.join(BASE, "history.csv"), busy(90.0, 200) + quiet(40.0, 100))
prof = heat.thermal_profile(heat.read_history())
check("10. load and idle are separated, not averaged together",
      prof["plateau_c"] == 90.0 and prof["idle_median_c"] == 40.0)
check("11. the span is measured in days, from the timestamps", prof["days"] >= 9.0,
      "got %s" % prof["days"])

print("=" * 78)
print("C. THE RAILS ON ADVICE")
print("=" * 78)

write(os.path.join(BASE, "history.csv"), busy(97.0, 30))
thin = heat.thermal_profile(heat.read_history())
check("12. thin data gives NO advice at all", heat.suggest_thresholds(thin, CFG) is None,
      "got %s" % (heat.suggest_thresholds(thin, CFG),))

write(os.path.join(BASE, "history.csv"), busy(96.0, 400))
hot = heat.thermal_profile(heat.read_history())
advice = heat.suggest_thresholds(hot, CFG)
check("13. a machine living at the threshold gets a suggestion",
      advice and advice["verdict"] == "pauses_during_work", "got %s" % (advice,))
check("14. the kill threshold is never raised", advice["kill"] == CFG["soc_kill_c"])
check("15. the suggested pause keeps its distance from kill",
      advice["pause"] <= CFG["soc_kill_c"] - heat.MIN_KILL_MARGIN,
      "pause %s vs kill %s" % (advice["pause"], CFG["soc_kill_c"]))
check("16. the pause-resume gap the user chose is preserved",
      round(advice["pause"] - advice["resume"], 1) == round(CFG["soc_pause_c"] - CFG["soc_resume_c"], 1),
      "gap %s" % round(advice["pause"] - advice["resume"], 1))

write(os.path.join(BASE, "history.csv"), busy(96.0, 400, cpu_limit=70))
throttled = heat.suggest_thresholds(heat.thermal_profile(heat.read_history()), CFG)
check("17. a machine macOS is ALREADY throttling is never pushed higher",
      throttled["verdict"] == "throttling" and throttled["pause"] == CFG["soc_pause_c"],
      "got %s" % (throttled,))

write(os.path.join(BASE, "history.csv"), busy(99.0, 400))
at_ceiling = heat.suggest_thresholds(heat.thermal_profile(heat.read_history()), CFG)
check("18. with no room under kill the answer is 'leave it', not a pause above kill",
      at_ceiling["verdict"] == "at_ceiling" and at_ceiling["pause"] == CFG["soc_pause_c"],
      "got %s" % (at_ceiling,))

write(os.path.join(BASE, "history.csv"), busy(80.0, 400))
fanless = heat.suggest_thresholds(heat.thermal_profile(heat.read_history()), CFG)
check("19. a fanless Mac idling far below the threshold is told it reacts late",
      fanless["verdict"] == "reacts_late" and fanless["pause"] < CFG["soc_pause_c"],
      "got %s" % (fanless,))

write(os.path.join(BASE, "history.csv"),
      [r.replace(",0,30.0,", ",3000,30.0,") for r in busy(80.0, 400)])
with_fans = heat.suggest_thresholds(heat.thermal_profile(heat.read_history()), CFG)
check("20. the same numbers on a Mac WITH fans are left alone",
      with_fans["verdict"] == "fits" and with_fans["pause"] == CFG["soc_pause_c"],
      "got %s" % (with_fans,))

check("21. no advice without thresholds to compare against",
      heat.suggest_thresholds(hot, {}) is None)

# Everything below is a way the advice could be wrong while every earlier check
# still passed. Each one is a number a person might paste into the fuse.
write(os.path.join(BASE, "history.csv"), busy(96.0, 5) + quiet(40.0, 300))
few = heat.thermal_profile(heat.read_history())
check("23. a plateau read off a handful of busy samples gives no advice",
      few["load_samples"] < heat.MIN_LOAD_SAMPLES
      and heat.suggest_thresholds(few, CFG) is None,
      "load samples %d, advice %s" % (few["load_samples"], heat.suggest_thresholds(few, CFG)))

write(os.path.join(BASE, "history.csv"), busy(96.0, 400) + [row(5, 12, 101.0, watts=30.0, top_cpu=600)])
touched = heat.suggest_thresholds(heat.thermal_profile(heat.read_history()), CFG)
check("24. a Mac that once reached the kill threshold is never given more margin",
      touched["verdict"] == "touched_kill" and touched["pause"] == CFG["soc_pause_c"],
      "got %s" % (touched,))

write(os.path.join(BASE, "history.csv"), busy(96.0, 400))
for bad in ({"soc_pause_c": 99, "soc_resume_c": 100, "soc_kill_c": 100},   # inverted
            {"soc_pause_c": 95, "soc_resume_c": 86, "soc_kill_c": 130},    # not a chip threshold
            {"soc_pause_c": 20, "soc_resume_c": 10, "soc_kill_c": 30},     # not a chip either
            {"soc_pause_c": "hot", "soc_resume_c": 86, "soc_kill_c": 100}):
    got = heat.suggest_thresholds(heat.thermal_profile(heat.read_history()), bad)
    check("25. nonsense in config.json produces no advice: %s" % bad, got is None,
          "got %s" % (got,))

# The guard writes CSV by joining on commas, so a process called "my,solver"
# shifts every later column. Such a row must not become a measurement.
write(os.path.join(BASE, "history.csv"), quiet(40.0, 250))
with io.open(os.path.join(BASE, "history.csv"), "a", encoding="utf-8") as f:
    f.write("2026-08-05 12:00:00+0200,nominal,95.0,70.0,33.0,3000,30.0,80,1,100,3.0,0,my,solver,600\n")
shifted = heat.thermal_profile(heat.read_history())
check("26. a shifted row (comma in the process name) is dropped, not measured",
      shifted["samples"] == 250 and shifted["peak_c"] == 40.0,
      "samples %d peak %s" % (shifted["samples"], shifted["peak_c"]))

# A byte order mark makes the first column name "﻿time" and every timestamp
# disappears, which silently turns a full history into "not enough data".
write(os.path.join(BASE, "history.csv"), quiet(40.0, 250))
raw = io.open(os.path.join(BASE, "history.csv"), encoding="utf-8").read()
io.open(os.path.join(BASE, "history.csv"), "w", encoding="utf-8").write("﻿" + raw)
bom = heat.thermal_profile(heat.read_history())
check("27. a byte order mark does not hide the timestamps", bom["days"] >= 2,
      "days %s" % bom["days"])

# One row with a broken clock (a restore, a jump, a machine from another
# timezone) must not buy two days of coverage.
write(os.path.join(BASE, "history.csv"),
      [row(5, 12, 40.0) for _ in range(250)]
      + ["2019-01-01 00:00:00+0200,nominal,40.0,70.0,33.0,0,4.0,80,1,100,3.0,0,x,5\n"])
jumped = heat.thermal_profile(heat.read_history())
check("28. one wrong clock buys no coverage at all: a day needs measurements",
      jumped["days"] == 1, "days %s" % jumped["days"])

# Fans that were stopped hours ago say nothing about what started them now.
write(os.path.join(BASE, "history.csv"),
      [row(1, 10, 45.0, rpm=0), row(1, 15, 55.0, rpm=2500)])
gap_only = heat.thermal_profile(heat.read_history())
check("29. a spin-up across a five-hour gap is not a measurement",
      gap_only["fan_start_c"] is None, "got %s" % gap_only["fan_start_c"])

# The history stores the guard's top TARGET, not the true top consumer: an
# orchestrator scattering short children reports ~0% CPU while the chip cooks.
write(os.path.join(BASE, "history.csv"),
      [row(1 + (i % 10), i % 24, 92.0, rpm=3000, watts=35.0, top_cpu=0) for i in range(300)])
by_watts = heat.thermal_profile(heat.read_history())
check("30. work is recognised by package draw even when no process looks busy",
      by_watts["load_samples"] == 300 and by_watts["plateau_c"] == 92.0,
      "load %d plateau %s" % (by_watts["load_samples"], by_watts["plateau_c"]))

# The worst possible advice: a resume threshold at or below the temperature this
# Mac shows while doing nothing. The job pauses and never comes back.
write(os.path.join(BASE, "history.csv"), busy(80.0, 300) + quiet(78.0, 200))
warm_idle = heat.suggest_thresholds(heat.thermal_profile(heat.read_history()), CFG)
check("22. resume is never suggested inside the idle band (a pause that never ends)",
      warm_idle["verdict"] == "fits"
      or warm_idle["resume"] > heat.thermal_profile(heat.read_history())["idle_p90_c"],
      "got %s" % (warm_idle,))

# Round two of the adversarial review: each of these forced a wrong answer out
# of the previous version.
write(os.path.join(BASE, "history.csv"),
      [row(10, 10, 50.0, rpm=0, minute=0), row(1, 10, 82.0, rpm=3000, minute=0)])
backwards = heat.thermal_profile(heat.read_history())
check("31. a spin-up measured across time running BACKWARDS is not a measurement",
      backwards["fan_start_c"] is None, "got %s" % backwards["fan_start_c"])

write(os.path.join(BASE, "history.csv"),
      [r.replace(",100,3.0,", ",nan,3.0,") for r in busy(96.0, 400)])
unknown = heat.thermal_profile(heat.read_history())
blind = heat.suggest_thresholds(unknown, CFG)
check("32. an unreadable cpu_limit is not read as 'never throttled'",
      unknown["throttle_unknown"] > 0 and blind["pause"] == CFG["soc_pause_c"],
      "unknown %s advice %s" % (unknown["throttle_unknown"], blind))

write(os.path.join(BASE, "history.csv"), busy(96.0, 400))
out_of_range = heat.suggest_thresholds(heat.thermal_profile(heat.read_history()),
                                       {"soc_pause_c": 95, "soc_resume_c": 86, "soc_kill_c": 115})
check("33. thresholds the daemon itself would reject produce no advice",
      out_of_range is None, "got %s" % (out_of_range,))

for shape in ("[]", '"x"', "17"):
    io.open(os.path.join(BASE, "config.json"), "w", encoding="utf-8").write(shape)
    check("34. config.json that is valid JSON but not an object does not crash: %s" % shape,
          heat.profile_command() == 0)
os.remove(os.path.join(BASE, "config.json"))

# A rarely used Mac writes two or three rows on a quiet day. Those days must
# still count, or the profile refuses to speak about a machine used for months.
write(os.path.join(BASE, "history.csv"),
      [row(1 + (i % 10), (i % 3) * 8, 40.0, minute=(i % 3) * 7) for i in range(30)])
sparse = heat.thermal_profile(heat.read_history())
check("36. days with only a few samples still count as days", sparse["days"] == 10,
      "days %s" % sparse["days"])

# An older history has no cpu_limit column at all - not the same as a reading of 100.
OLD_HEADER = "time,thermal_state,chip_C,gpu_C,battery_C,fan_rpm,watts,battery_pct,on_ac,load1,level\n"
with io.open(os.path.join(BASE, "history.csv"), "w", encoding="utf-8") as f:
    f.write(OLD_HEADER)
    for i in range(400):
        f.write("2026-08-%02d %02d:00:00+0200,nominal,96.0,70.0,33.0,3000,30.0,80,1,3.0,0\n"
                % (1 + (i % 10), i % 24))
old = heat.thermal_profile(heat.read_history())
old_advice = heat.suggest_thresholds(old, CFG)
check("37. a history without the cpu_limit column is 'unknown', never 'never throttled'",
      old["throttle_unknown"] == 400 and old_advice["pause"] == CFG["soc_pause_c"]
      and old_advice["verdict"] == "throttle_unknown",
      "unknown %s advice %s" % (old["throttle_unknown"], old_advice))

# The bound has to BITE, not merely exist as a positive constant.
real_max = heat.MAX_ROWS
heat.MAX_ROWS = 20
write(os.path.join(BASE, "history.csv"), quiet(40.0, 100))
check("38. the row limit actually stops the reader", len(heat.read_history()) == 20,
      "got %d" % len(heat.read_history()))
heat.MAX_ROWS = real_max
check("39. and the limit is not what a normal history hits",
      len(heat.read_history()) == 100 and heat.MAX_GENERATIONS > 0)

print("=" * 78)
print("  RESULT: %d/%d" % (ok, ok + fail))
shutil.rmtree(BASE, ignore_errors=True)
sys.exit(1 if fail else 0)
