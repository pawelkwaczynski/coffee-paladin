#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""thermal-metrics says what power_watts is, and build_info exists on a single Mac (23.10).

1. power_watts is macmon's all_power: CPU, GPU and neural engine. Measured 23.10 on this Mac:
   5.42 W chip power against 18.26 W for the whole system, so the old HELP "Power draw at the
   wall" invited a comparison with an energy meter that is off by more than 3x.
2. build_info printed only when the snapshot had guard_version, which only fleet snapshots
   carried; the local machine is read from status.json, so a Mac without a fleet folder never
   had the metric. status.json now carries guard_version (docs/spec/metrics-v1.md).

A real status_write() into an isolated TG_BASE, then thermal-metrics without --fleet.
Run with:  python3 tests/test_metrics_help_20261023.py
Starts no daemon and signals nothing.
"""
import os
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-metrics-help-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_metrics_help", os.path.join(SRC, "guard.py"))

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


soc = {"cpu": 61.0, "gpu": 58.0, "fans": [2100], "watts": 5.4, "ram_used": 20.0, "ram_total": 48.0,
       "swap_used": 1.0}
g._ostatnio_odrzucone["v"] = []
with patch.object(g, "thermal_pressure", return_value=(0, "nominal")), patch.object(g, "log"):
    snap = g.status_write("nominal", 31.0, soc, 61.0, True, 80, 100, 2.5, 0, "", [],
                          {"paused": {}, "_prog_pauza": 85.0, "_prog_wznowienia": 76.0, "_prog_ubicie": 90.0})

print("1. status.json")
test("status.json carries the daemon's version", snap.get("guard_version") == g.GUARD_VERSION,
     snap.get("guard_version"))

print("2. thermal-metrics on the local machine, no fleet folder")
p = subprocess.run([sys.executable, os.path.join(SRC, "thermal-metrics")], capture_output=True, text=True,
                   timeout=60, env=dict(os.environ, TG_BASE=BASE))
out = p.stdout
test("thermal-metrics runs", p.returncode == 0 and "coffee_paladin_up" in out, (p.returncode, p.stderr[-300:]))
build = [x for x in out.splitlines() if x.startswith("coffee_paladin_build_info{")]
test("build_info has a sample for the local machine, labelled with the version",
     len(build) == 1 and re.search(r'version="%s"' % re.escape(g.GUARD_VERSION), build[0])
     and build[0].endswith(" 1"), build)


def help_of(metric):
    return next((x[len("# HELP %s " % metric):] for x in out.splitlines()
                 if x.startswith("# HELP %s " % metric)), "")


power = help_of("coffee_paladin_power_watts")
test("power_watts HELP says chip power from macmon: CPU, GPU and neural engine",
     power.startswith("Chip power reported by macmon") and "CPU, GPU and neural engine" in power, power)
test("power_watts HELP says it is not the whole Mac and not at the wall",
     "not the whole Mac" in power and "not at the wall" in power and "Power draw at the wall" not in power, power)
test("build_info HELP says whose version it is",
     help_of("coffee_paladin_build_info") == "Version of the guard that wrote the snapshot, as a label",
     help_of("coffee_paladin_build_info"))

print("3. the spec")
with open(os.path.join(SRC, "docs", "spec", "metrics-v1.md"), encoding="utf-8") as f:
    spec = f.read()
status_part = spec.split("## 1. status.json", 1)[-1].split("\n## 2.", 1)[0]
test("metrics-v1.md lists guard_version in status.json",
     re.search(r"^\|\s*`guard_version`\s*\|\s*string\s*\|", status_part, re.M) is not None)
row = next((x for x in spec.splitlines() if x.startswith("| `coffee_paladin_build_info`")), "")
test("the build_info row no longer says the local machine has no sample",
     "local machine" in row and "has no sample" not in row, row)
# 23.10: both rows said the field is absent "up to and including 3.3.5" while GUARD_VERSION was
# still 3.3.5 and this very code wrote it. A release number there is wrong until the bump and
# easy to forget after it; the rows say "an older daemon" instead.
gv_row = next((x for x in status_part.splitlines() if re.match(r"\|\s*`guard_version`\s*\|", x)), "")
test("neither row names the current version as one that lacks guard_version",
     gv_row and g.GUARD_VERSION not in gv_row and g.GUARD_VERSION not in row, (gv_row, row))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
