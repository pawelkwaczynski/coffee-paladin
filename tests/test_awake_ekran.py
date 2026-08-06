#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Czuwanie ekranu to OSOBNA decyzja od czuwania systemu — i tak samo ustepuje bezpiecznikowi.

`caffeinate -is` trzyma system, ale pozwala zgasic ekran. Do prezentacji, dashboardu albo
podgladu renderu potrzebne jest `-d`. Swiecacy panel to wiecej pradu i ciepla, wiec:
domyslnie WYLACZONE, a przy goracej maszynie ekran gasnie razem z reszta czuwania.

Test nie uruchamia prawdziwego `caffeinate` — podstawia atrape pod `subprocess.Popen`
i sprawdza, z JAKIMI argumentami demon by go wolal. Sprawdza tez przypadki przeciwne:
przelaczenie w locie musi wymienic proces (flag caffeinate nie da sie zmienic), a poziom
termiczny 2 musi zabic czuwanie niezaleznie od ustawienia ekranu.

Uruchomienie:  python3 tests/test_awake_ekran.py
"""
import importlib.machinery
import io
import os
import shutil
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-awake-ekran-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

zaliczone = wszystkie = 0
WOLANIA = []


def test(nazwa, warunek, detal=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s  -> %s" % (nazwa, detal))


class AtrapaProcesu:
    """Udaje zywy proces caffeinate: `poll()` None znaczy 'dziala'."""

    def __init__(self, argv):
        self.argv = argv
        self.zywy = True
        self.ubity = False
        self.zebrany = False

    def poll(self):
        return None if self.zywy else 0

    def terminate(self):
        self.zywy = False
        self.ubity = True

    def wait(self, timeout=None):
        self.zywy = False
        self.zebrany = True          # bez wait() zostaje zombie - to musi byc sprawdzone
        return 0

    def kill(self):
        self.zywy = False
        self.ubity = True


def atrapa_popen(argv, **kw):
    WOLANIA.append(list(argv))
    return AtrapaProcesu(list(argv))


g.subprocess.Popen = atrapa_popen
g.play_sound = lambda *a, **k: None          # bez dzwiekow w tescie


def reset():
    WOLANIA.clear()
    g._caff["proc"] = None
    g._caff.pop("display", None)


CIEZKIE = [(123, 500.0, "ffmpeg", None)]     # cokolwiek, co wyglada jak ciezkie zadanie


def cfg(**k):
    c = dict(g.DEFAULTS)
    c["keep_awake_auto"] = True
    c.update(k)
    return c


print("1. domyslnie ekran GASNIE (caffeinate -is)")
reset()
g.keep_awake_update(cfg(), CIEZKIE, 0, {})
test("caffeinate wolany dokladnie raz", len(WOLANIA) == 1, WOLANIA)
test("bez flagi -d", WOLANIA and WOLANIA[0] == ["caffeinate", "-is"], WOLANIA)

print("\n2. keep_awake_display=true -> ekran tez trzymany (-isd)")
reset()
g.keep_awake_update(cfg(keep_awake_display=True), CIEZKIE, 0, {})
test("flaga -d obecna", WOLANIA and WOLANIA[0] == ["caffeinate", "-isd"], WOLANIA)

print("\n3. przelaczenie W LOCIE wymienia proces")
reset()
g.keep_awake_update(cfg(), CIEZKIE, 0, {})                       # start bez ekranu
pierwszy = g._caff["proc"]
g.keep_awake_update(cfg(keep_awake_display=True), CIEZKIE, 0, {})  # user wlacza ekran
test("stary proces zostal ubity", pierwszy.ubity, "stary caffeinate przezyl zmiane")
test("...i ZEBRANY przez wait (inaczej zostaje zombie)", pierwszy.zebrany,
     "terminate bez wait - luka z przegladu 04.08")
test("nowy wolany z -isd", len(WOLANIA) == 2 and WOLANIA[1] == ["caffeinate", "-isd"], WOLANIA)
test("i ten nowy zyje", g.keep_awake_update(cfg(keep_awake_display=True), CIEZKIE, 0, {}) is True)

print("\n4. BEZ zmiany ustawienia proces NIE jest wymieniany")
reset()
g.keep_awake_update(cfg(keep_awake_display=True), CIEZKIE, 0, {})
g.keep_awake_update(cfg(keep_awake_display=True), CIEZKIE, 0, {})
g.keep_awake_update(cfg(keep_awake_display=True), CIEZKIE, 0, {})
test("jedno wolanie mimo trzech przebiegow petli", len(WOLANIA) == 1,
     "%d wolan - demon wymienia caffeinate co cykl" % len(WOLANIA))

print("\n5. PRZYPADEK PRZECIWNY: goraco = ekran gasnie razem z czuwaniem")
reset()
g.keep_awake_update(cfg(keep_awake_display=True), CIEZKIE, 0, {})
proc = g._caff["proc"]
wynik = g.keep_awake_update(cfg(keep_awake_display=True), CIEZKIE, 2, {})   # poziom 2 = pauza
test("czuwanie zwolnione przy poziomie 2", wynik is False, wynik)
test("caffeinate faktycznie ubity", proc.ubity, "proces przezyl przegrzanie")
test("...i zebrany przy stopie termicznym", proc.zebrany, "zostaje zombie po przegrzaniu")
test("i nie wystartowal ponownie", len(WOLANIA) == 1, WOLANIA)

print("\n6. PRZYPADEK PRZECIWNY: brak ciezkich zadan = zadnego czuwania")
reset()
wynik = g.keep_awake_update(cfg(keep_awake_display=True), [], 0, {})
test("nic nie wystartowalo", len(WOLANIA) == 0 and wynik is False, WOLANIA)

print("\n7. LICZNIKI: rozroznianie 'zadanie sie skonczylo' od 'za goraco'")
reset()
st = {}
g.keep_awake_update(cfg(), CIEZKIE, 0, st)          # start
g.keep_awake_update(cfg(), CIEZKIE, 2, st)          # stop PRZEZ TERMIKE
test("licznik czuwania zwolnionego przez cieplo = 1",
     st.get("stats", {}).get("awake_released_hot") == 1, st.get("stats"))

reset()
st2 = {}
g.keep_awake_update(cfg(), CIEZKIE, 0, st2)         # start
g.keep_awake_update(cfg(), [], 0, st2)              # stop, bo zadanie sie skonczylo
test("koniec zadania NIE liczy sie jako zasluga bezpiecznika",
     "awake_released_hot" not in st2.get("stats", {}), st2.get("stats"))

print("\n8. licznik() sam w sobie")
st3 = {}
g.licznik(st3, "pauses")
g.licznik(st3, "pauses")
g.licznik(st3, "kills")
test("zlicza narastajaco", st3["stats"]["pauses"] == 2 and st3["stats"]["kills"] == 1, st3)
test("zapisuje moment startu liczenia", isinstance(st3["stats"].get("since"), (int, float)),
     st3["stats"].get("since"))
test("nie wywala sie na zepsutym stanie", (g.licznik(None, "pauses") or True))

print("\n9. NAJWAZNIEJSZE: RECZNA sesja tez ustepuje bezpiecznikowi")
# Luka z przegladu 04.08: sekcje 1-8 sprawdzaly gorace tylko dla trybu automatycznego,
# wiec mutacja `(auto and lvl < 2) or manual` - czyli obejscie bezpiecznika dla sesji
# recznej - przechodzila 16/16. To najgrozniejszy mozliwy blad w tym produkcie.
import json
reset()
with io.open(os.path.join(BASE, "awake.json"), "w", encoding="utf-8") as f:
    json.dump({"mode": "forever"}, f)          # czlowiek wlaczyl czuwanie bezterminowe
c = dict(g.DEFAULTS)                            # UWAGA: keep_awake_auto WYLACZONY
c["keep_awake_auto"] = False
wynik = g.keep_awake_update(c, [], 0, {})       # zimno -> czuwanie ma dzialac
test("reczna sesja trzyma czuwanie, gdy chlodno", wynik is True and len(WOLANIA) == 1, WOLANIA)
proc = g._caff["proc"]
wynik = g.keep_awake_update(c, [], 2, {})       # goraco -> MUSI ustapic
test("reczna sesja USTEPUJE przy poziomie 2", wynik is False, wynik)
test("caffeinate recznej sesji faktycznie ubity", proc.ubity, "przezyl przegrzanie")
try:
    os.remove(os.path.join(BASE, "awake.json"))
except OSError:
    pass

shutil.rmtree(BASE, ignore_errors=True)
print("\n%d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
