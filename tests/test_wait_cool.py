#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify safe-run --wait-cool waits for cooling instead of silently refusing start.

safe-run refused to start twice on a hot chip (91.8 C and 90.8 C), and nobody
noticed; the job simply did not happen because the refusal was buried in a long log.
The --wait-cool flag turns refusal into waiting for the guard's resume threshold.

Run with:  python3 tests/test_wait_cool.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import contextlib
import importlib.machinery
import io
import json
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
os.environ["SAFE_RUN_WAIT_POLL"] = "0.01"
sr = importlib.machinery.SourceFileLoader("sr", os.path.join(SRC, "safe-run")).load_module()
json.dump({"soc_pause_c": 95.0, "soc_resume_c": 87.0}, open(os.path.join(BASE, "config.json"), "w"))

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


def snapshot(chip, resume=87.0, age=0, level=0):
    p = os.path.join(BASE, "status.json")
    thresholds = {"pause": 95, "kill": 100}
    if resume is not None:
        thresholds["resume"] = resume
    json.dump({"level": level, "chip_c": chip, "thresholds": thresholds}, open(p, "w"))
    if age:
        os.utime(p, (time.time() - age, time.time() - age))
    return p


print("safe-run --wait-cool")

# --- parser ---
argv0 = sys.argv
sys.argv = ["safe-run", "--", "true"]
opt, _ = sr.parse()
test("without flag wait_cool is disabled", opt["wait_cool"] is False, str(opt))
sys.argv = ["safe-run", "--wait-cool", "--hours", "2", "--", "true"]
opt, cmd = sr.parse()
test("--wait-cool sets flag and does not eat the command",
     opt["wait_cool"] is True and cmd == ["true"] and opt["hours"] == 2.0,
     "%s %s" % (opt, cmd))
sys.argv = argv0

# --- read_chip_state ---
snapshot(91.0)
chip, threshold, lvl = sr.read_chip_state()
test("fresh snapshot: chip and resume threshold from snapshot",
     chip == 91.0 and threshold == 87.0, "chip=%s threshold=%s" % (chip, threshold))

snapshot(91.0, resume=None)
chip, threshold, lvl = sr.read_chip_state()
test("snapshot without resume field: threshold from config.json (old guard)",
     chip == 91.0 and threshold == 87.0, "chip=%s threshold=%s" % (chip, threshold))

snapshot(99.0, age=300)
chip, threshold, lvl = sr.read_chip_state()
test("5-minute-old snapshot: chip unknown (do not hang on a dead guard)",
     chip is None, "chip=%s" % chip)

snapshot("zepsute")
chip, threshold, lvl = sr.read_chip_state()
test("junk chip_c in snapshot does not crash read", chip is None, "chip=%s" % chip)

os.remove(os.path.join(BASE, "status.json"))
chip, threshold, lvl = sr.read_chip_state()
test("missing snapshot: chip unknown, threshold from config",
     chip is None and threshold == 87.0, "chip=%s threshold=%s" % (chip, threshold))

# --- wait loop; replace measurement sources and count sleeps ---
real_values = (sr.thermal_state, sr.batt_temp, sr.read_chip_state, sr.time.sleep)
sleeps = []


def wait(chip_sequence, state="nominal", battery=30.0, level_sequence=None):
    """Run the wait loop over chip readings and return (result, sleep_count)."""
    sleeps.clear()
    counter = {"i": 0}

    def fake_chip():
        i = min(counter["i"], len(chip_sequence) - 1)
        lvl = level_sequence[min(counter["i"], len(level_sequence) - 1)] if level_sequence else 0
        counter["i"] += 1
        return chip_sequence[i], 87.0, lvl

    sr.thermal_state = lambda: state
    sr.batt_temp = lambda: battery
    sr.read_chip_state = fake_chip
    sr.time.sleep = lambda s: sleeps.append(s)
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            minuty = sr.wait_for_cooldown(40.0)
        return minuty, len(sleeps), out.getvalue()
    finally:
        sr.thermal_state, sr.batt_temp, sr.read_chip_state, sr.time.sleep = real_values


minuty, amount, text = wait([91.0, 89.0, 86.0])
test("waits until chip drops TO resume threshold (2 sleeps at 91->89->86)",
     amount == 2, "sleeps=%d" % amount)
test("waiting message printed with reason",
     "wait" in text and "chip 91.0" in text, text.strip()[:100])

minuty, amount, text = wait([86.0])
test("cool machine: returns without sleeping", amount == 0, "sleeps=%d" % amount)

minuty, amount, text = wait([None])
test("chip unknown (dead guard) + cool rest: does NOT hang forever",
     amount == 0, "sleeps=%d" % amount)

minuty, amount, text = wait([50.0, 50.0, 50.0], level_sequence=[2, 2, 0])
test("guard level>=2 keeps waiting despite cool chip (throttling/battery)",
     amount == 2 and "guard level 2" in text,
     "sleeps=%d %s" % (amount, text.strip()[:80]))

# Hot battery keeps waiting despite a cool chip; cooling battery ends it.
battery_counter = {"i": 0}


def battery_cools():
    battery_counter["i"] += 1
    return 41.0 if battery_counter["i"] <= 2 else 30.0


sr.thermal_state = lambda: "nominal"
sr.batt_temp = battery_cools
sr.read_chip_state = lambda: (50.0, 87.0, 0)
sr.time.sleep = lambda s: sleeps.append(s)
sleeps.clear()
try:
    with contextlib.redirect_stdout(io.StringIO()) as out_bat:
        sr.wait_for_cooldown(40.0)
finally:
    sr.thermal_state, sr.batt_temp, sr.read_chip_state, sr.time.sleep = real_values
test("hot battery keeps waiting despite cool chip, cooling battery ends it",
     len(sleeps) == 2 and "batt 41.0" in out_bat.getvalue(),
     "sleeps=%d %s" % (len(sleeps), out_bat.getvalue().strip()[:80]))

# --- main() routing: without flag, refusal rc 3 before anything starts ---
snapshot(92.0)
sys.argv = ["safe-run", "--", "true"]
with contextlib.redirect_stdout(io.StringIO()) as out:
    rc = sr.main()
test("without --wait-cool hot snapshot = rc 3 (retry_run.sh contract)",
     rc == 3 and "REFUSING" in out.getvalue(), "rc=%s %s" % (rc, out.getvalue().strip()[:80]))
test("refusal suggests --wait-cool", "--wait-cool" in out.getvalue(),
     out.getvalue().strip()[:120])
sys.argv = argv0

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
