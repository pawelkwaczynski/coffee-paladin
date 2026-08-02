#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy losowe RUNDA 2 - kod napisany w nocy 02.08.2026 (najmniej sprawdzony).

Uruchomienie:   python3 tests/test_fuzz2.py
                python3 tests/test_fuzz2.py --seed 7 --n 400

Czym to sie rozni od tests/test_fuzz.py (runda 1):
  * runda 1 pytala "czy funkcja rzuci wyjatkiem",
  * runda 2 pyta rowniez "czy funkcja podejmuje WLASCIWA decyzje" - czyli czy da sie
    tak nazwac plik, zeby agent AI stracil ochrone (albo zeby zwykly enkoder ja zyskal),
    czy tlumik logu naprawde tlumi, czy po `run()` nie zostaje proces potomny.

Zasady: wszystko w katalogu tymczasowym (TG_BASE), ~/.coffee-paladin nietkniete,
zaden ciezki proces nie jest uruchamiany (tylko /usr/bin/true, /bin/sleep i krotki
python3 -c), a na koncu sprawdzamy `pgrep`, czy nic po nas nie zostalo.
"""

import argparse
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT_SESJI = 9.0            # twardy limit na jedna funkcje
LIMIT_CALOSCI = 90.0         # twardy limit na caly plik
START = time.time()

TMP = tempfile.mkdtemp(prefix="tg-fuzz2-")
os.environ["TG_BASE"] = TMP
os.environ.setdefault("TG_LANG", "en")
os.makedirs(os.path.join(TMP, "managed"), exist_ok=True)

MARKER = "tgfuzz2-%d" % os.getpid()      # po tym znajdujemy wlasne procesy w pgrep


def zaladuj(nazwa, plik):
    return SourceFileLoader(nazwa, os.path.join(REPO, plik)).load_module()


guard = zaladuj("tgf2_guard", "guard.py")
fleet = zaladuj("tgf2_fleet", "fleet")
saferun = zaladuj("tgf2_saferun", "safe-run")
treport = zaladuj("tgf2_treport", "thermal-report")
heat = zaladuj("tgf2_heat", "heat")

PRAWDZIWY_RUN = guard.run          # potrzebny TYLKO w sesji run()
guard.run = lambda cmd, timeout=10: ""
saferun.sh = lambda cmd, timeout=15: ""
treport.sh = lambda cmd, timeout=30: ""
heat.sh = lambda cmd, timeout=15: ""

CFG_PATH = os.path.join(TMP, "config.json")
LOG_PATH = os.path.join(TMP, "guard.log")
STATUS_PATH = os.path.join(TMP, "status.json")
HIST_PATH = os.path.join(TMP, "history.csv")
EVENTS_PATH = os.path.join(TMP, "events.log")

# ---------------------------------------------------------------- raport

ZNALEZISKA = {}
PRZEBIEGI = {}
OK_FUNKCJE = []


def skroc(x, n=260):
    s = x if isinstance(x, str) else repr(x)
    return s if len(s) <= n else s[:n] + "...<%d znakow>" % len(s)


class Sesja(object):
    def __init__(self, nazwa, seed, limit=LIMIT_SESJI):
        self.nazwa = nazwa
        self.rng = random.Random("%s|%s" % (seed, nazwa))
        self.start = time.time()
        self.limit = limit
        self.n = 0
        self.bledy = 0
        self.bzdury = 0

    def czas_minal(self):
        return (time.time() - self.start > self.limit
                or time.time() - START > LIMIT_CALOSCI - 4)

    def _dodaj(self, klucz, wejscie, opis, powaga):
        k = (self.nazwa, klucz)
        if k in ZNALEZISKA:
            ZNALEZISKA[k]["ile"] += 1
            return
        ZNALEZISKA[k] = {"funkcja": self.nazwa, "wejscie": skroc(wejscie),
                         "opis": opis, "powaga": powaga, "ile": 1}

    def blad(self, wejscie, exc, powaga="WYSOKA"):
        self.bledy += 1
        self._dodaj("EXC:" + type(exc).__name__, wejscie,
                    "wyjatek wychodzi z funkcji: %s: %s" % (type(exc).__name__, exc), powaga)

    def bzdura(self, wejscie, opis, powaga="SREDNIA", klucz=None):
        self.bzdury += 1
        self._dodaj(klucz or opis[:60], wejscie, opis, powaga)

    def koniec(self):
        PRZEBIEGI[self.nazwa] = {"przebiegi": self.n,
                                 "sekundy": round(time.time() - self.start, 2),
                                 "bledy": self.bledy, "bzdury": self.bzdury}
        if not self.bledy and not self.bzdury:
            OK_FUNKCJE.append(self.nazwa)


# ================================================================ 1. args_bez_sciezek
#
# Pytanie nie brzmi "czy sie wywroci", tylko: da sie tak NAZWAC PLIK, zeby proces
# bedacy agentem stracil ochrone - albo zeby zwykly enkoder ja zyskal (i grzal Maca
# dalej, bo guard nie ma prawa go dotknac)?

ROZSZ_ZNANE = sorted(guard.ROZSZERZENIA_DANYCH)
# realne formaty medialne i robocze, ktorych NIE MA na liscie ROZSZERZENIA_DANYCH
ROZSZ_NIEZNANE = [".mxf", ".ts", ".m2ts", ".braw", ".r3d", ".exr", ".heif", ".bmp",
                  ".ogv", ".opus", ".wma", ".vob", ".mts", ".jxl", ".dpx", ".cr3",
                  ".mkv.bak", ".mp4.part", ".mov.tmp", ".mp4.crdownload"]
KATALOGI_Z_AGENTEM = ["claude_brain", "codex_out", "mcp_dane", "cursor_projekt",
                      "claude brain", ".vscode_backup"]
KATALOGI_NEUTRALNE = ["wideo", "Movies", "archiwum", "Z_FTP"]
NARZEDZIA = ["ffmpeg", "/opt/homebrew/bin/ffmpeg", "x265", "python3", "HandBrakeCLI"]

# tak samo, jak robi to pick_targets (guard.py: any(n.lower() in args ...))
NEVER_ARG = list(guard.DEFAULTS["never_arg_patterns"]) + list(guard.WLASNE_NAZWY)


def chroniony(args):
    return any(n.lower() in args for n in NEVER_ARG)


def zadanie_z_danymi(rng):
    """Enkoder mielacy plik lezacy w katalogu z nazwa agenta. MA byc pauzowalny.

    Kazdy wariant to inny MECHANIZM potencjalnego obejscia - i to on jest kluczem
    znaleziska, zeby raport mowil "spacja w sciezce", a nie 40 razy to samo.
    """
    kat = rng.choice(KATALOGI_Z_AGENTEM)
    nieznane = rng.random() < 0.5
    ext = rng.choice(ROZSZ_NIEZNANE if nieznane else ROZSZ_ZNANE)
    wej = "/Users/x/Desktop/%s/wideo/rec%s" % (kat, ext)
    wyj = "/Users/x/Desktop/%s/out/rec_x265%s" % (kat, rng.choice(ROZSZ_ZNANE))
    styl = rng.random()
    cudzyslow = styl < 0.2
    katalog_jako_arg = 0.2 <= styl < 0.35
    if cudzyslow:
        wej, wyj = '"%s"' % wej, '"%s"' % wyj            # sciezki w cudzyslowach
    elif katalog_jako_arg:
        wyj = os.path.dirname(wyj) + "/"                 # katalog docelowy, nie plik
    cmd = "%s -y -i %s -c:v libx265 -preset slow %s" % (rng.choice(NARZEDZIA), wej, wyj)
    if " " in kat:
        powod = "spacja w sciezce (ps rozbija argument na dwa tokeny)"
    elif nieznane:
        powod = "rozszerzenie %s spoza ROZSZERZENIA_DANYCH" % ext
    elif cudzyslow:
        powod = "sciezka w cudzyslowach (splitext widzi rozszerzenie z cudzyslowem)"
    elif katalog_jako_arg:
        powod = "argumentem jest KATALOG, nie plik"
    else:
        powod = "sciezka z rozszerzeniem Z LISTY (wariant kontrolny)"
    return cmd, False, powod        # False = NIE powinien byc chroniony


AGENCI = [
    "node /Users/x/.nvm/versions/node/v20/lib/node_modules/@anthropic-ai/claude-code/cli.js",
    "python3 -m mcp.server.stdio --transport stdio",
    "node /Users/x/.vscode/extensions/ms-python/server.js --stdio",
    "node /Users/x/Library/typescript-language-server/lib/cli.js --stdio",
    "/Applications/Cursor.app/Contents/MacOS/Cursor --type=renderer",
    "python3 /Users/x/.local/bin/codex exec",
    "python3 /Users/x/thermal-guard/guard.py",
    "/bin/sh /Users/x/.local/bin/safe-run ffmpeg -i a.mkv",
]


def agent(rng):
    """Proces, ktory MUSI zostac chroniony (SIGSTOP na agencie = zabity agent)."""
    baza = rng.choice(AGENCI)
    styl = rng.random()
    powod = "wzorzec"
    if styl < 0.2:
        # tozsamosc agenta zapisana w pliku o rozszerzeniu z listy danych
        baza = rng.choice([
            "node /Users/x/agents/mcp/server.bin",
            "python3 /Users/x/claude/agent.pt",
            "node /Users/x/codex/dist/index.db",
            "python3 /Users/x/cursor/plugin.pdf",
        ])
        powod = "tozsamosc w pliku o rozszerzeniu danych"
    elif styl < 0.35:
        baza += " --workdir /Users/x/Desktop/wideo/rec.mkv"
        powod = "agent z argumentem-plikiem danych"
    return baza, True, powod


def fuzz_args_ochrona(seed, n):
    s = Sesja("guard.args_bez_sciezek [ochrona]", seed)
    stary = guard.full_args
    ekstrema = [
        "", "   ", "\x00", "\x00 ffmpeg -i /Users/x/claude/a.mkv",
        "ffmpeg " + " ".join("/Users/x/claude/f%d.mkv" % i for i in range(10000)),
        "ffmpeg -i /Users/x/claude" + " " * 3 + "brain/rec.mkv",
        "ffmpeg -i '/Users/x/claude brain/rec.mkv'",
        "ffmpeg -i /Users/x/claude_brain/rec.MKV",
        "ffmpeg -i /Users/x/claude_brain/rec.mkv\x00.txt",
        "ffmpeg -i /Users/x/claude_brain/rec.mkv;rm -rf /",
        "A" * 200000,
        "\n".join(["ffmpeg", "-i", "/Users/x/claude_brain/a.mkv"]),
        "ffmpeg -i //Users//x//claude_brain//rec.mkv",
        "ffmpeg -i ../claude_brain/rec.mkv",
        "ffmpeg -i /Users/x/claude_brain/rec.mkv/",       # sciezka zakonczona ukosnikiem
    ]
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            if i < len(ekstrema):
                cmd, oczek, powod = ekstrema[i], None, "wejscie ekstremalne"
            elif s.rng.random() < 0.55:
                cmd, oczek, powod = zadanie_z_danymi(s.rng)
            else:
                cmd, oczek, powod = agent(s.rng)
            guard.full_args = lambda pid, _w=cmd: _w
            try:
                out = guard.args_bez_sciezek(s.rng.randint(1, 99999))
            except Exception as e:
                s.blad(cmd, e)
                continue
            if not isinstance(out, str):
                s.bzdura(cmd, "zwrocono %s zamiast str" % type(out).__name__, "WYSOKA",
                         klucz="zly-typ")
                continue
            if oczek is None:
                continue
            jest = chroniony(out)
            if jest and oczek is False:
                s.bzdura(cmd,
                         "ZWYKLE ZADANIE STAJE SIE NIETYKALNE (%s): po wycieciu sciezek zostalo "
                         "%r, co pasuje do never_arg_patterns. Guard nie ma prawa go zapauzowac, "
                         "wiec Mac grzeje sie dalej - dokladnie ten blad, dla ktorego funkcja "
                         "powstala." % (powod, skroc(out, 90)),
                         "WYSOKA", klucz="falszywa-ochrona: " + powod)
            elif not jest and oczek is True:
                s.bzdura(cmd,
                         "AGENT TRACI OCHRONE (%s): po wycieciu sciezek zostalo %r, zaden wzorzec "
                         "juz nie pasuje. Taki proces mozna zamrozic (SIGSTOP), a agent AI po "
                         "zamrozeniu nie wraca do zycia." % (powod, skroc(out, 90)),
                         "WYSOKA", klucz="utrata-ochrony: " + powod)
    finally:
        guard.full_args = stary
    s.koniec()


# ================================================================ 2. _loguj_awake

def fuzz_loguj_awake(seed, n):
    s = Sesja("guard._loguj_awake [tlumik]", seed)
    zebrane = []
    stary_log, stary_now = guard.log, guard.now
    zegar = {"t": 1000.0}
    guard.log = lambda msg, tag=None: zebrane.append(msg)
    guard.now = lambda: zegar["t"]

    def reset():
        guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0})
        del zebrane[:]

    try:
        # a) 10 000 przelaczen w tej samej sekundzie - czy tlumik trzyma i czy licznik
        #    pominietych trafia do komunikatu (a nie np. przepelnia go megabajtem)
        reset()
        s.n += 1
        for i in range(10000):
            guard._loguj_awake("KEEP-AWAKE %s" % ("start" if i % 2 else "stop"))
        if len(zebrane) > 2:
            s.bzdura("10 000 przelaczen w tej samej sekundzie",
                     "tlumik przepuscil %d wpisow zamiast <=1 na 10 min" % len(zebrane),
                     "SREDNIA", klucz="tlumik-nieszczelny")
        if any(len(x) > 200 for x in zebrane):
            s.bzdura("10 000 przelaczen", "komunikat urosl do %d znakow"
                     % max(len(x) for x in zebrane), "SREDNIA", klucz="dlugi-komunikat")
        if guard._awake_log["pominiete"] < 0:
            s.bzdura("10 000 przelaczen", "licznik pominietych jest ujemny", "SREDNIA")

        # b) czy po uplywie 10 minut licznik pominietych naprawde trafia do logu
        reset()
        s.n += 1
        guard._loguj_awake("A")
        for _ in range(500):
            guard._loguj_awake("B")
        zegar["t"] += 601
        guard._loguj_awake("C")
        if not any("przelaczen" in x for x in zebrane[1:]):
            s.bzdura("A, 500xB, +601 s, C",
                     "po tlumieniu 500 zdarzen kolejny wpis nie mowi, ile ich pominieto "
                     "(czarna skrzynka gubi skale zjawiska)", "NISKA", klucz="brak-licznika")

        # c) TEN SAM komunikat po dowolnie dlugim czasie
        reset()
        s.n += 1
        guard._loguj_awake("KEEP-AWAKE start")
        ile_przed = len(zebrane)
        for k in range(1, 6):
            zegar["t"] += 86400.0 * k
            guard._loguj_awake("KEEP-AWAKE start")
        if len(zebrane) == ile_przed:
            s.bzdura("ten sam komunikat co 24 h przez 5 dni",
                     "identyczny komunikat NIGDY nie trafia juz do logu (warunek "
                     "`msg == ostatni` nie ma limitu czasu). Keep-awake wlaczony na staly "
                     "stan znika z czarnej skrzynki po pierwszym wpisie, a licznik "
                     "pominietych (%d) rosnie bez konca." % guard._awake_log["pominiete"],
                     "SREDNIA", klucz="ten-sam-msg-na-zawsze")

        # d) zegar cofniety (NTP albo powrot z uspienia) - now() to time.time(), nie monotonic
        reset()
        s.n += 1
        guard._loguj_awake("X")
        zegar["t"] -= 3600.0
        przed = len(zebrane)
        for _ in range(10):
            zegar["t"] += 60.0
            guard._loguj_awake("Y" if _ % 2 else "Z")
        if len(zebrane) == przed:
            s.bzdura("zegar cofniety o godzine",
                     "po cofnieciu zegara (NTP/powrot z uspienia) tlumik milczy tak dlugo, "
                     "az czas realny nadgoni - keep-awake nie zostawia sladu w logu",
                     "NISKA", klucz="zegar-w-tyl")

        # e) losowe typy i dlugosci
        warianty = [None, 0, 1, -1, True, 3.5, [], {}, b"bajty", "\x00", "\x1b[2J",
                    "A" * 100000, "%s %d", "‮ rtl", object()]
        for i in range(max(0, n - 5)):
            if s.czas_minal():
                break
            s.n += 1
            if s.rng.random() < 0.4:
                guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0})
            zegar["t"] += s.rng.choice([0.0, 0.1, 700.0])
            msg = warianty[i % len(warianty)] if i < 60 else s.rng.choice(warianty)
            try:
                guard._loguj_awake(msg)
            except Exception as e:
                s.blad(msg, e, "NISKA")
    finally:
        guard.log, guard.now = stary_log, stary_now
        guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0})
    s.koniec()


# ================================================================ 3. run()

def zywe_dzieci():
    """Nasze procesy potomne wedlug pgrep (po unikalnym markerze w linii polecen)."""
    try:
        out = subprocess.run(["pgrep", "-f", MARKER], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=5).stdout.decode()
    except Exception:
        return []
    return [x for x in out.split() if x.strip() and x.strip() != str(os.getpid())]


def fuzz_run(seed, n):
    s = Sesja("guard.run [sprzatanie po dziecku]", seed, limit=45.0)
    PY = sys.executable

    def scen(rng, i):
        r = rng.random()
        if r < 0.30:
            return ["/usr/bin/true"], 5, "natychmiastowy sukces"
        if r < 0.45:
            return ["/nie/ma/takiego/programu-" + MARKER], 5, "polecenie nie istnieje"
        if r < 0.55:
            return "/nie/ma/takiego-" + MARKER, 5, "cmd jako string, nie lista"
        if r < 0.62:
            return ["/usr/bin/false"], 5, "kod wyjscia != 0"
        if r < 0.70:
            return [PY, "-c", "print('%s'*10)" % MARKER], 5, "krotkie wyjscie"
        if r < 0.78:
            return [PY, "-c", "import sys;sys.stdout.write('%s'+'A'*(4*1024*1024))" % MARKER], \
                   5, "4 MB na stdout"
        if r < 0.86:
            return [PY, "-c",
                    "import signal,time,sys;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                    "sys.stderr.write('%s');time.sleep(30)" % MARKER], 0.15, \
                   "ignoruje SIGTERM, timeout"
        if r < 0.94:
            # wnuk MUSI miec marker we wlasnej linii polecen, inaczej pgrep go nie widzi
            return ["/bin/sh", "-c",
                    "%s -c 'import time;time.sleep(27)' %s & wait" % (PY, MARKER)], 0.15, \
                   "wnuk przezywajacy zabicie dziecka"
        return ["/usr/bin/true"], 0, "timeout zerowy"

    zostawione = set()
    try:
        guard.run = PRAWDZIWY_RUN
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            cmd, tmo, opis = scen(s.rng, i)
            try:
                out = guard.run(cmd, timeout=tmo)
            except Exception as e:
                s.blad({"cmd": skroc(cmd, 120), "timeout": tmo, "opis": opis}, e, "WYSOKA")
                continue
            if not isinstance(out, str):
                s.bzdura(opis, "zwrocono %s zamiast str" % type(out).__name__, "WYSOKA",
                         klucz="zly-typ")
            if "nie istnieje" in opis or "string" in opis:
                continue        # nic sie nie uruchomilo - pgrep bylby strata czasu
            time.sleep(0.005)
            zywe = zywe_dzieci()
            if zywe:
                zostawione.update(zywe)
                s.bzdura({"cmd": skroc(cmd, 120), "timeout": tmo},
                         "po powrocie z run() zyje jeszcze %d proces(ow) potomnych (%s) - "
                         "przypadek: %s" % (len(zywe), ",".join(zywe[:4]), opis),
                         "WYSOKA" if "wnuk" not in opis else "SREDNIA",
                         klucz="osierocony-proces:" + opis[:20])
                # sprzatamy po sobie NATYCHMIAST, zeby test nie hodowal procesow
                subprocess.run(["pkill", "-9", "-f", MARKER], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    finally:
        subprocess.run(["pkill", "-9", "-f", MARKER], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        guard.run = lambda cmd, timeout=10: ""
    s.koniec()


# ================================================================ 4. zajmij_wylacznosc

def fuzz_wylacznosc(seed, n):
    s = Sesja("guard.zajmij_wylacznosc", seed)
    lock = os.path.join(TMP, "guard.lock")
    uchwyty = []
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            wariant = i % 6
            opis = ""
            try:
                if wariant == 0:
                    opis = "czysto"
                    for f in uchwyty:
                        f.close()
                    del uchwyty[:]
                    if os.path.isdir(lock):
                        shutil.rmtree(lock, ignore_errors=True)
                    f1 = guard.zajmij_wylacznosc()
                    if f1 is None:
                        s.bzdura(opis, "pierwsza instancja NIE dostala blokady", "WYSOKA",
                                 klucz="brak-blokady")
                    else:
                        uchwyty.append(f1)
                elif wariant == 1:
                    opis = "druga instancja przy trzymanej blokadzie"
                    f2 = guard.zajmij_wylacznosc()
                    if f2 is not None:
                        uchwyty.append(f2)
                        s.bzdura(opis, "DWIE instancje dostaly blokade naraz - dwa demony na "
                                       "maszynie moga sie wzajemnie pauzowac", "WYSOKA",
                                 klucz="podwojna-blokada")
                elif wariant == 2:
                    opis = "PID w guard.lock po nieudanej probie"
                    tresc = ""
                    try:
                        with open(lock) as f:
                            tresc = f.read()
                    except Exception:
                        pass
                    if not tresc.strip():
                        s.bzdura(opis,
                                 "guard.lock jest PUSTY, mimo ze demon zyje: przegrana instancja "
                                 "otwiera plik w trybie 'w' (obcina go) ZANIM sprobuje flock, "
                                 "wiec kazde nieudane uruchomienie kasuje PID wlasciciela blokady",
                                 "SREDNIA", klucz="wyczyszczony-pid")
                elif wariant == 3:
                    opis = "guard.lock jest KATALOGIEM"
                    for f in uchwyty:
                        f.close()
                    del uchwyty[:]
                    if os.path.exists(lock):
                        os.unlink(lock)
                    os.makedirs(lock, exist_ok=True)
                    try:
                        r = guard.zajmij_wylacznosc()
                        if r is not None:
                            uchwyty.append(r)
                    except Exception as e:
                        s.blad(opis, e, "SREDNIA")
                    shutil.rmtree(lock, ignore_errors=True)
                elif wariant == 4:
                    opis = "katalog BASE tylko do odczytu"
                    for f in uchwyty:
                        f.close()
                    del uchwyty[:]
                    if os.path.exists(lock):
                        os.unlink(lock)
                    os.chmod(TMP, 0o500)
                    try:
                        r = guard.zajmij_wylacznosc()
                        if r is not None:
                            uchwyty.append(r)
                    except Exception as e:
                        s.blad(opis, e, "SREDNIA")
                    finally:
                        os.chmod(TMP, 0o755)
                else:
                    opis = "zwolnienie i ponowne zajecie"
                    for f in uchwyty:
                        f.close()
                    del uchwyty[:]
                    r = guard.zajmij_wylacznosc()
                    if r is None:
                        s.bzdura(opis, "po zamknieciu uchwytu blokada NIE zostala zwolniona",
                                 "WYSOKA", klucz="blokada-nie-zwolniona")
                    else:
                        uchwyty.append(r)
            except Exception as e:
                s.blad(opis, e, "SREDNIA")
    finally:
        for f in uchwyty:
            try:
                f.close()
            except Exception:
                pass
        os.chmod(TMP, 0o755)
        if os.path.isdir(lock):
            shutil.rmtree(lock, ignore_errors=True)
    s.koniec()


# ================================================================ 5. load_cfg: progi

RODZINY = (("soc_resume_c", "soc_pause_c", "soc_kill_c", 40.0, 110.0),
           ("batt_resume_c", "batt_pause_c", "batt_kill_c", 20.0, 60.0))

LICZBY_PROGOW = [0, 1, -1, -273.15, 20.0, 39.999, 40.0, 40.1, 45, 60.0, 60.1, 76.0,
                 85.0, 90.0, 109.9, 110.0, 110.1, 1e6, -1e6, 1e308, 1e-323, 0.5,
                 "85", "85.0", "goraco", True, False, None, [85], {"v": 85}]


def fuzz_load_cfg_progi(seed, n):
    s = Sesja("guard.load_cfg [progi]", seed)
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            d = {}
            for r, p, k, lo, hi in RODZINY:
                if s.rng.random() < 0.85:
                    if s.rng.random() < 0.5:      # trojka blisko granic zakresu
                        baza = s.rng.choice([lo, hi, (lo + hi) / 2.0])
                        d[r] = baza + s.rng.choice([-2, -0.001, 0, 0.001, 2])
                        d[p] = baza + s.rng.choice([-4, 0, 0.002, 4])
                        d[k] = baza + s.rng.choice([-6, 0, 0.003, 6])
                    else:
                        d[r] = s.rng.choice(LICZBY_PROGOW)
                        d[p] = s.rng.choice(LICZBY_PROGOW)
                        d[k] = s.rng.choice(LICZBY_PROGOW)
            try:
                tekst = json.dumps(d, allow_nan=True)
            except Exception:
                continue
            with open(CFG_PATH, "w") as f:
                f.write(tekst)
            del guard._zle_typy[:]
            try:
                cfg = guard.load_cfg()
            except Exception as e:
                s.blad(tekst, e, "WYSOKA")
                continue
            for r, p, k, lo, hi in RODZINY:
                try:
                    vr, vp, vk = float(cfg[r]), float(cfg[p]), float(cfg[k])
                except Exception as e:
                    s.blad(tekst, e, "WYSOKA")
                    continue
                if not (vr < vp < vk):
                    s.bzdura(tekst, "po walidacji progi %s NIE rosna: %s=%.3f %s=%.3f %s=%.3f "
                                    "(rowne progi = mlynek pauza/wznowienie albo SIGTERM przy "
                                    "progu pauzy)" % (r.split("_")[0], r, vr, p, vp, k, vk),
                             "WYSOKA", klucz="progi-nie-rosna:" + r.split("_")[0])
                for nazwa, v in ((r, vr), (p, vp), (k, vk)):
                    if not (lo <= v <= hi):
                        s.bzdura(tekst, "po walidacji %s=%.3f jest poza zakresem fizycznym "
                                        "%.0f-%.0f - kontrola zakresu nie zadzialala"
                                 % (nazwa, v, lo, hi), "WYSOKA",
                                 klucz="poza-zakresem:" + nazwa)
            # idempotencja: zapis poprawionego configu i ponowne wczytanie nie moze
            # przesuwac progow dalej (inaczej kazdy restart obniza je o 2 C)
            with open(CFG_PATH, "w") as f:
                json.dump({kk: cfg[kk] for r, p, k, lo, hi in RODZINY for kk in (r, p, k)}, f)
            try:
                cfg2 = guard.load_cfg()
            except Exception as e:
                s.blad(tekst, e, "WYSOKA")
                continue
            for r, p, k, lo, hi in RODZINY:
                for kk in (r, p, k):
                    if float(cfg[kk]) != float(cfg2[kk]):
                        s.bzdura(tekst, "walidacja nie jest idempotentna: %s %.3f -> %.3f przy "
                                        "ponownym wczytaniu (kazdy restart demona przesuwa prog)"
                                 % (kk, float(cfg[kk]), float(cfg2[kk])), "SREDNIA",
                                 klucz="brak-idempotencji")
    finally:
        with open(CFG_PATH, "w") as f:
            f.write("{}")
        del guard._zle_typy[:]
    s.koniec()


# ================================================================ 6. fleet.load_hosts

FLEET_DIR = os.path.join(TMP, "flota")

# znaki pisane WYLACZNIE escape'ami - w zrodle nie ma niewidzialnych bajtow
NIEWIDZIALNE = [
    "\u202e",          # RTL override - odwraca kolejnosc wyswietlania reszty wiersza
    "\u200b",          # zero-width space
    "\u2028",          # separator linii (Unicode)
    "\u2029",          # separator akapitu
    "\ufeff",          # BOM w srodku tekstu
    "\u0301" * 20,     # zalgo: 20 znakow lacznych
    "\u3164",          # HANGUL FILLER - "pusty", ale drukowalny
    "\u2066", "\u202d",
    "\x1b[2J", "\x1b[1;1H", "\r", "\x07", "\n",
]

# czego szukamy w GOTOWYM wydruku tabeli (nigdy pusty string!)
ZAKAZANE_W_WYDRUKU = [("\x1b", "ESC (sekwencja ANSI)"), ("\r", "CR (kasuje wiersz)"),
                      ("\x07", "BEL"), ("\u202e", "RTL override"),
                      ("\u200b", "zero-width space"), ("\u2028", "separator linii"),
                      ("\ufeff", "BOM")]   # UWAGA: bez "\n" - tabela sama ma nowe linie

WROGIE_MIGAWKI = [
    "{}", "null", "[]", '"tekst"', "5", "{", "\x00\xff",
    '{"host": "\\u202eevil"}',
    '{"host": "\\u001b[2Jznikaj"}',
    '{"host": "%s"}' % ("A" * 500),
    '{"level": "nan"}', '{"level": "inf"}', '{"level": 1e400}', '{"level": [1]}',
    '{"level": "3"}', '{"level": true}',
    '{"fans": ["3.5"]}', '{"fans": ["nan"]}', '{"fans": [1e400]}', '{"fans": "1200"}',
    '{"fans": [null, "x", 1200]}',
    '{"chip_c": "goraco"}', '{"chip_c": "nan"}',
    '{"ram_total_gb": 16}',
    '{"ram_total_gb": 16, "ram_used_gb": "osiem"}',
    '{"stats": {"pauses": "duzo"}}',
    '{"stats": {"pauses": 1, "kills": "x"}}',
    '{"stats": []}',
    '{"paused": "ffmpeg"}', '{"paused": [1,2,3]}', '{"paused": [{"a":1}]}',
    '{"on_ac": "moze"}', '{"on_ac": null}',
    '{"last_hard_shutdown": {"time": "\\u001b[2J\\u001b[1;1HWSZYSTKO OK"}}',
    '{"last_hard_shutdown": {"time": "\\r\\nfalszywy wiersz"}}',
    '{"last_hard_shutdown": []}',
    '{"disk_used_pct": "95"}', '{"disk_used_pct": "nan"}',
    '{"cpu_limit": "50"}', '{"cpu_limit": 1e400}',
    '{"model": 12345}', '{"model": null}',
]


def losowa_migawka(rng):
    d = {}
    pola = ["host", "model", "chip_c", "watts", "ram_used_gb", "ram_total_gb",
            "disk_used_pct", "battery_pct", "cpu_limit", "level", "fans", "paused",
            "stats", "last_hard_shutdown", "on_ac"]
    for k in rng.sample(pola, rng.randint(1, len(pola))):
        r = rng.random()
        if r < 0.2:
            d[k] = rng.choice(["", "0", "nan", "inf", "-1", "3.5", "abc",
                               rng.choice(NIEWIDZIALNE) + "host"])
        elif r < 0.4:
            d[k] = rng.choice([0, 1, -1, 3, 4, 99, 10 ** 40, 1e308, float("nan"),
                               float("inf"), -0.0])
        elif r < 0.55:
            d[k] = rng.choice([None, True, False])
        elif r < 0.75:
            d[k] = rng.choice([[], [1200, 0], ["x"], [None], [{"a": 1}],
                               [rng.choice(NIEWIDZIALNE) + "proc"]])
        else:
            d[k] = rng.choice([{}, {"pauses": 1}, {"pauses": "x"},
                               {"time": rng.choice(NIEWIDZIALNE) + "2026-08-02"}])
    return d


def fuzz_fleet(seed, n):
    s = Sesja("fleet.load_hosts + render", seed)
    if os.path.isdir(FLEET_DIR):
        shutil.rmtree(FLEET_DIR, ignore_errors=True)
    os.makedirs(FLEET_DIR, exist_ok=True)
    nazwy = ["mbp.json", "neo.json", ".ukryty.json", "render-01.json.icloud",
             "host bez rozszerzenia", "‮evil.json"]
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            for f in os.listdir(FLEET_DIR):
                try:
                    os.unlink(os.path.join(FLEET_DIR, f))
                except Exception:
                    pass
            wejscia = {}
            if i < len(WROGIE_MIGAWKI):
                tresci = [WROGIE_MIGAWKI[i]]
            else:
                tresci = []
                for _ in range(s.rng.randint(1, 3)):
                    if s.rng.random() < 0.3:
                        tresci.append(s.rng.choice(WROGIE_MIGAWKI))
                    else:
                        try:
                            tresci.append(json.dumps(losowa_migawka(s.rng), allow_nan=True))
                        except Exception:
                            tresci.append("{}")
            for j, t in enumerate(tresci):
                nazwa = nazwy[(i + j) % len(nazwy)] if i < 40 else s.rng.choice(nazwy)
                p = os.path.join(FLEET_DIR, nazwa)
                with open(p, "wb") as f:
                    f.write(t.encode("utf-8", "surrogateescape"))
                wejscia[nazwa] = skroc(t, 120)
            try:
                hosts = fleet.load_hosts(FLEET_DIR)
            except Exception as e:
                s.blad(wejscia, e, "WYSOKA")
                continue
            if not isinstance(hosts, list):
                s.bzdura(wejscia, "load_hosts zwrocil %s" % type(hosts).__name__, "WYSOKA")
                continue
            for h in hosts:
                lv = h.get("level")
                if not isinstance(lv, int) or isinstance(lv, bool) or not (0 <= lv <= 3):
                    if "_age" in h and h.get("_age") != 1e9:      # wpis .icloud nie ma level
                        s.bzdura(wejscia, "level po normalizacji = %r (render indeksuje nim "
                                          "liste 4-elementowa)" % (lv,), "WYSOKA",
                                 klucz="level-nieznormalizowany")
            # to jest WLASCIWY test: jedna zepsuta migawka nie moze wywalic tabeli floty
            bufor = io.StringIO()
            try:
                with redirect_stdout(bufor):
                    fleet.render(FLEET_DIR)
            except Exception as e:
                s.bzdura(wejscia,
                         "JEDNA zepsuta migawka WYWALA CALA TABELE floty: %s: %s "
                         "(operator nie widzi zadnej maszyny, takze tych zdrowych)"
                         % (type(e).__name__, e), "WYSOKA",
                         klucz="render-EXC:" + type(e).__name__)
                continue
            tekst = bufor.getvalue()
            for zly, nazwa_zlego in ZAKAZANE_W_WYDRUKU:
                if zly and zly in tekst:
                    s.bzdura(wejscia,
                             "znak %s z obcej migawki trafia PROSTO na terminal operatora - "
                             "moze skasowac juz wypisane wiersze razem z ostrzezeniem o awarii "
                             "(_czysty_tekst nie obejmuje tego pola)" % nazwa_zlego,
                             "WYSOKA", klucz="wstrzykniecie:" + nazwa_zlego)
    finally:
        shutil.rmtree(FLEET_DIR, ignore_errors=True)
    s.koniec()


# ================================================================ 7. chip_juz_goracy

def fuzz_chip_swiezosc(seed, n):
    s = Sesja("safe-run.chip_juz_goracy [swiezosc]", seed)
    wieki = [0, 1, 60, 119, 119.9, 120, 120.1, 121, 300, 86400, -30, -1e6]
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            wiek = wieki[i % len(wieki)] if i < 60 else s.rng.choice(wieki)
            chip = s.rng.choice([None, 0.0, 60.0, 79.9, 80.0, 80.1, 85.0, 92.0, 130.0,
                                 float("nan"), float("inf"), "85", "goraco"])
            lvl = s.rng.choice([0, 1, 2, 3, "2", None, True, 99, -1, float("nan")])
            progi = s.rng.choice([None, {}, {"pause": 85.0}, {"pause": 78.0},
                                  {"pause": "85"}, {"pause": None}, {"pause": float("nan")},
                                  [85.0], "85"])
            d = {"level": lvl, "chip_c": chip, "thresholds": progi}
            try:
                tresc = json.dumps(d, allow_nan=True)
            except Exception:
                continue
            with open(STATUS_PATH, "w") as f:
                f.write(tresc)
            os.utime(STATUS_PATH, (time.time() - wiek, time.time() - wiek))
            try:
                r = saferun.chip_juz_goracy()
            except Exception as e:
                s.blad({"wiek_s": wiek, "status": tresc}, e, "SREDNIA")
                continue
            if not (isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], bool)):
                s.bzdura(tresc, "zwrocono %r zamiast (bool, str)" % (r,), "SREDNIA",
                         klucz="zly-typ")
                continue
            goraco = r[0]
            # oracle 1: swieza migawka z goracym chipem MUSI zatrzymac start zadania
            prog = 85.0
            if isinstance(progi, dict) and isinstance(progi.get("pause"), (int, float)):
                prog = float(progi["pause"])
            if (0 <= wiek <= 110 and isinstance(chip, float) and chip == chip
                    and chip not in (float("inf"),) and chip >= prog - 5.0 and not goraco):
                s.bzdura({"wiek_s": wiek, "status": tresc},
                         "swieza migawka mowi chip %.1f C przy progu %.1f, a safe-run i tak "
                         "PUSZCZA ciezkie zadanie" % (chip, prog), "WYSOKA",
                         klucz="przepuszcza-goraco")
            # oracle 2: migawka starsza niz 120 s = guard nie zyje (pisze co 15 s),
            # a wlasnie wtedy nikt nie pilnuje temperatury
            if wiek > 130 and goraco is False and isinstance(chip, float) and chip >= 90:
                s.bzdura({"wiek_s": wiek, "status": tresc},
                         "migawka sprzed %.0f s pokazuje %.1f C, ale safe-run traktuje ja jako "
                         "'brak danych' i puszcza zadanie. Nieswieza migawka znaczy, ze demon "
                         "NIE ZYJE - czyli nikt nie pilnuje temperatury tego zadania"
                         % (wiek, chip), "SREDNIA", klucz="nieswieza-migawka-przepuszcza")
            if wiek < 0 and goraco is False and isinstance(chip, float) and chip >= 95:
                s.bzdura({"wiek_s": wiek, "status": tresc},
                         "migawka z PRZYSZLOSCI (zegar/NTP) jest traktowana jak swieza albo jak "
                         "brak danych zaleznie od znaku roznicy - decyzja o starcie zadania "
                         "zalezy od zegara, nie od temperatury", "NISKA",
                         klucz="migawka-z-przyszlosci")
    finally:
        if os.path.exists(STATUS_PATH):
            os.unlink(STATUS_PATH)
    s.koniec()


# ================================================================ 8. thermal-report

def fuzz_report(seed, n):
    s = Sesja("thermal-report [szczyt + sciezka pdf]", seed)
    cele = ["raport.txt", "raport", "raport.tar.gz", ".ukryty", "raport.", "a.b/raport",
            "a.b/raport.txt", "kat.z.kropka/raport.txt", "raport z odstepem.txt",
            "raport\x1b.txt", "‮raport.txt", "raport.PDF", "raport..txt"]
    dzis = time.strftime("%Y-%m-%d")
    naglowek = "time,thermal_state,chip_C,gpu_C,battery_C,fan_rpm,watts,batt_pct,on_ac,cpu_limit,load1,level\n"
    stary_argv = sys.argv
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1

            # --- a) sciezka PDF: musi zostac W TYM SAMYM katalogu co raport tekstowy
            cel = cele[i % len(cele)]
            pelny = os.path.join(TMP, cel)
            pdf = os.path.splitext(pelny)[0] + ".pdf"
            if os.path.dirname(pdf) != os.path.dirname(pelny):
                s.bzdura(cel, "PDF laduje w INNYM katalogu niz raport: %s -> %s"
                         % (pelny, pdf), "WYSOKA", klucz="pdf-poza-katalogiem")
            if pdf == pelny or not pdf.endswith(".pdf"):
                s.bzdura(cel, "sciezka PDF wyszla dziwna: %r" % pdf, "SREDNIA",
                         klucz="pdf-zla-nazwa")

            # --- b) szczyt temperatury z history.csv (z sanity-checkiem 0 < v <= 120)
            wiersze = []
            oczekiwany = 0.0
            for _ in range(s.rng.randint(0, 12)):
                r = s.rng.random()
                if r < 0.6:
                    v = round(s.rng.uniform(30, 119), 1)
                    wiersze.append("%s 10:00:00,nominal,%s,,,0,10,90,1,100,2.0,0" % (dzis, v))
                    oczekiwany = max(oczekiwany, v)
                elif r < 0.7:
                    v = s.rng.choice(["999.9", "1e400", "nan", "-5", "0", "120.1", ""])
                    wiersze.append("%s 10:00:00,nominal,%s,,,0,10,90,1,100,2.0,0" % (dzis, v))
                elif r < 0.8:
                    wiersze.append("%s 10:00:00,nominal,88.8" % dzis)        # ucieta linia
                elif r < 0.9:
                    wiersze.append("2000-01-01 10:00:00,nominal,118.0,,,0,10,90,1,100,2.0,0")
                else:
                    wiersze.append(s.rng.choice(["", ",,,,,,,,,,,,", "A" * 2000,
                                                 "\x00,\x00,\x00,,,0,0,0,0,0,0,0"]))
            with open(HIST_PATH, "w") as f:
                f.write(naglowek + "\n".join(wiersze) + "\n")
            with open(LOG_PATH, "w") as f:
                f.write("%s 10:00:00  [PAUSE] PAUSED ffmpeg (pid 1, 90%% CPU) - hot\n" % dzis)
            with open(EVENTS_PATH, "w") as f:
                f.write('{"time": "%s 10:00:00", "type": "HARD", "description": "x"}\n' % dzis)
            if i % 7 == 0:      # hardware.json po recznej edycji: poprawny JSON, nie-obiekt
                with open(os.path.join(TMP, "hardware.json"), "w") as f:
                    f.write(s.rng.choice(["[]", '"x"', "5", "null"]))
            else:
                with open(os.path.join(TMP, "hardware.json"), "w") as f:
                    f.write('{"chip": "Apple M4 Pro", "fan_count": 2}')
            wyjscie = os.path.join(TMP, "out_%d.txt" % (i % 3))
            sys.argv = ["thermal-report", "--file", wyjscie, "--days", "2"]
            wej = {"cel": cel, "wierszy": len(wiersze), "hardware": i % 7 == 0}
            try:
                with redirect_stdout(io.StringIO()):
                    treport.main()
            except Exception as e:
                s.blad(wej, e, "SREDNIA")
                continue
            try:
                with open(wyjscie) as f:
                    tekst = f.read()
            except Exception as e:
                s.blad(wej, e, "SREDNIA")
                continue
            m = re.search(r"PEAK MEASURED CHIP TEMPERATURE: ([0-9.]+) C", tekst)
            if oczekiwany and not m:
                s.bzdura(wej, "raport nie podaje szczytu, choc w zakresie byl pomiar %.1f C"
                         % oczekiwany, "SREDNIA", klucz="brak-szczytu")
            elif m and abs(float(m.group(1)) - oczekiwany) > 0.05:
                s.bzdura(wej, "szczyt w raporcie %.1f C, a najwyzszy poprawny pomiar %.1f C"
                         % (float(m.group(1)), oczekiwany), "WYSOKA", klucz="zly-szczyt")
            if m and "MEASUREMENT TIMELINE" in tekst:
                if tekst.index("PEAK MEASURED") > tekst.index("MEASUREMENT TIMELINE"):
                    s.bzdura(wej, "wiersz ze szczytem jest WEWNATRZ osi pomiarow zamiast nad nia",
                             "NISKA", klucz="szczyt-nie-tam")
    finally:
        sys.argv = stary_argv
        for p in (HIST_PATH, EVENTS_PATH, os.path.join(TMP, "hardware.json")):
            if os.path.exists(p):
                os.unlink(p)
    s.koniec()


# ================================================================ 9. statystyki_dnia

def fuzz_stat_znaczniki(seed, n):
    s = Sesja("guard.statystyki_dnia [znaczniki]", seed)
    dzis = time.strftime("%Y-%m-%d")
    jutro = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    # nazwy procesow, ktore SAME zawieraja slowo-klucz parsera
    zatrute_nazwy = ["sigterm_bench", "PAUSED_render", "resumed-worker", "koncze zadanie.sh"]
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            linie = []
            ocz = {"pauses": 0, "resumes": 0, "kills": 0}
            for _ in range(s.rng.randint(0, 10)):
                r = s.rng.random()
                nazwa = s.rng.choice(["ffmpeg", "x265"] + zatrute_nazwy)
                czyste = nazwa not in zatrute_nazwy
                if r < 0.4:
                    linie.append("%s 10:00:00  [PAUSE] PAUSED %s (pid 1, 90%% CPU) - hot"
                                 % (dzis, nazwa))
                    if czyste:
                        ocz["pauses"] += 1
                elif r < 0.7:
                    linie.append("%s 10:00:00  [RESUME] RESUMED %s (pid 1) - cool"
                                 % (dzis, nazwa))
                    if czyste:
                        ocz["resumes"] += 1
                elif r < 0.85:
                    linie.append("%s 10:00:00  [KILL] TERMINATED (SIGTERM) %s (pid 1) - crit"
                                 % (dzis, nazwa))
                    if czyste:
                        ocz["kills"] += 1
                else:
                    linie.append(s.rng.choice([
                        "%s 10:00:00  KEEP-AWAKE start" % dzis,
                        "%s 10:00:00  [PAUSE] PAUSED x (pid 1)" % jutro,   # data z przyszlosci
                        "linia bez daty w ogole",
                        "%s 10:00:00  %s" % (dzis, "A" * (1000000 if i < 8 else 20000)),
                        "%s 10:00:00  CONFIG: odrzucone: never_extra" % dzis,
                        "%s 10:00:00  ОБНАРУЖЕНО "
                        "приостановка"
                        % dzis,                                             # stary wpis po rosyjsku
                        "%s 10:00:00  暂停任务" % dzis,     # stary wpis po chinsku
                        "%s 10:00:00  PAUSA de la tarea" % dzis,            # stary wpis po hiszpansku
                    ]))
            tresc = "\n".join(linie) + "\n"
            bajty = tresc.encode("utf-8")
            zepsute = s.rng.random() < 0.15
            if zepsute:      # jeden nie-UTF-8 bajt na koncu logu
                bajty = bajty + b"\xff\xfe niepoprawne utf-8\n"
            with open(LOG_PATH, "wb") as f:
                f.write(bajty)
            try:
                st = guard.statystyki_dnia()
            except Exception as e:
                s.blad(skroc(tresc, 200), e, "WYSOKA")
                continue
            if set(st) != {"pauses", "resumes", "kills"}:
                s.bzdura(skroc(tresc, 200), "zwrocono %r" % (st,), "WYSOKA", klucz="zly-typ")
                continue
            if zepsute and sum(ocz.values()) and not sum(st.values()):
                s.bzdura(skroc(tresc, 200),
                         "JEDEN nie-UTF-8 bajt w guard.log KASUJE CALA STATYSTYKE DNIA: "
                         "w logu bylo %d interwencji, funkcja zwraca same zera. Plik jest "
                         "czytany w blokach, wiec zly bajt na koncu wywala dekoder JUZ przy "
                         "pierwszym readline(), a `except Exception` polyka to bez slowa - "
                         "pasek pokazuje 'dzis 0 pauz' po nocy pelnej pauz"
                         % sum(ocz.values()), "SREDNIA", klucz="log-nie-utf8-zeruje")
            for k in ocz:
                if st[k] < ocz[k] and not zepsute:
                    s.bzdura(skroc(tresc, 300),
                             "GUBI zdarzenia: %s=%d, a w logu bylo %d (statystyka dnia w pasku "
                             "pokazuje mniej interwencji, niz naprawde bylo)"
                             % (k, st[k], ocz[k]), "SREDNIA", klucz="gubi:" + k)
                elif st[k] > ocz[k] + 6 and not zepsute:
                    s.bzdura(skroc(tresc, 300),
                             "LICZY ZA DUZO: %s=%d przy %d prawdziwych zdarzeniach - nazwa "
                             "procesu zawierajaca slowo-klucz (np. 'sigterm_bench') jest liczona "
                             "jak zdarzenie, a kolejnosc warunkow przypisuje ja do ubic"
                             % (k, st[k], ocz[k]), "NISKA", klucz="liczy-za-duzo:" + k)
    finally:
        if os.path.exists(LOG_PATH):
            os.unlink(LOG_PATH)
    s.koniec()


# ================================================================ raport

def wypisz_raport(seed, n):
    print("=" * 78)
    print("FUZZING RUNDA 2 (kod z nocy 02.08.2026) - ziarno %s, ~%d wejsc na funkcje" % (seed, n))
    print("katalog roboczy (TG_BASE): %s" % TMP)
    print("=" * 78)
    print("\n%-42s %8s %7s %7s %7s" % ("funkcja", "przebieg", "sek", "wyjatki", "bzdury"))
    print("-" * 78)
    for nazwa, d in PRZEBIEGI.items():
        print("%-42s %8d %7.2f %7d %7d"
              % (nazwa, d["przebiegi"], d["sekundy"], d["bledy"], d["bzdury"]))
    print("\n" + "=" * 78)
    lista = list(ZNALEZISKA.values())
    if not lista:
        print("ZNALEZISKA: brak - wszystko przetrwalo ostrzal.")
    else:
        print("ZNALEZISKA (%d roznych; x = ile wejsc je wywolalo):" % len(lista))
        kol = {"WYSOKA": 0, "SREDNIA": 1, "NISKA": 2}
        for i, z in enumerate(sorted(lista, key=lambda x: (kol.get(x["powaga"], 9), x["funkcja"])), 1):
            print("\n%d. [%s] %s  (x%d)" % (i, z["powaga"], z["funkcja"], z["ile"]))
            print("   co: %s" % z["opis"])
            print("   wejscie: %s" % z["wejscie"])
    print("\n" + "=" * 78)
    czyste = [x for x in PRZEBIEGI if x in OK_FUNKCJE]
    print("BEZ ZARZUTU (%d): %s" % (len(czyste), ", ".join(czyste) if czyste else "-"))
    zostalo = zywe_dzieci()
    print("PROCESY PO TESCIE (pgrep -f %s): %s" % (MARKER, zostalo or "brak - czysto"))
    print("CZAS CALOSCI: %.1f s" % (time.time() - START))
    print("=" * 78)
    return 1 if any(z["powaga"] == "WYSOKA" for z in lista) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260802)
    ap.add_argument("--n", type=int, default=260)
    a = ap.parse_args()
    random.seed(a.seed)
    with open(CFG_PATH, "w") as f:
        f.write("{}")
    try:
        fuzz_args_ochrona(a.seed, max(a.n, 400))
        fuzz_loguj_awake(a.seed, a.n)
        fuzz_run(a.seed, a.n)
        fuzz_wylacznosc(a.seed, a.n)
        fuzz_load_cfg_progi(a.seed, a.n)
        fuzz_fleet(a.seed, a.n)
        fuzz_chip_swiezosc(a.seed, a.n)
        fuzz_report(a.seed, a.n)
        fuzz_stat_znaczniki(a.seed, a.n)
        rc = wypisz_raport(a.seed, a.n)
    except Exception:
        traceback.print_exc()
        rc = 2
    finally:
        subprocess.run(["pkill", "-9", "-f", MARKER], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        os.chmod(TMP, 0o755)
        shutil.rmtree(TMP, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
