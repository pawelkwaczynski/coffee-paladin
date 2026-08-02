#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Artefakty dowodowe musza znaczyc TO SAMO w kazdej strefie (pozycja 2 z listy).

Do 2.1.7 `ts()` pisal gole `%Y-%m-%d %H:%M:%S` - czas lokalny bez informacji, ktory
to lokalny. Zdarzenia w events.log byly filtrowane po polu `epoch` (absolutnym),
a history.csv i guard.log po TEKSCIE interpretowanym w strefie CZYTELNIKA.

Odtworzone 02.08.2026: pad zapisany 23:30 w Warszawie, raport `--from/--to` na ten
sam dzien czytany w Auckland pokazywal ZERO zdarzen krytycznych, a tuz obok drukowal
os czasu, `[KILL]` z tej samej sekundy i szczyt 98,7 C. Dokument roszczeniowy
twierdzil jednoczesnie, ze nic sie nie stalo i ze chip miał 98,7 C.

Kontrakt, ktorego pilnuje ten plik:
  1. stempel ma 24 znaki, a jego pierwsze 19 to DOKLADNIE stary format
     (kazdy istniejacy parser bioracy `linia[:19]` musi dzialac dalej),
  2. ten sam plik czytany w roznych strefach daje SPOJNY dokument - albo wszystkie
     sekcje widza zdarzenie, albo zadna,
  3. pliki bez offsetu (legacy) dalej sie czytaja.

Uruchomienie:  python3 tests/test_strefa_czasowa.py
Nie dotyka prawdziwego ~/.coffee-paladin.
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


# --- 1. ksztalt stempla -------------------------------------------------------------
os.environ["TZ"] = "Europe/Warsaw"
time.tzset()
s = g.ts(1785706200.0)                      # 2026-08-02 23:30:00 +0200
test("1. stempel ma 24 znaki i offset na koncu",
     len(s) == 24 and s[19] in "+-", "dostalem %r" % s)
test("2. pierwsze 19 znakow to DOKLADNIE stary format (wsteczna zgodnosc)",
     re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", s[:19]) is not None,
     "dostalem %r" % s[:19])

# --- 2. parser daje ten sam wynik w kazdej strefie ----------------------------------
odczyty = {}
for strefa in ("Europe/Warsaw", "America/Los_Angeles", "Pacific/Auckland", "Pacific/Midway"):
    os.environ["TZ"] = strefa
    time.tzset()
    odczyty[strefa] = g.czas_abs(s)
test("3. czas_abs() ze stempla z offsetem jest IDENTYCZNY w kazdej strefie",
     len(set(odczyty.values())) == 1 and abs(list(odczyty.values())[0] - 1785706200.0) < 1,
     "%s" % odczyty)

os.environ["TZ"] = "Europe/Warsaw"
time.tzset()
test("4. stempel legacy (bez offsetu) dalej sie parsuje",
     abs(g.czas_abs("2026-08-02 23:30:00") - 1785706200.0) < 1,
     "dostalem %s" % g.czas_abs("2026-08-02 23:30:00"))
test("5. smiec nie wywala parsera",
     g.czas_abs("xyzzy") == 0.0 and g.czas_abs("") == 0.0 and g.czas_abs(None) == 0.0)

# --- 3. dokument dowodowy jest SPOJNY w kazdej strefie -------------------------------
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
test("6. w KAZDEJ strefie dokument jest spojny (wszystkie sekcje widza zdarzenie albo zadna)",
     not niespojne, "niespojne: %s" % niespojne)

# to jest dokladnie ten przypadek, ktory wczesniej klamal
w_auckland = sekcje("Pacific/Auckland")
test("7. Auckland: nie ma juz 'zero zdarzen' obok wydrukowanego szczytu 98,7 C",
     not (w_auckland["zdarzenie"] is False and w_auckland["szczyt"] is True),
     "zdarzenie=%s szczyt=%s" % (w_auckland["zdarzenie"], w_auckland["szczyt"]))

# --- 4. legacy: pliki bez offsetu dalej czytelne -------------------------------------
przygotuj("2026-08-02 23:30:00", EPOCH)
w_domu = sekcje("Europe/Warsaw")
test("8. legacy w strefie zapisu: raport nadal widzi pomiary i interwencje",
     w_domu["os_czasu"] and w_domu["interwencja"] and w_domu["szczyt"],
     "%s" % w_domu)

shutil.rmtree(BASE, ignore_errors=True)
os.environ["TZ"] = "Europe/Warsaw"
time.tzset()
ok = sum(wyniki)
print("\nWYNIK: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
