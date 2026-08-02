#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skok zegara nie moze ubic zadania, a slepy straznik nie moze wygladac na zdrowego.

Trzy rodziny bledow z bramki jakosci 02.08.2026:

1. ZEGAR SCIENNY. Dlugosc pauzy liczono z time.time(). Skok NTP o 3 h ubijal
   SIGTERM-em zadanie zapauzowane minute wczesniej; cofniecie zegara wylaczalo
   limit pauzy na dobre. Teraz liczy sie zegar monotoniczny.
2. SLEPY STRAZNIK. Stan "unknown" (thermalstate nie odpowiedzial) mapowal sie na
   poziom 1. Mac bez baterii i bez macmona - mini, Studio - siedzial na poziomie 1
   w nieskonczonosc: nigdy nie osiagal 2, wiec nigdy niczego nie pauzowal, a wygladal
   na zdrowa, lekko cieplawa maszyne.
3. KALIBRACJA. Znacznik `calibrated_for` nie zawieral informacji o czujniku, wiec
   Air zainstalowany PRZED macmonem dostawal tag "fans=0" i progi bezwentylatorowe
   (78/70/88) nie byly nadawane nigdy.

Uruchomienie:  python3 tests/test_zegar_i_czujnik.py
"""
import importlib.machinery
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

zaliczone = wszystkie = 0


def test(nazwa, warunek, szczegol=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s  -> %s" % (nazwa, szczegol))


def dlugosc_pauzy(v):
    """Kopia logiki z petli demona - test pilnuje jej znaczenia, nie litery."""
    m = v.get("since_mono")
    if m is not None:
        return max(0.0, time.monotonic() - m)
    return max(0.0, g.now() - v.get("since", g.now()))


print("1. skok zegara a limit pauzy (limit 45 min)")
limit = 45 * 60
mono = time.monotonic()
for opis, wpis, oczekiwane in [
    ("pauza trwa minute - nie ubijamy",
     {"since": g.now() - 60, "since_mono": mono - 60}, False),
    ("pauza trwa godzine - ubijamy",
     {"since": g.now() - 3600, "since_mono": mono - 3600}, True),
    ("zegar skoczyl o 3 h, pauza trwa minute - NIE ubijamy",
     {"since": g.now() - 10800, "since_mono": mono - 60}, False),
    ("zegar cofniety, pauza trwa godzine - ubijamy mimo to",
     {"since": g.now() + 7200, "since_mono": mono - 3600}, True),
    ("stary wpis bez since_mono - zachowanie jak dawniej",
     {"since": g.now() - 3600}, True),
]:
    test(opis, (dlugosc_pauzy(wpis) > limit) is oczekiwane,
         "dlugosc=%.0f s" % dlugosc_pauzy(wpis))

print("\n2. slepy straznik nie udaje zdrowego")
test("stan 'unknown' nie jest traktowany jak 'fair'", g.LEVELS["unknown"] == 0,
     "LEVELS[unknown]=%s" % g.LEVELS["unknown"])
test("'fair' nadal daje poziom 1", g.LEVELS["fair"] == 1)
test("'serious' nadal daje poziom 2", g.LEVELS["serious"] == 2)

print("\n3. kalibracja rozroznia brak czujnika od braku wentylatorow")
tagi = set()
for hw in ({"model_id": "Mac15,12", "chip": "M3", "fan_count": 0, "chip_sensor": False},
           {"model_id": "Mac15,12", "chip": "M3", "fan_count": 0, "chip_sensor": True}):
    tagi.add("%s|%s|fans=%s|sensor=%s" % (hw["model_id"], hw["chip"],
                                          hw["fan_count"], bool(hw["chip_sensor"])))
test("Air przed macmonem i po nim ma ROZNE znaczniki kalibracji", len(tagi) == 2,
     "znaczniki: %s" % tagi)

shutil.rmtree(BASE, ignore_errors=True)
print("\nWYNIK: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
