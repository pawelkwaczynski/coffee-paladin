#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure evidence reports do not lie, destroy files, or accept bad input silently.

  * item 6 - an empty data directory produced a document full of "(none detected...)"
    and an empty timeline, which looked like proof of machine health. It only meant
    nothing had been measured.
  * item 7 - `--pdf` destroyed foreign files in three ways: overwrite without notice,
    truncate to 0 B when Chrome was missing, or delete with `os.remove` when cupsfilter
    returned an error.
  * item 8 - reversed range, date typo, and `--days` without a number exited 0 and
    generated a report for a different period than requested. In an evidence document,
    that is a false negative: "nothing happened in this period".

Run with:  python3 tests/test_raport_bezpieczny.py
Does not touch the real ~/.coffee-paladin.
"""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAPORT = os.path.join(SRC, "thermal-report")
BASE = tempfile.mkdtemp(prefix="tg-raport-")
DZIS = time.strftime("%Y-%m-%d")

wyniki = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


def uruchom(*args):
    p = subprocess.run([sys.executable, RAPORT] + list(args),
                       capture_output=True, text=True, timeout=180,
                       env=dict(os.environ, TG_BASE=BASE, TG_LANG="en"))
    return p.returncode, p.stdout, p.stderr


def daj_pomiary():
    with io.open(os.path.join(BASE, "history.csv"), "w", encoding="utf-8") as f:
        f.write("time,thermal_state,chip_C,gpu_C,batt_C,fan,W,batt_pct,ac,cpu,load,level\n")
        f.write("%s 10:00:00+0200,nominal,55.0,,,0,10,90,1,100,2.0,0\n" % DZIS)


def czysc():
    for n in list(os.listdir(BASE)):
        os.remove(os.path.join(BASE, n))


# ---------------------------------------------------------------- item 6
print("=== poz. 6: brak POMIAROW to nie brak ZDARZEN ===")
czysc()
cel = os.path.join(BASE, "pusty.txt")
uruchom("--file", cel, "--days", "7")
tekst = io.open(cel, encoding="utf-8").read()
test("1. przy pustym katalogu dokument MOWI, ze nic nie zarejestrowano",
     "NO MEASUREMENTS IN THIS RANGE" in tekst,
     "brak ostrzezenia - dokument czyta sie jak dowod zdrowia")
test("2. ostrzezenie stoi na GORZE, nie na koncu",
     tekst.index("NO MEASUREMENTS") < len(tekst) // 3,
     "pozycja %d z %d" % (tekst.index("NO MEASUREMENTS") if "NO MEASUREMENTS" in tekst else -1,
                          len(tekst)))
# Countercase.
daj_pomiary()
cel2 = os.path.join(BASE, "zdanymi.txt")
uruchom("--file", cel2, "--days", "2")
test("3. gdy pomiary SA, zadnego ostrzezenia nie ma",
     "NO MEASUREMENTS" not in io.open(cel2, encoding="utf-8").read())

# ---------------------------------------------------------------- item 7
print("\n=== poz. 7: --pdf nie tyka cudzych plikow ===")
czysc()
daj_pomiary()
cudzy = os.path.join(BASE, "wyniki.pdf")
io.open(cudzy, "w", encoding="utf-8").write("CUDZE WAZNE DANE - 2000 stron wynikow badan")
suma_przed = hashlib.sha256(io.open(cudzy, "rb").read()).hexdigest()

rc, out, err = uruchom("--file", os.path.join(BASE, "wyniki.txt"), "--days", "2", "--pdf")
test("4. cudzy wyniki.pdf istnieje po przebiegu", os.path.exists(cudzy))
test("5. ...i jest bajt w bajt taki sam",
     os.path.exists(cudzy)
     and hashlib.sha256(io.open(cudzy, "rb").read()).hexdigest() == suma_przed,
     "plik zostal zmieniony albo obciety")
nowy = out.strip().splitlines()[-1] if out.strip() else ""
test("6. PDF mimo to powstal, pod wolna nazwa",
     nowy.endswith(".pdf") and os.path.exists(nowy) and nowy != cudzy,
     "zwrocono %r" % nowy)
test("7. nie zostaly pliki robocze .thermal_report_*",
     not [n for n in os.listdir(BASE) if n.startswith(".thermal_report_")],
     "%s" % [n for n in os.listdir(BASE) if n.startswith(".thermal_report_")])

# ---------------------------------------------------------------- item 8
print("\n=== poz. 8: zly zakres NIE moze konczyc sie kodem 0 ===")
czysc()
daj_pomiary()
cel = os.path.join(BASE, "z.txt")
for opis, args in (
    ("odwrocony zakres", ["--from", "2026-08-05", "--to", "2026-08-01"]),
    ("literowka w dacie --from", ["--from", "2026-13-45", "--to", "2026-08-01"]),
    ("literowka w dacie --to", ["--from", "2026-08-01", "--to", "2026-99-99"]),
    ("--days bez liczby", ["--days"]),
    ("--days abc", ["--days", "abc"]),
    ("--days 0", ["--days", "0"]),
):
    rc, out, err = uruchom("--file", cel, *args)
    test("%s -> kod bledu i komunikat" % opis, rc != 0 and err.strip(),
         "rc=%d stderr=%r" % (rc, err[:70]))

print("\n=== przypadek przeciwny: poprawne zakresy dzialaja ===")
for opis, args in (
    ("--days 3", ["--days", "3"]),
    ("--from/--to poprawne", ["--from", "2026-08-01", "--to", "2026-08-02"]),
    ("--all", ["--all"]),
    ("bez argumentow zakresu", []),
):
    rc, out, err = uruchom("--file", cel, *args)
    test("%s -> kod 0" % opis, rc == 0, "rc=%d stderr=%r" % (rc, err[:70]))

# ---------------------------------------------------------------- item 9
print("\n=== poz. 9: dlugi raport skracany JAWNIE, bez gubienia dowodu ===")
czysc()
# 12,000 measurements, including one HOT intervention, must survive shortening.
t0 = time.time() - 60 * 86400
with io.open(os.path.join(BASE, "history.csv"), "w", encoding="utf-8") as f:
    f.write("time,thermal_state,chip_C,gpu_C,batt_C,fan,W,batt_pct,ac,cpu,load,level\n")
    for i in range(12000):
        stempel = time.strftime("%Y-%m-%d %H:%M:%S+0200", time.localtime(t0 + i * 15))
        if i == 7777:
            f.write("%s,critical,99.4,60.0,40.0,4800,60.0,80,1,60,9.10,3\n" % stempel)
        else:
            f.write("%s,nominal,%.1f,45.0,31.0,0,12.5,90,1,100,2.30,0\n" % (stempel, 40 + i % 20))

cel = os.path.join(BASE, "duzy.txt")
uruchom("--file", cel, "--all")
tekst = io.open(cel, encoding="utf-8").read()
wierszy_osi = len([l for l in tekst.splitlines() if l.startswith("  20")])

test("18. dlugi raport zostal skrocony", wierszy_osi < 12000,
     "na osi %d wierszy z 12000" % wierszy_osi)
test("19. ...i dokument MOWI, ze skrocil (nie po cichu)",
     "TIMELINE SHORTENED" in tekst)
test("20. szczyt 99,4 C nadal wykryty", "PEAK MEASURED CHIP TEMPERATURE: 99.4 C" in tekst,
     "brak szczytu")
test("21. GORACY wiersz z interwencja PRZETRWAL skracanie",
     "critical, 99.4" in tekst,
     "wiersz dowodowy wyrzucony przy skracaniu - to bylby dokladnie ten blad, "
     "ktorego ta pozycja dotyczy")

# Countercase: small dataset remains untouched.
czysc()
daj_pomiary()
cel = os.path.join(BASE, "maly.txt")
uruchom("--file", cel, "--all")
maly = io.open(cel, encoding="utf-8").read()
test("22. maly zbior: zadnego skracania i wszystkie wiersze na miejscu",
     "TIMELINE SHORTENED" not in maly
     and len([l for l in maly.splitlines() if l.startswith("  20")]) == 1)

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(wyniki)
print("\nWYNIK: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
