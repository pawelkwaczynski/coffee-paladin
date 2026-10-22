#!/usr/bin/env python3
"""Regression checks for status consumers with unknown CPU limits and thermal pressure."""
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-consumers-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_consumers", os.path.join(SRC, "guard.py"))
h = load_source("heat_consumers", os.path.join(SRC, "heat"))
f = load_source("fleet_consumers", os.path.join(SRC, "fleet"))
m = load_source("metrics_consumers", os.path.join(SRC, "thermal-metrics"))
passed = total = 0


def check(name, ok):
    global passed, total
    total += 1
    passed += bool(ok)
    print("  [%s] %s" % ("PASS" if ok else "FAIL", name))


with open(os.path.join(BASE, "config.json"), "w") as out:
    json.dump({"soc_pause_c": 85, "soc_resume_c": 76, "soc_kill_c": 100}, out)
start = time.time() - 3 * 86400
soc = {"gpu": 70, "fans": [3000], "watts": 30}
for i in range(300):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S%z", time.localtime(start + i * 600))
    with patch.object(g, "ts", return_value=stamp):
        row = g.hist_row("fair", soc, 88 + i % 3, 35, [3000], 90, True,
                         None, 6, 1, (123, 250, "ffmpeg", 123))
    g.hist_write(row)
with patch.object(h.sys, "argv", ["heat", "--profile"]), contextlib.redirect_stdout(io.StringIO()) as out:
    h.profile_command()
profile = out.getvalue()
check("C2 unknown limit gives numeric advice", "pause   92.0" in profile and "resume  83.0" in profile)
check("C2 unknown limit explained once", profile.count("macOS reports no CPU limit") == 1)
with open(g.HIST_PATH, newline="") as src:
    reader = csv.DictReader(src)
    fields = reader.fieldnames
    history = list(reader)
with open(g.HIST_PATH, "w", newline="") as dst:
    writer = csv.DictWriter(dst, fields)
    writer.writeheader()
    for row in history:
        row["cpu_limit"] = "100"
        writer.writerow(row)
with patch.object(h.sys, "argv", ["heat", "--profile"]), contextlib.redirect_stdout(io.StringIO()) as out:
    h.profile_command()
known_profile = out.getvalue()
check("C2 known 100 limit keeps original advice", "The CPU was never throttled" in known_profile and
      "pause   92.0" in known_profile and "macOS reports no CPU limit" not in known_profile)
for code in ("PL", "RU", "ZH", "ES"):
    lang = getattr(h, code)
    check("C2 %s translations" % code, all(k in lang for k in (
        "   macOS reports no CPU limit on this Mac; throttling is unknown.",
        "   the plateau reaches the pause threshold; CPU throttling is unknown, so review this threshold advice before applying it.")))

host = {"_age": 0, "level": 1, "thermal_pressure": {"level": 3, "name": "trapping"},
        "fans": [], "on_ac": True, "cpu_limit": None}
check("C3 fleet flags trapping pressure", any("thermal pressure: trapping" in s for s in f.issues_for(host)))
fleet_dir = os.path.join(BASE, "fleet")
os.mkdir(fleet_dir)
with open(os.path.join(fleet_dir, "sample.json"), "w") as out:
    json.dump(dict(host, epoch=time.time(), host="sample"), out)
with patch.object(f.sys, "argv", ["fleet", "--dir", fleet_dir, "--json"]), \
     contextlib.redirect_stdout(io.StringIO()) as out:
    fleet_exit = f.main()
fleet_json = json.loads(out.getvalue())
check("C3 fleet JSON includes pressure issue", fleet_exit == 2 and
      "macOS thermal pressure: trapping" in fleet_json["hosts"][0]["issues"])
for code in ("PL", "RU", "ZH", "ES"):
    lang = getattr(f, code)
    check("C3 %s translations" % code, all(k in lang for k in (
        "macOS thermal pressure: %s", "heavy", "trapping", "sleeping")))
reg = m.Registry()
snap = {"epoch": time.time(), "thermal_pressure": {"level": 3, "name": "trapping"}}
m.collect(reg, snap, os.path.join(BASE, "status.json"), {"host": "test"})
check("C3 metrics exports pressure gauge", "coffee_paladin_thermal_pressure_level{host=\"test\"} 3" in reg.render())
check("C3 pressure has HELP and TYPE", "# HELP coffee_paladin_thermal_pressure_level" in reg.render() and
      "# TYPE coffee_paladin_thermal_pressure_level gauge" in reg.render())
empty = m.Registry()
m.collect(empty, {"epoch": time.time(), "thermal_pressure": None},
          os.path.join(BASE, "status.json"), {"host": "test"})
check("C3 unknown pressure omits gauge", "coffee_paladin_thermal_pressure_level" not in empty.render())

with open(os.path.join(BASE, "status.json"), "w") as out:
    json.dump({"epoch": time.time() - 37 * 3600,
               "thermal_pressure": {"level": 2, "name": "heavy"}}, out)
if hasattr(h, "thermal_pressure"):
    with patch.object(h, "thermal_pressure", return_value=(0, "nominal")), \
         patch.object(h, "sh", return_value=""), patch.object(h, "guard_alive", return_value=False), \
         patch.object(h.sys, "argv", ["heat"]), contextlib.redirect_stdout(io.StringIO()) as out:
        h.main()
    view = out.getvalue()
else:
    view = ""
check("C4 live pressure replaces stale heavy", "thermal pressure: nominal" in view and
      "thermal pressure: heavy" not in view)
if hasattr(h, "thermal_pressure"):
    with patch.object(h, "thermal_pressure", return_value=(0, "nominal")), \
         patch.object(h, "sh", return_value=""), patch.object(h, "guard_alive", return_value=False), \
         patch.object(h.sys, "argv", ["heat", "--json"]), contextlib.redirect_stdout(io.StringIO()) as out:
        h.main()
    measured = json.loads(out.getvalue())["measured"]
else:
    measured = {}
check("C4 JSON includes live measured pressure", measured.get("thermal_pressure") == {"level": 0, "name": "nominal"})
if hasattr(h, "thermal_pressure"):
    with patch.object(h, "thermal_pressure", return_value=None), \
         patch.object(h, "sh", return_value=""), patch.object(h, "guard_alive", return_value=False), \
         patch.object(h.sys, "argv", ["heat"]), contextlib.redirect_stdout(io.StringIO()) as out:
        h.main()
    stale_view = out.getvalue()
else:
    stale_view = ""
check("C4 stale snapshot omitted when live read fails", "thermal pressure:" not in stale_view)
with open(os.path.join(BASE, "status.json"), "w") as out:
    json.dump({"epoch": time.time(),
               "thermal_pressure": {"level": 2, "name": "heavy"}}, out)
if hasattr(h, "thermal_pressure"):
    with patch.object(h, "thermal_pressure", return_value=None), \
         patch.object(h, "sh", return_value=""), patch.object(h, "guard_alive", return_value=False), \
         patch.object(h.sys, "argv", ["heat"]), contextlib.redirect_stdout(io.StringIO()) as out:
        h.main()
    fresh_view = out.getvalue()
else:
    fresh_view = ""
check("C4 fresh snapshot used when live read fails", "thermal pressure: heavy" in fresh_view)

bar = open(os.path.join(SRC, "heatbar.swift")).read()
check("C5 Swift keeps unknown CPU limit optional", 's.cpuLimit = numInt(j["cpu_limit"])\n' in bar and
      "var cpuLimit: Int?" in bar)
reg = m.Registry()
m.collect(reg, {"epoch": time.time(), "cpu_limit": 100},
          os.path.join(BASE, "status.json"), {"host": "test"})
check("C6 CPU limit HELP describes pmset", "macOS CPU_Speed_Limit from pmset" in reg.render())
print("RESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
