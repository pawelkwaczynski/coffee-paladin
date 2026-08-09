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
FLOTA = os.path.join(BASE, "flota")
os.makedirs(FLOTA)

wyniki = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


def migawka(nazwa, wiek_s=0, **pola):
    # wiek_s ages the snapshot content (time/epoch), not just mtime. Fleet trusts
    # the file content because iCloud mtime lies.
    t0 = time.time() - wiek_s
    d = {"host": nazwa, "time": time.strftime("%Y-%m-%d %H:%M:%S%z", time.localtime(t0)),
         "epoch": round(t0, 3),
         "thermal_state": "nominal", "paused": [], "fans": [0, 0], "level": 0}
    d.update(pola)
    p = os.path.join(FLOTA, nazwa + ".json")
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(d, f)
    if wiek_s:
        os.utime(p, (t0, t0))
    return p


def uruchom(*args):
    p = subprocess.run([sys.executable, FLEET] + list(args), capture_output=True,
                       text=True, timeout=90, env=dict(os.environ, TG_LANG="en"))
    return p.returncode, p.stdout, p.stderr


def czysc():
    for n in os.listdir(FLOTA):
        os.remove(os.path.join(FLOTA, n))


# ---------------------------------------------------------------- item 16
print("=== poz. 16: 'nie raportuje' nie moze ucinac reszty problemow ===")
czysc()
migawka("Neo", wiek_s=3600, chip_c=98.7, level=3, thermal_state="critical",
        last_hard_shutdown={"time": "2026-08-01 03:12:00+0200"})
rc, out, err = uruchom("--dir", FLOTA)
test("1. host nieraportujacy jest oznaczony", "STALE" in out)
test("2. ...ale twardy pad NIE znika za tym oznaczeniem", "hard shutdown" in out,
     "pad zjedzony przez wczesny return")
test("3. ...ani goraco", "HOT" in out, "brak informacji o 99 C")
test("4. ...ani martwe wentylatory", "fans dead" in out)

# ---------------------------------------------------------------- item 17
print("\n=== poz. 17: migawka bez sensu to nie zdrowa maszyna ===")
czysc()
migawka("TylkoChip", chip_c=float("inf"), battery_c=30.0)
migawka("TylkoLevel", chip_c=45.0, level=float("nan"))
migawka("Wszystko", chip_c=float("inf"), battery_c=float("inf"), level=float("nan"))
migawka("Zdrowy", chip_c=45.0, battery_c=30.0)
rc, out, err = uruchom("--dir", FLOTA)
for host, pole in (("TylkoChip", "chip_c"), ("TylkoLevel", "level"), ("Wszystko", "chip_c")):
    linia = [l for l in out.splitlines() if l.startswith(host)]
    test("5.%s: %s z nieskonczonoscia/NaN jest oznaczony" % (host, pole),
         bool(linia) and "implausible" in linia[0],
         "linia: %r" % (linia[0][:90] if linia else "brak"))
zdrowy = [l for l in out.splitlines() if l.startswith("Zdrowy")]
test("6. zdrowa maszyna NIE dostaje falszywego ostrzezenia",
     bool(zdrowy) and "implausible" not in zdrowy[0],
     "linia: %r" % (zdrowy[0][:90] if zdrowy else "brak"))
test("7. liczba maszyn wymagajacych uwagi to 3, nie 4",
     "3 machine(s) need attention" in out,
     [l for l in out.splitlines() if "need attention" in l])

# ---------------------------------------------------------------- item 18
print("\n=== poz. 18: flagi bez argumentu ===")
for flaga in ("--dir", "--set-dir"):
    rc, out, err = uruchom(flaga)
    test("8.%s bez argumentu: kod bledu, nie traceback" % flaga,
         rc != 0 and "Traceback" not in err and err.strip(),
         "rc=%d err=%r" % (rc, err[:80]))

# Countercase: it works with an argument.
czysc()
migawka("OK", chip_c=45.0)
rc, out, err = uruchom("--dir", FLOTA)
test("9. --dir z poprawna sciezka dziala", rc in (0, 2) and "OK" in out,
     "rc=%d" % rc)

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(wyniki)
print("\nWYNIK: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
