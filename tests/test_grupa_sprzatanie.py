#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""safe-run: sprzatanie grupy procesow przy wyjsciu + okno laski --grace.

Powod powstania (08.08.2026): lider zadania pod safe-run dostal SIGTERM
z zewnatrz (pojedynczy pid, nie killpg). safe-run zakonczyl sie i wyrejestrowal
zadanie - a proces potomny (solver SAT) zostal w grupie i mielil dalej ~8 godzin
bez budzetu czasu i bez rejestracji, az do recznego ubicia. Test odtwarza
dokladnie ten uklad na zywych procesach i pilnuje, ze sprzatanie grupy go lapie.

Uruchomienie:  python3 tests/test_grupa_sprzatanie.py
Nie dotyka prawdziwego ~/.coffee-paladin - pracuje w katalogu tymczasowym.
"""
import importlib.machinery
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
sr = importlib.machinery.SourceFileLoader("sr", os.path.join(SRC, "safe-run")).load_module()
json.dump({}, open(os.path.join(BASE, "config.json"), "w"))

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


def grupa_z_wnukiem():
    """Lider we wlasnej grupie + dziecko w tle w tej samej grupie."""
    p = subprocess.Popen(["/bin/sh", "-c", "sleep 300 & exec sleep 300"],
                         preexec_fn=os.setsid)
    time.sleep(0.3)                       # niech sh zdazy odpalic dziecko w tle
    return p


print("safe-run: sprzatanie grupy + --grace")

# --- parser ---
argv0 = sys.argv
sys.argv = ["safe-run", "--", "true"]
opt, _ = sr.parse()
test("domyslny grace = 30 s (dotychczasowe zachowanie)", opt["grace"] == 30.0, str(opt))
sys.argv = ["safe-run", "--grace", "120", "--", "true"]
opt, _ = sr.parse()
test("--grace 120 ustawia okno laski", opt["grace"] == 120.0, str(opt))
sys.argv = ["safe-run", "--grace", "999999", "--", "true"]
opt, _ = sr.parse()
test("grace ma sufit 1 h", opt["grace"] == 3600.0, str(opt))
sys.argv = argv0

# --- zywi_w_grupie ---
p = grupa_z_wnukiem()
pids = sr.zywi_w_grupie(p.pid)
test("widzi lidera i wnuka w grupie (>= 2 pidy)", len(pids) >= 2, str(pids))
test("nie widzi w grupie NAS", os.getpid() not in pids, str(pids))

# --- odtworzenie incydentu: lider ubity POJEDYNCZO, wnuk zostaje ---
os.kill(p.pid, signal.SIGTERM)
p.wait()
time.sleep(0.3)
sieroty = sr.zywi_w_grupie(p.pid)
test("po smierci lidera wnuk-sierota ZYJE w grupie (repro incydentu)",
     len(sieroty) >= 1, str(sieroty))

t0 = time.time()
sr.sprzatnij_grupe(p.pid, grace=5.0)
czas = time.time() - t0
test("sprzatnij_grupe klade sierote", sr.zywi_w_grupie(p.pid) == [],
     str(sr.zywi_w_grupie(p.pid)))
test("sleep umiera na SIGTERM - bez czekania calego okna laski", czas < 4.0,
     "%.1f s" % czas)

# --- sierota ZAMROZONA (stan T): CONT przed TERM, inaczej sygnal wisi jako pending ---
p = grupa_z_wnukiem()
os.kill(p.pid, signal.SIGTERM)
p.wait()
time.sleep(0.3)
sieroty = sr.zywi_w_grupie(p.pid)
for pid in sieroty:
    os.kill(pid, signal.SIGSTOP)
sr.sprzatnij_grupe(p.pid, grace=5.0)
test("zamrozona sierota tez ginie (CONT przed TERM)",
     sr.zywi_w_grupie(p.pid) == [], str(sr.zywi_w_grupie(p.pid)))

# --- uparty proces (ignoruje SIGTERM) dostaje SIGKILL po oknie laski ---
p = subprocess.Popen(["/bin/sh", "-c", "trap '' TERM; sleep 300"],
                     preexec_fn=os.setsid)
time.sleep(0.3)
t0 = time.time()
sr.sprzatnij_grupe(p.pid, grace=2.0)
p.wait()
czas = time.time() - t0
test("ignorujacy SIGTERM ginie od SIGKILL po oknie laski",
     sr.zywi_w_grupie(p.pid) == [] and 1.5 <= czas < 8.0,
     "%.1f s, zywi=%s" % (czas, sr.zywi_w_grupie(p.pid)))

shutil.rmtree(BASE, ignore_errors=True)
print("\nWYNIK: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
