#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify three resume defects found on a live Mac.

A bad day had 15 pauses, zero resumes, and four jobs killed by SIGTERM. Existing tests
missed it because each mechanism looked correct in isolation.

1. Resume gate took a hostage. Any sensor could trigger pause, but every sensor could
   block resume. Battery cools over minutes and can sit around ~37 C during long encodes,
   so with chip thresholds 95/87 a chip-triggered pause never ended: chip dropped to 71 C
   in 20 seconds, while battery, three degrees below its own 40 C pause threshold that it
   never crossed, kept the job in state T until termination. Fix: latch per sensor, set at
   its own pause threshold and clear at its own resume threshold.

2. Guard trusted its note, not the system. A `paused` entry only says SIGSTOP was sent
   at some point. A process manually resumed with `kill -CONT` or resumed by safe-run's
   duty limiter could run at full power while its entry kept aging, then receive SIGTERM
   mid-job after 45 minutes. Fix: terminate only what `ps` shows as stopped, and delete
   the other entries.

3. Limiter lock checked the wrong pid. `guard_paused(proc.pid)` asked about the group
   leader, while the guard freezes the process producing heat, often child ffmpeg. The
   answer was "no, guard did not pause this", so the limiter's micro-pause ended with
   `killpg(SIGCONT)` and woke the whole group, including what the guard had just frozen.
   Fix: ask about the whole process group, not a bare pid.

Run with:  python3 tests/test_wznowienie.py
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
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()
sr = importlib.machinery.SourceFileLoader("sr", os.path.join(SRC, "safe-run")).load_module()

zaliczone = wszystkie = 0
sprzataj = []


def test(nazwa, warunek, szczegol=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s  -> %s" % (nazwa, szczegol))


def grupa_z_dzieckiem():
    """Start a leader plus child in one process group, matching safe-run jobs.

    Two Popen calls cannot assemble this: a process can only join a group from its own
    session, while `start_new_session` gives each one a separate session. The shell is
    the session and group leader, and its children inherit the group.
    """
    lider = subprocess.Popen(["bash", "-c", "sleep 600 & sleep 600"],
                             start_new_session=True)
    sprzataj.append(lider)
    time.sleep(0.5)
    pgid = os.getpgid(lider.pid)
    dzieci = []
    for linia in subprocess.run(["ps", "-Ao", "pid=,pgid="],
                                capture_output=True, text=True).stdout.splitlines():
        czesci = linia.split()
        if len(czesci) == 2 and int(czesci[1]) == pgid and int(czesci[0]) != lider.pid:
            dzieci.append(int(czesci[0]))
    return lider, pgid, dzieci


def sprzatnij():
    """Leave no process after the test, including children of the shell leader.

    Killing only the leader leaves orphaned `sleep` processes because children have
    their own pids. Signal the whole group, preceded by SIGCONT: a stopped process will
    not handle SIGTERM, so without resume it could remain forever.
    """
    moja_grupa = os.getpgid(0)
    for p in sprzataj:
        try:
            pgid = os.getpgid(p.pid)
        except OSError:
            pgid = None
        # Never signal our own group. Processes started without `start_new_session`
        # sit in the test group, so killpg would also kill the test itself. That is
        # exactly the class of bug this file tests: group signals reach wider than
        # they seem.
        if pgid is not None and pgid != moja_grupa:
            for sygnal in (signal.SIGCONT, signal.SIGKILL):
                try:
                    os.killpg(pgid, sygnal)
                except OSError:
                    pass
        try:
            p.send_signal(signal.SIGCONT)
        except Exception:
            pass
        try:
            p.kill()
            p.wait(timeout=5)
        except Exception:
            pass
    shutil.rmtree(BASE, ignore_errors=True)


# ---------------------------------------------------------------- 1. sensor latch
print("1. sensor blocks resume only when it caused the pause")
PAUZA_B, WZNOW_B = 40.0, 36.0          # Battery thresholds.
PAUZA_C, WZNOW_C = 95.0, 87.0          # Chip thresholds for compression queue.

st = {}
test("battery 36.7 C (below its own threshold 40) does NOT block - this is the defect",
     g.zatrzask_czujnika(st, "_batt_hot", 36.7, PAUZA_B, WZNOW_B) is False,
     "latch: %s" % st.get("_batt_hot"))
test("battery 37.9 C (today's peak) also does not block",
     g.zatrzask_czujnika(st, "_batt_hot", 37.9, PAUZA_B, WZNOW_B) is False)
test("battery 39.9 C - still below threshold, still does not block",
     g.zatrzask_czujnika(st, "_batt_hot", 39.9, PAUZA_B, WZNOW_B) is False)

# But when battery really crosses its threshold, hysteresis must work as before.
st = {}
test("battery 41 C lights the latch",
     g.zatrzask_czujnika(st, "_batt_hot", 41.0, PAUZA_B, WZNOW_B) is True)
test("battery 39 C: latch STILL holds (hysteresis, no threshold bouncing)",
     g.zatrzask_czujnika(st, "_batt_hot", 39.0, PAUZA_B, WZNOW_B) is True)
test("battery 36.5 C: still holds, because resume threshold is 36",
     g.zatrzask_czujnika(st, "_batt_hot", 36.5, PAUZA_B, WZNOW_B) is True)
test("battery 36 C: latch turns off",
     g.zatrzask_czujnika(st, "_batt_hot", 36.0, PAUZA_B, WZNOW_B) is False)

st = {"_batt_hot": True, "_batt_hot_prog": [45.0, 36.0]}
test("live threshold change (calibration/slider) clears latch from before the change",
     g.zatrzask_czujnika(st, "_batt_hot", 37.0, PAUZA_B, WZNOW_B) is False,
     "latch lit against OLD threshold pair means nothing against the new one")

st = {}
g.zatrzask_czujnika(st, "_batt_hot", 41.0, PAUZA_B, WZNOW_B)
test("missing battery reading turns latch off (as before the change: None = no block)",
     g.zatrzask_czujnika(st, "_batt_hot", None, PAUZA_B, WZNOW_B) is False)


# The whole gate goes through `bramka_wznowienia()`, exactly the function the daemon
# executes. A local copy of this condition would pass even if the loop's original broke.
CFG = {"batt_pause_c": PAUZA_B, "batt_resume_c": WZNOW_B,
       "soc_pause_c": PAUZA_C, "soc_resume_c": WZNOW_C}

st = {}
test("chip 94 C blocks resume even when pause was caused by system state",
     g.bramka_wznowienia(CFG, st, 30.0, 94.0, "nominal") is False,
     "chip latch would let this through - hence the strict threshold")
test("chip 88 C still blocks (chip hysteresis untouched)",
     g.bramka_wznowienia(CFG, st, 30.0, 88.0, "nominal") is False)
test("chip 71.2 C with cool battery - RESUME",
     g.bramka_wznowienia(CFG, st, 30.0, 71.2, "nominal") is True)
test("missing chip sensor does not block resume",
     g.bramka_wznowienia(CFG, st, 30.0, None, "nominal") is True)
test("system state 'serious' blocks regardless of temperatures",
     g.bramka_wznowienia(CFG, st, 30.0, 50.0, "serious") is False)

# Exact 19:42:38 -> 19:43 situation.
st = {}
test("at pause time (chip 95.2 / battery 36.7) do NOT resume",
     g.bramka_wznowienia(CFG, st, 36.7, 95.2, "nominal") is False)
test("20 seconds later (chip 71.2 / battery 36.6) RESUME - before fix it did NOT",
     g.bramka_wznowienia(CFG, st, 36.6, 71.2, "nominal") is True)
# When battery really overheats, the gate must hold as before.
test("battery 41 C with cold chip HOLDS resume (cell protection remains)",
     g.bramka_wznowienia(CFG, st, 41.0, 60.0, "nominal") is False)
test("battery 37 C after overheating STILL holds (latch, resume threshold is 36)",
     g.bramka_wznowienia(CFG, st, 37.0, 60.0, "nominal") is False)
test("battery 35.5 C turns latch off and resumes",
     g.bramka_wznowienia(CFG, st, 35.5, 60.0, "nominal") is True)

# ------------------------------------------------------- 2. terminate only stopped processes
print("\n2. SIGTERM after time limit goes only to a process that is really stopped")
p = subprocess.Popen(["sleep", "600"])
sprzataj.append(p)
time.sleep(0.3)
wpis = {"comm": "Python", "manual": False}


def stoi(pid, info=None):
    return g.wpis_stoi(str(pid), info if info is not None else wpis, *g.zatrzymane_teraz())


test("running process: wpis_stoi() = False", stoi(p.pid) is False)
os.kill(p.pid, signal.SIGSTOP)
time.sleep(0.3)
test("after SIGSTOP: wpis_stoi() = True", stoi(p.pid) is True)
os.kill(p.pid, signal.SIGCONT)
time.sleep(0.3)
test("after SIGCONT (Pawel's manual resume at 20:02): wpis_stoi() = False",
     stoi(p.pid) is False)
test("dead pid does not count as stopped", stoi(999999) is False)

# Group case: leader runs, but a child in its group is stopped. Do not delete the
# entry, because it is the only note anyone can use to resume that child.
lider2, pgid2, dzieci2 = grupa_z_dzieckiem()
test("test group has a child (otherwise this scenario checks nothing)",
     len(dzieci2) >= 1, "children: %s" % dzieci2)
if dzieci2:
    dziecko = dzieci2[0]
    os.kill(dziecko, signal.SIGSTOP)
    time.sleep(0.3)
    wpis_grupowy = {"comm": "ffmpeg", "manual": False, "pgid": pgid2}
    test("leader runs, child in group is stopped -> entry STAYS (otherwise child remains T)",
         stoi(lider2.pid, wpis_grupowy) is True)
    os.kill(dziecko, signal.SIGCONT)
    time.sleep(0.3)
    test("whole group runs -> entry to delete",
         stoi(lider2.pid, wpis_grupowy) is False)

# Expired filter: same arithmetic as the loop.
stary = {"since": g.now() - 60 * 60, "since_mono": time.monotonic() - 60 * 60,
         "mono_id": g._MONO_ID, "comm": "Python", "manual": False}
paused = {str(p.pid): stary}
limit_s = 45 * 60


def do_ubicia():
    return g.wpisy_przeterminowane(paused, limit_s, g.zatrzymane_teraz())


test("entry older than 45 min, but process RUNS - do not kill (this killed 20:27 measurement)",
     do_ubicia() == [], "to kill: %s" % do_ubicia())
test("...and same entry IS on deletion list as woken outside guard",
     g.wpisy_nieaktualne(paused, g.zatrzymane_teraz()) == [str(p.pid)])
os.kill(p.pid, signal.SIGSTOP)
time.sleep(0.3)
test("same entry when process REALLY is stopped - kill (guard still works)",
     do_ubicia() == [str(p.pid)], "to kill: %s" % do_ubicia())
test("...and then do NOT delete it as stale",
     g.wpisy_nieaktualne(paused, g.zatrzymane_teraz()) == [])
os.kill(p.pid, signal.SIGCONT)

# A failed `ps` measurement (None) must not trigger either execution path. Empty output
# used to mean "nothing is stopped", so the guard would delete a frozen job's entry and
# leave it in state T without a note.
os.kill(p.pid, signal.SIGSTOP)
time.sleep(0.3)
test("ps unavailable -> do not delete any entry", g.wpisy_nieaktualne(paused, None) == [])
test("ps unavailable -> do not kill anything", g.wpisy_przeterminowane(paused, limit_s, None) == [])
_stary_run = g.run
g.run = lambda *a, **k: ""
try:
    test("zatrzymane_teraz() with empty ps output returns None, not 'nothing is stopped'",
         g.zatrzymane_teraz() is None)
finally:
    g.run = _stary_run
os.kill(p.pid, signal.SIGCONT)

# ------------------------------------------------- 3. limiter lock knows the whole group
print("\n3. limiter does not wake a group where guard froze something")
lider, grupa, dzieci = grupa_z_dzieckiem()
test("test group has a child (this is what ffmpeg under safe-run looks like)", len(dzieci) >= 1,
     "children: %s" % dzieci)
DZIECKO = dzieci[0] if dzieci else lider.pid

stan = os.path.join(BASE, "state.json")
json.dump({"paused": {str(DZIECKO): {"pgid": grupa, "comm": "ffmpeg"}}},
          open(stan, "w"))
test("guard froze CHILD from our group -> limiter sees pause and does NOT wake",
     sr.guard_paused(lider.pid) is True,
     "before fix this was False and limiter did killpg(SIGCONT)")

json.dump({"paused": {str(DZIECKO): {"pgid": grupa + 4242, "comm": "ffmpeg"}}},
          open(stan, "w"))
test("foreign group does not block our limiter", sr.guard_paused(lider.pid) is False)

json.dump({"paused": {str(lider.pid): {"pgid": grupa, "comm": "sleep"}}}, open(stan, "w"))
test("guard froze leader directly - still works as before",
     sr.guard_paused(lider.pid) is True)

# Live foreign process with a recorded pgid equal to ours: the note lies, the system
# tells the truth. Without checking `os.getpgid(entry)`, the limiter would wait forever
# for an unrelated guard decision and leave its own job in state T.
obcy = subprocess.Popen(["sleep", "600"], start_new_session=True)
sprzataj.append(obcy)
time.sleep(0.3)
json.dump({"paused": {str(obcy.pid): {"pgid": grupa, "comm": "ffmpeg"}}}, open(stan, "w"))
test("live foreign process with foreign recorded pgid does not block limiter",
     sr.guard_paused(lider.pid) is False)

json.dump({"paused": {}}, open(stan, "w"))
test("nothing frozen - limiter works normally",
     sr.guard_paused(lider.pid) is False)

# Dead entry plus recycled group number cannot hang the limiter forever.
json.dump({"paused": {"999999": {"pgid": grupa, "comm": "ffmpeg"}}}, open(stan, "w"))
test("entry for nonexistent process does not block limiter (pgid recycling)",
     sr.guard_paused(lider.pid) is False)

# Stale snapshot means "nobody can decide"; keep that rule intact.
json.dump({"paused": {str(DZIECKO): {"pgid": grupa}}}, open(stan, "w"))
os.utime(stan, (time.time() - 600, time.time() - 600))
test("dead daemon (snapshot from 10 min ago) does not keep job frozen",
     sr.guard_paused(lider.pid) is False)

sprzatnij()
print("\nRESULT: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
