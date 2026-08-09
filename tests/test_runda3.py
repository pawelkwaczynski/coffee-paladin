#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify review-round regressions and config-clamp visibility.

1. Startup resume without a measurement. Daemon restart via update or kickstart -k used
   `do_resume("guard startup")` before any measurement, giving a hot job ~15 s of full
   power above threshold. The same `bramka_wznowienia` used by the loop now gates startup
   resume.

2. SIGSTOP -> save_state window. State was saved after the signal; a daemon killed in
   that window left a frozen process with no entry, stuck in state T forever. The intent
   entry is now written to disk before the signal and removed if the signal fails
   with ESRCH/EPERM.

3. SIGTERM after a stale snapshot. `ps` from the start of a cycle can be several seconds
   old; manual `kill -CONT` mid-cycle meant SIGTERM to a process already running at full
   speed. `do_terminate` re-checks `wpis_stoi` just before firing, and a failed measurement
   (`None`) stops execution entirely.

4. `load_state` trusted format. `paused` as a list or a non-numeric key caused a startup
   crashloop. Type normalization logs and cuts the bad fragment while keeping the rest.

5. One bad entry blinded the limiter. In `safe-run.guard_paused`, a non-numeric `pgid`
   reached the outer `except`, so the whole function reported "nothing is stopped" and
   the limiter resumed a group the guard had just frozen. The fix is local shielding:
   skip only the bad entry, and validate direct pid hits by group to avoid pid reuse.

6. Config clamping was a silent file-memory split. The fix is a notification plus the
   `config_corrections` field in status.json.

Run with:  python3 tests/test_runda3.py
Mutation proof that the test can fail: old code from HEAD~ must fail:
  git show <stary>:guard.py > /tmp/old_guard.py
  TG_TEST_GUARD=/tmp/old_guard.py python3 tests/test_runda3.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import ast
import errno
import importlib.machinery
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import types

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD_SRC = os.environ.get("TG_TEST_GUARD") or os.path.join(SRC, "guard.py")
SAFERUN_SRC = os.environ.get("TG_TEST_SAFERUN") or os.path.join(SRC, "safe-run")
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", GUARD_SRC).load_module()
sr = importlib.machinery.SourceFileLoader("sr", SAFERUN_SRC).load_module()

zaliczone = wszystkie = 0
dzieci = []


def test(nazwa, warunek, szczegol=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s %s" % (nazwa, szczegol))


def dziecko(sesja=False):
    p = subprocess.Popen(["sleep", "300"], start_new_session=sesja,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dzieci.append(p)
    return p


def cfg_test():
    c = g.load_cfg()
    c["dry_run"] = False
    c["notify"] = False
    c["sound"] = False
    return c


try:
    # ---------------------------------------------------------------- 1. startup gate
    print("1. startowe wznowienie przechodzi przez bramka_wznowienia (AST na zywym kodzie)")
    drzewo = ast.parse(open(GUARD_SRC).read())
    main_fn = next(n for n in ast.walk(drzewo)
                   if isinstance(n, ast.FunctionDef) and n.name == "main")
    trafiony = False
    for n in ast.walk(main_fn):
        if isinstance(n, ast.If) and "guard startup" in ast.dump(n) \
                and "bramka_wznowienia" in ast.dump(n.test):
            trafiony = True
    test("do_resume('guard startup') stoi za bramka_wznowienia", trafiony)

    # ---------------------------------------------------------------- 2. intent entry
    print("2. do_pause: wpis w stanie ISTNIEJE juz w chwili sygnalu")
    cfg = cfg_test()
    logi = []
    stary_log, stary_notify = g.log, g.notify
    g.log = lambda *a, **k: logi.append(a[0] if a else "")
    g.notify = lambda *a, **k: None

    p = dziecko()
    st = {"paused": {}, "demoted": [], "demoted_info": {}}
    kolejnosc = []
    stary_sig = g.sig

    def sig_szpieg(pid, pgid, s):
        kolejnosc.append(str(pid) in st["paused"])
        return 0
    g.sig = sig_szpieg
    g.do_pause(cfg, st, [(p.pid, 99.0, "sleep", None)], "test")
    test("wpis byl na miejscu PRZED sygnalem", kolejnosc == [True], repr(kolejnosc))
    test("po udanej pauzie wpis zostaje", str(p.pid) in st["paused"])

    st2 = {"paused": {}, "demoted": [], "demoted_info": {}}
    g.sig = lambda pid, pgid, s: errno.EPERM
    g.do_pause(cfg, st2, [(p.pid, 99.0, "sleep", None)], "test")
    test("EPERM: wpis-intencja skasowany", str(p.pid) not in st2["paused"])
    test("EPERM: pid w zbiorze niedotykalnych", p.pid in g._nie_da_sie)
    g._nie_da_sie.clear()

    st3 = {"paused": {}, "demoted": [], "demoted_info": {}}
    g.sig = lambda pid, pgid, s: errno.ESRCH
    g.do_pause(cfg, st3, [(p.pid, 99.0, "sleep", None)], "test")
    test("ESRCH: wpis-intencja skasowany", str(p.pid) not in st3["paused"])
    g.sig = stary_sig

    # ---------------------------------------------------------------- 3. re-check in do_terminate
    print("3. do_terminate: strzal tylko w to, co NAPRAWDE stoi TERAZ")
    strzaly = []

    def sig_licznik(pid, pgid, s):
        strzaly.append((pid, s))
        return stary_sig(pid, pgid, s)

    # a) Process is running, nobody stopped it: entry removed, no signals.
    p_biega = dziecko()
    st = {"paused": {str(p_biega.pid): {"since": g.now(), "comm": "sleep", "pgid": None}},
          "demoted": [], "demoted_info": {}}
    g.sig = sig_licznik
    g.do_terminate(cfg, st, "test")
    test("chodzacy proces NIE dostal SIGTERM", not strzaly, repr(strzaly))
    test("wpis po chodzacym procesie skasowany", str(p_biega.pid) not in st["paused"])
    test("proces przezyl", p_biega.poll() is None)

    # b) `ps` fails: no decisions, entries stay.
    stary_run = g.run
    g.run = lambda *a, **k: ""
    st = {"paused": {str(p_biega.pid): {"since": g.now(), "comm": "sleep", "pgid": None}},
          "demoted": [], "demoted_info": {}}
    strzaly[:] = []
    wynik = g.do_terminate(cfg, st, "test")
    test("pusty ps: nic nie ubite, wpis zostaje",
         wynik is False and str(p_biega.pid) in st["paused"] and not strzaly)
    g.run = stary_run

    # c) Process is stopped: SIGTERM fires, so execution path still works.
    p_stoi = dziecko()
    os.kill(p_stoi.pid, signal.SIGSTOP)
    time.sleep(0.3)
    st = {"paused": {str(p_stoi.pid): {"since": g.now(), "comm": "sleep", "pgid": None}},
          "demoted": [], "demoted_info": {}}
    strzaly[:] = []
    stary_time = g.time
    g.time = types.SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic,
                                   time=time.time)
    g.do_terminate(cfg, st, "test")
    g.time = stary_time
    test("stojacy proces dostal SIGTERM",
         any(s == signal.SIGTERM for _, s in strzaly), repr(strzaly))
    g.sig = stary_sig

    # ---------------------------------------------------------------- 4. load_state
    print("4. load_state: normalizacja typow zamiast crashloopa")
    sciezka = g.STATE_PATH
    with open(sciezka, "w") as f:
        json.dump({"paused": [1, 2, 3], "demoted": {}, "demoted_info": []}, f)
    st = g.load_state()
    test("paused-lista (stary format) -> pusty dict", st["paused"] == {})
    test("demoted zlego typu -> pusta lista", st["demoted"] == [])
    test("demoted_info zlego typu -> pusty dict", st["demoted_info"] == {})
    with open(sciezka, "w") as f:
        json.dump({"paused": {"abc": {"comm": "x"}, "123": "zly", "456": {"comm": "y"}}}, f)
    st = g.load_state()
    test("klucz nie-liczba i wpis nie-dict wyciete, zdrowy wpis zostaje",
         list(st["paused"]) == ["456"], repr(st["paused"]))
    try:
        os.remove(sciezka)
    except OSError:
        pass

    # ---------------------------------------------------------------- 5. guard_paused
    print("5. safe-run.guard_paused: zepsuty wpis nie oslepia, pid-reuse nie zatrzymuje")
    lider = subprocess.Popen(
        ["bash", "-c", "sleep 300 & echo $!; wait"], start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    dzieci.append(lider)
    czlonek = int(lider.stdout.readline().strip())

    def zapisz_stan(paused):
        with open(os.path.join(sr.BASE, "state.json"), "w") as f:
            json.dump({"paused": paused}, f)

    # Broken entry (non-numeric pgid) before a healthy entry for our group.
    zapisz_stan({str(os.getpid()): {"pgid": "abc", "comm": "smiec"},
                 str(lider.pid): {"pgid": lider.pid, "comm": "bash"}})
    test("zepsuty wpis pominiety, PRAWDZIWA pauza grupy widoczna",
         sr.guard_paused(czlonek) is True)
    # pid reuse: entry for our pid but a foreign group must not stop us.
    zapisz_stan({str(czlonek): {"pgid": 999999999, "comm": "duch"}})
    test("trafienie pid z obca grupa (pid-reuse) = nie stoi",
         sr.guard_paused(czlonek) is False)
    # Entry for our pid with matching group still works.
    zapisz_stan({str(czlonek): {"pgid": lider.pid, "comm": "bash"}})
    test("trafienie pid ze zgodna grupa = stoi", sr.guard_paused(czlonek) is True)
    try:
        os.remove(os.path.join(sr.BASE, "state.json"))
    except OSError:
        pass

    # ---------------------------------------------------------------- 6. rate limit + clamp
    print("6. untouchable raz na godzine; klamp configu widoczny w statusie")
    zegar = [1000000.0]
    stary_now = g.now
    g.now = lambda: zegar[0]
    g._NIETYKALNI_PODCIAG.clear()
    logi[:] = []
    g._loguj_nietykalny_podciag("corespotlightd", "spotlight", 200.0)
    zegar[0] += 700          # 11:40 later; old 10 min code would already log.
    g._loguj_nietykalny_podciag("corespotlightd", "spotlight", 200.0)
    test("drugi wpis w tej samej godzinie wyciszony", len(logi) == 1, repr(len(logi)))
    zegar[0] += 3600
    g._loguj_nietykalny_podciag("corespotlightd", "spotlight", 200.0)
    test("po godzinie wolno znow", len(logi) == 2)
    g.now = stary_now
    g._NIETYKALNI_PODCIAG.clear()

    powiadomienia = []
    g.notify = lambda cfg, tytul, tresc, key="d": powiadomienia.append((key, tresc))
    with open(g.CFG_PATH, "w") as f:
        json.dump({"soc_pause_c": "goraco"}, f)
    g._ostatnio_odrzucone["v"] = []
    g.load_cfg()
    test("klamp: powiadomienie z trescia poprawki",
         any(k == "cfgclamp" and "soc_pause_c" in t for k, t in powiadomienia),
         repr(powiadomienia))
    test("klamp: lista korekt do statusu niepusta", bool(g._ostatnio_odrzucone["v"]))
    dane = g.status_write("nominal", 30.0, None, None, True, 80, 100, 0.5, 0, "",
                          [], {"paused": {}, "demoted_info": {}})
    test("status.json niesie config_corrections", bool(dane.get("config_corrections")))
    with open(g.CFG_PATH, "w") as f:
        json.dump({}, f)
    g.load_cfg()
    test("naprawiony plik czysci liste korekt", g._ostatnio_odrzucone["v"] == [])
    try:
        os.remove(g.CFG_PATH)
    except OSError:
        pass
    g.log, g.notify = stary_log, stary_notify

finally:
    for p in dzieci:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGCONT)
        except OSError:
            pass
        try:
            os.kill(p.pid, signal.SIGCONT)
        except OSError:
            pass
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL) if p.pid == os.getpgid(p.pid) \
                else os.kill(p.pid, signal.SIGKILL)
        except OSError:
            try:
                os.kill(p.pid, signal.SIGKILL)
            except OSError:
                pass
        try:
            p.wait(timeout=5)
        except Exception:
            pass

print("\n%d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
