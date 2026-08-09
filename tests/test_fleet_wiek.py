#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute fleet report age from snapshot content, not file mtime.

iCloud can preserve an old mtime while the snapshot content is fresh, making a
healthy Mac that reports every minute appear as "STALE - not reporting (94 h)".
The true age is in the `epoch`/`time` fields inside the file.

Cases, including countercases where false stale and false health are equally bad:
  1. old mtime + fresh content -> not STALE (iCloud artifact)
  2. fresh mtime + old content -> STALE (dead daemon, file just synced)
  3. no `epoch`, old zoned `time` -> STALE (daemon before 2.3.4)
  4. no `epoch`, junk `time` -> age from mtime (last resort, as before the fix)
  5. future `epoch` -> not STALE and not negative age (remote clock skew)
  6. `time` in a different zone -> absolute time, not local time

Run with:  python3 tests/test_fleet_wiek.py
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
from datetime import datetime, timedelta, timezone

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(SRC, "fleet")
BASE = tempfile.mkdtemp(prefix="tg-fleet-wiek-")
FLEET_DATA_DIR = os.path.join(BASE, "flota")
os.makedirs(FLEET_DATA_DIR)

results = []


def test(name, condition, detail=""):
    results.append(bool(condition))
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           ("  -> " + detail) if detail and not condition else ""))


def write_snapshot(name, content, mtime=None):
    p = os.path.join(FLEET_DATA_DIR, name + ".json")
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(content, f)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def time_text(epoch, zone=None):
    tz = zone if zone is not None else timezone(timedelta(seconds=-time.timezone))
    return datetime.fromtimestamp(epoch, tz).strftime("%Y-%m-%d %H:%M:%S%z")


def run_tool():
    p = subprocess.run([sys.executable, FLEET, "--dir", FLEET_DATA_DIR], capture_output=True,
                       text=True, timeout=90, env=dict(os.environ, TG_LANG="en"))
    return p.returncode, p.stdout, p.stderr


def line(out, host):
    for w in out.splitlines():
        if w.startswith(host):
            return w
    return ""


def clean():
    for n in os.listdir(FLEET_DATA_DIR):
        os.remove(os.path.join(FLEET_DATA_DIR, n))


BASELINE = {"thermal_state": "nominal", "paused": [], "fans": [500], "level": 0}
now = time.time()

print("=== 1+2: content beats mtime in BOTH directions ===")
clean()
# iCloud artifact: report from moments ago, mtime from 94 h ago.
write_snapshot("SwiezyStaryMtime", dict(BASELINE, host="SwiezyStaryMtime",
       epoch=round(now - 30, 3), time=time_text(now - 30)), mtime=now - 94 * 3600)
# Opposite case: the daemon died an hour ago and iCloud just synced the file.
write_snapshot("StaraTresc", dict(BASELINE, host="StaraTresc",
       epoch=round(now - 3600, 3), time=time_text(now - 3600)), mtime=now)
rc, out, err = run_tool()
test("1. fresh content + old mtime: NOT STALE",
     "STALE" not in line(out, "SwiezyStaryMtime"), line(out, "SwiezyStaryMtime")[:90])
test("2. old content + fresh mtime: IS STALE",
     "STALE" in line(out, "StaraTresc"), line(out, "StaraTresc")[:90])

print("\n=== 3+4: daemons from before the `epoch` format ===")
clean()
d = dict(BASELINE, host="TylkoTime", time=time_text(now - 3600))
d.pop("epoch", None)
write_snapshot("TylkoTime", d, mtime=now)                       # Without epoch, time counts.
d = dict(BASELINE, host="SmieciTime", time="wczoraj kolo poludnia")
d.pop("epoch", None)
write_snapshot("SmieciTime", d, mtime=now - 3600)               # Junk time: fallback to mtime.
d = dict(BASELINE, host="SmieciSwiezy", time=12345)
d.pop("epoch", None)
write_snapshot("SmieciSwiezy", d, mtime=now)                    # Junk time + fresh mtime: healthy.
rc, out, err = run_tool()
test("3. old zoned `time`, no epoch: STALE despite fresh mtime",
     "STALE" in line(out, "TylkoTime"), line(out, "TylkoTime")[:90])
test("4a. junk `time`: fallback to mtime (old -> STALE)",
     "STALE" in line(out, "SmieciTime"), line(out, "SmieciTime")[:90])
test("4b. junk `time`: fallback to mtime (fresh -> healthy)",
     "STALE" not in line(out, "SmieciSwiezy"), line(out, "SmieciSwiezy")[:90])

print("\n=== 5+6: clocks on remote machines ===")
clean()
write_snapshot("ZegarWPrzod", dict(BASELINE, host="ZegarWPrzod",
       epoch=round(now + 900, 3), time=time_text(now + 900)), mtime=now)
d = dict(BASELINE, host="InnaStrefa",
         time=time_text(now - 30, timezone(timedelta(hours=-7))))
d.pop("epoch", None)
write_snapshot("InnaStrefa", d, mtime=now - 94 * 3600)
# Junk epoch (inf/text) cannot crash the table or outrank time.
write_snapshot("EpochSmieci", dict(BASELINE, host="EpochSmieci",
       epoch="duzo", time=time_text(now - 30)), mtime=now - 94 * 3600)
rc, out, err = run_tool()
test("5. epoch from the future: not STALE, table lives",
     rc in (0, 2) and line(out, "ZegarWPrzod") != "" and
     "STALE" not in line(out, "ZegarWPrzod"), line(out, "ZegarWPrzod")[:90])
test("6. fresh `time` in -0700 zone + old mtime: NOT STALE (absolute time)",
     "STALE" not in line(out, "InnaStrefa"), line(out, "InnaStrefa")[:90])
test("7. junk epoch: fresh `time` saves it, not mtime",
     "STALE" not in line(out, "EpochSmieci"), line(out, "EpochSmieci")[:90])

print("\n=== guard --version ===")
env = dict(os.environ, TG_BASE=os.path.join(BASE, "dom"))
p = subprocess.run([sys.executable, os.path.join(SRC, "guard.py"), "--version"],
                   capture_output=True, text=True, timeout=30, env=env)
test("8. --version: version on stdout, code 0",
     p.returncode == 0 and p.stdout.startswith("coffee-paladin ")
     and p.stdout.split()[-1][0].isdigit(),
     "rc=%d out=%r" % (p.returncode, p.stdout[:60]))
test("9. --version does not create data directory (works before ensure_dirs)",
     not os.path.exists(os.path.join(BASE, "dom")))

shutil.rmtree(BASE, ignore_errors=True)
print("\nTOTAL: %d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
