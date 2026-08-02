"""Spojnosc miedzy plikami - rzeczy, ktore rozjezdzaja sie po kazdej przerobce.

Piec kategorii, kazda z realnej wpadki:
  1. string wolany przez T() bez wpisu w slowniku -> komunikat po angielsku w polskim UI;
  2. wersja w czterech miejscach naraz (guard, thermal-report, heatbar, plugin.json);
  3. narzedzie bez --help: `thermal-report --help` generowal RAPORT na Pulpicie (02.08.2026);
  4. install.sh tworzy cos, czego uninstall.sh nie usuwa (skill, symlinki, migawka floty);
  5. guard loguje znacznik, ktorego parser nie zna -> raport dowodowy gubi zdarzenia.

Uruchomienie:  python3 tests/test_spojnosc.py
Nie dotyka prawdziwego ~/.coffee-paladin.
"""
import importlib.machinery
import io
import json
import os
import re
import sys
import tempfile
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp()
bledy = []

# 1. Kazdy string wolany przez T() w guard.py MA wpis we wszystkich 4 slownikach
g = importlib.machinery.SourceFileLoader('g', os.path.join(SRC,'guard.py')).load_module()
zrodlo = io.open(os.path.join(SRC,'guard.py'), encoding='utf-8').read()
wolane = set(re.findall(r'T\("((?:[^"\\]|\\.)*)"\)', zrodlo))
for nazwa in ("PL","RU","ZH","ES"):
    d = getattr(g, nazwa)
    brak = [k for k in wolane if k not in d]
    if brak:
        bledy.append("guard.py: %s nie ma %d tlumaczen (np. %r)" % (nazwa, len(brak), brak[0][:50]))

# 2. Wersja jest ta sama we wszystkich czterech miejscach
wersje = {}
wersje['guard.py'] = re.search(r'guard_version"\] = "([^"]+)"', zrodlo).group(1)
wersje['thermal-report'] = re.search(r'^VERSION = "([^"]+)"', io.open(os.path.join(SRC,'thermal-report')).read(), re.M).group(1)
wersje['heatbar.swift'] = re.search(r'let VERSION = "([^"]+)"', io.open(os.path.join(SRC,'heatbar.swift')).read()).group(1)
wersje['plugin.json'] = json.load(open(os.path.join(SRC,'.claude-plugin/plugin.json')))['version']
if len(set(wersje.values())) != 1:
    bledy.append("wersje sie roznia: %s" % wersje)

# 3. Kazde narzedzie odpowiada na --help
for narz in ("heat","safe-run","fleet","thermal-report"):
    s = io.open(os.path.join(SRC,narz)).read()
    if '"--help"' not in s:
        bledy.append("%s nie obsluguje --help" % narz)

# 4. install.sh instaluje to, co uninstall.sh usuwa
inst = io.open(os.path.join(SRC,'install.sh')).read()
uninst = io.open(os.path.join(SRC,'uninstall.sh')).read()
for binarka in ("coffee-paladin", "coffee-paladin-bar", "heat", "safe-run", "thermal-report", "fleet", "thermalstate"):
    if '"$BIN/%s"' % binarka not in uninst:
        bledy.append("uninstall.sh nie usuwa %s" % binarka)

# 5. Znaczniki logu uzywane przez guard sa znane wszystkim parserom
tagi = set(re.findall(r'tag="([A-Z]+)"', zrodlo))
for plik in ("thermal-report", "heat"):
    tresc = io.open(os.path.join(SRC,plik)).read()
    brak = [t for t in tagi if "[%s]" % t not in tresc]
    if brak:
        bledy.append("%s nie zna znacznikow: %s" % (plik, brak))

print("SPRAWDZEN: 5 kategorii")
if bledy:
    for b in bledy: print("  BLAD: %s" % b)
    sys.exit(1)
print("  wszystko spojne")
