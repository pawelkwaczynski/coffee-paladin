"""Spojnosc miedzy plikami - rzeczy, ktore rozjezdzaja sie po kazdej przerobce.

Osiem kategorii, kazda z realnej wpadki:
  1. string wolany przez T() bez wpisu w slowniku -> komunikat po angielsku w polskim UI;
  2. wersja w czterech miejscach naraz (guard, thermal-report, heatbar, plugin.json);
  3. narzedzie bez --help: `thermal-report --help` generowal RAPORT na Pulpicie (02.08.2026);
  4. install.sh tworzy cos, czego uninstall.sh nie usuwa (skill, symlinki, migawka floty);
  5. guard loguje znacznik, ktorego parser nie zna -> raport dowodowy gubi zdarzenia.
  6. kopia pokolenia() w guard.py i thermal-report nie moze sie rozjechac;
  7. parser czasu w czterech narzedziach musi dawac ten sam wynik;
  8. bundle .app ma byc tworzony i usuwany symetrycznie, bez dotykania /Applications w tescie.

Uruchomienie:  python3 tests/test_spojnosc.py
Nie dotyka prawdziwego ~/.coffee-paladin.
"""
import ast
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

# 1. Kazdy string wolany przez T() MA wpis we wszystkich 4 slownikach - w KAZDYM
#    pliku z wlasnym slownikiem, nie tylko w guard.py. Sprawdzanie samego guarda bylo
#    dziura: brakujace tlumaczenia w thermal-report i fleet przechodzily bez slowa
#    (lista otwartych, pozycja 19), a AGENTS.md wymaga piatki EN/PL/RU/ZH/ES wszedzie.
#    Czytamy AST, nie regex: regex zwracal SUROWY tekst zrodla, wiec "\n## BATTERY\n"
#    wychodzilo jako backslash+n i nie pasowalo do klucza slownika, ktory ma prawdziwy
#    znak nowej linii. Pierwsza wersja tej kontroli zglosila z tego powodu 6 nieistniejacych
#    brakow. AST daje wartosc taka, jaka naprawde zobaczy T() - razem ze sklejaniem
#    sasiadujacych literalow i escape'ami.
def wolane_T(tekst):
    wynik = set()
    for w in ast.walk(ast.parse(tekst)):
        if (isinstance(w, ast.Call) and isinstance(w.func, ast.Name) and w.func.id == "T"
                and w.args and isinstance(w.args[0], ast.Constant)
                and isinstance(w.args[0].value, str)):
            wynik.add(w.args[0].value)
    return wynik


for plik in ("guard.py", "thermal-report", "fleet", "heat", "safe-run"):
    sciezka = os.path.join(SRC, plik)
    if not os.path.exists(sciezka):
        continue
    tresc = io.open(sciezka, encoding='utf-8').read()
    mod = importlib.machinery.SourceFileLoader(
        're_' + re.sub(r'\W', '_', plik), sciezka).load_module()
    if not all(hasattr(mod, n) for n in ("PL", "RU", "ZH", "ES")):
        continue                      # plik bez wlasnych slownikow
    wolane = wolane_T(tresc)
    for nazwa in ("PL", "RU", "ZH", "ES"):
        d = getattr(mod, nazwa)
        brak = sorted(k for k in wolane if k not in d)
        if brak:
            bledy.append("%s: %s nie ma %d tlumaczen (np. %r)"
                         % (plik, nazwa, len(brak), brak[0][:60]))
zrodlo = io.open(os.path.join(SRC, 'guard.py'), encoding='utf-8').read()

# 2. Wersja jest ta sama we wszystkich czterech miejscach
wersje = {}
wersje['guard.py'] = re.search(r'^GUARD_VERSION = "([^"]+)"', zrodlo, re.M).group(1)
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

# 4b. Bundle .app jest takim samym artefaktem instalacji jak binarki: jesli instalator
#     stworzy go w dwoch mozliwych lokalizacjach, deinstalator ma zabrac obie. Test jest
#     statyczny celowo - poprzednie kontrole instalatora odpalane na zywo zostawialy smieci
#     w prawdziwym HOME i wymagaly recznego sprzatania po nieudanym tescie.
if ('coffee-paladin.app' not in inst or 'APP_CONTENTS="$APP_BUNDLE/Contents"' not in inst
        or 'APP_MACOS="$APP_CONTENTS/MacOS"' not in inst
        or 'APP_RESOURCES="$APP_CONTENTS/Resources"' not in inst):
    bledy.append("install.sh nie tworzy struktury coffee-paladin.app/Contents")
if 'CFBundleExecutable' not in inst or 'CFBundleIdentifier' not in inst or 'LSUIElement' not in inst:
    bledy.append("install.sh nie zapisuje wymaganych kluczy Info.plist dla bundle")
if 'wersja_heatbar' not in inst or 'let VERSION = ' not in inst:
    bledy.append("install.sh nie czyta wersji bundle z heatbar.swift")
if 'tools/zrob_ikone.sh' not in inst or 'AppIcon.icns' not in inst:
    bledy.append("install.sh nie buduje AppIcon.icns z osobnego narzedzia")
if 'codesign -s - -f "$APP_BUNDLE"' not in inst:
    bledy.append("install.sh nie podpisuje calego bundle ad hoc")
if 'ln -s "$BAR_EXEC" "$BIN/coffee-paladin-bar"' not in inst:
    bledy.append("install.sh nie zostawia symlinka zgodnosciowego coffee-paladin-bar")
if '__BAR_EXEC__' not in io.open(os.path.join(SRC, 'pl.pawel.coffee-paladin-bar.plist')).read():
    bledy.append("LaunchAgent paska nie ma placeholdera __BAR_EXEC__")
for app in ('"/Applications/coffee-paladin.app"', '"$HOME/Applications/coffee-paladin.app"'):
    if app not in uninst:
        bledy.append("uninstall.sh nie usuwa bundle %s" % app)

# 5. Znaczniki logu uzywane przez guard sa znane wszystkim parserom.
#    ASERCJA BYLA "GREPEM PO ZRODLE": sprawdzala, czy napis "[PAUSE]" WYSTEPUJE w pliku -
#    a wiec przechodzila takze wtedy, gdy napis siedzial w komentarzu albo w martwym
#    kodzie, i wtedy, gdy parser byl zepsuty. Teraz karmimy parsery PRAWDZIWA linia
#    logu z kazdym znacznikiem i sprawdzamy, czy naprawde ja policzyly (przeglad, poz. 20).
tagi = sorted(set(re.findall(r'tag="([A-Z]+)"', zrodlo)))
try:
    import shutil as _sh5
    import tempfile as _tf5
    _t5 = _tf5.mkdtemp()
    os.environ["TG_BASE"] = _t5
    _dzis = __import__("time").strftime("%Y-%m-%d")
    with io.open(os.path.join(_t5, "guard.log"), "w", encoding="utf-8") as _f:
        for _tag in tagi:
            _f.write("%s 10:00:00+0200  [%s] proces testowy (pid 1) - powod\n" % (_dzis, _tag))
    _g5 = importlib.machinery.SourceFileLoader('tag_g', os.path.join(SRC, 'guard.py')).load_module()
    _stat = _g5.statystyki_dnia() if hasattr(_g5, "statystyki_dnia") else None
    if _stat is not None and not any(v for v in _stat.values()):
        bledy.append("statystyki_dnia nie rozpoznaly ZADNEGO ze znacznikow %s "
                     "- parser logu jest zepsuty albo znaczniki sie rozjechaly" % tagi)
    # thermal-report: KARMIMY go logiem i sprawdzamy, czy naprawde policzyl kazda linie.
    # Poprzednia wersja szukala literalu "[PAUSE]" w zrodle - i zglosila falszywy alarm,
    # bo parser uzywa alternatywy w regexie (\[(PAUSE|RESUME|...)\]), gdzie takiego
    # ciagu po prostu nie ma. Grep po zrodle myli OBECNOSC NAPISU z DZIALANIEM kodu;
    # dokladnie o to chodzilo w pozycji 20.
    import subprocess as _sp5
    _cel5 = os.path.join(_t5, "raport.txt")
    _sp5.run([sys.executable, os.path.join(SRC, "thermal-report"), "--file", _cel5, "--days", "2"],
             capture_output=True, text=True, timeout=120,
             env=dict(os.environ, TG_BASE=_t5, TG_LANG="en"))
    _raport = io.open(_cel5, encoding="utf-8", errors="replace").read()
    _nieznane = [t for t in tagi if ("[%s]" % t) not in _raport]
    if _nieznane:
        bledy.append("thermal-report NIE POLICZYL linii ze znacznikami %s - "
                     "raport dowodowy gubi te interwencje" % _nieznane)
    _sh5.rmtree(_t5, ignore_errors=True)
except Exception as _e5:
    bledy.append("nie moge sprawdzic znacznikow logu: %s: %s" % (type(_e5).__name__, _e5))

# 6. `pokolenia()` istnieje w guard.py i w thermal-report jako CELOWA kopia (narzedzia sa
#    samodzielne, nie importuja demona) - obie musza dawac ten sam wynik. Kopia logiki to dlug,
#    ktory zawsze wraca; tu jest przynajmniej pilnowany.
try:
    import shutil as _sh
    import tempfile as _tf
    _t = _tf.mkdtemp()
    _p = os.path.join(_t, "history.csv")
    for _n in ("", ".1", ".2", ".3"):
        io.open(_p + _n, "w").write("x")
    _g = importlib.machinery.SourceFileLoader('pg', os.path.join(SRC, 'guard.py')).load_module()
    _tr = importlib.machinery.SourceFileLoader('ptr', os.path.join(SRC, 'thermal-report')).load_module()
    if not hasattr(_tr, "pokolenia"):
        bledy.append("thermal-report nie ma pokolenia() - rotacja znowu utnie dowody")
    elif _g.pokolenia(_p) != _tr.pokolenia(_p):
        bledy.append("pokolenia() rozjechalo sie miedzy guard.py a thermal-report: %s vs %s"
                     % ([os.path.basename(x) for x in _g.pokolenia(_p)],
                        [os.path.basename(x) for x in _tr.pokolenia(_p)]))
    _sh.rmtree(_t, ignore_errors=True)
except Exception as _e:
    bledy.append("nie moge porownac pokolenia(): %s: %s" % (type(_e).__name__, _e))

# 7. parser stempla czasu zyje w CZTERECH plikach jako celowa kopia (guard.czas_abs,
#    thermal-report.czas_z, heat.czas_abs, safe-run.czas_abs). Wszystkie musza dawac ten
#    sam wynik, w tym na stemplu z offsetem, legacy i na smieciu - inaczej jedno narzedzie
#    po cichu pominie kazdy swiezy wiersz history.csv.
try:
    _probki = ["2026-08-02 23:30:00+0200", "2026-08-02 23:30:00", "2026-08-02 23:30:00-0800",
               "xyzzy", "", "2026-13-45 99:99:99"]
    _impl = {}
    for _plik, _nazwa in (("guard.py", "czas_abs"), ("thermal-report", "czas_z"),
                          ("heat", "czas_abs"), ("safe-run", "czas_abs")):
        _m = importlib.machinery.SourceFileLoader(
            'cz_' + re.sub(r'\W', '_', _plik), os.path.join(SRC, _plik)).load_module()
        if not hasattr(_m, _nazwa):
            bledy.append("%s nie ma %s() - stempel z offsetem wywali mu parsowanie" % (_plik, _nazwa))
            continue
        _impl[_plik] = [getattr(_m, _nazwa)(x) for x in _probki]
    if len(set(tuple(v) for v in _impl.values())) > 1:
        bledy.append("parser stempla rozjechal sie miedzy plikami: %s"
                     % {k: v for k, v in _impl.items()})
except Exception as _e:
    bledy.append("nie moge porownac parsera stempla: %s: %s" % (type(_e).__name__, _e))

print("SPRAWDZEN: 8 kategorii")
if bledy:
    for b in bledy: print("  BLAD: %s" % b)
    sys.exit(1)
print("  wszystko spojne")
