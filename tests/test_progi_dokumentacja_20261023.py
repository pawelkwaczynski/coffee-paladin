#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The thresholds the docs name are the ones the code enforces (23.10).

The code has two chip profiles: DEFAULTS for a Mac with fans (pause/resume/terminate) and the
values auto_calibrate() sets on a fanless Mac when the user has not touched the thresholds.
The docs had drifted: "the 90 °C pause" (90 is the terminate threshold), "the chip is allowed
to run to 90 °C" (it is paused at 85), "the temperature threshold is yours to set" on a fanless
Mac (calibration sets it), and SKILL.md gave 85 °C as a fanless Mac's default pause.

Every number here is read from guard.py with ast, never from a list kept next to the docs:
1. README.md: no "<N> °C pause" with N other than a pause threshold, the battery/chip sentence
   and the fanless paragraph name the code's values, both profiles are named.
2. README.pl.md: the same sentences in Polish.
3. skills/coffee-paladin/SKILL.md: the pause message points at thresholds in status.json and
   names both profiles; no fanless sentence gives the fan profile's pause as its default; the
   grep incident uses the temperature README.md reports for it.

Run with:  python3 tests/test_progi_dokumentacja_20261023.py
Reads files only.
"""
import ast
import os
import re
import sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def read(rel):
    with open(os.path.join(SRC, rel), encoding="utf-8") as f:
        return f.read()


def flat(text):
    return " ".join(text.split())


def literal_dict(node):
    return {k.value: v.value for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}


tree = ast.parse(read("guard.py"))
defaults = {}
fanless = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DEFAULTS" for t in node.targets):
        defaults = literal_dict(node.value)
    if isinstance(node, ast.FunctionDef) and node.name == "auto_calibrate":
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "update" \
                    and sub.args and isinstance(sub.args[0], ast.Dict):
                values = literal_dict(sub.args[0])
                if "soc_pause_c" in values:
                    fanless = values

KEYS = ("soc_pause_c", "soc_resume_c", "soc_kill_c")


def n(x):
    return str(int(x)) if float(x) == int(x) else str(x)


print("0. the numbers, from guard.py")
test("DEFAULTS has the three chip thresholds and the battery pause", all(k in defaults for k in KEYS + ("batt_pause_c",)),
     sorted(defaults)[:20])
test("auto_calibrate sets the three chip thresholds on a fanless Mac", all(k in fanless for k in KEYS), fanless)
if not (all(k in defaults for k in KEYS + ("batt_pause_c",)) and all(k in fanless for k in KEYS)):
    print("\nRESULT: %d/%d" % (passed, total))
    sys.exit(1)
FAN = "/".join(n(defaults[k]) for k in KEYS)
AIR = "/".join(n(fanless[k]) for k in KEYS)
PAUSE, RESUME, KILL = (n(defaults[k]) for k in KEYS)
AIR_PAUSE, AIR_RESUME, AIR_KILL = (n(fanless[k]) for k in KEYS)
BATT = n(defaults["batt_pause_c"])
print("  with fans %s, fanless %s, battery pause %s" % (FAN, AIR, BATT))
PAUSES = {PAUSE, AIR_PAUSE, BATT}

print("1. README.md")
en = flat(read("README.md"))
wrong = sorted(set(m for m in re.findall(r"(\d+(?:\.\d+)?) °C pause", en) if m not in PAUSES))
test("no '<N> °C pause' with N that is not a pause threshold", not wrong, wrong)
m = re.search(r"That is why its pause threshold is (\d+) °C while the chip's is (\d+) °C \((\d+) °C on a fanless Mac\)", en)
test("battery vs chip: the battery pause and both chip pause thresholds",
     m is not None and m.groups() == (BATT, PAUSE, AIR_PAUSE), m.groups() if m else None)
cooling = en.split("**Cooling is what differs.**", 1)[-1].split("`~/.coffee-paladin/config.json`", 1)[0]
test("the fanless paragraph says calibration sets %s" % AIR, AIR in cooling and "yours to set" not in cooling, cooling)
m = re.search(r"Thresholds ship as two profiles, (\S+) with fans and (\S+) without", en)
test("heat --profile names both profiles", m is not None and m.groups() == (FAN, AIR), m.groups() if m else None)
test("the calibration paragraph names the fanless profile (control)", "chip thresholds (%s)" % AIR in en)

print("2. README.pl.md")
pl = flat(read("README.pl.md"))
wrong = sorted(set(m for m in re.findall(r"pauz\w* przy (\d+(?:\.\d+)?) °C", pl) if m not in PAUSES))
test("no 'pauza przy <N> °C' with N that is not a pause threshold", not wrong, wrong)
m = re.search(r"Dlatego jej próg pauzy to (\d+) °C, a próg chipa (\d+) °C \((\d+) °C w Macu bez wentylatora\)", pl)
test("battery vs chip: the battery pause and both chip pause thresholds",
     m is not None and m.groups() == (BATT, PAUSE, AIR_PAUSE), m.groups() if m else None)
test("the calibration paragraph names the fanless profile (control)", "niższe (%s)" % AIR in pl)

print("3. skills/coffee-paladin/SKILL.md")
skill = read("skills/coffee-paladin/SKILL.md")
fan_default = "%s °C by default" % PAUSE
# A line may name both profiles ("85 °C by default, 78 °C on a fanless Mac"); what must not be
# left is a fanless Mac described with the fan profile's default alone.
bad = [line for line in skill.splitlines()
       if fan_default in line and "fanless" in re.sub(r"\d+ °C on a fanless Mac", "", line)]
test("no fanless sentence gives %s as its default" % fan_default, not bad, bad)
quote = next((line for line in skill.splitlines() if line.startswith("> The Mac reached its pause threshold")), "")
test("the pause message points at thresholds.pause and thresholds.resume in status.json",
     "`thresholds.pause`" in quote and "`thresholds.resume`" in quote and "status.json" in quote, quote)
test("and names both profiles' pause and resume",
     all(s in quote for s in ("%s °C by default" % PAUSE, "%s °C on a fanless Mac" % AIR_PAUSE,
                              "%s °C by default" % RESUME, "%s °C on a fanless Mac" % AIR_RESUME)), quote)
readme_incident = re.search(r"held a fanless Mac at (\d+) °C", en)
skill_incident = re.search(r"fanless Mac was held at (\d+) °C", flat(skill))
test("the grep incident uses the temperature README.md reports for it",
     readme_incident and skill_incident and readme_incident.group(1) == skill_incident.group(1),
     (readme_incident and readme_incident.group(0), skill_incident and skill_incident.group(0)))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
