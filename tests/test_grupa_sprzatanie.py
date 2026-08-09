#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify safe-run process-group cleanup on exit and the --grace window.

If a safe-run leader receives SIGTERM from outside as a single pid, not killpg,
safe-run can exit and unregister the job while a child process remains in the group.
That child then runs without a time budget and without registration until manually
killed. This test recreates that layout with live processes and verifies group
cleanup catches it.

Run with:  python3 tests/test_grupa_sprzatanie.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
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
    """Start a leader in its own group with a background child in the same group."""
    p = subprocess.Popen(["/bin/sh", "-c", "sleep 300 & exec sleep 300"],
                         preexec_fn=os.setsid)
    time.sleep(0.3)                       # Let sh start the background child.
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

# --- live processes in group ---
p = grupa_z_wnukiem()
pids = sr.zywi_w_grupie(p.pid)
test("widzi lidera i wnuka w grupie (>= 2 pidy)", len(pids) >= 2, str(pids))
test("nie widzi w grupie NAS", os.getpid() not in pids, str(pids))

# --- Reproduce single-pid leader termination while the grandchild remains ---
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

# --- Frozen orphan (state T): CONT before TERM, or the signal stays pending ---
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

# --- Stubborn process that ignores SIGTERM receives SIGKILL after the grace window ---
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
