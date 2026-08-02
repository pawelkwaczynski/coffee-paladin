#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Czy safe-run naprawde odmawia startu na goracej maszynie.

Powod powstania (02.08.2026): safe-run pytal wylacznie o ProcessInfo.thermalState
i o temperature baterii. Na Apple Silicon thermalState potrafi pokazywac "nominal",
gdy chip ma 92 C — system uznaje, ze radzi sobie wentylatorami. Efekt: safe-run
wystartowal zadanie na maszynie, na ktorej guard pauzowal ffmpeg co kilkanascie
sekund. Test pilnuje, zeby decyzja opierala sie na tym, co guard NAPRAWDE mierzy.

Uruchomienie:  python3 tests/test_safe_run_hot.py
Nie dotyka prawdziwego ~/.coffee-paladin — pracuje w katalogu tymczasowym.
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


print("safe-run: odmowa startu na goracej maszynie")

for opis, lvl, chip, oczekiwane in [
    ("zimna maszyna nie blokuje startu", 0, 45.0, False),
    ("cieplo, ale wiecej niz 5 C do progu - start wolny", 0, 79.0, False),
    ("5 C pod progiem pauzy - START ZABLOKOWANY", 0, 80.0, True),
    ("powyzej progu pauzy - START ZABLOKOWANY", 0, 92.0, True),
    ("guard raportuje poziom 2 - START ZABLOKOWANY", 2, 50.0, True),
    ("guard raportuje poziom krytyczny - START ZABLOKOWANY", 3, 50.0, True),
]:
    migawka(lvl, chip)
    wynik, _ = sr.chip_juz_goracy()
    test(opis, wynik is oczekiwane, "level=%s chip=%s -> %s" % (lvl, chip, wynik))

migawka(0, 99.0, wiek=300)
w, _ = sr.chip_juz_goracy()
test("migawka sprzed 5 minut nie jest podstawa do blokady", w is False, "zwrocono %s" % w)

os.remove(os.path.join(BASE, "status.json"))
w, _ = sr.chip_juz_goracy()
test("brak status.json nie blokuje startu (guard i tak ostrzeze)", w is False, "zwrocono %s" % w)

shutil.rmtree(BASE, ignore_errors=True)
print("\nWYNIK: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
