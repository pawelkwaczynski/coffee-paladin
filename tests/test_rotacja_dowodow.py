#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure log rotation cannot lose evidence.

The guard rotates `guard.log` and `history.csv` at 5 MB. It used to do this with one
`os.replace(path, path + ".1")`, while `thermal-report` read only the current file.
Reproduced effects:
  * just after rotation, the same `--days 2` showed 44.0 C instead of peak 98.7 C,
  * a second rotation overwrote `.1`, permanently deleting evidence.

This is a document for service or a warranty claim. Losing one reading can lose the
whole case.

Run with:  python3 tests/test_rotacja_dowodow.py
Does not touch the real ~/.coffee-paladin; everything is in a temporary directory.
"""
import importlib.machinery
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-rotacja-")
os.environ["TG_BASE"] = BASE
os.environ.setdefault("TG_LANG", "en")

g = importlib.machinery.SourceFileLoader("rot_guard", os.path.join(SRC, "guard.py")).load_module()

wyniki = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


DZIS = time.strftime("%Y-%m-%d")
NAGLOWEK = "time,thermal_state,chip_C,gpu_C,batt_C,fan,W,batt_pct,ac,cpu,load,level\n"


def wiersz(temp, godzina):
    return "%s %s,nominal,%s,,,0,10,90,1,100,2.0,0\n" % (DZIS, godzina, temp)


def napisz_historie(*pary):
    with io.open(g.HIST_PATH, "w", encoding="utf-8") as f:
        f.write(NAGLOWEK)
        for temp, godz in pary:
            f.write(wiersz(temp, godz))


def przepelnij_i_zrotuj(path):
    with io.open(path, "a", encoding="utf-8") as f:
        f.write("# " + "x" * (g.MAX_LOG_BYTES + 10) + "\n")
    g.rotate(path)


def raport(dni=2):
    cel = os.path.join(BASE, "raport.txt")
    subprocess.run([sys.executable, os.path.join(SRC, "thermal-report"),
                    "--file", cel, "--days", str(dni)],
                   capture_output=True, text=True, timeout=90,
                   env=dict(os.environ, TG_BASE=BASE, TG_LANG="en"))
    return io.open(cel, encoding="utf-8", errors="replace").read()


def szczyt_z(tekst):
    import re
    m = re.search(r"PEAK MEASURED CHIP TEMPERATURE: ([0-9.]+) C", tekst)
    return float(m.group(1)) if m else None


print("=== evidence rotation ===")

# 1. Initial state: peak is visible.
napisz_historie(("98.7", "09:00:00"), ("55.0", "09:01:00"))
test("1. before rotation the report shows peak 98.7 C", szczyt_z(raport()) == 98.7,
     "got %s" % szczyt_z(raport()))

# 2. After rotation, the peak must not disappear.
przepelnij_i_zrotuj(g.HIST_PATH)
napisz_historie(("44.0", "10:00:00"))
po = szczyt_z(raport())
test("2. after rotation the report STILL shows 98.7 C (not 44.0 from the new file)", po == 98.7,
     "got %s - report reads only the current file" % po)

# 3. A second rotation does not delete the first generation.
przepelnij_i_zrotuj(g.HIST_PATH)
napisz_historie(("40.0", "11:00:00"))
zrodla = g.generations(g.HIST_PATH)
gdzie = [os.path.basename(p) for p in zrodla
         if "98.7" in io.open(p, encoding="utf-8", errors="replace").read()[:5000]]
test("3. after SECOND rotation the 98.7 C reading still exists on disk", bool(gdzie),
     "lost; files: %s" % sorted(os.listdir(BASE)))
test("4. and report sees it", szczyt_z(raport()) == 98.7, "got %s" % szczyt_z(raport()))

# 5. Generations are chronological, oldest first, or the timeline lies.
nazwy = [os.path.basename(p) for p in g.generations(g.HIST_PATH)]
test("5. generations in chronological order, current file last",
     nazwy == sorted(nazwy, key=lambda n: -int(n.split(".")[-1]) if n[-1].isdigit() else 0)
     and nazwy[-1] == "history.csv",
     "order: %s" % nazwy)

# 6. Generation cap works: old entries fall out instead of growing forever.
for _ in range(g.MAX_LOG_GENERATIONS + 3):
    przepelnij_i_zrotuj(g.HIST_PATH)
    napisz_historie(("41.0", "12:00:00"))
ile = len([n for n in os.listdir(BASE) if n.startswith("history.csv.")])
test("6. generation count does not exceed MAX_LOG_GENERATIONS", ile <= g.MAX_LOG_GENERATIONS,
     "there are %d generations with limit %d" % (ile, g.MAX_LOG_GENERATIONS))

# --- Countercase: without rotation, nothing changes ---
print("\n=== opposite case (no rotation) ===")
for n in list(os.listdir(BASE)):
    if n.startswith("history.csv."):
        os.remove(os.path.join(BASE, n))
napisz_historie(("77.0", "09:00:00"), ("50.0", "09:30:00"))
test("7. without rotation: one source and peak from it",
     g.generations(g.HIST_PATH) == [g.HIST_PATH] and szczyt_z(raport()) == 77.0,
     "sources=%s peak=%s" % (g.generations(g.HIST_PATH), szczyt_z(raport())))

# 8. No file at all means an empty list, not an exception.
os.remove(g.HIST_PATH)
test("8. missing file: generations() returns empty list without exception", g.generations(g.HIST_PATH) == [])

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(wyniki)
print("\nRESULT: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
