#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fleet: wiek zgloszenia liczony z TRESCI migawki, nie z mtime pliku.

Incydent 07.08.2026: iCloud trzymal mtime sprzed dni przy swiezej tresci, wiec
zdrowy, raportujacy co minute Mac wisial w tabeli jako "STALE - not reporting
(94 h)". Prawda o wieku jest w polach `epoch`/`time` wewnatrz pliku.

Przypadki (w tym PRZECIWNE - falszywe STALE i falszywe zdrowie sa rownie zle):
  1. stary mtime + swieza tresc  -> NIE STALE   (artefakt iCloud)
  2. swiezy mtime + stara tresc  -> STALE       (martwy demon, plik dopiero dosynchronizowany)
  3. bez `epoch`, stary `time` ze strefa -> STALE  (demon sprzed 2.3.4)
  4. bez `epoch`, `time`-smieci  -> wiek z mtime (ostatecznosc, jak przed poprawka)
  5. `epoch` z przyszlosci       -> nie STALE i nie ujemny wiek (zegar obcej maszyny)
  6. `time` w INNEJ strefie niz nasza -> liczy sie absolutnie, nie lokalnie

Uruchomienie:  python3 tests/test_fleet_wiek.py
Nie dotyka prawdziwego ~/.coffee-paladin.
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
FLOTA = os.path.join(BASE, "flota")
os.makedirs(FLOTA)

wyniki = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


def zapisz(nazwa, tresc, mtime=None):
    p = os.path.join(FLOTA, nazwa + ".json")
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(tresc, f)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def czas_txt(epoch, strefa=None):
    tz = strefa if strefa is not None else timezone(timedelta(seconds=-time.timezone))
    return datetime.fromtimestamp(epoch, tz).strftime("%Y-%m-%d %H:%M:%S%z")


def uruchom():
    p = subprocess.run([sys.executable, FLEET, "--dir", FLOTA], capture_output=True,
                       text=True, timeout=90, env=dict(os.environ, TG_LANG="en"))
    return p.returncode, p.stdout, p.stderr


def linia(out, host):
    for w in out.splitlines():
        if w.startswith(host):
            return w
    return ""


def czysc():
    for n in os.listdir(FLOTA):
        os.remove(os.path.join(FLOTA, n))


BAZOWA = {"thermal_state": "nominal", "paused": [], "fans": [500], "level": 0}
teraz = time.time()

print("=== 1+2: tresc wygrywa z mtime w OBIE strony ===")
czysc()
# artefakt iCloud: raport sprzed chwili, mtime sprzed 94 h
zapisz("SwiezyStaryMtime", dict(BAZOWA, host="SwiezyStaryMtime",
       epoch=round(teraz - 30, 3), time=czas_txt(teraz - 30)), mtime=teraz - 94 * 3600)
# odwrotnie: demon umarl godzine temu, iCloud wlasnie dosynchronizowal plik
zapisz("StaraTresc", dict(BAZOWA, host="StaraTresc",
       epoch=round(teraz - 3600, 3), time=czas_txt(teraz - 3600)), mtime=teraz)
rc, out, err = uruchom()
test("1. swieza tresc + stary mtime: NIE jest STALE",
     "STALE" not in linia(out, "SwiezyStaryMtime"), linia(out, "SwiezyStaryMtime")[:90])
test("2. stara tresc + swiezy mtime: JEST STALE",
     "STALE" in linia(out, "StaraTresc"), linia(out, "StaraTresc")[:90])

print("\n=== 3+4: demony sprzed formatu `epoch` ===")
czysc()
d = dict(BAZOWA, host="TylkoTime", time=czas_txt(teraz - 3600))
d.pop("epoch", None)
zapisz("TylkoTime", d, mtime=teraz)                       # bez epoch: liczy sie time
d = dict(BAZOWA, host="SmieciTime", time="wczoraj kolo poludnia")
d.pop("epoch", None)
zapisz("SmieciTime", d, mtime=teraz - 3600)               # smieci: zostaje mtime
d = dict(BAZOWA, host="SmieciSwiezy", time=12345)
d.pop("epoch", None)
zapisz("SmieciSwiezy", d, mtime=teraz)                    # smieci + swiezy mtime: zdrowy
rc, out, err = uruchom()
test("3. stary `time` ze strefa, bez epoch: STALE mimo swiezego mtime",
     "STALE" in linia(out, "TylkoTime"), linia(out, "TylkoTime")[:90])
test("4a. `time`-smieci: fallback do mtime (stary -> STALE)",
     "STALE" in linia(out, "SmieciTime"), linia(out, "SmieciTime")[:90])
test("4b. `time`-smieci: fallback do mtime (swiezy -> zdrowy)",
     "STALE" not in linia(out, "SmieciSwiezy"), linia(out, "SmieciSwiezy")[:90])

print("\n=== 5+6: zegary obcych maszyn ===")
czysc()
zapisz("ZegarWPrzod", dict(BAZOWA, host="ZegarWPrzod",
       epoch=round(teraz + 900, 3), time=czas_txt(teraz + 900)), mtime=teraz)
d = dict(BAZOWA, host="InnaStrefa",
         time=czas_txt(teraz - 30, timezone(timedelta(hours=-7))))
d.pop("epoch", None)
zapisz("InnaStrefa", d, mtime=teraz - 94 * 3600)
# epoch-smieci (inf/tekst) nie moze wywalic tabeli ani dac przewagi nad time
zapisz("EpochSmieci", dict(BAZOWA, host="EpochSmieci",
       epoch="duzo", time=czas_txt(teraz - 30)), mtime=teraz - 94 * 3600)
rc, out, err = uruchom()
test("5. epoch z przyszlosci: nie STALE, tabela zyje",
     rc in (0, 2) and linia(out, "ZegarWPrzod") != "" and
     "STALE" not in linia(out, "ZegarWPrzod"), linia(out, "ZegarWPrzod")[:90])
test("6. swiezy `time` w strefie -0700 + stary mtime: NIE STALE (czas absolutny)",
     "STALE" not in linia(out, "InnaStrefa"), linia(out, "InnaStrefa")[:90])
test("7. epoch-smieci: ratuje go swiezy `time`, nie mtime",
     "STALE" not in linia(out, "EpochSmieci"), linia(out, "EpochSmieci")[:90])

print("\n=== guard --version ===")
env = dict(os.environ, TG_BASE=os.path.join(BASE, "dom"))
p = subprocess.run([sys.executable, os.path.join(SRC, "guard.py"), "--version"],
                   capture_output=True, text=True, timeout=30, env=env)
test("8. --version: wersja na stdout, kod 0",
     p.returncode == 0 and p.stdout.startswith("coffee-paladin ")
     and p.stdout.split()[-1][0].isdigit(),
     "rc=%d out=%r" % (p.returncode, p.stdout[:60]))
test("9. --version nie tworzy katalogu danych (dziala przed ensure_dirs)",
     not os.path.exists(os.path.join(BASE, "dom")))

shutil.rmtree(BASE, ignore_errors=True)
print("\nRAZEM: %d/%d PASS" % (sum(wyniki), len(wyniki)))
sys.exit(0 if all(wyniki) else 1)
