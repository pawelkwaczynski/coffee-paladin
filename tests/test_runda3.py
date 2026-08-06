#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runda przegladu 3 (05.08.2026): piec zastanych slabosci + widocznosc klampu configu.

1. STARTOWE WZNOWIENIE BEZ POMIARU. Restart demona (aktualizacja, kickstart -k) robil
   `do_resume("guard startup")` ZANIM cokolwiek zmierzyl - gorace zadanie dostawalo
   ~15 s pelnej pary przy chipie nad progiem. Lek: ta sama `bramka_wznowienia`,
   ktorej uzywa petla, stoi teraz przed startowym wznowieniem.

2. OKNO SIGSTOP -> save_state. Zapis stanu szedl PO sygnale: demon ubity w tym oknie
   zostawial proces zamrozony bez wpisu - czyli w stanie T na zawsze. Lek: wpis-intencja
   na dysku PRZED sygnalem, kasowany gdy sygnal sie nie uda (ESRCH/EPERM).

3. SIGTERM PO NIESWIEZEJ MIGAWCE. `ps` z poczatku cyklu ma kilkanascie sekund; reczny
   `kill -CONT` w srodku cyklu znaczyl SIGTERM w proces chodzacy pelna para.
   Lek: re-check `wpis_stoi` w `do_terminate` tuz przed strzalem; nieudany pomiar
   (`None`) wstrzymuje egzekucje w calosci.

4. `load_state` UFAL FORMATOWI. `paused` jako lista (stary format) albo klucz nie-liczba
   dawaly crashloop przy starcie, z ktorego KeepAlive restartuje demona w ten sam mur.
   Lek: normalizacja typow z logiem, zly fragment wyciety, reszta stanu zostaje.

5. JEDEN ZEPSUTY WPIS OSLEPIAL LIMITER. W `safe-run.guard_paused` nienumeryczny `pgid`
   lecial do zewnetrznego `except` i CALA funkcja mowila "nic nie stoi" - limiter budzil
   grupe, ktora bezpiecznik przed chwila zamrozil. Lek: lokalna oslona, pomijamy tylko
   wadliwy wpis. Plus: bezposrednie trafienie pid waliduje grupe (pid-reuse).

6. KLAMP CONFIGU BYL CICHYM ROZJAZDEM plik<->pamiec (05.08: plik mowil 100, demon
   chodzil na 98). Lek: powiadomienie + pole `config_corrections` w status.json.

Uruchomienie:  python3 tests/test_runda3.py
Mutacja (dowod, ze test umie zawiesc) - stary kod z HEAD~ musi oblac:
  git show <stary>:guard.py > /tmp/old_guard.py
  TG_TEST_GUARD=/tmp/old_guard.py python3 tests/test_runda3.py
Nie dotyka prawdziwego ~/.coffee-paladin - pracuje w katalogu tymczasowym.
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
    # ---------------------------------------------------------------- 1. startowa bramka
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

    # ---------------------------------------------------------------- 2. wpis-intencja
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

    # ---------------------------------------------------------------- 3. re-check w do_terminate
    print("3. do_terminate: strzal tylko w to, co NAPRAWDE stoi TERAZ")
    strzaly = []

    def sig_licznik(pid, pgid, s):
        strzaly.append((pid, s))
        return stary_sig(pid, pgid, s)

    # a) proces CHODZI (nikt go nie zatrzymal) -> wpis skasowany, zero sygnalow
    p_biega = dziecko()
    st = {"paused": {str(p_biega.pid): {"since": g.now(), "comm": "sleep", "pgid": None}},
          "demoted": [], "demoted_info": {}}
    g.sig = sig_licznik
    g.do_terminate(cfg, st, "test")
    test("chodzacy proces NIE dostal SIGTERM", not strzaly, repr(strzaly))
    test("wpis po chodzacym procesie skasowany", str(p_biega.pid) not in st["paused"])
    test("proces przezyl", p_biega.poll() is None)

    # b) `ps` pada -> zadnych decyzji, wpisy zostaja
    stary_run = g.run
    g.run = lambda *a, **k: ""
    st = {"paused": {str(p_biega.pid): {"since": g.now(), "comm": "sleep", "pgid": None}},
          "demoted": [], "demoted_info": {}}
    strzaly[:] = []
    wynik = g.do_terminate(cfg, st, "test")
    test("pusty ps: nic nie ubite, wpis zostaje",
         wynik is False and str(p_biega.pid) in st["paused"] and not strzaly)
    g.run = stary_run

    # c) proces STOI -> SIGTERM idzie (sciezka egzekucji dalej dziala)
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

    # zepsuty wpis (pgid nie-liczba) PRZED zdrowym wpisem o naszej grupie
    zapisz_stan({str(os.getpid()): {"pgid": "abc", "comm": "smiec"},
                 str(lider.pid): {"pgid": lider.pid, "comm": "bash"}})
    test("zepsuty wpis pominiety, PRAWDZIWA pauza grupy widoczna",
         sr.guard_paused(czlonek) is True)
    # pid-reuse: wpis o NASZYM pid, ale z cudza grupa - nie moze nas zatrzymac
    zapisz_stan({str(czlonek): {"pgid": 999999999, "comm": "duch"}})
    test("trafienie pid z obca grupa (pid-reuse) = nie stoi",
         sr.guard_paused(czlonek) is False)
    # wpis o naszym pid ze zgodna grupa - dalej dziala
    zapisz_stan({str(czlonek): {"pgid": lider.pid, "comm": "bash"}})
    test("trafienie pid ze zgodna grupa = stoi", sr.guard_paused(czlonek) is True)
    try:
        os.remove(os.path.join(sr.BASE, "state.json"))
    except OSError:
        pass

    # ---------------------------------------------------------------- 6. rate-limit + klamp
    print("6. untouchable raz na godzine; klamp configu widoczny w statusie")
    zegar = [1000000.0]
    stary_now = g.now
    g.now = lambda: zegar[0]
    g._NIETYKALNI_PODCIAG.clear()
    logi[:] = []
    g._loguj_nietykalny_podciag("corespotlightd", "spotlight", 200.0)
    zegar[0] += 700          # 11:40 pozniej - stary kod (10 min) juz by logowal
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
