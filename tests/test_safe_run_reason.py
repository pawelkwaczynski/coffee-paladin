#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that a refused start names the condition that actually blocks it.

safe-run printed "the Mac is already hot" for every refusal. With the battery gate
closed (on battery, below batt_pct_pause) the chip sat at 38 C, the message said hot,
and the job waited two hours on --wait-cool for a cooldown that could never fix it.
The refusal has to say battery and charger in that case, and give the numbers.

Run with:  python3 tests/test_safe_run_reason.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ.pop("TG_SAFE_RUN_PGID", None)      # not a nested run


def load(name, lang):
    os.environ["TG_LANG"] = lang
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(SRC, "safe-run"))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


sr = load("sr_reason_en", "en")
sr_pl = load("sr_reason_pl", "pl")

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


def reason(mod, st, conf):
    fn = getattr(mod, "start_block_reason", None)
    return fn(st, conf) if fn else "<no start_block_reason>"


BATTERY = {"level": 2, "reason": "battery 34% on battery power", "on_ac": False,
           "battery_pct": 34, "chip_c": 38.0, "thresholds": {"pause": 103.0}}
HOT = {"level": 2, "reason": "chip 104.2 C", "on_ac": True, "battery_pct": 80,
       "chip_c": 104.2, "thresholds": {"pause": 103.0}}
CONF = {"batt_pct_pause": 50, "soc_pause_c": 103}

print("1. start_block_reason: the reason is built from status.json and config.json")
r = reason(sr, BATTERY, CONF)
test("battery below the gate: battery, charger and both numbers",
     "on battery at 34%" in r and "threshold 50%" in r and "plug in the charger" in r, r)
test("battery below the gate does not claim heat", "hot" not in r and "chip" not in r, r)
test("battery reason is exact",
     r == "the Mac is on battery at 34% (threshold 50%), plug in the charger", r)
r = reason(sr, dict(BATTERY, battery_pct=50), CONF)
test("exactly at the gate counts, as in guard.severity (<=)", "on battery at 50%" in r, r)
r = reason(sr, dict(BATTERY, on_ac=True, battery_pct=5, level=0), CONF)
test("low battery on the charger is not a reason", r == "", repr(r))
r = reason(sr, dict(BATTERY, on_ac=None, level=0), CONF)
test("unknown power source is not called battery", r == "", repr(r))
r = reason(sr, HOT, CONF)
test("hot chip: chip temperature and threshold", r == "chip 104.2 °C, threshold 103 °C", r)
r = reason(sr, dict(HOT, level=0, chip_c=99.0), CONF)
test("chip inside the 5 C start margin says so",
     r == "chip 99.0 °C, threshold 103 °C, safe-run keeps a 5 °C margin", r)
r = reason(sr, dict(HOT, chip_c=99.0, thresholds=None), {"soc_pause_c": 98})
test("threshold falls back to config when the snapshot has none",
     r == "chip 99.0 °C, threshold 98 °C", r)
r = reason(sr, dict(BATTERY, chip_c=104.2), CONF)
test("battery AND hot chip: both named", "on battery at 34%" in r and "chip 104.2" in r, r)
r = reason(sr, {"level": 2, "reason": "CPU throttled to 40%", "on_ac": True,
                "battery_pct": 90, "chip_c": 60.0, "thresholds": {"pause": 103.0}}, CONF)
test("any other level 2: the guard's own reason with the level", r == "guard level 2: CPU throttled to 40%", r)
r = reason(sr, {"level": 3, "reason": "", "chip_c": None}, CONF)
test("level without a reason still names the level", r == "guard level 3: n/a", r)
test("no snapshot: empty reason", reason(sr, None, CONF) == "" and reason(sr, [], CONF) == "")
test("cool machine: empty reason", reason(sr, dict(HOT, level=0, chip_c=50.0), CONF) == "")

junk_ok = True
for st in ({"level": float("inf"), "chip_c": "goraco", "thresholds": "85"},
           {"level": float("nan"), "chip_c": float("nan"), "thresholds": [85.0]},
           {"level": "2", "on_ac": False, "battery_pct": float("-inf"), "thresholds": {"pause": None}},
           {"level": True, "on_ac": False, "battery_pct": "abc", "chip_c": float("inf")}):
    try:
        if not isinstance(reason(sr, st, {"batt_pct_pause": "x"}), str):
            junk_ok = False
    except Exception as e:                      # noqa: BLE001 - the point of the check
        junk_ok = False
        print("     raised %r on %r" % (e, st))
test("junk values never raise", junk_ok)

print("\n2. chip_already_hot reads the files")
STATUS = os.path.join(BASE, "status.json")
CONFIG = os.path.join(BASE, "config.json")
with open(CONFIG, "w") as f:
    json.dump(CONF, f)
w, r = sr.chip_already_hot()
test("missing status.json: no block, no reason", (w, r) == (False, ""), (w, r))
with open(STATUS, "w") as f:
    json.dump(BATTERY, f)
w, r = sr.chip_already_hot()
test("battery snapshot: blocked with the battery reason", w is True and "plug in the charger" in r, (w, r))

print("\n3. the refusal printed by main()")


def refusal(mod, st, state="nominal", temp=None):
    with open(STATUS, "w") as f:
        json.dump(st, f)
    saved = mod.thermal_state, mod.batt_temp, sys.argv
    mod.thermal_state, mod.batt_temp = (lambda: state), (lambda: temp)
    sys.argv = ["safe-run", "--", "true"]
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = mod.main()
    finally:
        mod.thermal_state, mod.batt_temp, sys.argv = saved
    line = [l for l in out.getvalue().splitlines() if "REFUSING" in l or "ODMOWA" in l]
    return rc, (line[0] if line else out.getvalue().strip())


rc, msg = refusal(sr, BATTERY)
test("battery: rc 3 and the refusal names battery and charger",
     rc == 3 and "on battery at 34% (threshold 50%), plug in the charger" in msg, msg)
test("battery: the refusal does not say the Mac is hot",
     "already hot" not in msg and "machine" not in msg, msg)
rc, msg = refusal(sr, HOT)
test("hot chip: the refusal names chip and threshold",
     rc == 3 and "chip 104.2 °C, threshold 103 °C" in msg, msg)
rc, msg = refusal(sr, dict(HOT, level=0, chip_c=50.0), state="serious")
test("thermalState serious with a cool snapshot is named", rc == 3 and "thermalState=serious" in msg, msg)
rc, msg = refusal(sr, dict(HOT, level=0, chip_c=50.0), temp=39.0)
test("warm battery is named with its own threshold",
     rc == 3 and "battery 39.0 °C, threshold 40 °C, safe-run keeps a 2 °C margin" in msg, msg)
rc, msg = refusal(sr_pl, BATTERY)
test("PL: Mac na baterii, próg, podłącz zasilacz",
     rc == 3 and "ODMOWA STARTU - Mac na baterii 34 % (próg 50 %), podłącz zasilacz." in msg, msg)
rc, msg = refusal(sr_pl, HOT)
test("PL: chip i próg", rc == 3 and "chip 104.2 °C, próg 103 °C" in msg, msg)

print("\n4. --wait-cool names the same reason while it waits")


def wait_message(mod, st, after):
    """Run wait_for_cooldown on snapshot `st`; the first sleep swaps in `after`."""
    with open(STATUS, "w") as f:
        json.dump(st, f)

    def fake_sleep(_s):
        with open(STATUS, "w") as f:
            json.dump(after, f)

    saved = mod.thermal_state, mod.batt_temp, mod.time.sleep
    mod.thermal_state, mod.batt_temp, mod.time.sleep = (lambda: "nominal"), (lambda: None), fake_sleep
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            mod.wait_for_cooldown(40.0)
    finally:
        mod.thermal_state, mod.batt_temp, mod.time.sleep = saved
    return out.getvalue().strip()


PLUGGED = dict(BATTERY, level=0, on_ac=True, reason="")
msg = wait_message(sr, BATTERY, PLUGGED)
test("battery: the wait names battery and charger",
     "on battery at 34% (threshold 50%), plug in the charger" in msg, msg)
test("battery: the wait does not say the Mac is hot or cooling",
     "is hot" not in msg and "cools down" not in msg, msg)
msg = wait_message(sr_pl, BATTERY, PLUGGED)
test("PL: czekanie mówi o baterii, nie o gorącym Macu",
     "Mac na baterii 34 % (próg 50 %), podłącz zasilacz" in msg and "gorący" not in msg, msg)
msg = wait_message(sr, dict(HOT, thresholds={"pause": 103.0, "resume": 94.0}),
                   dict(HOT, level=0, chip_c=60.0))
test("hot chip: the wait names the chip against the resume threshold, once",
     "chip 104.2 C > 94 C" in msg and "threshold 103" not in msg, msg)

print("\n5. every new string is translated, with the same placeholders")
keys = ["safe-run: REFUSING TO START - %s. Use --wait-cool to wait, or pass --allow-hot.",
        "the Mac is on battery at %d%% (threshold %d%%), plug in the charger",
        "chip %.1f °C, threshold %.0f °C", "battery %.1f °C, threshold %.0f °C",
        ", safe-run keeps a %d °C margin", "guard level %s: %s",
        "safe-run: --wait-cool - not starting yet (%s), waiting until that clears (checking every 60 s)"]
specs = re.compile(r"%(?:%|[-.0-9]*[sdfg])")
missing = []
for lang, d in sorted(getattr(sr, "DICTS", {}).items()):
    for k in keys:
        v = d.get(k)
        if v is None or v == k or specs.findall(v) != specs.findall(k):
            missing.append("%s: %s" % (lang, k[:40]))
test("PL/RU/ZH/ES carry all new strings", not missing and len(getattr(sr, "DICTS", {})) == 4,
     "; ".join(missing))

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
