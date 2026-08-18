#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure fleet does not truncate issues, fake health, or traceback on bad CLI input.

  * item 16 - "STALE - not reporting" used to end with `return out`, truncating all
    other host issues. A Mac that hard-shutdown at chip 98.7 C and did not come back
    showed only "not reporting" in ISSUES. The most important fleet fact disappeared
    behind the least important one.
  * item 17 - a snapshot full of infinities was reported as healthy: `float("nan") >= 2`
    is False, so a host with chip_c=inf and level=NaN showed "calm".
  * item 18 - `--dir` and `--set-dir` without an argument produced a raw traceback.

Run with:  python3 tests/test_fleet_problemy.py
Does not touch the real ~/.coffee-paladin.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(SRC, "fleet")
BASE = tempfile.mkdtemp(prefix="tg-fleet-")
FLEET_DATA_DIR = os.path.join(BASE, "flota")
os.makedirs(FLEET_DATA_DIR)

results = []


def test(name, condition, detail=""):
    results.append(bool(condition))
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           ("  -> " + detail) if detail and not condition else ""))


def snapshot(name, age_seconds=0, **fields):
    # wiek_s ages the snapshot content (time/epoch), not just mtime. Fleet trusts
    # the file content because iCloud mtime lies.
    t0 = time.time() - age_seconds
    d = {"host": name, "time": time.strftime("%Y-%m-%d %H:%M:%S%z", time.localtime(t0)),
         "epoch": round(t0, 3),
         "thermal_state": "nominal", "paused": [], "fans": [0, 0], "level": 0}
    d.update(fields)
    p = os.path.join(FLEET_DATA_DIR, name + ".json")
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(d, f)
    if age_seconds:
        os.utime(p, (t0, t0))
    return p


def run_tool(*args):
    p = subprocess.run([sys.executable, FLEET] + list(args), capture_output=True,
                       text=True, timeout=90, env=dict(os.environ, TG_LANG="en"))
    return p.returncode, p.stdout, p.stderr


def clean():
    for n in os.listdir(FLEET_DATA_DIR):
        os.remove(os.path.join(FLEET_DATA_DIR, n))


# ---------------------------------------------------------------- item 16
print("=== item 16: 'not reporting' must not hide the rest of the problems ===")
clean()
snapshot("Neo", age_seconds=3600, chip_c=98.7, level=3, thermal_state="critical",
        last_hard_shutdown={"time": "2026-08-01 03:12:00+0200"})
rc, out, err = run_tool("--dir", FLEET_DATA_DIR)
test("1. non-reporting host is marked", "STALE" in out)
test("2. ...but hard shutdown does NOT disappear behind that marker", "hard shutdown" in out,
     "hard shutdown eaten by early return")
test("3. ...nor heat", "HOT" in out, "missing information about 99 C")
test("4. ...nor dead fans", "fans dead" in out)

# ---------------------------------------------------------------- item 17
print("\n=== item 17: nonsensical snapshot is not a healthy machine ===")
clean()
snapshot("TylkoChip", chip_c=float("inf"), battery_c=30.0)
snapshot("TylkoLevel", chip_c=45.0, level=float("nan"))
snapshot("Wszystko", chip_c=float("inf"), battery_c=float("inf"), level=float("nan"))
snapshot("Zdrowy", chip_c=45.0, battery_c=30.0)
rc, out, err = run_tool("--dir", FLEET_DATA_DIR)
for host, field in (("TylkoChip", "chip_c"), ("TylkoLevel", "level"), ("Wszystko", "chip_c")):
    line = [l for l in out.splitlines() if l.startswith(host)]
    test("5.%s: %s with infinity/NaN is marked" % (host, field),
         bool(line) and "implausible" in line[0],
         "line: %r" % (line[0][:90] if line else "missing"))
healthy = [l for l in out.splitlines() if l.startswith("Zdrowy")]
test("6. healthy machine does NOT get a false warning",
     bool(healthy) and "implausible" not in healthy[0],
     "line: %r" % (healthy[0][:90] if healthy else "missing"))
test("7. machines needing attention count is 3, not 4",
     "3 machine(s) need attention" in out,
     [l for l in out.splitlines() if "need attention" in l])

# ---------------------------------------------------------------- item 18
print("\n=== item 18: flags without an argument ===")
for flag in ("--dir", "--set-dir"):
    rc, out, err = run_tool(flag)
    test("8.%s without argument: error code, not traceback" % flag,
         rc != 0 and "Traceback" not in err and err.strip(),
         "rc=%d err=%r" % (rc, err[:80]))

# Countercase: it works with an argument.
clean()
snapshot("OK", chip_c=45.0)
rc, out, err = run_tool("--dir", FLEET_DATA_DIR)
test("9. --dir with a valid path works", rc in (0, 2) and "OK" in out,
     "rc=%d" % rc)

# ------------------------------------------------- remembered readings (chip_stale)
# A host whose sensor did not answer publishes its last good chip value with
# chip_stale=true. The fleet table must not turn a remembered number into a hardware
# accusation ("fans dead at 95 C") or quote it as this machine's temperature.
print("\n=== remembered chip readings must not accuse hardware ===")
clean()
snapshot("MEASURED", chip_c=95.0, fans=[0, 0], level=2)
rc, out, err = run_tool("--dir", FLEET_DATA_DIR)
test("10. a measured hot chip with dead fans is still reported",
     "fans dead" in out and "95" in out, out[:200])

clean()
snapshot("REMEMBERED", chip_c=95.0, fans=[0, 0], level=2, chip_stale=True)
rc, out, err = run_tool("--dir", FLEET_DATA_DIR)
row = " | ".join(l for l in out.splitlines() if "REMEMBERED" in l)
test("11. a remembered one never says the fans are dead", "fans dead" not in out, row)
test("12. the ISSUES text keeps the warning without quoting the number",
     "HOT - guard is intervening" in row and "HOT - 95" not in row, row)
test("13. the CHIP column marks it as remembered rather than hiding it",
     "~95C" in row, row)

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(results)
print("\nRESULT: %d/%d" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
