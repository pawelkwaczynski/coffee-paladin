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
print("1. czujnik blokuje wznowienie tylko wtedy, gdy sam kazal pauzowac")
PAUZA_B, WZNOW_B = 40.0, 36.0          # Battery thresholds.
PAUZA_C, WZNOW_C = 95.0, 87.0          # Chip thresholds for compression queue.

st = {}
test("bateria 36,7 C (ponizej wlasnego progu 40) NIE blokuje - to jest ten defekt",
     g.zatrzask_czujnika(st, "_batt_hot", 36.7, PAUZA_B, WZNOW_B) is False,
     "zatrzask: %s" % st.get("_batt_hot"))
test("bateria 37,9 C (dzisiejszy szczyt) tez nie blokuje",
     g.zatrzask_czujnika(st, "_batt_hot", 37.9, PAUZA_B, WZNOW_B) is False)
test("bateria 39,9 C - dalej ponizej progu, dalej nie blokuje",
     g.zatrzask_czujnika(st, "_batt_hot", 39.9, PAUZA_B, WZNOW_B) is False)

# But when battery really crosses its threshold, hysteresis must work as before.
st = {}
test("bateria 41 C zapala zatrzask",
     g.zatrzask_czujnika(st, "_batt_hot", 41.0, PAUZA_B, WZNOW_B) is True)
test("bateria 39 C: zatrzask DALEJ trzyma (histereza, nie odbijamy sie od progu)",
     g.zatrzask_czujnika(st, "_batt_hot", 39.0, PAUZA_B, WZNOW_B) is True)
test("bateria 36,5 C: dalej trzyma, bo prog wznowienia to 36",
     g.zatrzask_czujnika(st, "_batt_hot", 36.5, PAUZA_B, WZNOW_B) is True)
test("bateria 36 C: zatrzask gasnie",
     g.zatrzask_czujnika(st, "_batt_hot", 36.0, PAUZA_B, WZNOW_B) is False)

st = {"_batt_hot": True, "_batt_hot_prog": [45.0, 36.0]}
test("zmiana progu w locie (kalibracja/suwak) kasuje zatrzask sprzed zmiany",
     g.zatrzask_czujnika(st, "_batt_hot", 37.0, PAUZA_B, WZNOW_B) is False,
     "zatrzask zapalony wzgledem STAREJ pary progow nie znaczy nic wobec nowej")

st = {}
g.zatrzask_czujnika(st, "_batt_hot", 41.0, PAUZA_B, WZNOW_B)
test("brak odczytu baterii gasi zatrzask (jak w kodzie sprzed zmiany: None = nie blokuje)",
     g.zatrzask_czujnika(st, "_batt_hot", None, PAUZA_B, WZNOW_B) is False)


# The whole gate goes through `bramka_wznowienia()`, exactly the function the daemon
# executes. A local copy of this condition would pass even if the loop's original broke.
CFG = {"batt_pause_c": PAUZA_B, "batt_resume_c": WZNOW_B,
       "soc_pause_c": PAUZA_C, "soc_resume_c": WZNOW_C}

st = {}
test("chip 94 C blokuje wznowienie, nawet gdy pauze wywolal stan systemowy",
     g.bramka_wznowienia(CFG, st, 30.0, 94.0, "nominal") is False,
     "zatrzask na chipie puscilby to dalej - stad surowy prog")
test("chip 88 C dalej blokuje (histereza chipu nietknieta)",
     g.bramka_wznowienia(CFG, st, 30.0, 88.0, "nominal") is False)
test("chip 71,2 C przy chlodnej baterii - WZNAWIAMY",
     g.bramka_wznowienia(CFG, st, 30.0, 71.2, "nominal") is True)
test("brak czujnika chipa nie blokuje wznowienia",
     g.bramka_wznowienia(CFG, st, 30.0, None, "nominal") is True)
test("stan systemowy 'serious' blokuje niezaleznie od temperatur",
     g.bramka_wznowienia(CFG, st, 30.0, 50.0, "serious") is False)

# Exact 19:42:38 -> 19:43 situation.
st = {}
test("w chwili pauzy (chip 95,2 / bateria 36,7) NIE wznawiamy",
     g.bramka_wznowienia(CFG, st, 36.7, 95.2, "nominal") is False)
test("20 sekund pozniej (chip 71,2 / bateria 36,6) WZNAWIAMY - przed poprawka NIE",
     g.bramka_wznowienia(CFG, st, 36.6, 71.2, "nominal") is True)
# When battery really overheats, the gate must hold as before.
test("bateria 41 C przy zimnym chipie WSTRZYMUJE wznowienie (ochrona ogniw zostaje)",
     g.bramka_wznowienia(CFG, st, 41.0, 60.0, "nominal") is False)
test("bateria 37 C po zagotowaniu DALEJ trzyma (zatrzask, prog wznowienia to 36)",
     g.bramka_wznowienia(CFG, st, 37.0, 60.0, "nominal") is False)
test("bateria 35,5 C gasi zatrzask i wznawiamy",
     g.bramka_wznowienia(CFG, st, 35.5, 60.0, "nominal") is True)

# ------------------------------------------------------- 2. terminate only stopped processes
print("\n2. SIGTERM po limicie czasu leci tylko w proces, ktory naprawde stoi")
p = subprocess.Popen(["sleep", "600"])
sprzataj.append(p)
time.sleep(0.3)
wpis = {"comm": "Python", "manual": False}


def stoi(pid, info=None):
    return g.wpis_stoi(str(pid), info if info is not None else wpis, *g.zatrzymane_teraz())


test("proces chodzacy: wpis_stoi() = False", stoi(p.pid) is False)
os.kill(p.pid, signal.SIGSTOP)
time.sleep(0.3)
test("po SIGSTOP: wpis_stoi() = True", stoi(p.pid) is True)
os.kill(p.pid, signal.SIGCONT)
time.sleep(0.3)
test("po SIGCONT (reczne wznowienie Pawla o 20:02): wpis_stoi() = False",
     stoi(p.pid) is False)
test("martwy pid nie liczy sie jako zatrzymany", stoi(999999) is False)

# Group case: leader runs, but a child in its group is stopped. Do not delete the
# entry, because it is the only note anyone can use to resume that child.
lider2, pgid2, dzieci2 = grupa_z_dzieckiem()
test("grupa testowa ma dziecko (inaczej ten scenariusz nic nie sprawdza)",
     len(dzieci2) >= 1, "dzieci: %s" % dzieci2)
if dzieci2:
    dziecko = dzieci2[0]
    os.kill(dziecko, signal.SIGSTOP)
    time.sleep(0.3)
    wpis_grupowy = {"comm": "ffmpeg", "manual": False, "pgid": pgid2}
    test("lider chodzi, dziecko z grupy stoi -> wpis ZOSTAJE (inaczej dziecko zostaje w T)",
         stoi(lider2.pid, wpis_grupowy) is True)
    os.kill(dziecko, signal.SIGCONT)
    time.sleep(0.3)
    test("cala grupa chodzi -> wpis do skasowania",
         stoi(lider2.pid, wpis_grupowy) is False)

# Expired filter: same arithmetic as the loop.
stary = {"since": g.now() - 60 * 60, "since_mono": time.monotonic() - 60 * 60,
         "mono_id": g._MONO_ID, "comm": "Python", "manual": False}
paused = {str(p.pid): stary}
limit_s = 45 * 60


def do_ubicia():
    return g.wpisy_przeterminowane(paused, limit_s, g.zatrzymane_teraz())


test("wpis starszy niz 45 min, ale proces CHODZI - nie ubijamy (to zabilo pomiar 20:27)",
     do_ubicia() == [], "do ubicia: %s" % do_ubicia())
test("...i ten sam wpis JEST na liscie do skasowania jako obudzony poza guardem",
     g.wpisy_nieaktualne(paused, g.zatrzymane_teraz()) == [str(p.pid)])
os.kill(p.pid, signal.SIGSTOP)
time.sleep(0.3)
test("ten sam wpis, gdy proces NAPRAWDE stoi - ubijamy (bezpiecznik dalej dziala)",
     do_ubicia() == [str(p.pid)], "do ubicia: %s" % do_ubicia())
test("...i wtedy NIE kasujemy go jako nieaktualnego",
     g.wpisy_nieaktualne(paused, g.zatrzymane_teraz()) == [])
os.kill(p.pid, signal.SIGCONT)

# A failed `ps` measurement (None) must not trigger either execution path. Empty output
# used to mean "nothing is stopped", so the guard would delete a frozen job's entry and
# leave it in state T without a note.
os.kill(p.pid, signal.SIGSTOP)
time.sleep(0.3)
test("ps niedostepny -> nie kasujemy zadnego wpisu", g.wpisy_nieaktualne(paused, None) == [])
test("ps niedostepny -> nie ubijamy niczego", g.wpisy_przeterminowane(paused, limit_s, None) == [])
_stary_run = g.run
g.run = lambda *a, **k: ""
try:
    test("zatrzymane_teraz() przy pustym wyniku ps zwraca None, nie 'nic nie stoi'",
         g.zatrzymane_teraz() is None)
finally:
    g.run = _stary_run
os.kill(p.pid, signal.SIGCONT)

# ------------------------------------------------- 3. limiter lock knows the whole group
print("\n3. limiter nie budzi grupy, w ktorej guard cos zamrozil")
lider, grupa, dzieci = grupa_z_dzieckiem()
test("grupa testowa ma dziecko (tak wyglada ffmpeg pod safe-run)", len(dzieci) >= 1,
     "dzieci: %s" % dzieci)
DZIECKO = dzieci[0] if dzieci else lider.pid

stan = os.path.join(BASE, "state.json")
json.dump({"paused": {str(DZIECKO): {"pgid": grupa, "comm": "ffmpeg"}}},
          open(stan, "w"))
test("guard zamrozil DZIECKO z naszej grupy -> limiter widzi pauze i NIE budzi",
     sr.guard_paused(lider.pid) is True,
     "przed poprawka bylo False i limiter robil killpg(SIGCONT)")

json.dump({"paused": {str(DZIECKO): {"pgid": grupa + 4242, "comm": "ffmpeg"}}},
          open(stan, "w"))
test("cudza grupa nie blokuje naszego limitera", sr.guard_paused(lider.pid) is False)

json.dump({"paused": {str(lider.pid): {"pgid": grupa, "comm": "sleep"}}}, open(stan, "w"))
test("guard zamrozil lidera wprost - dalej dziala jak przedtem",
     sr.guard_paused(lider.pid) is True)

# Live foreign process with a recorded pgid equal to ours: the note lies, the system
# tells the truth. Without checking `os.getpgid(entry)`, the limiter would wait forever
# for an unrelated guard decision and leave its own job in state T.
obcy = subprocess.Popen(["sleep", "600"], start_new_session=True)
sprzataj.append(obcy)
time.sleep(0.3)
json.dump({"paused": {str(obcy.pid): {"pgid": grupa, "comm": "ffmpeg"}}}, open(stan, "w"))
test("zywy obcy proces z cudzym zapisanym pgid nie blokuje limitera",
     sr.guard_paused(lider.pid) is False)

json.dump({"paused": {}}, open(stan, "w"))
test("nic nie zamrozone - limiter pracuje normalnie",
     sr.guard_paused(lider.pid) is False)

# Dead entry plus recycled group number cannot hang the limiter forever.
json.dump({"paused": {"999999": {"pgid": grupa, "comm": "ffmpeg"}}}, open(stan, "w"))
test("wpis po nieistniejacym procesie nie blokuje limitera (recykling pgid)",
     sr.guard_paused(lider.pid) is False)

# Stale snapshot means "nobody can decide"; keep that rule intact.
json.dump({"paused": {str(DZIECKO): {"pgid": grupa}}}, open(stan, "w"))
os.utime(stan, (time.time() - 600, time.time() - 600))
test("martwy demon (migawka sprzed 10 min) nie trzyma zadania zamrozonego",
     sr.guard_paused(lider.pid) is False)

sprzatnij()
print("\nWYNIK: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
