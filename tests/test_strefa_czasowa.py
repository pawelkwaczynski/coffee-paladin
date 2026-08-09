#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure evidence artifacts mean the same thing in every time zone.

`ts()` used to write bare `%Y-%m-%d %H:%M:%S`: local time without saying which local
time. events.log was filtered by absolute `epoch`, while history.csv and guard.log
were filtered by text interpreted in the reader's time zone.

A shutdown recorded at 23:30 in Warsaw and read in Auckland for the same `--from/--to`
day showed zero critical events while also printing the timeline, `[KILL]` from the
same second, and peak 98.7 C. The claim document said both that nothing happened and
that the chip reached 98.7 C.

Contract checked here:
  1. timestamp has 24 characters, and the first 19 are exactly the old format so every
     existing parser using `linia[:19]` keeps working,
  2. the same file read in different zones yields a consistent document: either every
     section sees the event or none do,
  3. legacy files without offsets still parse.

Run with:  python3 tests/test_strefa_czasowa.py
Does not touch the real ~/.coffee-paladin.
"""
import importlib.machinery
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-strefa-")
os.environ["TG_BASE"] = BASE
os.environ.setdefault("TG_LANG", "en")

g = importlib.machinery.SourceFileLoader("tz_guard", os.path.join(SRC, "guard.py")).load_module()

wyniki = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


# --- 1. timestamp shape -------------------------------------------------------------
os.environ["TZ"] = "Europe/Warsaw"
time.tzset()
s = g.ts(1785706200.0)                      # 2026-08-02 23:30:00 +0200
test("1. timestamp has 24 characters and offset at the end",
     len(s) == 24 and s[19] in "+-", "got %r" % s)
test("2. first 19 characters are EXACTLY the old format (backward compatibility)",
     re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", s[:19]) is not None,
     "got %r" % s[:19])

# --- 2. parser returns the same result in every zone ---------------------------------
odczyty = {}
for strefa in ("Europe/Warsaw", "America/Los_Angeles", "Pacific/Auckland", "Pacific/Midway"):
    os.environ["TZ"] = strefa
    time.tzset()
    odczyty[strefa] = g.abs_epoch(s)
test("3. abs_epoch() from offset timestamp is IDENTICAL in every zone",
     len(set(odczyty.values())) == 1 and abs(list(odczyty.values())[0] - 1785706200.0) < 1,
     "%s" % odczyty)

os.environ["TZ"] = "Europe/Warsaw"
time.tzset()
test("4. legacy timestamp (without offset) still parses",
     abs(g.abs_epoch("2026-08-02 23:30:00") - 1785706200.0) < 1,
     "got %s" % g.abs_epoch("2026-08-02 23:30:00"))
test("5. junk does not crash parser",
     g.abs_epoch("xyzzy") == 0.0 and g.abs_epoch("") == 0.0 and g.abs_epoch(None) == 0.0)

# --- 3. evidence document is consistent in every zone --------------------------------
DZIEN = "2026-08-02"
STEMPEL = "2026-08-02 23:30:00+0200"
EPOCH = 1785706200


def przygotuj(stempel, epoch_pole=True):
    with io.open(os.path.join(BASE, "history.csv"), "w", encoding="utf-8") as f:
        f.write("time,thermal_state,chip_C,gpu_C,batt_C,fan,W,batt_pct,ac,cpu,load,level\n")
        f.write("%s,critical,98.7,,,0,60,90,1,100,8.0,3\n" % stempel)
    with io.open(os.path.join(BASE, "guard.log"), "w", encoding="utf-8") as f:
        f.write("%s  [KILL] killed ffmpeg (98.7 C)\n" % stempel)
    with io.open(os.path.join(BASE, "events.log"), "w", encoding="utf-8") as f:
        f.write('{"time": "%s", %s"type": "HARD_SHUTDOWN", "description": "x"}\n'
                % (stempel, ('"epoch": %d, ' % epoch_pole) if epoch_pole else ""))


def sekcje(strefa):
    cel = os.path.join(BASE, "r_%s.txt" % strefa.replace("/", "_"))
    subprocess.run([sys.executable, os.path.join(SRC, "thermal-report"),
                    "--file", cel, "--from", DZIEN, "--to", DZIEN],
                   capture_output=True, text=True, timeout=90,
                   env=dict(os.environ, TG_BASE=BASE, TG_LANG="en", TZ=strefa))
    t = io.open(cel, encoding="utf-8", errors="replace").read()
    return {"zdarzenie": "HARD_SHUTDOWN" in t,
            "os_czasu": bool(re.search(r"^  \d{4}-\d{2}-\d{2} ", t, re.M)),
            "interwencja": "[KILL]" in t,
            "szczyt": "PEAK MEASURED" in t}


przygotuj(STEMPEL, EPOCH)
niespojne = []
for strefa in ("Europe/Warsaw", "America/Los_Angeles", "Pacific/Auckland", "Pacific/Midway"):
    s_ = sekcje(strefa)
    if len(set(s_.values())) != 1:
        niespojne.append((strefa, s_))
test("6. in EVERY zone the document is consistent (all sections see event or none do)",
     not niespojne, "inconsistent: %s" % niespojne)

# This is the exact case that used to lie.
w_auckland = sekcje("Pacific/Auckland")
test("7. Auckland: no more 'zero events' beside printed peak 98.7 C",
     not (w_auckland["zdarzenie"] is False and w_auckland["szczyt"] is True),
     "event=%s peak=%s" % (w_auckland["zdarzenie"], w_auckland["szczyt"]))

# --- 4. legacy: files without offsets remain readable --------------------------------
przygotuj("2026-08-02 23:30:00", EPOCH)
w_domu = sekcje("Europe/Warsaw")
test("8. legacy in write zone: report still sees measurements and interventions",
     w_domu["os_czasu"] and w_domu["interwencja"] and w_domu["szczyt"],
     "%s" % w_domu)

shutil.rmtree(BASE, ignore_errors=True)
os.environ["TZ"] = "Europe/Warsaw"
time.tzset()
ok = sum(wyniki)
print("\nRESULT: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
