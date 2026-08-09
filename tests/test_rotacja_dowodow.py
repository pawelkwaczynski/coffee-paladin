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

results = []


def test(name, condition, detail=""):
    results.append(bool(condition))
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           ("  -> " + detail) if detail and not condition else ""))


TODAY = time.strftime("%Y-%m-%d")
HEADER = "time,thermal_state,chip_C,gpu_C,batt_C,fan,W,batt_pct,ac,cpu,load,level\n"


def row(temp, hour):
    return "%s %s,nominal,%s,,,0,10,90,1,100,2.0,0\n" % (TODAY, hour, temp)


def write_history(*pary):
    with io.open(g.HIST_PATH, "w", encoding="utf-8") as f:
        f.write(HEADER)
        for temp, hour_text in pary:
            f.write(row(temp, hour_text))


def fill_and_rotate(path):
    with io.open(path, "a", encoding="utf-8") as f:
        f.write("# " + "x" * (g.MAX_LOG_BYTES + 10) + "\n")
    g.rotate(path)


def report(days=2):
    target = os.path.join(BASE, "raport.txt")
    subprocess.run([sys.executable, os.path.join(SRC, "thermal-report"),
                    "--file", target, "--days", str(days)],
                   capture_output=True, text=True, timeout=90,
                   env=dict(os.environ, TG_BASE=BASE, TG_LANG="en"))
    return io.open(target, encoding="utf-8", errors="replace").read()


def peak_from(text):
    import re
    m = re.search(r"PEAK MEASURED CHIP TEMPERATURE: ([0-9.]+) C", text)
    return float(m.group(1)) if m else None


print("=== evidence rotation ===")

# 1. Initial state: peak is visible.
write_history(("98.7", "09:00:00"), ("55.0", "09:01:00"))
test("1. before rotation the report shows peak 98.7 C", peak_from(report()) == 98.7,
     "got %s" % peak_from(report()))

# 2. After rotation, the peak must not disappear.
fill_and_rotate(g.HIST_PATH)
write_history(("44.0", "10:00:00"))
after = peak_from(report())
test("2. after rotation the report STILL shows 98.7 C (not 44.0 from the new file)", after == 98.7,
     "got %s - report reads only the current file" % after)

# 3. A second rotation does not delete the first generation.
fill_and_rotate(g.HIST_PATH)
write_history(("40.0", "11:00:00"))
sources = g.generations(g.HIST_PATH)
location = [os.path.basename(p) for p in sources
         if "98.7" in io.open(p, encoding="utf-8", errors="replace").read()[:5000]]
test("3. after SECOND rotation the 98.7 C reading still exists on disk", bool(location),
     "lost; files: %s" % sorted(os.listdir(BASE)))
test("4. and report sees it", peak_from(report()) == 98.7, "got %s" % peak_from(report()))

# 5. Generations are chronological, oldest first, or the timeline lies.
names = [os.path.basename(p) for p in g.generations(g.HIST_PATH)]
test("5. generations in chronological order, current file last",
     names == sorted(names, key=lambda n: -int(n.split(".")[-1]) if n[-1].isdigit() else 0)
     and names[-1] == "history.csv",
     "order: %s" % names)

# 6. Generation cap works: old entries fall out instead of growing forever.
for _ in range(g.MAX_LOG_GENERATIONS + 3):
    fill_and_rotate(g.HIST_PATH)
    write_history(("41.0", "12:00:00"))
amount = len([n for n in os.listdir(BASE) if n.startswith("history.csv.")])
test("6. generation count does not exceed MAX_LOG_GENERATIONS", amount <= g.MAX_LOG_GENERATIONS,
     "there are %d generations with limit %d" % (amount, g.MAX_LOG_GENERATIONS))

# --- Countercase: without rotation, nothing changes ---
print("\n=== opposite case (no rotation) ===")
for n in list(os.listdir(BASE)):
    if n.startswith("history.csv."):
        os.remove(os.path.join(BASE, n))
write_history(("77.0", "09:00:00"), ("50.0", "09:30:00"))
test("7. without rotation: one source and peak from it",
     g.generations(g.HIST_PATH) == [g.HIST_PATH] and peak_from(report()) == 77.0,
     "sources=%s peak=%s" % (g.generations(g.HIST_PATH), peak_from(report())))

# 8. No file at all means an empty list, not an exception.
os.remove(g.HIST_PATH)
test("8. missing file: generations() returns empty list without exception", g.generations(g.HIST_PATH) == [])

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(results)
print("\nRESULT: %d/%d" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
