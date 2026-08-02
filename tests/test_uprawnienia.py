#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dane paladyna nie moga byc czytelne dla innych kont na tym Macu.

Powod (02.08.2026): katalog danych powstawal z prawami 0755, a `config.json` 0644.
Na Macu z kilkoma kontami kazdy lokalny uzytkownik mogl przeczytac `ntfy_topic` -
czyli, jak mowi wlasna dokumentacja narzedzia, JEDYNE zabezpieczenie powiadomien:
kto zna temat, czyta cudze alerty i moze wysylac falszywe. W `managed/` leza
dodatkowo pelne linie polecen zadan (sciezki projektow, nazwy plikow).

Uruchomienie:  python3 tests/test_uprawnienia.py
Pracuje w katalogu tymczasowym - nie dotyka prawdziwego ~/.coffee-paladin.
"""
import importlib.machinery
import json
import os
import shutil
import stat
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

zaliczone = wszystkie = 0


def test(nazwa, warunek, szczegol=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s  -> %s" % (nazwa, szczegol))


def prawa(p):
    return stat.S_IMODE(os.stat(p).st_mode)


print("uprawnienia katalogu danych")

shutil.rmtree(BASE, ignore_errors=True)
g.ensure_dirs()
test("swiezy katalog danych: 0700", prawa(BASE) == 0o700, oct(prawa(BASE)))
test("swiezy managed/: 0700", prawa(g.MANAGED_DIR) == 0o700, oct(prawa(g.MANAGED_DIR)))

# istniejaca instalacja ze zlymi prawami musi zostac zaciesniona przy starcie
os.chmod(BASE, 0o755)
os.chmod(g.MANAGED_DIR, 0o755)
json.dump({"ntfy_topic": "sekret-123"}, open(g.CFG_PATH, "w"))
os.chmod(g.CFG_PATH, 0o644)
g.ensure_dirs()
test("stara instalacja: katalog zaciesniony do 0700", prawa(BASE) == 0o700, oct(prawa(BASE)))
test("stara instalacja: config zaciesniony do 0600", prawa(g.CFG_PATH) == 0o600, oct(prawa(g.CFG_PATH)))
test("config po zmianie praw nadal czytelny dla wlasciciela",
     json.load(open(g.CFG_PATH)).get("ntfy_topic") == "sekret-123")

for sciezka, opis in ((BASE, "katalog"), (g.CFG_PATH, "config.json")):
    test("%s: zero praw dla grupy i innych" % opis, not (prawa(sciezka) & 0o077),
         oct(prawa(sciezka)))

shutil.rmtree(BASE, ignore_errors=True)
print("\nWYNIK: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
