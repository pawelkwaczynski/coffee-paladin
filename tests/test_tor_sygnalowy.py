#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the signal path on live processes: sig / do_pause / do_resume / do_terminate.

Coverage mutation found that none of these four functions appeared by name in tests,
even though they do the guard's actual work. Untested contracts included:
  * whether `dry_run` really blocks SIGSTOP, not just logs,
  * whether a manually frozen job avoids SIGTERM after a threshold breach,
  * whether failed `killpg` falls back to `kill` on the pid,
  * whether SIGKILL has 20 s grace after SIGTERM,
  * whether failed SIGCONT does not remove the state entry.

Check the real effect in `ps` (state T/R), not log text. "PAUZA" in the log means
nothing until the process is actually stopped.

Modeled after test_demote_promote.py.
Run with:  python3 tests/test_tor_sygnalowy.py
Does not touch the real ~/.coffee-paladin. All test processes are cleaned up.
"""
import importlib.machinery
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-sygnaly-")
os.environ["TG_BASE"] = BASE
os.environ.setdefault("TG_LANG", "en")

g = importlib.machinery.SourceFileLoader("sg_guard", os.path.join(SRC, "guard.py")).load_module()
g.notify = lambda *a, **k: None          # No system notifications in the test.

wyniki = []
DZIECI = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


def odpal(wlasna_grupa=True):
    """Start a live cheap process; `yes` burns CPU so load effects are visible."""
    p = subprocess.Popen(["yes"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=wlasna_grupa)
    DZIECI.append(p)
    time.sleep(0.25)
    return p


def stan(pid):
    """Return kernel process state: T/TN = stopped, R/S = running, '' = dead."""
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                         capture_output=True, text=True).stdout.strip()
    return out


def stoi(pid):
    return stan(pid).startswith("T")


def zyje(pid):
    """Return whether pid is live, treating zombies ('Z') as dead.

    Without this distinction, the test treated a killed process as live and fooled itself.
    """
    s_ = stan(pid)
    return bool(s_) and not s_.startswith("Z")


def swiezy_stan():
    return {"paused": {}, "reczna_pauza": False}


def cel(p, cpu=95.0, comm="yes"):
    return (p.pid, cpu, comm, os.getpgid(p.pid))


CFG = g.load_cfg()
CFG["dry_run"] = False

print("=== sig(): realny skutek, nie log ===")
p = odpal()
test("1. proces startuje i biegnie", not stoi(p.pid) and zyje(p.pid), "stat=%r" % stan(p.pid))
test("2. sig(SIGSTOP) zwraca 0", g.sig(p.pid, os.getpgid(p.pid), signal.SIGSTOP) == 0)
time.sleep(0.25)
test("3. ...i proces NAPRAWDE stoi (ps mowi T)", stoi(p.pid), "stat=%r" % stan(p.pid))
g.sig(p.pid, os.getpgid(p.pid), signal.SIGCONT)
time.sleep(0.25)
test("4. sig(SIGCONT) naprawde go wznawia", not stoi(p.pid), "stat=%r" % stan(p.pid))

# Failed killpg falls back to the pid itself.
test("5. przy nieistniejacej grupie sig() spada na kill(pid) i dziala",
     g.sig(p.pid, 999999, signal.SIGSTOP) == 0 and (time.sleep(0.25) or stoi(p.pid)),
     "stat=%r" % stan(p.pid))
g.sig(p.pid, None, signal.SIGCONT)
test("6. martwy pid zwraca errno, nie zero",
     g.sig(999998, None, signal.SIGSTOP) != 0)

print("\n=== do_pause(): dry_run MUSI blokowac sygnal ===")
p2 = odpal()
st = swiezy_stan()
cfg_dry = dict(CFG)
cfg_dry["dry_run"] = True
g.do_pause(cfg_dry, st, [cel(p2)], "test")
time.sleep(0.25)
test("7. dry_run: proces NIE zostal zatrzymany", not stoi(p2.pid), "stat=%r" % stan(p2.pid))
test("8. dry_run: nic nie trafilo do stanu", not st["paused"])

st = swiezy_stan()
g.do_pause(CFG, st, [cel(p2)], "test")
time.sleep(0.25)
test("9. bez dry_run: proces stoi", stoi(p2.pid), "stat=%r" % stan(p2.pid))
test("10. ...i jest zapisany w stanie z pgid", str(p2.pid) in st["paused"]
     and st["paused"][str(p2.pid)].get("pgid") == os.getpgid(p2.pid))
test("11. drugie wywolanie nie dubluje wpisu",
     (g.do_pause(CFG, st, [cel(p2)], "test") or True) and len(st["paused"]) == 1)

print("\n=== do_resume(): wznawia i czysci stan ===")
g.do_resume(CFG, st, "test")
time.sleep(0.3)
test("12. proces biegnie po wznowieniu", not stoi(p2.pid), "stat=%r" % stan(p2.pid))
test("13. stan pauz jest pusty", not st["paused"])

print("\n=== do_terminate(): reczne zamrozenie jest NIETYKALNE ===")
p3 = odpal()
st = swiezy_stan()
g.do_pause(CFG, st, [cel(p3)], "reczne", manual=True)
time.sleep(0.25)
test("14. reczna pauza dziala", stoi(p3.pid) and st["paused"][str(p3.pid)].get("manual"))
g.do_terminate(CFG, st, "prog krytyczny")
time.sleep(0.4)
test("15. do_terminate NIE ubija recznie zamrozonego zadania", zyje(p3.pid),
     "proces zginal - to cios w plecy uzytkownika")
test("16. ...i zostawia go w stanie", str(p3.pid) in st["paused"])
g.do_resume(CFG, st, "sprzatanie")

print("\n=== do_terminate(): dry_run i realne ubicie ===")
p4 = odpal()
st = swiezy_stan()
g.do_pause(CFG, st, [cel(p4)], "goraco")
time.sleep(0.2)
g.do_terminate(cfg_dry, st, "test dry")
time.sleep(0.3)
test("17. dry_run: zadanie zyje mimo 'ubicia'", zyje(p4.pid), "stat=%r" % stan(p4.pid))

p5 = odpal()
st = swiezy_stan()
g.do_pause(CFG, st, [cel(p5)], "goraco")
time.sleep(0.2)
t0 = time.time()
g.do_terminate(CFG, st, "prog krytyczny")
trwalo = time.time() - t0
time.sleep(0.4)
test("18. realne ubicie: proces nie zyje", not zyje(p5.pid), "stat=%r" % stan(p5.pid))
test("19. ...i zniknal ze stanu", str(p5.pid) not in st["paused"])
test("20. SIGKILL dostal 20 s laski po SIGTERM (nie od razu)", trwalo >= 19.0,
     "do_terminate trwalo %.1f s - laska skrocona albo wyciety sleep" % trwalo)

print("\n=== przypadek przeciwny: proces spoza listy nie jest ruszany ===")
p6 = odpal()
st = swiezy_stan()
g.do_pause(CFG, st, [], "pusta lista celow")
time.sleep(0.2)
test("21. pusta lista celow: nikt nie zostal zatrzymany",
     not stoi(p6.pid) and not st["paused"], "stat=%r" % stan(p6.pid))

for p in DZIECI:
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGCONT)
    except OSError:
        pass
    try:
        p.kill()
        p.wait(timeout=5)
    except Exception:
        pass
shutil.rmtree(BASE, ignore_errors=True)

zywe = [p.pid for p in DZIECI if zyje(p.pid)]
test("22. test nie zostawil po sobie zadnego procesu", not zywe, "zyja: %s" % zywe)

ok = sum(wyniki)
print("\nWYNIK: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
