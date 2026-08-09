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
print("=== item 6: no MEASUREMENTS does not mean no EVENTS ===")
czysc()
cel = os.path.join(BASE, "pusty.txt")
uruchom("--file", cel, "--days", "7")
tekst = io.open(cel, encoding="utf-8").read()
test("1. with empty directory, document SAYS nothing was recorded",
     "NO MEASUREMENTS IN THIS RANGE" in tekst,
     "missing warning - document reads like proof of health")
test("2. warning is at the TOP, not the end",
     tekst.index("NO MEASUREMENTS") < len(tekst) // 3,
     "position %d of %d" % (tekst.index("NO MEASUREMENTS") if "NO MEASUREMENTS" in tekst else -1,
                          len(tekst)))
# Countercase.
daj_pomiary()
cel2 = os.path.join(BASE, "zdanymi.txt")
uruchom("--file", cel2, "--days", "2")
test("3. when measurements EXIST, there is no warning",
     "NO MEASUREMENTS" not in io.open(cel2, encoding="utf-8").read())

# ---------------------------------------------------------------- item 7
print("\n=== item 7: --pdf does not touch foreign files ===")
czysc()
daj_pomiary()
cudzy = os.path.join(BASE, "wyniki.pdf")
io.open(cudzy, "w", encoding="utf-8").write("CUDZE WAZNE DANE - 2000 stron wynikow badan")
suma_przed = hashlib.sha256(io.open(cudzy, "rb").read()).hexdigest()

rc, out, err = uruchom("--file", os.path.join(BASE, "wyniki.txt"), "--days", "2", "--pdf")
test("4. foreign wyniki.pdf exists after the run", os.path.exists(cudzy))
test("5. ...and is byte-for-byte identical",
     os.path.exists(cudzy)
     and hashlib.sha256(io.open(cudzy, "rb").read()).hexdigest() == suma_przed,
     "file was changed or truncated")
nowy = out.strip().splitlines()[-1] if out.strip() else ""
test("6. PDF was still created under a free name",
     nowy.endswith(".pdf") and os.path.exists(nowy) and nowy != cudzy,
     "returned %r" % nowy)
test("7. no .thermal_report_* temp files left behind",
     not [n for n in os.listdir(BASE) if n.startswith(".thermal_report_")],
     "%s" % [n for n in os.listdir(BASE) if n.startswith(".thermal_report_")])

# ---------------------------------------------------------------- item 8
print("\n=== item 8: bad range must NOT exit with code 0 ===")
czysc()
daj_pomiary()
cel = os.path.join(BASE, "z.txt")
for opis, args in (
    ("reversed range", ["--from", "2026-08-05", "--to", "2026-08-01"]),
    ("typo in --from date", ["--from", "2026-13-45", "--to", "2026-08-01"]),
    ("typo in --to date", ["--from", "2026-08-01", "--to", "2026-99-99"]),
    ("--days without a number", ["--days"]),
    ("--days abc", ["--days", "abc"]),
    ("--days 0", ["--days", "0"]),
):
    rc, out, err = uruchom("--file", cel, *args)
    test("%s -> error code and message" % opis, rc != 0 and err.strip(),
         "rc=%d stderr=%r" % (rc, err[:70]))

print("\n=== opposite case: valid ranges work ===")
for opis, args in (
    ("--days 3", ["--days", "3"]),
    ("--from/--to valid", ["--from", "2026-08-01", "--to", "2026-08-02"]),
    ("--all", ["--all"]),
    ("without range arguments", []),
):
    rc, out, err = uruchom("--file", cel, *args)
    test("%s -> code 0" % opis, rc == 0, "rc=%d stderr=%r" % (rc, err[:70]))

# ---------------------------------------------------------------- item 9
print("\n=== item 9: long report shortened EXPLICITLY without losing evidence ===")
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

test("18. long report was shortened", wierszy_osi < 12000,
     "%d rows on the axis out of 12000" % wierszy_osi)
test("19. ...and document SAYS it shortened (not silently)",
     "TIMELINE SHORTENED" in tekst)
test("20. peak 99.4 C still detected", "PEAK MEASURED CHIP TEMPERATURE: 99.4 C" in tekst,
     "missing peak")
test("21. HOT intervention row SURVIVED shortening",
     "critical, 99.4" in tekst,
     "evidence row discarded during shortening - exactly the bug this item covers")

# Countercase: small dataset remains untouched.
czysc()
daj_pomiary()
cel = os.path.join(BASE, "maly.txt")
uruchom("--file", cel, "--all")
maly = io.open(cel, encoding="utf-8").read()
test("22. small dataset: no shortening and all rows in place",
     "TIMELINE SHORTENED" not in maly
     and len([l for l in maly.splitlines() if l.startswith("  20")]) == 1)

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(wyniki)
print("\nRESULT: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
