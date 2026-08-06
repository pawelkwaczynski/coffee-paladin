#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wariant A (decyzja Pawla 06.08.2026) + wygaszanie keep-awake (TODO 8).

WARIANT A: systemowe demony indeksowania (corespotlightd i spol.) zostaja NIETYKALNE
dla pauzy i ubicia (lista never jest swieta), ale ida OSOBNYM kanalem do degradacji
na E-cores. Powod: corespotlightd grzal do 215% CPU cala noc jako "untouchable"
(165 wpisow logu, 04/05.08.2026), a AGENTS.md slusznie zakazuje oslabiania never.

WYGASZANIE: po zejsciu ostatniego ciezkiego zadania czuwanie (caffeinate) trzyma
jeszcze keep_awake_hold_s sekund. Bez tego przerwa miedzy plikami kolejki zwalniala
blokade snu (45-59 przelaczen na dobe), a Mac z agresywnym usypianiem moglby zasnac
w srodku nocnej kolejki. Upal ma pierwszenstwo: poziom >=2 zwalnia NATYCHMIAST.

Uruchomienie:  python3 tests/test_wariant_a.py
Na kodzie sprzed zmiany test pada juz na imporcie (_DEMOTE_ONLY nie istnieje).
Nie dotyka prawdziwego ~/.coffee-paladin - pracuje w katalogu tymczasowym.
"""
import importlib.machinery
import os
import signal
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD_SRC = os.environ.get("TG_TEST_GUARD") or os.path.join(SRC, "guard.py")
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", GUARD_SRC).load_module()

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


def dziecko():
    p = subprocess.Popen(["sleep", "300"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dzieci.append(p)
    return p


logi = []
stary_log, stary_notify, stary_play = g.log, g.notify, g.play_sound
g.log = lambda *a, **k: logi.append(a[0] if a else "")
g.notify = lambda *a, **k: None
g.play_sound = lambda *a, **k: None

try:
    # ------------------------------------------------ 1. kanal demote-only w pick_targets
    print("1. pick_targets: systemowy demon NIE jest celem pauzy, JEST kandydatem do demote")
    cfg = g.load_cfg()
    cfg["dry_run"] = False
    cfg["cpu_min_percent"] = 10.0
    # (pid, ppid, cpu, comm) - pidy zmyslone, pick_targets nie sygnalizuje
    procs = [(11111, 1, 200.0, "corespotlightd"),
             (22222, 1, 150.0, "bluetoothd"),          # never, ale NIE system_demote
             (33333, 1, 120.0, "spotlightknowledged.updater")]
    cele = g.pick_targets(cfg, procs, {})
    pidy_celow = {c[0] for c in cele}
    demote_pidy = {d[0] for d in g._DEMOTE_ONLY}
    test("corespotlightd poza celami pauzy", 11111 not in pidy_celow)
    test("corespotlightd w kanale demote-only", 11111 in demote_pidy)
    test("substring: spotlightknowledged.updater tez w kanale", 33333 in demote_pidy)
    test("bluetoothd nietykalny CALKOWICIE (ani pauza, ani demote)",
         22222 not in pidy_celow and 22222 not in demote_pidy)

    # snapshot niesie kanal jako 14. element (integracja na zywym systemie)
    mig = g.snapshot(cfg)
    test("snapshot zwraca 14 elementow, ostatni to lista", len(mig) == 14
         and isinstance(mig[13], list), repr(len(mig)))

    # ------------------------------------------------ 2. do_demote na kanale demote-only
    print("2. do_demote: wlasny proces schodzi na E-cores i wraca; cudzy pid nie klamie")
    cfg["demote_cpu_percent"] = 10.0
    cfg["demote_after_minutes"] = 0
    cfg["demote_above_c"] = 10.0
    p = dziecko()
    st = {"paused": {}, "demoted": [], "demoted_info": {}}
    hist = {}
    g.do_demote(cfg, st, [(p.pid, 100.0, "sleep", None)], hist, soc_t=50.0)
    test("wlasny proces zdegradowany (taskpolicy rc=0)", p.pid in st["demoted"])
    test("nazwa w demoted_info (widoczna w status.json)",
         st["demoted_info"].get(str(p.pid), {}).get("comm") == "sleep")
    g.do_promote(cfg, st, hist, soc_t=20.0)
    test("po ostygnieciu powrot na P-cores", p.pid not in st["demoted"])

    # pid, ktorego taskpolicy nie przyjmie (pid 1 = launchd, cudzy wlasciciel)
    st2 = {"paused": {}, "demoted": [], "demoted_info": {}}
    logi[:] = []
    g.do_demote(cfg, st2, [(1, 100.0, "launchd", None)], {}, soc_t=50.0)
    test("cudzy proces: NIE wpisany do demoted (log nie klamie)", 1 not in st2["demoted"])
    test("cudzy proces: jedna linia DEMOTE failed",
         sum(1 for m in logi if "DEMOTE failed" in str(m)) == 1, repr(logi))
    logi[:] = []
    g.do_demote(cfg, st2, [(1, 100.0, "launchd", None)], {}, soc_t=50.0)
    test("ponowienie wyciszone (zbior pominietych)",
         not any("DEMOTE failed" in str(m) for m in logi))
    g._demote_nie_da_sie.clear()

    # ------------------------------------------------ 3. wygaszanie keep-awake
    print("3. keep-awake: przerwa miedzy plikami NIE zwalnia snu; upal zwalnia NATYCHMIAST")
    cfg["keep_awake_auto"] = True
    cfg["keep_awake_display"] = False
    cfg["keep_awake_hold_s"] = 3600
    cfg["sound"] = False
    zadanie = [(999999, 300.0, "ffmpeg", None)]

    trzyma = g.keep_awake_update(cfg, zadanie, lvl=0)
    test("ciezkie zadanie + chlodno = czuwanie wstaje", trzyma is True)
    trzyma = g.keep_awake_update(cfg, [], lvl=0)
    test("zadanie znika, hold trwa = czuwanie NIE pada", trzyma is True)
    trzyma = g.keep_awake_update(cfg, [], lvl=2)
    test("upal w trakcie holdu = czuwanie pada NATYCHMIAST", trzyma is False)

    # hold=0 przywraca stare zachowanie: stop od razu po zejsciu zadania
    cfg["keep_awake_hold_s"] = 0
    g.keep_awake_update(cfg, zadanie, lvl=0)
    trzyma = g.keep_awake_update(cfg, [], lvl=0)
    test("hold=0: stop od razu (stare zachowanie)", trzyma is False)

    # hold nigdy nie WSZCZYNA czuwania - tylko przedluza zywe
    cfg["keep_awake_hold_s"] = 3600
    trzyma = g.keep_awake_update(cfg, [], lvl=0)
    test("hold nie wszczyna czuwania z niczego", trzyma is False)

finally:
    # czuwanie nie moze przezyc testu
    try:
        g.keep_awake_update({"keep_awake_auto": False, "keep_awake_hold_s": 0,
                             "sound": False}, [], lvl=3)
    except Exception:
        pass
    proc = g._caff.get("proc")
    if proc is not None and proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)
    for p in dzieci:
        try:
            os.kill(p.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            p.wait(timeout=5)
        except Exception:
            pass
    g.log, g.notify, g.play_sound = stary_log, stary_notify, stary_play

print("\n%d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
