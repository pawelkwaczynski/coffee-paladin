#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify safe-run --wait-cool waits for cooling instead of silently refusing start.

safe-run refused to start twice on a hot chip (91.8 C and 90.8 C), and nobody
noticed; the job simply did not happen because the refusal was buried in a long log.
The --wait-cool flag turns refusal into waiting for the guard's resume threshold.

Run with:  python3 tests/test_wait_cool.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import contextlib
import importlib.machinery
import io
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
os.environ["SAFE_RUN_WAIT_POLL"] = "0.01"
sr = importlib.machinery.SourceFileLoader("sr", os.path.join(SRC, "safe-run")).load_module()
json.dump({"soc_pause_c": 95.0, "soc_resume_c": 87.0}, open(os.path.join(BASE, "config.json"), "w"))

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


def migawka(chip, resume=87.0, wiek=0, level=0):
    p = os.path.join(BASE, "status.json")
    progi = {"pause": 95, "kill": 100}
    if resume is not None:
        progi["resume"] = resume
    json.dump({"level": level, "chip_c": chip, "thresholds": progi}, open(p, "w"))
    if wiek:
        os.utime(p, (time.time() - wiek, time.time() - wiek))
    return p


print("safe-run --wait-cool")

# --- parser ---
argv0 = sys.argv
sys.argv = ["safe-run", "--", "true"]
opt, _ = sr.parse()
test("without flag wait_cool is disabled", opt["wait_cool"] is False, str(opt))
sys.argv = ["safe-run", "--wait-cool", "--hours", "2", "--", "true"]
opt, cmd = sr.parse()
test("--wait-cool sets flag and does not eat the command",
     opt["wait_cool"] is True and cmd == ["true"] and opt["hours"] == 2.0,
     "%s %s" % (opt, cmd))
sys.argv = argv0

# --- chip_odczyt ---
migawka(91.0)
chip, prog, lvl = sr.chip_odczyt()
test("fresh snapshot: chip and resume threshold from snapshot",
     chip == 91.0 and prog == 87.0, "chip=%s threshold=%s" % (chip, prog))

migawka(91.0, resume=None)
chip, prog, lvl = sr.chip_odczyt()
test("snapshot without resume field: threshold from config.json (old guard)",
     chip == 91.0 and prog == 87.0, "chip=%s threshold=%s" % (chip, prog))

migawka(99.0, wiek=300)
chip, prog, lvl = sr.chip_odczyt()
test("5-minute-old snapshot: chip unknown (do not hang on a dead guard)",
     chip is None, "chip=%s" % chip)

migawka("zepsute")
chip, prog, lvl = sr.chip_odczyt()
test("junk chip_c in snapshot does not crash read", chip is None, "chip=%s" % chip)

os.remove(os.path.join(BASE, "status.json"))
chip, prog, lvl = sr.chip_odczyt()
test("missing snapshot: chip unknown, threshold from config",
     chip is None and prog == 87.0, "chip=%s threshold=%s" % (chip, prog))

# --- wait loop; replace measurement sources and count sleeps ---
prawdziwe = (sr.thermal_state, sr.batt_temp, sr.chip_odczyt, sr.time.sleep)
drzemki = []


def czekaj(sekwencja_chip, stan="nominal", bateria=30.0, sekwencja_lvl=None):
    """Run the wait loop over chip readings and return (result, sleep_count)."""
    drzemki.clear()
    licznik = {"i": 0}

    def falszywy_chip():
        i = min(licznik["i"], len(sekwencja_chip) - 1)
        lvl = sekwencja_lvl[min(licznik["i"], len(sekwencja_lvl) - 1)] if sekwencja_lvl else 0
        licznik["i"] += 1
        return sekwencja_chip[i], 87.0, lvl

    sr.thermal_state = lambda: stan
    sr.batt_temp = lambda: bateria
    sr.chip_odczyt = falszywy_chip
    sr.time.sleep = lambda s: drzemki.append(s)
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            minuty = sr.czekaj_na_ochlodzenie(40.0)
        return minuty, len(drzemki), out.getvalue()
    finally:
        sr.thermal_state, sr.batt_temp, sr.chip_odczyt, sr.time.sleep = prawdziwe


minuty, ile, tekst = czekaj([91.0, 89.0, 86.0])
test("waits until chip drops TO resume threshold (2 sleeps at 91->89->86)",
     ile == 2, "sleeps=%d" % ile)
test("waiting message printed with reason",
     "wait" in tekst and "chip 91.0" in tekst, tekst.strip()[:100])

minuty, ile, tekst = czekaj([86.0])
test("cool machine: returns without sleeping", ile == 0, "sleeps=%d" % ile)

minuty, ile, tekst = czekaj([None])
test("chip unknown (dead guard) + cool rest: does NOT hang forever",
     ile == 0, "sleeps=%d" % ile)

minuty, ile, tekst = czekaj([50.0, 50.0, 50.0], sekwencja_lvl=[2, 2, 0])
test("guard level>=2 keeps waiting despite cool chip (throttling/battery)",
     ile == 2 and "guard level 2" in tekst,
     "sleeps=%d %s" % (ile, tekst.strip()[:80]))

# Hot battery keeps waiting despite a cool chip; cooling battery ends it.
licznik_bat = {"i": 0}


def bateria_stygnie():
    licznik_bat["i"] += 1
    return 41.0 if licznik_bat["i"] <= 2 else 30.0


sr.thermal_state = lambda: "nominal"
sr.batt_temp = bateria_stygnie
sr.chip_odczyt = lambda: (50.0, 87.0, 0)
sr.time.sleep = lambda s: drzemki.append(s)
drzemki.clear()
try:
    with contextlib.redirect_stdout(io.StringIO()) as out_bat:
        sr.czekaj_na_ochlodzenie(40.0)
finally:
    sr.thermal_state, sr.batt_temp, sr.chip_odczyt, sr.time.sleep = prawdziwe
test("hot battery keeps waiting despite cool chip, cooling battery ends it",
     len(drzemki) == 2 and "batt 41.0" in out_bat.getvalue(),
     "sleeps=%d %s" % (len(drzemki), out_bat.getvalue().strip()[:80]))

# --- main() routing: without flag, refusal rc 3 before anything starts ---
migawka(92.0)
sys.argv = ["safe-run", "--", "true"]
with contextlib.redirect_stdout(io.StringIO()) as out:
    rc = sr.main()
test("without --wait-cool hot snapshot = rc 3 (retry_run.sh contract)",
     rc == 3 and "REFUSING" in out.getvalue(), "rc=%s %s" % (rc, out.getvalue().strip()[:80]))
test("refusal suggests --wait-cool", "--wait-cool" in out.getvalue(),
     out.getvalue().strip()[:120])
sys.argv = argv0

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
