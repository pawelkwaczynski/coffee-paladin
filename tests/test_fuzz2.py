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
SESSION_LIMIT_SECONDS = 9.0            # Hard limit per function.
TOTAL_LIMIT_SECONDS = 90.0         # Hard limit for the whole file.
START = time.time()

TMP = tempfile.mkdtemp(prefix="tg-fuzz2-")
os.environ["TG_BASE"] = TMP
os.environ.setdefault("TG_LANG", "en")
os.makedirs(os.path.join(TMP, "managed"), exist_ok=True)

MARKER = "tgfuzz2-%d" % os.getpid()      # Used to find our own processes in pgrep.


def load_module(name, file_path):
    return SourceFileLoader(name, os.path.join(REPO, file_path)).load_module()


guard = load_module("tgf2_guard", "guard.py")
fleet = load_module("tgf2_fleet", "fleet")
saferun = load_module("tgf2_saferun", "safe-run")
treport = load_module("tgf2_treport", "thermal-report")
heat = load_module("tgf2_heat", "heat")

REAL_RUN = guard.run          # Needed only in the run() session.
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

FINDINGS = {}
RUNS = {}
OK_FUNCTIONS = []


def shorten(x, n=260):
    s = x if isinstance(x, str) else repr(x)
    return s if len(s) <= n else s[:n] + "...<%d chars>" % len(s)


class Session(object):
    def __init__(self, name, seed, limit=SESSION_LIMIT_SECONDS):
        self.name = name
        self.rng = random.Random("%s|%s" % (seed, name))
        self.start = time.time()
        self.limit = limit
        self.n = 0
        self.errors = 0
        self.bzdury = 0

    def time_elapsed(self):
        return (time.time() - self.start > self.limit
                or time.time() - START > TOTAL_LIMIT_SECONDS - 4)

    def _add(self, key, input_value, description, severity):
        k = (self.name, key)
        if k in FINDINGS:
            FINDINGS[k]["ile"] += 1
            return
        FINDINGS[k] = {"funkcja": self.name, "wejscie": shorten(input_value),
                         "opis": description, "powaga": severity, "ile": 1}

    def error(self, input_value, exc, severity="HIGH"):
        self.errors += 1
        self._add("EXC:" + type(exc).__name__, input_value,
                    "exception escapes function: %s: %s" % (type(exc).__name__, exc), severity)

    def nonsense(self, input_value, description, severity="MEDIUM", key=None):
        self.bzdury += 1
        self._add(key or description[:60], input_value, description, severity)

    def finish(self):
        RUNS[self.name] = {"przebiegi": self.n,
                                 "sekundy": round(time.time() - self.start, 2),
                                 "bledy": self.errors, "bzdury": self.bzdury}
        if not self.errors and not self.bzdury:
            OK_FUNCTIONS.append(self.name)


# ================================================================ 1. args_without_paths
#
# The question is not just whether it crashes. It is whether a file can be named so
# an agent process loses protection, or a plain encoder gains it and keeps heating
# the Mac because the guard must not touch it.

KNOWN_EXTS = sorted(getattr(guard, "ROZSZERZENIA_DANYCH", (".json", ".csv", ".log", ".txt")))
# Real media and working formats that are not in ROZSZERZENIA_DANYCH.
UNKNOWN_EXTS = [".mxf", ".ts", ".m2ts", ".braw", ".r3d", ".exr", ".heif", ".bmp",
                  ".ogv", ".opus", ".wma", ".vob", ".mts", ".jxl", ".dpx", ".cr3",
                  ".mkv.bak", ".mp4.part", ".mov.tmp", ".mp4.crdownload"]
AGENT_DIRS = ["claude_brain", "codex_out", "mcp_dane", "cursor_projekt",
                      "claude brain", ".vscode_backup"]
NEUTRAL_DIRS = ["wideo", "Movies", "archiwum", "Z_FTP"]
TOOLS = ["ffmpeg", "/opt/homebrew/bin/ffmpeg", "x265", "python3", "HandBrakeCLI"]

# Same check pick_targets performs: guard.py has any(n.lower() in args ...).
NEVER_ARG = list(guard.DEFAULTS["never_arg_patterns"]) + list(guard.OWN_NAMES)


def protected(args):
    return any(n.lower() in args for n in NEVER_ARG)


def data_job(rng):
    """Generate an encoder command for data inside an agent-named directory.

    The command must be pausable. Each variant represents a distinct bypass
    mechanism so the report names the mechanism instead of repeating one finding.
    """
    kat = rng.choice(AGENT_DIRS)
    nieznane = rng.random() < 0.5
    ext = rng.choice(UNKNOWN_EXTS if nieznane else KNOWN_EXTS)
    input_path = "/Users/x/Desktop/%s/wideo/rec%s" % (kat, ext)
    output_path = "/Users/x/Desktop/%s/out/rec_x265%s" % (kat, rng.choice(KNOWN_EXTS))
    styl = rng.random()
    quoted = styl < 0.2
    dir_as_arg = 0.2 <= styl < 0.35
    if quoted:
        input_path, output_path = '"%s"' % input_path, '"%s"' % output_path            # Quoted paths.
    elif dir_as_arg:
        output_path = os.path.dirname(output_path) + "/"                 # Target directory, not a file.
    narz = rng.choice(TOOLS)
    if guard.is_interpreter(os.path.basename(narz).lower()):
        # For an interpreter, process identity is the executed script, not the
        # video file. `python3 -y -i rec.mkv` is not a real command shape; it only
        # proves python3 is an interpreter. A real Python job has the script first.
        cmd = "%s /Users/x/skrypty/kompresor.py -y -i %s -c:v libx265 -preset slow %s" % (
            narz, input_path, output_path)
    else:
        cmd = "%s -y -i %s -c:v libx265 -preset slow %s" % (narz, input_path, output_path)
    if " " in kat:
        reason = "space in path (ps splits argument into two tokens)"
    elif nieznane:
        reason = "unusual data-file extension (%s)" % ext
    elif quoted:
        reason = "path in quotes"
    elif dir_as_arg:
        reason = "argument is a DIRECTORY, not a file"
    else:
        reason = "typical data-file extension (control variant)"
    return cmd, False, reason        # False = should not be protected.


AGENTS = [
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
    base_data = rng.choice(AGENTS)
    styl = rng.random()
    reason = "pattern"
    if styl < 0.2:
        # Agent identity stored in a file whose extension is on the data list.
        base_data = rng.choice([
            "node /Users/x/agents/mcp/server.bin",
            "python3 /Users/x/claude/agent.pt",
            "node /Users/x/codex/dist/index.db",
            "python3 /Users/x/cursor/plugin.pdf",
        ])
        reason = "identity in a file with a data extension"
    elif styl < 0.35:
        base_data += " --workdir /Users/x/Desktop/wideo/rec.mkv"
        reason = "agent with data-file argument"
    return base_data, True, reason


def fuzz_args_protection(seed, n):
    s = Session("guard.args_without_paths [protection]", seed)
    old = guard.full_args
    extremes = [
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
            if s.time_elapsed():
                break
            s.n += 1
            if i < len(extremes):
                cmd, oczek, reason = extremes[i], None, "extreme input"
            elif s.rng.random() < 0.55:
                cmd, oczek, reason = data_job(s.rng)
            else:
                cmd, oczek, reason = agent(s.rng)
            guard.full_args = lambda pid, _w=cmd: _w
            try:
                out = guard.args_without_paths(s.rng.randint(1, 99999))
            except Exception as e:
                s.error(cmd, e)
                continue
            if not isinstance(out, str):
                s.nonsense(cmd, "returned %s instead of str" % type(out).__name__, "HIGH",
                         key="zly-typ")
                continue
            if oczek is None:
                continue
            present = protected(out)
            if present and oczek is False:
                s.nonsense(cmd,
                         "PLAIN JOB BECOMES UNTOUCHABLE (%s): after cutting paths, "
                         "%r remains and matches never_arg_patterns. Guard is not allowed to pause it, "
                         "so the Mac keeps heating - exactly the bug this function was built for."
                         % (reason, shorten(out, 90)),
                         "HIGH", key="falszywa-ochrona: " + reason)
            elif not present and oczek is True:
                s.nonsense(cmd,
                         "AGENT LOSES PROTECTION (%s): after cutting paths, %r remains and no pattern "
                         "matches anymore. Such a process can be frozen (SIGSTOP), and the AI agent "
                         "does not come back to life after freezing." % (reason, shorten(out, 90)),
                         "HIGH", key="utrata-ochrony: " + reason)
    finally:
        guard.full_args = old
    s.finish()


# ================================================================ 2. _loguj_awake

def fuzz_log_awake(seed, n):
    s = Session("guard._loguj_awake [throttle]", seed)
    collected = []
    old_log, old_now = guard.log, guard.now
    clock = {"t": 1000.0}
    guard.log = lambda msg, tag=None: collected.append(msg)
    guard.now = lambda: clock["t"]

    def reset():
        guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0})
        del collected[:]

    try:
        # a) 10,000 switches in the same second: verify throttling holds and the
        #    skipped counter reaches the message without growing it by a megabyte.
        reset()
        s.n += 1
        for i in range(10000):
            guard._loguj_awake("KEEP-AWAKE %s" % ("start" if i % 2 else "stop"))
        if len(collected) > 2:
            s.nonsense("10,000 switches in the same second",
                     "throttle let %d entries through instead of <=1 per 10 min" % len(collected),
                     "MEDIUM", key="tlumik-nieszczelny")
        if any(len(x) > 200 for x in collected):
            s.nonsense("10,000 switches", "message grew to %d characters"
                     % max(len(x) for x in collected), "MEDIUM", key="dlugi-komunikat")
        if guard._awake_log["pominiete"] < 0:
            s.nonsense("10,000 switches", "skipped counter is negative", "MEDIUM")

        # b) Verify the skipped counter really reaches the log after 10 minutes.
        reset()
        s.n += 1
        guard._loguj_awake("A")
        for _ in range(500):
            guard._loguj_awake("B")
        clock["t"] += 601
        guard._loguj_awake("C")
        if not any("przelaczen" in x for x in collected[1:]):
            s.nonsense("A, 500xB, +601 s, C",
                     "after throttling 500 events, next entry does not say how many were skipped "
                     "(black box loses event scale)", "LOW", key="brak-licznika")

        # c) The same message after any amount of time.
        reset()
        s.n += 1
        guard._loguj_awake("KEEP-AWAKE start")
        count_before = len(collected)
        for k in range(1, 6):
            clock["t"] += 86400.0 * k
            guard._loguj_awake("KEEP-AWAKE start")
        if len(collected) == count_before:
            s.nonsense("same message every 24 h for 5 days",
                     "identical message NEVER reaches the log again (`msg == ostatni` condition "
                     "has no time limit). Keep-awake enabled permanently disappears from the black "
                     "box after the first entry, and skipped counter (%d) grows forever."
                     % guard._awake_log["pominiete"],
                     "MEDIUM", key="ten-sam-msg-na-zawsze")

        # d) Clock moved backward by NTP or wake from sleep. now() is time.time(), not monotonic.
        reset()
        s.n += 1
        guard._loguj_awake("X")
        clock["t"] -= 3600.0
        before = len(collected)
        for _ in range(10):
            clock["t"] += 60.0
            guard._loguj_awake("Y" if _ % 2 else "Z")
        if len(collected) == before:
            s.nonsense("clock moved back by one hour",
                     "after clock moves backward (NTP/wake from sleep), throttle stays silent until "
                     "real time catches up - keep-awake leaves no trace in log",
                     "LOW", key="zegar-w-tyl")

        # e) Random types and lengths.
        variants = [None, 0, 1, -1, True, 3.5, [], {}, b"bajty", "\x00", "\x1b[2J",
                    "A" * 100000, "%s %d", "‮ rtl", object()]
        for i in range(max(0, n - 5)):
            if s.time_elapsed():
                break
            s.n += 1
            if s.rng.random() < 0.4:
                guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0})
            clock["t"] += s.rng.choice([0.0, 0.1, 700.0])
            msg = variants[i % len(variants)] if i < 60 else s.rng.choice(variants)
            try:
                guard._loguj_awake(msg)
            except Exception as e:
                s.error(msg, e, "LOW")
    finally:
        guard.log, guard.now = old_log, old_now
        guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0})
    s.finish()


# ================================================================ 3. run()

def live_children():
    """Return our child processes from pgrep using the unique command-line marker."""
    try:
        out = subprocess.run(["pgrep", "-f", MARKER], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=5).stdout.decode()
    except Exception:
        return []
    return [x for x in out.split() if x.strip() and x.strip() != str(os.getpid())]


def fuzz_run(seed, n):
    s = Session("guard.run [child cleanup]", seed, limit=45.0)
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

    left_behind = set()
    try:
        guard.run = REAL_RUN
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            cmd, tmo, description = scen(s.rng, i)
            try:
                out = guard.run(cmd, timeout=tmo)
            except Exception as e:
                s.error({"cmd": shorten(cmd, 120), "timeout": tmo, "opis": description}, e, "HIGH")
                continue
            if not isinstance(out, str):
                s.nonsense(description, "returned %s instead of str" % type(out).__name__, "HIGH",
                         key="zly-typ")
            if "does not exist" in description or "string" in description:
                continue        # Nothing started, so pgrep would be wasted work.
            time.sleep(0.005)
            alive = live_children()
            if alive:
                left_behind.update(alive)
                s.nonsense({"cmd": shorten(cmd, 120), "timeout": tmo},
                         "after run() returns, %d child process(es) are still alive (%s) - "
                         "case: %s" % (len(alive), ",".join(alive[:4]), description),
                         "HIGH" if "grandchild" not in description else "MEDIUM",
                         key="osierocony-proces:" + description[:20])
                # Clean up immediately so the test does not grow process leftovers.
                subprocess.run(["pkill", "-9", "-f", MARKER], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    finally:
        subprocess.run(["pkill", "-9", "-f", MARKER], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        guard.run = lambda cmd, timeout=10: ""
    s.finish()


# ================================================================ 4. acquire_exclusive

def handle(r):
    """Return whether acquire_exclusive() returned a lock handle.

    guard.main documents three outcomes: file means this process owns the lock, None
    means someone else owns it, and False means the lock file could not be opened and
    the daemon starts without exclusivity. This fuzzer used to check only `is not None`,
    putting `False` into the handle list and then calling .close() on it. That caused
    AttributeError noise and state drift that once reported a nonexistent double lock.
    """
    return hasattr(r, "close")


def fuzz_exclusivity(seed, n):
    s = Session("guard.acquire_exclusive", seed)
    lock = os.path.join(TMP, "guard.lock")
    handles = []
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            variant = i % 6
            description = ""
            try:
                if variant == 0:
                    description = "clean"
                    for f in handles:
                        f.close()
                    del handles[:]
                    if os.path.isdir(lock):
                        shutil.rmtree(lock, ignore_errors=True)
                    f1 = guard.acquire_exclusive()
                    if not handle(f1):
                        s.nonsense(description, "first instance did NOT get the lock (returned %r)"
                                 % (f1,), "HIGH", key="brak-blokady")
                    else:
                        handles.append(f1)
                elif variant == 1:
                    description = "second instance while lock is held"
                    if not handles:
                        continue      # Nobody holds the lock, so there is nothing to check.
                    f2 = guard.acquire_exclusive()
                    if handle(f2):
                        handles.append(f2)
                        s.nonsense(description, "TWO instances acquired the lock at once - two daemons on "
                                       "one machine can pause each other", "HIGH",
                                 key="podwojna-blokada")
                elif variant == 2:
                    description = "PID in guard.lock after failed attempt"
                    content = ""
                    try:
                        with open(lock) as f:
                            content = f.read()
                    except Exception:
                        pass
                    if not content.strip():
                        s.nonsense(description,
                                 "guard.lock is EMPTY even though daemon is alive: the losing instance "
                                 "opens the file in 'w' mode (truncating it) BEFORE trying flock, "
                                 "so every failed startup erases the lock owner's PID",
                                 "MEDIUM", key="wyczyszczony-pid")
                elif variant == 3:
                    description = "guard.lock is a DIRECTORY"
                    for f in handles:
                        f.close()
                    del handles[:]
                    if os.path.exists(lock):
                        os.unlink(lock)
                    os.makedirs(lock, exist_ok=True)
                    try:
                        r = guard.acquire_exclusive()
                        if handle(r):
                            handles.append(r)
                    except Exception as e:
                        s.error(description, e, "MEDIUM")
                    shutil.rmtree(lock, ignore_errors=True)
                elif variant == 4:
                    description = "BASE directory is read-only"
                    for f in handles:
                        f.close()
                    del handles[:]
                    if os.path.exists(lock):
                        os.unlink(lock)
                    os.chmod(TMP, 0o500)
                    try:
                        r = guard.acquire_exclusive()
                        if handle(r):
                            handles.append(r)
                    except Exception as e:
                        s.error(description, e, "MEDIUM")
                    finally:
                        os.chmod(TMP, 0o755)
                else:
                    description = "release and reacquire"
                    for f in handles:
                        f.close()
                    del handles[:]
                    r = guard.acquire_exclusive()
                    if r is None:
                        s.nonsense(description, "after closing the handle, the lock was NOT released",
                                 "HIGH", key="blokada-nie-zwolniona")
                    else:
                        handles.append(r)
            except Exception as e:
                s.error(description, e, "MEDIUM")
    finally:
        for f in handles:
            try:
                f.close()
            except Exception:
                pass
        os.chmod(TMP, 0o755)
        if os.path.isdir(lock):
            shutil.rmtree(lock, ignore_errors=True)
    s.finish()


# ================================================================ 5. load_cfg: thresholds

FAMILIES = (("soc_resume_c", "soc_pause_c", "soc_kill_c", 40.0, 110.0),
           ("batt_resume_c", "batt_pause_c", "batt_kill_c", 20.0, 60.0))

THRESHOLD_NUMBERS = [0, 1, -1, -273.15, 20.0, 39.999, 40.0, 40.1, 45, 60.0, 60.1, 76.0,
                 85.0, 90.0, 109.9, 110.0, 110.1, 1e6, -1e6, 1e308, 1e-323, 0.5,
                 "85", "85.0", "goraco", True, False, None, [85], {"v": 85}]


def fuzz_load_cfg_thresholds(seed, n):
    s = Session("guard.load_cfg [thresholds]", seed)
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            d = {}
            for r, p, k, lo, hi in FAMILIES:
                if s.rng.random() < 0.85:
                    if s.rng.random() < 0.5:      # Three values near range boundaries.
                        base_data = s.rng.choice([lo, hi, (lo + hi) / 2.0])
                        d[r] = base_data + s.rng.choice([-2, -0.001, 0, 0.001, 2])
                        d[p] = base_data + s.rng.choice([-4, 0, 0.002, 4])
                        d[k] = base_data + s.rng.choice([-6, 0, 0.003, 6])
                    else:
                        d[r] = s.rng.choice(THRESHOLD_NUMBERS)
                        d[p] = s.rng.choice(THRESHOLD_NUMBERS)
                        d[k] = s.rng.choice(THRESHOLD_NUMBERS)
            try:
                text = json.dumps(d, allow_nan=True)
            except Exception:
                continue
            with open(CFG_PATH, "w") as f:
                f.write(text)
            del guard._zle_typy[:]
            try:
                cfg = guard.load_cfg()
            except Exception as e:
                s.error(text, e, "HIGH")
                continue
            for r, p, k, lo, hi in FAMILIES:
                try:
                    vr, vp, vk = float(cfg[r]), float(cfg[p]), float(cfg[k])
                except Exception as e:
                    s.error(text, e, "HIGH")
                    continue
                if not (vr < vp < vk):
                    s.nonsense(text, "after validation, %s thresholds do NOT increase: "
                                    "%s=%.3f %s=%.3f %s=%.3f (equal thresholds = pause/resume "
                                    "loop or SIGTERM at pause threshold)"
                             % (r.split("_")[0], r, vr, p, vp, k, vk),
                             "HIGH", key="progi-nie-rosna:" + r.split("_")[0])
                for name, v in ((r, vr), (p, vp), (k, vk)):
                    if not (lo <= v <= hi):
                        s.nonsense(text, "after validation, %s=%.3f is outside physical range "
                                        "%.0f-%.0f - range validation did not work"
                                 % (name, v, lo, hi), "HIGH",
                                 key="poza-zakresem:" + name)
            # Idempotence: writing corrected config and reading it again must not
            # shift thresholds further, or every restart lowers them by 2 C.
            with open(CFG_PATH, "w") as f:
                json.dump({kk: cfg[kk] for r, p, k, lo, hi in FAMILIES for kk in (r, p, k)}, f)
            try:
                cfg2 = guard.load_cfg()
            except Exception as e:
                s.error(text, e, "HIGH")
                continue
            for r, p, k, lo, hi in FAMILIES:
                for kk in (r, p, k):
                    if float(cfg[kk]) != float(cfg2[kk]):
                        s.nonsense(text, "validation is not idempotent: %s %.3f -> %.3f on "
                                        "reload (every daemon restart moves the threshold)"
                                 % (kk, float(cfg[kk]), float(cfg2[kk])), "MEDIUM",
                                 key="brak-idempotencji")
    finally:
        with open(CFG_PATH, "w") as f:
            f.write("{}")
        del guard._zle_typy[:]
    s.finish()


# ================================================================ 6. fleet.load_hosts

FLEET_DIR = os.path.join(TMP, "flota")

# Characters are written only as escapes; the source has no invisible bytes.
INVISIBLE = [
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
FORBIDDEN_IN_OUTPUT = [("\x1b", "ESC (ANSI sequence)"), ("\r", "CR (clears line)"),
                      ("\x07", "BEL"), ("\u202e", "RTL override"),
                      ("\u200b", "zero-width space"), ("\u2028", "line separator"),
                      ("\ufeff", "BOM")]   # Note: no "\n"; the table has its own newlines.

HOSTILE_SNAPSHOTS = [
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


def random_snapshot(rng):
    d = {}
    fields = ["host", "model", "chip_c", "watts", "ram_used_gb", "ram_total_gb",
            "disk_used_pct", "battery_pct", "cpu_limit", "level", "fans", "paused",
            "stats", "last_hard_shutdown", "on_ac"]
    for k in rng.sample(fields, rng.randint(1, len(fields))):
        r = rng.random()
        if r < 0.2:
            d[k] = rng.choice(["", "0", "nan", "inf", "-1", "3.5", "abc",
                               rng.choice(INVISIBLE) + "host"])
        elif r < 0.4:
            d[k] = rng.choice([0, 1, -1, 3, 4, 99, 10 ** 40, 1e308, float("nan"),
                               float("inf"), -0.0])
        elif r < 0.55:
            d[k] = rng.choice([None, True, False])
        elif r < 0.75:
            d[k] = rng.choice([[], [1200, 0], ["x"], [None], [{"a": 1}],
                               [rng.choice(INVISIBLE) + "proc"]])
        else:
            d[k] = rng.choice([{}, {"pauses": 1}, {"pauses": "x"},
                               {"time": rng.choice(INVISIBLE) + "2026-08-02"}])
    return d


def fuzz_fleet(seed, n):
    s = Session("fleet.load_hosts + render", seed)
    if os.path.isdir(FLEET_DIR):
        shutil.rmtree(FLEET_DIR, ignore_errors=True)
    os.makedirs(FLEET_DIR, exist_ok=True)
    names = ["mbp.json", "neo.json", ".ukryty.json", "render-01.json.icloud",
             "host bez rozszerzenia", "‮evil.json"]
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            for f in os.listdir(FLEET_DIR):
                try:
                    os.unlink(os.path.join(FLEET_DIR, f))
                except Exception:
                    pass
            inputs = {}
            if i < len(HOSTILE_SNAPSHOTS):
                contents = [HOSTILE_SNAPSHOTS[i]]
            else:
                contents = []
                for _ in range(s.rng.randint(1, 3)):
                    if s.rng.random() < 0.3:
                        contents.append(s.rng.choice(HOSTILE_SNAPSHOTS))
                    else:
                        try:
                            contents.append(json.dumps(random_snapshot(s.rng), allow_nan=True))
                        except Exception:
                            contents.append("{}")
            for j, t in enumerate(contents):
                name = names[(i + j) % len(names)] if i < 40 else s.rng.choice(names)
                p = os.path.join(FLEET_DIR, name)
                with open(p, "wb") as f:
                    f.write(t.encode("utf-8", "surrogateescape"))
                inputs[name] = shorten(t, 120)
            try:
                hosts = fleet.load_hosts(FLEET_DIR)
            except Exception as e:
                s.error(inputs, e, "HIGH")
                continue
            if not isinstance(hosts, list):
                s.nonsense(inputs, "load_hosts returned %s" % type(hosts).__name__, "HIGH")
                continue
            for h in hosts:
                lv = h.get("level")
                if not isinstance(lv, int) or isinstance(lv, bool) or not (0 <= lv <= 3):
                    if "_age" in h and h.get("_age") != 1e9:      # .icloud entry has no level.
                        s.nonsense(inputs, "level after normalization = %r (render uses it to "
                                          "index a 4-element list)" % (lv,), "HIGH",
                                 key="level-nieznormalizowany")
            # This is the real test: one broken snapshot cannot crash the fleet table.
            buffer = io.StringIO()
            try:
                with redirect_stdout(buffer):
                    fleet.render(FLEET_DIR)
            except Exception as e:
                s.nonsense(inputs,
                         "ONE broken snapshot CRASHES THE WHOLE FLEET TABLE: %s: %s "
                         "(operator sees no machines at all, including healthy ones)"
                         % (type(e).__name__, e), "HIGH",
                         key="render-EXC:" + type(e).__name__)
                continue
            text = buffer.getvalue()
            for bad_value, bad_name in FORBIDDEN_IN_OUTPUT:
                if bad_value and bad_value in text:
                    s.nonsense(inputs,
                             "%s character from a foreign snapshot reaches the operator terminal "
                             "directly - it can erase already printed rows together with the failure "
                             "warning (_clean_text does not cover this field)" % bad_name,
                             "HIGH", key="wstrzykniecie:" + bad_name)
    finally:
        shutil.rmtree(FLEET_DIR, ignore_errors=True)
    s.finish()


# ================================================================ 7. chip_already_hot

def fuzz_chip_freshness(seed, n):
    s = Session("safe-run.chip_already_hot [freshness]", seed)
    ages = [0, 1, 60, 119, 119.9, 120, 120.1, 121, 300, 86400, -30, -1e6]
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            age = ages[i % len(ages)] if i < 60 else s.rng.choice(ages)
            chip = s.rng.choice([None, 0.0, 60.0, 79.9, 80.0, 80.1, 85.0, 92.0, 130.0,
                                 float("nan"), float("inf"), "85", "goraco"])
            lvl = s.rng.choice([0, 1, 2, 3, "2", None, True, 99, -1, float("nan")])
            thresholds = s.rng.choice([None, {}, {"pause": 85.0}, {"pause": 78.0},
                                  {"pause": "85"}, {"pause": None}, {"pause": float("nan")},
                                  [85.0], "85"])
            d = {"level": lvl, "chip_c": chip, "thresholds": thresholds}
            try:
                content = json.dumps(d, allow_nan=True)
            except Exception:
                continue
            with open(STATUS_PATH, "w") as f:
                f.write(content)
            os.utime(STATUS_PATH, (time.time() - age, time.time() - age))
            try:
                r = saferun.chip_already_hot()
            except Exception as e:
                s.error({"wiek_s": age, "status": content}, e, "MEDIUM")
                continue
            if not (isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], bool)):
                s.nonsense(content, "returned %r instead of (bool, str)" % (r,), "MEDIUM",
                         key="zly-typ")
                continue
            hot = r[0]
            # Oracle 1: a fresh snapshot with a hot chip must stop job start.
            threshold = 85.0
            if isinstance(thresholds, dict) and isinstance(thresholds.get("pause"), (int, float)):
                threshold = float(thresholds["pause"])
            if (0 <= age <= 110 and isinstance(chip, float) and chip == chip
                    and chip not in (float("inf"),) and chip >= threshold - 5.0 and not hot):
                s.nonsense({"wiek_s": age, "status": content},
                         "fresh snapshot says chip %.1f C at threshold %.1f, but safe-run still "
                         "STARTS the heavy job" % (chip, threshold), "HIGH",
                         key="przepuszcza-goraco")
            # Oracle 2: a snapshot older than 120 s means the guard is not alive
            # because it writes every 15 s. Product decision: do not block the job,
            # because safe-run must also work where the daemon is absent and refusal
            # would be worse than no supervision. The function must signal this via
            # "STALE" as the second tuple element so safe-run can warn that nobody
            # will watch the job temperature. Silence was the defect; allowing the
            # job is not.
            if age > 130 and hot is False and r[1] != "STALE":
                s.nonsense({"wiek_s": age, "status": content},
                         "snapshot is %.0f s old (daemon is likely dead), but the function does not "
                         "signal it with 'STALE' - safe-run will not warn the user that the job "
                         "WILL NOT be supervised" % age,
                         "MEDIUM", key="nieswieza-migawka-bez-ostrzezenia")
            if age < 0 and hot is False and isinstance(chip, float) and chip >= 95:
                s.nonsense({"wiek_s": age, "status": content},
                         "snapshot from the FUTURE (clock/NTP) is treated as fresh or as missing "
                         "data depending on the difference sign - job start decision depends on "
                         "the clock, not temperature", "LOW",
                         key="migawka-z-przyszlosci")
    finally:
        if os.path.exists(STATUS_PATH):
            os.unlink(STATUS_PATH)
    s.finish()


# ================================================================ 8. thermal-report

def fuzz_report(seed, n):
    s = Session("thermal-report [peak + pdf path]", seed)
    targets = ["raport.txt", "raport", "raport.tar.gz", ".ukryty", "raport.", "a.b/raport",
            "a.b/raport.txt", "kat.z.kropka/raport.txt", "raport z odstepem.txt",
            "raport\x1b.txt", "‮raport.txt", "raport.PDF", "raport..txt"]
    today = time.strftime("%Y-%m-%d")
    naglowek = "time,thermal_state,chip_C,gpu_C,battery_C,fan_rpm,watts,batt_pct,on_ac,cpu_limit,load1,level\n"
    old_argv = sys.argv
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1

            # --- a) PDF path must stay in the same directory as the text report.
            target = targets[i % len(targets)]
            pelny = os.path.join(TMP, target)
            pdf = os.path.splitext(pelny)[0] + ".pdf"
            if os.path.dirname(pdf) != os.path.dirname(pelny):
                s.nonsense(target, "PDF lands in a DIFFERENT directory than the report: %s -> %s"
                         % (pelny, pdf), "HIGH", key="pdf-poza-katalogiem")
            if pdf == pelny or not pdf.endswith(".pdf"):
                s.nonsense(target, "PDF path came out strange: %r" % pdf, "MEDIUM",
                         key="pdf-zla-nazwa")

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
                    iter_lines.append("%s 10:00:00,nominal,%s,,,0,10,90,1,100,2.0,0" % (today, v))
                    oczekiwany = max(oczekiwany, v)
                elif r < 0.7:
                    v = s.rng.choice(["999.9", "1e400", "nan", "-5", "0", "120.1", "110.5", ""])
                    iter_lines.append("%s 10:00:00,nominal,%s,,,0,10,90,1,100,2.0,0" % (today, v))
                elif r < 0.8:
                    iter_lines.append("%s 10:00:00,nominal,88.8" % today)        # Truncated line.
                elif r < 0.9:
                    iter_lines.append("2000-01-01 10:00:00,nominal,108.0,,,0,10,90,1,100,2.0,0")
                else:
                    iter_lines.append(s.rng.choice(["", ",,,,,,,,,,,,", "A" * 2000,
                                                 "\x00,\x00,\x00,,,0,0,0,0,0,0,0"]))
            with open(HIST_PATH, "w") as f:
                f.write(naglowek + "\n".join(iter_lines) + "\n")
            with open(LOG_PATH, "w") as f:
                f.write("%s 10:00:00  [PAUSE] PAUSED ffmpeg (pid 1, 90%% CPU) - hot\n" % today)
            with open(EVENTS_PATH, "w") as f:
                f.write('{"time": "%s 10:00:00", "type": "HARD", "description": "x"}\n' % today)
            if i % 7 == 0:      # hardware.json after manual edit: valid JSON, not an object.
                with open(os.path.join(TMP, "hardware.json"), "w") as f:
                    f.write(s.rng.choice(["[]", '"x"', "5", "null"]))
            else:
                with open(os.path.join(TMP, "hardware.json"), "w") as f:
                    f.write('{"chip": "Apple M4 Pro", "fan_count": 2}')
            output = os.path.join(TMP, "out_%d.txt" % (i % 3))
            sys.argv = ["thermal-report", "--file", output, "--days", "2"]
            input_path = {"cel": target, "wierszy": len(iter_lines), "hardware": i % 7 == 0}
            try:
                with redirect_stdout(io.StringIO()):
                    treport.main()
            except Exception as e:
                s.error(input_path, e, "MEDIUM")
                continue
            try:
                with open(output) as f:
                    text = f.read()
            except Exception as e:
                s.error(input_path, e, "MEDIUM")
                continue
            m = re.search(r"PEAK MEASURED CHIP TEMPERATURE: ([0-9.]+) C", text)
            if oczekiwany and not m:
                s.nonsense(input_path, "report does not show the peak, although a valid %.1f C reading existed"
                         % oczekiwany, "MEDIUM", key="brak-szczytu")
            elif m and abs(float(m.group(1)) - oczekiwany) > 0.05:
                s.nonsense(input_path, "report peak %.1f C, but highest valid reading was %.1f C"
                         % (float(m.group(1)), oczekiwany), "HIGH", key="zly-szczyt")
            if m and "MEASUREMENT TIMELINE" in text:
                # The peak must sit below the section header but above measurement
                # rows. The oracle used to compare it to the header position, flagging
                # every correct placement as "inside the axis". The right boundary is
                # the first data row. Compute boundaries from the section header because
                # date-prefixed rows also appear in EVENTS and INTERVENTIONS above this
                # section; a whole-document search found those and produced false hits.
                _from_time = text.index("MEASUREMENT TIMELINE")
                _rows = re.search(r"^  \d{4}-\d{2}-\d{2} ", text[_from_time:], re.M)
                _boundary = (_from_time + _rows.start()) if _rows else len(text)
                if text.index("PEAK MEASURED") > _boundary:
                    s.nonsense(input_path, "peak row is INSIDE the measurement axis instead of above it",
                             "LOW", key="szczyt-nie-tam")
    finally:
        sys.argv = old_argv
        for p in (HIST_PATH, EVENTS_PATH, os.path.join(TMP, "hardware.json")):
            if os.path.exists(p):
                os.unlink(p)
    s.finish()


# ================================================================ 9. day_stats

def fuzz_stat_markers(seed, n):
    s = Session("guard.day_stats [markers]", seed)
    today = time.strftime("%Y-%m-%d")
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    # Process names that themselves contain a parser keyword.
    poisoned_names = ["sigterm_bench", "PAUSED_render", "resumed-worker", "koncze zadanie.sh"]
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            lines = []
            ocz = {"pauses": 0, "resumes": 0, "kills": 0}
            for _ in range(s.rng.randint(0, 10)):
                r = s.rng.random()
                name = s.rng.choice(["ffmpeg", "x265"] + poisoned_names)
                clean_run = name not in poisoned_names
                if r < 0.4:
                    lines.append("%s 10:00:00  [PAUSE] PAUSED %s (pid 1, 90%% CPU) - hot"
                                 % (today, name))
                    if clean_run:
                        ocz["pauses"] += 1
                elif r < 0.7:
                    lines.append("%s 10:00:00  [RESUME] RESUMED %s (pid 1) - cool"
                                 % (today, name))
                    if clean_run:
                        ocz["resumes"] += 1
                elif r < 0.85:
                    lines.append("%s 10:00:00  [KILL] TERMINATED (SIGTERM) %s (pid 1) - crit"
                                 % (today, name))
                    if clean_run:
                        ocz["kills"] += 1
                else:
                    lines.append(s.rng.choice([
                        "%s 10:00:00  KEEP-AWAKE start" % today,
                        "%s 10:00:00  [PAUSE] PAUSED x (pid 1)" % tomorrow,   # Future date.
                        "linia bez daty w ogole",
                        "%s 10:00:00  %s" % (today, "A" * (1000000 if i < 8 else 20000)),
                        "%s 10:00:00  CONFIG: odrzucone: never_extra" % today,
                        "%s 10:00:00  ОБНАРУЖЕНО "
                        "приостановка"
                        % today,                                             # Old Russian entry.
                        "%s 10:00:00  暂停任务" % today,     # Old Chinese entry.
                        "%s 10:00:00  PAUSA de la tarea" % today,            # Old Spanish entry.
                    ]))
            content = "\n".join(lines) + "\n"
            byte_count = content.encode("utf-8")
            broken = s.rng.random() < 0.15
            if broken:      # One non-UTF-8 byte at the end of the log.
                byte_count = byte_count + b"\xff\xfe niepoprawne utf-8\n"
            with open(LOG_PATH, "wb") as f:
                f.write(byte_count)
            try:
                st = guard.day_stats()
            except Exception as e:
                s.error(shorten(content, 200), e, "HIGH")
                continue
            if set(st) != {"pauses", "resumes", "kills"}:
                s.nonsense(shorten(content, 200), "returned %r" % (st,), "HIGH", key="zly-typ")
                continue
            if broken and sum(ocz.values()) and not sum(st.values()):
                s.nonsense(shorten(content, 200),
                         "ONE non-UTF-8 byte in guard.log ERASES THE WHOLE DAY STATISTICS: "
                         "the log had %d interventions, the function returns all zeros. The file "
                         "is read in blocks, so a bad byte at the end breaks the decoder already "
                         "on the first readline(), and `except Exception` swallows it silently - "
                         "the menu bar shows 'today 0 pauses' after a night full of pauses"
                         % sum(ocz.values()), "MEDIUM", key="log-nie-utf8-zeruje")
            for k in ocz:
                if st[k] < ocz[k] and not broken:
                    s.nonsense(shorten(content, 300),
                             "LOSES events: %s=%d, but the log had %d (menu bar day statistics "
                             "show fewer interventions than really happened)"
                             % (k, st[k], ocz[k]), "MEDIUM", key="gubi:" + k)
                elif st[k] > ocz[k] + 6 and not broken:
                    s.nonsense(shorten(content, 300),
                             "COUNTS TOO MUCH: %s=%d with %d real events - a process name "
                             "containing a keyword (for example 'sigterm_bench') is counted "
                             "as an event, and condition order assigns it to kills"
                             % (k, st[k], ocz[k]), "LOW", key="liczy-za-duzo:" + k)
    finally:
        if os.path.exists(LOG_PATH):
            os.unlink(LOG_PATH)
    s.finish()


# ================================================================ report

def print_report(seed, n):
    print("=" * 78)
    print("FUZZING ROUND 2 (code from the night of 2026-08-02) - seed %s, ~%d inputs per function" % (seed, n))
    print("working directory (TG_BASE): %s" % TMP)
    print("=" * 78)
    print("\n%-42s %8s %7s %7s %7s" % ("function", "runs", "sec", "errors", "findings"))
    print("-" * 78)
    for name, d in RUNS.items():
        print("%-42s %8d %7.2f %7d %7d"
              % (name, d["przebiegi"], d["sekundy"], d["bledy"], d["bzdury"]))
    print("\n" + "=" * 78)
    items = list(FINDINGS.values())
    if not items:
        print("FINDINGS: none - everything survived the fuzzing.")
    else:
        print("FINDINGS (%d distinct; x = number of inputs that triggered it):" % len(items))
        kol = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        for i, z in enumerate(sorted(items, key=lambda x: (kol.get(x["powaga"], 9), x["funkcja"])), 1):
            print("\n%d. [%s] %s  (x%d)" % (i, z["powaga"], z["funkcja"], z["ile"]))
            print("   what: %s" % z["opis"])
            print("   input: %s" % z["wejscie"])
    print("\n" + "=" * 78)
    clean_run = [x for x in RUNS if x in OK_FUNCTIONS]
    print("CLEAN (%d): %s" % (len(clean_run), ", ".join(clean_run) if clean_run else "-"))
    remaining = live_children()
    print("PROCESSES AFTER TEST (pgrep -f %s): %s" % (MARKER, remaining or "none - clean"))
    print("TOTAL TIME: %.1f s" % (time.time() - START))
    print("=" * 78)
    return 1 if any(z["powaga"] == "HIGH" for z in items) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260802)
    ap.add_argument("--n", type=int, default=260)
    a = ap.parse_args()
    random.seed(a.seed)
    with open(CFG_PATH, "w") as f:
        f.write("{}")
    try:
        fuzz_args_protection(a.seed, max(a.n, 400))
        fuzz_log_awake(a.seed, a.n)
        fuzz_run(a.seed, a.n)
        fuzz_exclusivity(a.seed, a.n)
        fuzz_load_cfg_thresholds(a.seed, a.n)
        fuzz_fleet(a.seed, a.n)
        fuzz_chip_freshness(a.seed, a.n)
        fuzz_report(a.seed, a.n)
        fuzz_stat_markers(a.seed, a.n)
        rc = print_report(a.seed, a.n)
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
