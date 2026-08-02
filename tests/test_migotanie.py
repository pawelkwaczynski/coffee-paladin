#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trzy znaleziska z ZYWYCH logow 02.08.2026, zgloszone z drugiej sesji.

1. MIGOTANIE PAUZY. Progi chipu maja histereze (pauza 95 / wznowienie 87), ale drugi
   wyzwalacz - stan termiczny systemu - jest binarny i histerezy NIE MA. Zmierzone
   10:46:45-10:48:42: szesc par pauza/wznowienie w cyklach 15-sekundowych przy chipie
   84-85 C, czyli DZIESIEC stopni ponizej progu pauzy. Zadanie skakalo, nic sie nie
   chlodzilo. Lek: minimalny czas pauzy.
2. FALSZYWY ALARM CHLODZENIA. 10:32:43 "chip 75,9 C, oba wentylatory 0 obr/min" -
   a chwile pozniej krecily 2300-2900. Alarm lapal ROZBIEG, nie awarie. Lek: warunek
   musi sie utrzymac przez kilka odczytow.
3. PODWOJNE LICZENIE CPU. Ten sam procesor trafial na liste kandydatow dwa razy:
   jako rodzic z suma poddrzewa i jako dziecko z wlasnym zuzyciem ("bash 276%" obok
   "ffmpeg 276%", przy `ps` dla basha 0,0%). Lek: zostaje najwyzszy przodek.

Uruchomienie:  python3 tests/test_migotanie.py
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


print("1. minimalny czas pauzy konczy oscylacje")
cfg = g.load_cfg()
test("min_pause_seconds jest w konfiguracji", cfg.get("min_pause_seconds", 0) >= 30,
     "wartosc: %s" % cfg.get("min_pause_seconds"))

mono = time.monotonic()
for opis, wpis, wolno_wznowic in [
    ("pauza sprzed 5 s - NIE wznawiamy (to wlasnie dawalo migotanie)",
     {"since": g.now() - 5, "since_mono": mono - 5, "mono_id": g._MONO_ID}, False),
    ("pauza sprzed 59 s - NIE wznawiamy",
     {"since": g.now() - 59, "since_mono": mono - 59, "mono_id": g._MONO_ID}, False),
    ("pauza sprzed 120 s - wznawiamy",
     {"since": g.now() - 120, "since_mono": mono - 120, "mono_id": g._MONO_ID}, True),
    ("pauza poprzedniego demona, 10 min wg zegara sciennego - wznawiamy",
     {"since": g.now() - 600, "since_mono": mono + 5000, "mono_id": "999:1"}, True),
]:
    wiek = g._wiek_pauzy(wpis)
    test(opis, (wiek >= cfg.get("min_pause_seconds", 60)) is wolno_wznowic,
         "wiek=%.0f s, prog=%s" % (wiek, cfg.get("min_pause_seconds")))

print("\n2. alarm chlodzenia wymaga utrzymania warunku")
test("fan_alert_polls jest w konfiguracji i wiekszy niz 1",
     cfg.get("fan_alert_polls", 1) > 1, "wartosc: %s" % cfg.get("fan_alert_polls"))

st = {}
soc_zimny = {"cpu": 50.0, "fans": [0, 0]}
soc_gorący = {"cpu": 80.0, "fans": [0, 0]}
alarmy = []
_zapisz = g.zapisz_zdarzenie
g.zapisz_zdarzenie = lambda *a, **k: alarmy.append(a[0] if a else "?")
try:
    # pojedynczy odczyt "goraco + zero obrotow" = ROZBIEG, nie awaria
    g.fan_alarm(cfg, soc_gorący, 80.0, st)
    test("pierwszy odczyt NIE alarmuje (to rozbieg wentylatorow)", not alarmy,
         "alarmow: %d" % len(alarmy))
    g.fan_alarm(cfg, soc_gorący, 80.0, st)
    test("drugi odczyt tez nie", not alarmy, "alarmow: %d" % len(alarmy))
    g.fan_alarm(cfg, soc_gorący, 80.0, st)
    test("trzeci odczyt z rzedu ALARMUJE (to juz awaria)", len(alarmy) == 1,
         "alarmow: %d" % len(alarmy))
    # rozbieg: wentylatory ruszyly, licznik ma sie wyzerowac
    st2 = {}
    g.fan_alarm(cfg, soc_gorący, 80.0, st2)
    g.fan_alarm(cfg, {"cpu": 80.0, "fans": [2300, 2900]}, 80.0, st2)
    test("ruszenie wentylatorow zeruje licznik", st2.get("_fan_zero_polls") == 0,
         "licznik: %s" % st2.get("_fan_zero_polls"))
finally:
    g.zapisz_zdarzenie = _zapisz

print("\n3. ten sam procesor nie moze byc kandydatem dwa razy")
# bash (rodzic) sam nie zuzywa nic, cale CPU nalezy do dziecka ffmpeg
procs = [(100, 1, 0.0, "bash"), (200, 100, 280.0, "ffmpeg"), (300, 1, 90.0, "python3")]
cfg2 = dict(cfg)
cfg2["count_children"] = True
cfg2["managed_patterns"] = ["bash", "ffmpeg", "python3"]
cfg2["never_patterns"] = []
cfg2["never_extra"] = []
cele = g.pick_targets(cfg2, procs, {})
pidy = [t[0] for t in cele]
test("ffmpeg NIE jest osobnym kandydatem obok swojego rodzica", 200 not in pidy,
     "kandydaci: %s" % pidy)
test("bash (najwyzszy przodek) zostaje na liscie", 100 in pidy, "kandydaci: %s" % pidy)
test("niezalezny proces zostaje", 300 in pidy, "kandydaci: %s" % pidy)
test("CPU rodzica niesie sume poddrzewa",
     any(t[0] == 100 and t[1] >= 280 for t in cele), "cele: %s" % cele)

shutil.rmtree(BASE, ignore_errors=True)
print("\nWYNIK: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
