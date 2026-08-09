#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fuzz the second round of less-covered coffee-paladin code.

Run with:       python3 tests/test_fuzz2.py
                python3 tests/test_fuzz2.py --seed 7 --n 400

Compared with tests/test_fuzz.py:
  * round 1 asked whether a function raises an exception,
  * round 2 also asks whether a function makes the right decision, for example
    whether a file name can make an AI agent lose protection, make a plain encoder
    gain protection, bypass log throttling, or leave a child process after `run()`.

Rules: everything runs in a temporary directory (TG_BASE), ~/.coffee-paladin stays
untouched, no heavy process is started (only /usr/bin/true, /bin/sleep, and short
python3 -c commands), and the end checks `pgrep` for leftovers.
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
LIMIT_SESJI = 9.0            # Hard limit per function.
LIMIT_CALOSCI = 90.0         # Hard limit for the whole file.
START = time.time()

TMP = tempfile.mkdtemp(prefix="tg-fuzz2-")
os.environ["TG_BASE"] = TMP
os.environ.setdefault("TG_LANG", "en")
os.makedirs(os.path.join(TMP, "managed"), exist_ok=True)

MARKER = "tgfuzz2-%d" % os.getpid()      # Used to find our own processes in pgrep.


def zaladuj(nazwa, plik):
    return SourceFileLoader(nazwa, os.path.join(REPO, plik)).load_module()


guard = zaladuj("tgf2_guard", "guard.py")
fleet = zaladuj("tgf2_fleet", "fleet")
saferun = zaladuj("tgf2_saferun", "safe-run")
treport = zaladuj("tgf2_treport", "thermal-report")
heat = zaladuj("tgf2_heat", "heat")

PRAWDZIWY_RUN = guard.run          # Needed only in the run() session.
guard.run = lambda cmd, timeout=10: ""
saferun.sh = lambda cmd, timeout=15: ""
treport.sh = lambda cmd, timeout=30: ""
heat.sh = lambda cmd, timeout=15: ""

CFG_PATH = os.path.join(TMP, "config.json")
LOG_PATH = os.path.join(TMP, "guard.log")
STATUS_PATH = os.path.join(TMP, "status.json")
HIST_PATH = os.path.join(TMP, "history.csv")
EVENTS_PATH = os.path.join(TMP, "events.log")

# ---------------------------------------------------------------- report

ZNALEZISKA = {}
PRZEBIEGI = {}
OK_FUNKCJE = []


def skroc(x, n=260):
    s = x if isinstance(x, str) else repr(x)
    return s if len(s) <= n else s[:n] + "...<%d chars>" % len(s)


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

    def blad(self, wejscie, exc, powaga="HIGH"):
        self.bledy += 1
        self._dodaj("EXC:" + type(exc).__name__, wejscie,
                    "exception escapes function: %s: %s" % (type(exc).__name__, exc), powaga)

    def bzdura(self, wejscie, opis, powaga="MEDIUM", klucz=None):
        self.bzdury += 1
        self._dodaj(klucz or opis[:60], wejscie, opis, powaga)

    def koniec(self):
        PRZEBIEGI[self.nazwa] = {"przebiegi": self.n,
                                 "sekundy": round(time.time() - self.start, 2),
                                 "bledy": self.bledy, "bzdury": self.bzdury}
        if not self.bledy and not self.bzdury:
            OK_FUNKCJE.append(self.nazwa)


# ================================================================ 1. args_without_paths
#
# The question is not just whether it crashes. It is whether a file can be named so
# an agent process loses protection, or a plain encoder gains it and keeps heating
# the Mac because the guard must not touch it.

ROZSZ_ZNANE = sorted(getattr(guard, "ROZSZERZENIA_DANYCH", (".json", ".csv", ".log", ".txt")))
# Real media and working formats that are not in ROZSZERZENIA_DANYCH.
ROZSZ_NIEZNANE = [".mxf", ".ts", ".m2ts", ".braw", ".r3d", ".exr", ".heif", ".bmp",
                  ".ogv", ".opus", ".wma", ".vob", ".mts", ".jxl", ".dpx", ".cr3",
                  ".mkv.bak", ".mp4.part", ".mov.tmp", ".mp4.crdownload"]
KATALOGI_Z_AGENTEM = ["claude_brain", "codex_out", "mcp_dane", "cursor_projekt",
                      "claude brain", ".vscode_backup"]
KATALOGI_NEUTRALNE = ["wideo", "Movies", "archiwum", "Z_FTP"]
NARZEDZIA = ["ffmpeg", "/opt/homebrew/bin/ffmpeg", "x265", "python3", "HandBrakeCLI"]

# Same check pick_targets performs: guard.py has any(n.lower() in args ...).
NEVER_ARG = list(guard.DEFAULTS["never_arg_patterns"]) + list(guard.OWN_NAMES)


def chroniony(args):
    return any(n.lower() in args for n in NEVER_ARG)


def zadanie_z_danymi(rng):
    """Generate an encoder command for data inside an agent-named directory.

    The command must be pausable. Each variant represents a distinct bypass
    mechanism so the report names the mechanism instead of repeating one finding.
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
        wej, wyj = '"%s"' % wej, '"%s"' % wyj            # Quoted paths.
    elif katalog_jako_arg:
        wyj = os.path.dirname(wyj) + "/"                 # Target directory, not a file.
    narz = rng.choice(NARZEDZIA)
    if guard.is_interpreter(os.path.basename(narz).lower()):
        # For an interpreter, process identity is the executed script, not the
        # video file. `python3 -y -i rec.mkv` is not a real command shape; it only
        # proves python3 is an interpreter. A real Python job has the script first.
        cmd = "%s /Users/x/skrypty/kompresor.py -y -i %s -c:v libx265 -preset slow %s" % (
            narz, wej, wyj)
    else:
        cmd = "%s -y -i %s -c:v libx265 -preset slow %s" % (narz, wej, wyj)
    if " " in kat:
        powod = "space in path (ps splits argument into two tokens)"
    elif nieznane:
        powod = "unusual data-file extension (%s)" % ext
    elif cudzyslow:
        powod = "path in quotes"
    elif katalog_jako_arg:
        powod = "argument is a DIRECTORY, not a file"
    else:
        powod = "typical data-file extension (control variant)"
    return cmd, False, powod        # False = should not be protected.


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
    """Generate a process that must be protected from SIGSTOP."""
    baza = rng.choice(AGENCI)
    styl = rng.random()
    powod = "pattern"
    if styl < 0.2:
        # Agent identity stored in a file whose extension is on the data list.
        baza = rng.choice([
            "node /Users/x/agents/mcp/server.bin",
            "python3 /Users/x/claude/agent.pt",
            "node /Users/x/codex/dist/index.db",
            "python3 /Users/x/cursor/plugin.pdf",
        ])
        powod = "identity in a file with a data extension"
    elif styl < 0.35:
        baza += " --workdir /Users/x/Desktop/wideo/rec.mkv"
        powod = "agent with data-file argument"
    return baza, True, powod


def fuzz_args_ochrona(seed, n):
    s = Sesja("guard.args_without_paths [protection]", seed)
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
        "ffmpeg -i /Users/x/claude_brain/rec.mkv/",       # Path ending with a slash.
    ]
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            if i < len(ekstrema):
                cmd, oczek, powod = ekstrema[i], None, "extreme input"
            elif s.rng.random() < 0.55:
                cmd, oczek, powod = zadanie_z_danymi(s.rng)
            else:
                cmd, oczek, powod = agent(s.rng)
            guard.full_args = lambda pid, _w=cmd: _w
            try:
                out = guard.args_without_paths(s.rng.randint(1, 99999))
            except Exception as e:
                s.blad(cmd, e)
                continue
            if not isinstance(out, str):
                s.bzdura(cmd, "returned %s instead of str" % type(out).__name__, "HIGH",
                         klucz="zly-typ")
                continue
            if oczek is None:
                continue
            jest = chroniony(out)
            if jest and oczek is False:
                s.bzdura(cmd,
                         "PLAIN JOB BECOMES UNTOUCHABLE (%s): after cutting paths, "
                         "%r remains and matches never_arg_patterns. Guard is not allowed to pause it, "
                         "so the Mac keeps heating - exactly the bug this function was built for."
                         % (powod, skroc(out, 90)),
                         "HIGH", klucz="falszywa-ochrona: " + powod)
            elif not jest and oczek is True:
                s.bzdura(cmd,
                         "AGENT LOSES PROTECTION (%s): after cutting paths, %r remains and no pattern "
                         "matches anymore. Such a process can be frozen (SIGSTOP), and the AI agent "
                         "does not come back to life after freezing." % (powod, skroc(out, 90)),
                         "HIGH", klucz="utrata-ochrony: " + powod)
    finally:
        guard.full_args = stary
    s.koniec()


# ================================================================ 2. _loguj_awake

def fuzz_loguj_awake(seed, n):
    s = Sesja("guard._loguj_awake [throttle]", seed)
    zebrane = []
    stary_log, stary_now = guard.log, guard.now
    zegar = {"t": 1000.0}
    guard.log = lambda msg, tag=None: zebrane.append(msg)
    guard.now = lambda: zegar["t"]

    def reset():
        guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0})
        del zebrane[:]

    try:
        # a) 10,000 switches in the same second: verify throttling holds and the
        #    skipped counter reaches the message without growing it by a megabyte.
        reset()
        s.n += 1
        for i in range(10000):
            guard._loguj_awake("KEEP-AWAKE %s" % ("start" if i % 2 else "stop"))
        if len(zebrane) > 2:
            s.bzdura("10,000 switches in the same second",
                     "throttle let %d entries through instead of <=1 per 10 min" % len(zebrane),
                     "MEDIUM", klucz="tlumik-nieszczelny")
        if any(len(x) > 200 for x in zebrane):
            s.bzdura("10,000 switches", "message grew to %d characters"
                     % max(len(x) for x in zebrane), "MEDIUM", klucz="dlugi-komunikat")
        if guard._awake_log["pominiete"] < 0:
            s.bzdura("10,000 switches", "skipped counter is negative", "MEDIUM")

        # b) Verify the skipped counter really reaches the log after 10 minutes.
        reset()
        s.n += 1
        guard._loguj_awake("A")
        for _ in range(500):
            guard._loguj_awake("B")
        zegar["t"] += 601
        guard._loguj_awake("C")
        if not any("przelaczen" in x for x in zebrane[1:]):
            s.bzdura("A, 500xB, +601 s, C",
                     "after throttling 500 events, next entry does not say how many were skipped "
                     "(black box loses event scale)", "LOW", klucz="brak-licznika")

        # c) The same message after any amount of time.
        reset()
        s.n += 1
        guard._loguj_awake("KEEP-AWAKE start")
        ile_przed = len(zebrane)
        for k in range(1, 6):
            zegar["t"] += 86400.0 * k
            guard._loguj_awake("KEEP-AWAKE start")
        if len(zebrane) == ile_przed:
            s.bzdura("same message every 24 h for 5 days",
                     "identical message NEVER reaches the log again (`msg == ostatni` condition "
                     "has no time limit). Keep-awake enabled permanently disappears from the black "
                     "box after the first entry, and skipped counter (%d) grows forever."
                     % guard._awake_log["pominiete"],
                     "MEDIUM", klucz="ten-sam-msg-na-zawsze")

        # d) Clock moved backward by NTP or wake from sleep. now() is time.time(), not monotonic.
        reset()
        s.n += 1
        guard._loguj_awake("X")
        zegar["t"] -= 3600.0
        przed = len(zebrane)
        for _ in range(10):
            zegar["t"] += 60.0
            guard._loguj_awake("Y" if _ % 2 else "Z")
        if len(zebrane) == przed:
            s.bzdura("clock moved back by one hour",
                     "after clock moves backward (NTP/wake from sleep), throttle stays silent until "
                     "real time catches up - keep-awake leaves no trace in log",
                     "LOW", klucz="zegar-w-tyl")

        # e) Random types and lengths.
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
                s.blad(msg, e, "LOW")
    finally:
        guard.log, guard.now = stary_log, stary_now
        guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0})
    s.koniec()


# ================================================================ 3. run()

def zywe_dzieci():
    """Return our child processes from pgrep using the unique command-line marker."""
    try:
        out = subprocess.run(["pgrep", "-f", MARKER], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=5).stdout.decode()
    except Exception:
        return []
    return [x for x in out.split() if x.strip() and x.strip() != str(os.getpid())]


def fuzz_run(seed, n):
    s = Sesja("guard.run [child cleanup]", seed, limit=45.0)
    PY = sys.executable

    def scen(rng, i):
        r = rng.random()
        if r < 0.30:
            return ["/usr/bin/true"], 5, "immediate success"
        if r < 0.45:
            return ["/nie/ma/takiego/programu-" + MARKER], 5, "command does not exist"
        if r < 0.55:
            return "/nie/ma/takiego-" + MARKER, 5, "cmd as string, not list"
        if r < 0.62:
            return ["/usr/bin/false"], 5, "exit code != 0"
        if r < 0.70:
            return [PY, "-c", "print('%s'*10)" % MARKER], 5, "short output"
        if r < 0.78:
            return [PY, "-c", "import sys;sys.stdout.write('%s'+'A'*(4*1024*1024))" % MARKER], \
                   5, "4 MB na stdout"
        if r < 0.86:
            return [PY, "-c",
                    "import signal,time,sys;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                    "sys.stderr.write('%s');time.sleep(30)" % MARKER], 0.15, \
                   "ignores SIGTERM, timeout"
        if r < 0.94:
            # The grandchild must carry the marker in its own command line, or pgrep misses it.
            return ["/bin/sh", "-c",
                    "%s -c 'import time;time.sleep(27)' %s & wait" % (PY, MARKER)], 0.15, \
                   "grandchild surviving child kill"
        return ["/usr/bin/true"], 0, "zero timeout"

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
                s.blad({"cmd": skroc(cmd, 120), "timeout": tmo, "opis": opis}, e, "HIGH")
                continue
            if not isinstance(out, str):
                s.bzdura(opis, "returned %s instead of str" % type(out).__name__, "HIGH",
                         klucz="zly-typ")
            if "does not exist" in opis or "string" in opis:
                continue        # Nothing started, so pgrep would be wasted work.
            time.sleep(0.005)
            zywe = zywe_dzieci()
            if zywe:
                zostawione.update(zywe)
                s.bzdura({"cmd": skroc(cmd, 120), "timeout": tmo},
                         "after run() returns, %d child process(es) are still alive (%s) - "
                         "case: %s" % (len(zywe), ",".join(zywe[:4]), opis),
                         "HIGH" if "grandchild" not in opis else "MEDIUM",
                         klucz="osierocony-proces:" + opis[:20])
                # Clean up immediately so the test does not grow process leftovers.
                subprocess.run(["pkill", "-9", "-f", MARKER], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    finally:
        subprocess.run(["pkill", "-9", "-f", MARKER], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        guard.run = lambda cmd, timeout=10: ""
    s.koniec()


# ================================================================ 4. acquire_exclusive

def uchwyt(r):
    """Return whether acquire_exclusive() returned a lock handle.

    guard.main documents three outcomes: file means this process owns the lock, None
    means someone else owns it, and False means the lock file could not be opened and
    the daemon starts without exclusivity. This fuzzer used to check only `is not None`,
    putting `False` into the handle list and then calling .close() on it. That caused
    AttributeError noise and state drift that once reported a nonexistent double lock.
    """
    return hasattr(r, "close")


def fuzz_wylacznosc(seed, n):
    s = Sesja("guard.acquire_exclusive", seed)
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
                    opis = "clean"
                    for f in uchwyty:
                        f.close()
                    del uchwyty[:]
                    if os.path.isdir(lock):
                        shutil.rmtree(lock, ignore_errors=True)
                    f1 = guard.acquire_exclusive()
                    if not uchwyt(f1):
                        s.bzdura(opis, "first instance did NOT get the lock (returned %r)"
                                 % (f1,), "HIGH", klucz="brak-blokady")
                    else:
                        uchwyty.append(f1)
                elif wariant == 1:
                    opis = "second instance while lock is held"
                    if not uchwyty:
                        continue      # Nobody holds the lock, so there is nothing to check.
                    f2 = guard.acquire_exclusive()
                    if uchwyt(f2):
                        uchwyty.append(f2)
                        s.bzdura(opis, "TWO instances acquired the lock at once - two daemons on "
                                       "one machine can pause each other", "HIGH",
                                 klucz="podwojna-blokada")
                elif wariant == 2:
                    opis = "PID in guard.lock after failed attempt"
                    tresc = ""
                    try:
                        with open(lock) as f:
                            tresc = f.read()
                    except Exception:
                        pass
                    if not tresc.strip():
                        s.bzdura(opis,
                                 "guard.lock is EMPTY even though daemon is alive: the losing instance "
                                 "opens the file in 'w' mode (truncating it) BEFORE trying flock, "
                                 "so every failed startup erases the lock owner's PID",
                                 "MEDIUM", klucz="wyczyszczony-pid")
                elif wariant == 3:
                    opis = "guard.lock is a DIRECTORY"
                    for f in uchwyty:
                        f.close()
                    del uchwyty[:]
                    if os.path.exists(lock):
                        os.unlink(lock)
                    os.makedirs(lock, exist_ok=True)
                    try:
                        r = guard.acquire_exclusive()
                        if uchwyt(r):
                            uchwyty.append(r)
                    except Exception as e:
                        s.blad(opis, e, "MEDIUM")
                    shutil.rmtree(lock, ignore_errors=True)
                elif wariant == 4:
                    opis = "BASE directory is read-only"
                    for f in uchwyty:
                        f.close()
                    del uchwyty[:]
                    if os.path.exists(lock):
                        os.unlink(lock)
                    os.chmod(TMP, 0o500)
                    try:
                        r = guard.acquire_exclusive()
                        if uchwyt(r):
                            uchwyty.append(r)
                    except Exception as e:
                        s.blad(opis, e, "MEDIUM")
                    finally:
                        os.chmod(TMP, 0o755)
                else:
                    opis = "release and reacquire"
                    for f in uchwyty:
                        f.close()
                    del uchwyty[:]
                    r = guard.acquire_exclusive()
                    if r is None:
                        s.bzdura(opis, "after closing the handle, the lock was NOT released",
                                 "HIGH", klucz="blokada-nie-zwolniona")
                    else:
                        uchwyty.append(r)
            except Exception as e:
                s.blad(opis, e, "MEDIUM")
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


# ================================================================ 5. load_cfg: thresholds

RODZINY = (("soc_resume_c", "soc_pause_c", "soc_kill_c", 40.0, 110.0),
           ("batt_resume_c", "batt_pause_c", "batt_kill_c", 20.0, 60.0))

LICZBY_PROGOW = [0, 1, -1, -273.15, 20.0, 39.999, 40.0, 40.1, 45, 60.0, 60.1, 76.0,
                 85.0, 90.0, 109.9, 110.0, 110.1, 1e6, -1e6, 1e308, 1e-323, 0.5,
                 "85", "85.0", "goraco", True, False, None, [85], {"v": 85}]


def fuzz_load_cfg_progi(seed, n):
    s = Sesja("guard.load_cfg [thresholds]", seed)
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            d = {}
            for r, p, k, lo, hi in RODZINY:
                if s.rng.random() < 0.85:
                    if s.rng.random() < 0.5:      # Three values near range boundaries.
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
                s.blad(tekst, e, "HIGH")
                continue
            for r, p, k, lo, hi in RODZINY:
                try:
                    vr, vp, vk = float(cfg[r]), float(cfg[p]), float(cfg[k])
                except Exception as e:
                    s.blad(tekst, e, "HIGH")
                    continue
                if not (vr < vp < vk):
                    s.bzdura(tekst, "after validation, %s thresholds do NOT increase: "
                                    "%s=%.3f %s=%.3f %s=%.3f (equal thresholds = pause/resume "
                                    "loop or SIGTERM at pause threshold)"
                             % (r.split("_")[0], r, vr, p, vp, k, vk),
                             "HIGH", klucz="progi-nie-rosna:" + r.split("_")[0])
                for nazwa, v in ((r, vr), (p, vp), (k, vk)):
                    if not (lo <= v <= hi):
                        s.bzdura(tekst, "after validation, %s=%.3f is outside physical range "
                                        "%.0f-%.0f - range validation did not work"
                                 % (nazwa, v, lo, hi), "HIGH",
                                 klucz="poza-zakresem:" + nazwa)
            # Idempotence: writing corrected config and reading it again must not
            # shift thresholds further, or every restart lowers them by 2 C.
            with open(CFG_PATH, "w") as f:
                json.dump({kk: cfg[kk] for r, p, k, lo, hi in RODZINY for kk in (r, p, k)}, f)
            try:
                cfg2 = guard.load_cfg()
            except Exception as e:
                s.blad(tekst, e, "HIGH")
                continue
            for r, p, k, lo, hi in RODZINY:
                for kk in (r, p, k):
                    if float(cfg[kk]) != float(cfg2[kk]):
                        s.bzdura(tekst, "validation is not idempotent: %s %.3f -> %.3f on "
                                        "reload (every daemon restart moves the threshold)"
                                 % (kk, float(cfg[kk]), float(cfg2[kk])), "MEDIUM",
                                 klucz="brak-idempotencji")
    finally:
        with open(CFG_PATH, "w") as f:
            f.write("{}")
        del guard._zle_typy[:]
    s.koniec()


# ================================================================ 6. fleet.load_hosts

FLEET_DIR = os.path.join(TMP, "flota")

# Characters are written only as escapes; the source has no invisible bytes.
NIEWIDZIALNE = [
    "\u202e",          # RTL override, reverses display order for the rest of the line.
    "\u200b",          # zero-width space
    "\u2028",          # Unicode line separator.
    "\u2029",          # Unicode paragraph separator.
    "\ufeff",          # BOM inside text.
    "\u0301" * 20,     # Zalgo: 20 combining marks.
    "\u3164",          # HANGUL FILLER, "empty" but printable.
    "\u2066", "\u202d",
    "\x1b[2J", "\x1b[1;1H", "\r", "\x07", "\n",
]

# What to look for in the rendered table. Never use an empty string here.
ZAKAZANE_W_WYDRUKU = [("\x1b", "ESC (ANSI sequence)"), ("\r", "CR (clears line)"),
                      ("\x07", "BEL"), ("\u202e", "RTL override"),
                      ("\u200b", "zero-width space"), ("\u2028", "line separator"),
                      ("\ufeff", "BOM")]   # Note: no "\n"; the table has its own newlines.

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
                s.blad(wejscia, e, "HIGH")
                continue
            if not isinstance(hosts, list):
                s.bzdura(wejscia, "load_hosts returned %s" % type(hosts).__name__, "HIGH")
                continue
            for h in hosts:
                lv = h.get("level")
                if not isinstance(lv, int) or isinstance(lv, bool) or not (0 <= lv <= 3):
                    if "_age" in h and h.get("_age") != 1e9:      # .icloud entry has no level.
                        s.bzdura(wejscia, "level after normalization = %r (render uses it to "
                                          "index a 4-element list)" % (lv,), "HIGH",
                                 klucz="level-nieznormalizowany")
            # This is the real test: one broken snapshot cannot crash the fleet table.
            bufor = io.StringIO()
            try:
                with redirect_stdout(bufor):
                    fleet.render(FLEET_DIR)
            except Exception as e:
                s.bzdura(wejscia,
                         "ONE broken snapshot CRASHES THE WHOLE FLEET TABLE: %s: %s "
                         "(operator sees no machines at all, including healthy ones)"
                         % (type(e).__name__, e), "HIGH",
                         klucz="render-EXC:" + type(e).__name__)
                continue
            tekst = bufor.getvalue()
            for zly, nazwa_zlego in ZAKAZANE_W_WYDRUKU:
                if zly and zly in tekst:
                    s.bzdura(wejscia,
                             "%s character from a foreign snapshot reaches the operator terminal "
                             "directly - it can erase already printed rows together with the failure "
                             "warning (_clean_text does not cover this field)" % nazwa_zlego,
                             "HIGH", klucz="wstrzykniecie:" + nazwa_zlego)
    finally:
        shutil.rmtree(FLEET_DIR, ignore_errors=True)
    s.koniec()


# ================================================================ 7. chip_already_hot

def fuzz_chip_swiezosc(seed, n):
    s = Sesja("safe-run.chip_already_hot [freshness]", seed)
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
                r = saferun.chip_already_hot()
            except Exception as e:
                s.blad({"wiek_s": wiek, "status": tresc}, e, "MEDIUM")
                continue
            if not (isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], bool)):
                s.bzdura(tresc, "returned %r instead of (bool, str)" % (r,), "MEDIUM",
                         klucz="zly-typ")
                continue
            goraco = r[0]
            # Oracle 1: a fresh snapshot with a hot chip must stop job start.
            prog = 85.0
            if isinstance(progi, dict) and isinstance(progi.get("pause"), (int, float)):
                prog = float(progi["pause"])
            if (0 <= wiek <= 110 and isinstance(chip, float) and chip == chip
                    and chip not in (float("inf"),) and chip >= prog - 5.0 and not goraco):
                s.bzdura({"wiek_s": wiek, "status": tresc},
                         "fresh snapshot says chip %.1f C at threshold %.1f, but safe-run still "
                         "STARTS the heavy job" % (chip, prog), "HIGH",
                         klucz="przepuszcza-goraco")
            # Oracle 2: a snapshot older than 120 s means the guard is not alive
            # because it writes every 15 s. Product decision: do not block the job,
            # because safe-run must also work where the daemon is absent and refusal
            # would be worse than no supervision. The function must signal this via
            # "STALE" as the second tuple element so safe-run can warn that nobody
            # will watch the job temperature. Silence was the defect; allowing the
            # job is not.
            if wiek > 130 and goraco is False and r[1] != "STALE":
                s.bzdura({"wiek_s": wiek, "status": tresc},
                         "snapshot is %.0f s old (daemon is likely dead), but the function does not "
                         "signal it with 'STALE' - safe-run will not warn the user that the job "
                         "WILL NOT be supervised" % wiek,
                         "MEDIUM", klucz="nieswieza-migawka-bez-ostrzezenia")
            if wiek < 0 and goraco is False and isinstance(chip, float) and chip >= 95:
                s.bzdura({"wiek_s": wiek, "status": tresc},
                         "snapshot from the FUTURE (clock/NTP) is treated as fresh or as missing "
                         "data depending on the difference sign - job start decision depends on "
                         "the clock, not temperature", "LOW",
                         klucz="migawka-z-przyszlosci")
    finally:
        if os.path.exists(STATUS_PATH):
            os.unlink(STATUS_PATH)
    s.koniec()


# ================================================================ 8. thermal-report

def fuzz_report(seed, n):
    s = Sesja("thermal-report [peak + pdf path]", seed)
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

            # --- a) PDF path must stay in the same directory as the text report.
            cel = cele[i % len(cele)]
            pelny = os.path.join(TMP, cel)
            pdf = os.path.splitext(pelny)[0] + ".pdf"
            if os.path.dirname(pdf) != os.path.dirname(pelny):
                s.bzdura(cel, "PDF lands in a DIFFERENT directory than the report: %s -> %s"
                         % (pelny, pdf), "HIGH", klucz="pdf-poza-katalogiem")
            if pdf == pelny or not pdf.endswith(".pdf"):
                s.bzdura(cel, "PDF path came out strange: %r" % pdf, "MEDIUM",
                         klucz="pdf-zla-nazwa")

            # --- b) Peak temperature from history.csv, confidence band 0 < v <= 110.
            #        The upper bound moved from 150 to 110, the Apple Silicon T_j max
            #        described in thermal-report. Rows above it must be counted and
            #        described on a separate line, not silently skipped.
            iter_lines = []
            oczekiwany = 0.0
            for _ in range(s.rng.randint(0, 12)):
                r = s.rng.random()
                if r < 0.6:
                    v = round(s.rng.uniform(30, 109), 1)
                    iter_lines.append("%s 10:00:00,nominal,%s,,,0,10,90,1,100,2.0,0" % (dzis, v))
                    oczekiwany = max(oczekiwany, v)
                elif r < 0.7:
                    v = s.rng.choice(["999.9", "1e400", "nan", "-5", "0", "120.1", "110.5", ""])
                    iter_lines.append("%s 10:00:00,nominal,%s,,,0,10,90,1,100,2.0,0" % (dzis, v))
                elif r < 0.8:
                    iter_lines.append("%s 10:00:00,nominal,88.8" % dzis)        # Truncated line.
                elif r < 0.9:
                    iter_lines.append("2000-01-01 10:00:00,nominal,108.0,,,0,10,90,1,100,2.0,0")
                else:
                    iter_lines.append(s.rng.choice(["", ",,,,,,,,,,,,", "A" * 2000,
                                                 "\x00,\x00,\x00,,,0,0,0,0,0,0,0"]))
            with open(HIST_PATH, "w") as f:
                f.write(naglowek + "\n".join(iter_lines) + "\n")
            with open(LOG_PATH, "w") as f:
                f.write("%s 10:00:00  [PAUSE] PAUSED ffmpeg (pid 1, 90%% CPU) - hot\n" % dzis)
            with open(EVENTS_PATH, "w") as f:
                f.write('{"time": "%s 10:00:00", "type": "HARD", "description": "x"}\n' % dzis)
            if i % 7 == 0:      # hardware.json after manual edit: valid JSON, not an object.
                with open(os.path.join(TMP, "hardware.json"), "w") as f:
                    f.write(s.rng.choice(["[]", '"x"', "5", "null"]))
            else:
                with open(os.path.join(TMP, "hardware.json"), "w") as f:
                    f.write('{"chip": "Apple M4 Pro", "fan_count": 2}')
            wyjscie = os.path.join(TMP, "out_%d.txt" % (i % 3))
            sys.argv = ["thermal-report", "--file", wyjscie, "--days", "2"]
            wej = {"cel": cel, "wierszy": len(iter_lines), "hardware": i % 7 == 0}
            try:
                with redirect_stdout(io.StringIO()):
                    treport.main()
            except Exception as e:
                s.blad(wej, e, "MEDIUM")
                continue
            try:
                with open(wyjscie) as f:
                    tekst = f.read()
            except Exception as e:
                s.blad(wej, e, "MEDIUM")
                continue
            m = re.search(r"PEAK MEASURED CHIP TEMPERATURE: ([0-9.]+) C", tekst)
            if oczekiwany and not m:
                s.bzdura(wej, "report does not show the peak, although a valid %.1f C reading existed"
                         % oczekiwany, "MEDIUM", klucz="brak-szczytu")
            elif m and abs(float(m.group(1)) - oczekiwany) > 0.05:
                s.bzdura(wej, "report peak %.1f C, but highest valid reading was %.1f C"
                         % (float(m.group(1)), oczekiwany), "HIGH", klucz="zly-szczyt")
            if m and "MEASUREMENT TIMELINE" in tekst:
                # The peak must sit below the section header but above measurement
                # rows. The oracle used to compare it to the header position, flagging
                # every correct placement as "inside the axis". The right boundary is
                # the first data row. Compute boundaries from the section header because
                # date-prefixed rows also appear in EVENTS and INTERVENTIONS above this
                # section; a whole-document search found those and produced false hits.
                _od = tekst.index("MEASUREMENT TIMELINE")
                _wiersze = re.search(r"^  \d{4}-\d{2}-\d{2} ", tekst[_od:], re.M)
                _granica = (_od + _wiersze.start()) if _wiersze else len(tekst)
                if tekst.index("PEAK MEASURED") > _granica:
                    s.bzdura(wej, "peak row is INSIDE the measurement axis instead of above it",
                             "LOW", klucz="szczyt-nie-tam")
    finally:
        sys.argv = stary_argv
        for p in (HIST_PATH, EVENTS_PATH, os.path.join(TMP, "hardware.json")):
            if os.path.exists(p):
                os.unlink(p)
    s.koniec()


# ================================================================ 9. day_stats

def fuzz_stat_znaczniki(seed, n):
    s = Sesja("guard.day_stats [markers]", seed)
    dzis = time.strftime("%Y-%m-%d")
    jutro = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    # Process names that themselves contain a parser keyword.
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
                        "%s 10:00:00  [PAUSE] PAUSED x (pid 1)" % jutro,   # Future date.
                        "linia bez daty w ogole",
                        "%s 10:00:00  %s" % (dzis, "A" * (1000000 if i < 8 else 20000)),
                        "%s 10:00:00  CONFIG: odrzucone: never_extra" % dzis,
                        "%s 10:00:00  ОБНАРУЖЕНО "
                        "приостановка"
                        % dzis,                                             # Old Russian entry.
                        "%s 10:00:00  暂停任务" % dzis,     # Old Chinese entry.
                        "%s 10:00:00  PAUSA de la tarea" % dzis,            # Old Spanish entry.
                    ]))
            tresc = "\n".join(linie) + "\n"
            bajty = tresc.encode("utf-8")
            zepsute = s.rng.random() < 0.15
            if zepsute:      # One non-UTF-8 byte at the end of the log.
                bajty = bajty + b"\xff\xfe niepoprawne utf-8\n"
            with open(LOG_PATH, "wb") as f:
                f.write(bajty)
            try:
                st = guard.day_stats()
            except Exception as e:
                s.blad(skroc(tresc, 200), e, "HIGH")
                continue
            if set(st) != {"pauses", "resumes", "kills"}:
                s.bzdura(skroc(tresc, 200), "returned %r" % (st,), "HIGH", klucz="zly-typ")
                continue
            if zepsute and sum(ocz.values()) and not sum(st.values()):
                s.bzdura(skroc(tresc, 200),
                         "ONE non-UTF-8 byte in guard.log ERASES THE WHOLE DAY STATISTICS: "
                         "the log had %d interventions, the function returns all zeros. The file "
                         "is read in blocks, so a bad byte at the end breaks the decoder already "
                         "on the first readline(), and `except Exception` swallows it silently - "
                         "the menu bar shows 'today 0 pauses' after a night full of pauses"
                         % sum(ocz.values()), "MEDIUM", klucz="log-nie-utf8-zeruje")
            for k in ocz:
                if st[k] < ocz[k] and not zepsute:
                    s.bzdura(skroc(tresc, 300),
                             "LOSES events: %s=%d, but the log had %d (menu bar day statistics "
                             "show fewer interventions than really happened)"
                             % (k, st[k], ocz[k]), "MEDIUM", klucz="gubi:" + k)
                elif st[k] > ocz[k] + 6 and not zepsute:
                    s.bzdura(skroc(tresc, 300),
                             "COUNTS TOO MUCH: %s=%d with %d real events - a process name "
                             "containing a keyword (for example 'sigterm_bench') is counted "
                             "as an event, and condition order assigns it to kills"
                             % (k, st[k], ocz[k]), "LOW", klucz="liczy-za-duzo:" + k)
    finally:
        if os.path.exists(LOG_PATH):
            os.unlink(LOG_PATH)
    s.koniec()


# ================================================================ report

def wypisz_raport(seed, n):
    print("=" * 78)
    print("FUZZING ROUND 2 (code from the night of 2026-08-02) - seed %s, ~%d inputs per function" % (seed, n))
    print("working directory (TG_BASE): %s" % TMP)
    print("=" * 78)
    print("\n%-42s %8s %7s %7s %7s" % ("function", "runs", "sec", "errors", "findings"))
    print("-" * 78)
    for nazwa, d in PRZEBIEGI.items():
        print("%-42s %8d %7.2f %7d %7d"
              % (nazwa, d["przebiegi"], d["sekundy"], d["bledy"], d["bzdury"]))
    print("\n" + "=" * 78)
    lista = list(ZNALEZISKA.values())
    if not lista:
        print("FINDINGS: none - everything survived the fuzzing.")
    else:
        print("FINDINGS (%d distinct; x = number of inputs that triggered it):" % len(lista))
        kol = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        for i, z in enumerate(sorted(lista, key=lambda x: (kol.get(x["powaga"], 9), x["funkcja"])), 1):
            print("\n%d. [%s] %s  (x%d)" % (i, z["powaga"], z["funkcja"], z["ile"]))
            print("   what: %s" % z["opis"])
            print("   input: %s" % z["wejscie"])
    print("\n" + "=" * 78)
    czyste = [x for x in PRZEBIEGI if x in OK_FUNKCJE]
    print("CLEAN (%d): %s" % (len(czyste), ", ".join(czyste) if czyste else "-"))
    zostalo = zywe_dzieci()
    print("PROCESSES AFTER TEST (pgrep -f %s): %s" % (MARKER, zostalo or "none - clean"))
    print("TOTAL TIME: %.1f s" % (time.time() - START))
    print("=" * 78)
    return 1 if any(z["powaga"] == "HIGH" for z in lista) else 0


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
