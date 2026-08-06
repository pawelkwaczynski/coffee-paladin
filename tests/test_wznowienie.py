#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trzy defekty wznowienia, znalezione na ZYWYM Macu Pawla 04.08.2026.

Dzien wygladal tak: 15 pauz, ZERO wznowien, cztery zadania ubite SIGTERM-em.
Zaden test tego nie lapal, bo kazdy z trzech mechanizmow z osobna wygladal poprawnie.

1. BRAMKA WZNOWIENIA BRALA ZAKLADNIKA. Pauze wywolywal DOWOLNY czujnik, ale wznowienie
   blokowal KAZDY. Bateria stygnie kilka minut i przy dlugim kodowaniu trzyma ~37 C,
   wiec przy progach chipa 95/87 pauza WYWOLANA CHIPEM nie konczyla sie nigdy: chip
   schodzil do 71 C w 20 sekund, a bateria - trzy stopnie ponizej wlasnego progu 40 C,
   ktorego nigdy nie przekroczyla - trzymala zadanie w stanie T az do egzekucji.
   Lek: zatrzask per czujnik (zapala sie na wlasnym progu pauzy, gasnie na wlasnym
   progu wznowienia).

2. GUARD UFAL WLASNEJ NOTATCE, NIE SYSTEMOWI. Wpis w `paused` mowi tylko, ze kiedys
   poszedl SIGSTOP. Proces obudzony recznie (`kill -CONT`) albo przez duty-limiter
   safe-run pracowal pelna para, a jego wpis dalej sie postarzal - i po 45 minutach
   dostawal SIGTERM w polowie roboty. Tak zginal pomiar o 20:27, dwadziescia piec minut
   po tym, jak Pawel wznowil go recznie o 20:02.
   Lek: ubijamy tylko to, co `ps` pokazuje jako zatrzymane; reszte wpisow kasujemy.

3. BLOKADA LIMITERA PATRZYLA NA ZLY PID. `guard_paused(proc.pid)` pytalo o lidera grupy,
   a guard mrozi ten proces, ktory GRZEJE - czyli dziecko (ffmpeg). Odpowiedz brzmiala
   "nie, guard tego nie pauzowal", wiec mikro-pauza limitera konczyla sie
   `killpg(SIGCONT)` i budzila cala grupe razem z tym, co bezpiecznik przed chwila
   zamrozil. To dlatego ffmpeg "wznowil sie sam" o 19:42, a Python i 7zz puszczone
   nohupem zostaly w stanie T.
   Lek: pytanie o CALA GRUPE procesow, nie o goly pid.

Uruchomienie:  python3 tests/test_wznowienie.py
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
    """Lider + dziecko w JEDNEJ grupie procesow - tak wyglada zadanie pod safe-run.

    Nie da sie tego zlozyc dwoma Popenami: proces moze dolaczyc tylko do grupy
    z WLASNEJ sesji, a `start_new_session` daje kazdemu osobna. Robi to powloka:
    jest liderem sesji i grupy, a jej dzieci dziedzicza grupe.
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
    """Po tescie nie zostaje ANI JEDEN proces - takze dzieci powloki-lidera.

    Zabicie samego lidera zostawialo osierocone `sleep`, bo dzieci maja wlasne pidy.
    Sygnal idzie do CALEJ grupy, a przed nim SIGCONT: zatrzymany proces nie obsluzy
    SIGTERM-a, wiec bez wznowienia zostalby w pamieci na zawsze.
    """
    moja_grupa = os.getpgid(0)
    for p in sprzataj:
        try:
            pgid = os.getpgid(p.pid)
        except OSError:
            pgid = None
        # NIGDY do wlasnej grupy. Procesy startowane bez `start_new_session` siedza
        # w grupie testu, wiec `killpg` zabijalby takze sam test - i zabijal:
        # bateria zwracala rc=137 (SIGKILL) zamiast wyniku. Dokladnie ten gatunek
        # bledu, ktory ten plik testuje: sygnal grupowy trafia szerzej, niz sie wydaje.
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


# ---------------------------------------------------------------- 1. zatrzask czujnika
print("1. czujnik blokuje wznowienie tylko wtedy, gdy sam kazal pauzowac")
PAUZA_B, WZNOW_B = 40.0, 36.0          # bateria: progi Pawla
PAUZA_C, WZNOW_C = 95.0, 87.0          # chip: progi Pawla pod kolejke kompresji

st = {}
test("bateria 36,7 C (ponizej wlasnego progu 40) NIE blokuje - to jest ten defekt",
     g.zatrzask_czujnika(st, "_batt_hot", 36.7, PAUZA_B, WZNOW_B) is False,
     "zatrzask: %s" % st.get("_batt_hot"))
test("bateria 37,9 C (dzisiejszy szczyt) tez nie blokuje",
     g.zatrzask_czujnika(st, "_batt_hot", 37.9, PAUZA_B, WZNOW_B) is False)
test("bateria 39,9 C - dalej ponizej progu, dalej nie blokuje",
     g.zatrzask_czujnika(st, "_batt_hot", 39.9, PAUZA_B, WZNOW_B) is False)

# ...ale gdy bateria NAPRAWDE przekroczy swoj prog, histereza ma dzialac po staremu
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


# CALA BRAMKA - przez `bramka_wznowienia()`, czyli DOKLADNIE ta funkcje, ktora wykonuje
# demon. Wczesniej test mial wlasna kopie tego warunku i przechodzilby takze wtedy, gdyby
# ktos zepsul oryginal w petli (uwaga z recenzji, runda 2).
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

# dokladnie sytuacja z 19:42:38 -> 19:43
st = {}
test("w chwili pauzy (chip 95,2 / bateria 36,7) NIE wznawiamy",
     g.bramka_wznowienia(CFG, st, 36.7, 95.2, "nominal") is False)
test("20 sekund pozniej (chip 71,2 / bateria 36,6) WZNAWIAMY - przed poprawka NIE",
     g.bramka_wznowienia(CFG, st, 36.6, 71.2, "nominal") is True)
# a gdy bateria NAPRAWDE sie zagotuje, bramka ma trzymac tak jak dawniej
test("bateria 41 C przy zimnym chipie WSTRZYMUJE wznowienie (ochrona ogniw zostaje)",
     g.bramka_wznowienia(CFG, st, 41.0, 60.0, "nominal") is False)
test("bateria 37 C po zagotowaniu DALEJ trzyma (zatrzask, prog wznowienia to 36)",
     g.bramka_wznowienia(CFG, st, 37.0, 60.0, "nominal") is False)
test("bateria 35,5 C gasi zatrzask i wznawiamy",
     g.bramka_wznowienia(CFG, st, 35.5, 60.0, "nominal") is True)

# ------------------------------------------------------- 2. ubijamy tylko to, co stoi
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

# GRUPA: lider chodzi, ale dziecko z jego grupy stoi - wpisu kasowac NIE WOLNO,
# bo to jedyna notatka, przez ktora ktokolwiek moze to dziecko wznowic (uwaga z recenzji).
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

# filtr przeterminowanych - ta sama arytmetyka co w petli
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

# NIEUDANY POMIAR `ps` (None) nie moze uruchamiac zadnej z tych dwoch egzekucji.
# Przed poprawka pusty wynik znaczyl "nic nie stoi": guard skasowalby wpis zamrozonego
# zadania i zostawil je w stanie T bez notatki (uwaga z recenzji, runda 2).
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

# ------------------------------------------------- 3. blokada limitera zna cala grupe
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

# ZYWY, CUDZY proces z zapisanym pgid rownym naszemu: notatka klamie, system mowi prawde.
# Bez sprawdzenia `os.getpgid(wpis)` limiter czekalby w nieskonczonosc na decyzje guarda,
# ktora jego nie dotyczy - i zostawil WLASNE zadanie w stanie T (uwaga z recenzji, runda 2).
obcy = subprocess.Popen(["sleep", "600"], start_new_session=True)
sprzataj.append(obcy)
time.sleep(0.3)
json.dump({"paused": {str(obcy.pid): {"pgid": grupa, "comm": "ffmpeg"}}}, open(stan, "w"))
test("zywy obcy proces z cudzym zapisanym pgid nie blokuje limitera",
     sr.guard_paused(lider.pid) is False)

json.dump({"paused": {}}, open(stan, "w"))
test("nic nie zamrozone - limiter pracuje normalnie",
     sr.guard_paused(lider.pid) is False)

# MARTWY WPIS + recykling numeru grupy nie moze zawiesic limitera na zawsze
json.dump({"paused": {"999999": {"pgid": grupa, "comm": "ffmpeg"}}}, open(stan, "w"))
test("wpis po nieistniejacym procesie nie blokuje limitera (recykling pgid)",
     sr.guard_paused(lider.pid) is False)

# nieswieza migawka znaczy "nie ma komu decydowac" - ta zasada ma zostac nietknieta
json.dump({"paused": {str(DZIECKO): {"pgid": grupa}}}, open(stan, "w"))
os.utime(stan, (time.time() - 600, time.time() - 600))
test("martwy demon (migawka sprzed 10 min) nie trzyma zadania zamrozonego",
     sr.guard_paused(lider.pid) is False)

sprzatnij()
print("\nWYNIK: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
