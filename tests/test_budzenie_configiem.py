#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Przelacznik ochrony musi dzialac od razu, a nie po pelnym takcie petli.

Zglosil Pawel 03.08.2026: "switch pause job / watch only dziala strasznie wolno".
Przyczyna znaleziona w kodzie: przerywalna drzemka demona budzila sie na flage stopu,
na plik-rozkaz `command` i na zmiane `awake.json` — ale NIE na zmiane `config.json`.
A przelacznik ochrony (`dry_run`) idzie wlasnie configiem, bo pasek pisze go przez
`GuardCfg.set`. Jako jedyna reczna akcja nie mial wiec sciezki na wybudzenie petli
i czekal caly takt: przy suwaku interwalu ustawionym na 30 s wygladalo to jak
zawieszony przelacznik.

Ten test NIE czyta kodu ani logu w poszukiwaniu napisow — mierzy CZAS reakcji
prawdziwego demona z interwalem ustawionym na 20 s. Przed poprawka reakcja przychodzi
po ~20 s, po poprawce ponizej sekundy.

Demon dziala w izolacji (TG_BASE) i w trybie obserwacji, wiec nie dotyka procesow
uzytkownika. Nie dotyka prawdziwego ~/.coffee-paladin.

Uruchomienie:  python3 tests/test_budzenie_configiem.py
"""
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-budzenie-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"

INTERWAL = 20.0          # duzy, zeby roznica miedzy "od razu" a "po takcie" byla jednoznaczna
PROG_SZYBKO = 5.0        # z ogromnym zapasem ponizej INTERWAL, a i tak 4x powyzej realnej reakcji

wyniki = []
DZIECI = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


def plik(n):
    return os.path.join(BASE, n)


def zapisz_config(**klucze):
    d = {"dry_run": True, "poll_seconds": INTERWAL, "notify": False, "sound": False,
         "soc_pause_c": 200, "soc_kill_c": 250, "batt_pause_c": 200,
         "keep_awake_auto": False, "fan_check": False}
    d.update(klucze)
    with io.open(plik("config.json"), "w", encoding="utf-8") as f:
        json.dump(d, f)


def log_tekst():
    try:
        return io.open(plik("guard.log"), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def czekaj_na(warunek, ile=40.0, krok=0.2):
    koniec = time.time() + ile
    while time.time() < koniec:
        if warunek():
            return True
        time.sleep(krok)
    return False


print("=== demon z interwalem %d s ===" % INTERWAL)
zapisz_config()
demon = subprocess.Popen([sys.executable, os.path.join(SRC, "guard.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         env=dict(os.environ, TG_BASE=BASE, TG_LANG="en"))
DZIECI.append(demon)

test("1. demon wystartowal", czekaj_na(lambda: os.path.exists(plik("status.json"))),
     "brak status.json po 40 s")

# Czekamy, az petla wejdzie w drzemke po pierwszym pelnym takcie — inaczej mierzylibysmy
# resztke pierwszego przebiegu zamiast reakcji na zmiane configu.
time.sleep(3.0)

print("\n=== przelacznik ochrony: dry_run true -> false ===")
t0 = time.time()
zapisz_config(dry_run=False)
zauwazyl = czekaj_na(lambda: "CONFIG CHANGED" in log_tekst(), ile=INTERWAL + 15)
reakcja = time.time() - t0

test("2. demon W OGOLE zauwazyl zmiane configu", zauwazyl,
     "brak wpisu CONFIG CHANGED po %.0f s" % (INTERWAL + 15))
test("3. zareagowal SZYBCIEJ niz jeden takt petli (%.1f s < %.0f s)" % (reakcja, PROG_SZYBKO),
     zauwazyl and reakcja < PROG_SZYBKO,
     "reakcja po %.1f s - petla czekala na pelny takt (%.0f s)" % (reakcja, INTERWAL))
test("4. ...i faktycznie przelaczyl sie w tryb ochrony",
     czekaj_na(lambda: json.load(io.open(plik("status.json"),
                                         encoding="utf-8")).get("dry_run") is False, ile=10),
     "status.json dalej melduje tryb obserwacji")

print("\n=== przypadek przeciwny: BEZ zmiany configu petla nie krecci sie w kolko ===")
# Gdyby wybudzanie bylo zepsute w druga strone (np. porownanie zawsze rozne), demon
# przelatywalby takty non stop i palil CPU. Mierzymy, ile taktow robi w 6 sekund:
# przy interwale 20 s powinien nie zrobic ANI JEDNEGO nowego.
mtime_przed = os.path.getmtime(plik("status.json"))
time.sleep(6.0)
mtime_po = os.path.getmtime(plik("status.json"))
test("5. bez zmiany configu status NIE jest przepisywany co chwile",
     mtime_po == mtime_przed,
     "status.json zmienil sie w ciagu 6 s przy interwale %.0f s - petla nie spi" % INTERWAL)

print("\n=== sprzatanie ===")
demon.send_signal(signal.SIGTERM)
try:
    demon.wait(timeout=40)
except subprocess.TimeoutExpired:
    demon.kill()
    demon.wait(timeout=10)
test("6. demon zamknal sie czysto", os.path.exists(plik("clean_stop")),
     "brak clean_stop")

for p in DZIECI:
    if p.poll() is None:
        p.kill()
shutil.rmtree(BASE, ignore_errors=True)

print("\n%d/%d" % (sum(wyniki), len(wyniki)))
sys.exit(0 if all(wyniki) else 1)
