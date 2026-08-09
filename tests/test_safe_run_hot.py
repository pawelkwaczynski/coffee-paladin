#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that safe-run refuses to start on a hot machine.

safe-run used to check only ProcessInfo.thermalState and battery temperature. On
Apple Silicon, thermalState can report "nominal" while the chip is 92 C because the
system considers fans sufficient. That let safe-run start a job on a Mac where the
guard paused ffmpeg every several seconds. This test keeps the decision based on
what the guard actually measures.

Run with:  python3 tests/test_safe_run_hot.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import importlib.machinery
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
sr = importlib.machinery.SourceFileLoader("sr", os.path.join(SRC, "safe-run")).load_module()
json.dump({"soc_pause_c": 85.0}, open(os.path.join(BASE, "config.json"), "w"))

zaliczone = 0
wszystkie = 0


def test(nazwa, warunek, szczegol=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s  -> %s" % (nazwa, szczegol))


def migawka(level, chip, wiek=0):
    p = os.path.join(BASE, "status.json")
    json.dump({"level": level, "chip_c": chip,
               "thresholds": {"pause": 85, "kill": 90}}, open(p, "w"))
    if wiek:
        os.utime(p, (time.time() - wiek, time.time() - wiek))
    return p


print("safe-run: refusing start on a hot machine")

for opis, lvl, chip, oczekiwane in [
    ("cold machine does not block start", 0, 45.0, False),
    ("warm, but more than 5 C below threshold - start allowed", 0, 79.0, False),
    ("5 C below pause threshold - START BLOCKED", 0, 80.0, True),
    ("above pause threshold - START BLOCKED", 0, 92.0, True),
    ("guard reports level 2 - START BLOCKED", 2, 50.0, True),
    ("guard reports critical level - START BLOCKED", 3, 50.0, True),
]:
    migawka(lvl, chip)
    wynik, _ = sr.chip_juz_goracy()
    test(opis, wynik is oczekiwane, "level=%s chip=%s -> %s" % (lvl, chip, wynik))

migawka(0, 99.0, wiek=300)
w, _ = sr.chip_juz_goracy()
test("5-minute-old snapshot is not a basis for blocking", w is False, "returned %s" % w)

os.remove(os.path.join(BASE, "status.json"))
w, _ = sr.chip_juz_goracy()
test("missing status.json does not block start (guard will warn anyway)", w is False, "returned %s" % w)

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
