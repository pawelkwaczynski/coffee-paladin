#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fuzz pure coffee-paladin functions.

Run with:       python3 tests/test_fuzz.py
                python3 tests/test_fuzz.py --seed 12345   (different seed)
                python3 tests/test_fuzz.py --n 1000       (more runs)

The rule is not to read code looking for bugs; generate inputs and see what breaks.
Any exception that escapes a function is a finding. Result properties are checked
separately with oracles: a function can avoid exceptions and still return nonsense,
for example a NaN threshold that can never trigger.

Everything runs in a temporary directory (TG_BASE). No process is started because
subprocess calls are stubbed, so this does not load the machine.
"""

import argparse
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
import time
import traceback
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT_SECONDS = 60.0          # Hard limit per function; the machine may already be hot.

# ---------------------------------------------------------------- environment

TMP = tempfile.mkdtemp(prefix="tg-fuzz-")
os.environ["TG_BASE"] = TMP
os.environ.setdefault("TG_LANG", "en")
os.makedirs(os.path.join(TMP, "managed"), exist_ok=True)


def load_module(name, file_path):
    return SourceFileLoader(name, os.path.join(REPO, file_path)).load_module()


guard = load_module("tgfuzz_guard", "guard.py")
heat = load_module("tgfuzz_heat", "heat")
saferun = load_module("tgfuzz_saferun", "safe-run")
treport = load_module("tgfuzz_treport", "thermal-report")

# No real processes: every `ps`/`sysctl` result is a stub.
guard.run = lambda cmd, timeout=10: ""
heat.sh = lambda cmd, timeout=15: ""
saferun.sh = lambda cmd, timeout=15: ""
treport.sh = lambda cmd, timeout=30: ""

# ---------------------------------------------------------------- report

FINDINGS = {}          # (function, key) -> {opis, wejscie, powaga, ile}
RUNS = {}
OK_FUNCTIONS = []


def record_finding(function, key, input_value, description, severity):
    k = (function, key)
    if k in FINDINGS:
        FINDINGS[k]["ile"] += 1
        return
    FINDINGS[k] = {"funkcja": function, "klucz": key, "wejscie": shorten(input_value),
                     "opis": description, "powaga": severity, "ile": 1}


def shorten(x, n=300):
    s = repr(x)
    return s if len(s) <= n else s[:n] + "...<%d znakow>" % len(s)


def error_key(exc):
    return "EXC:" + type(exc).__name__


def finite_value(w):
    """Check finiteness without blowing up on a 400-digit int."""
    if isinstance(w, bool):
        return True
    if isinstance(w, int):
        return True
    try:
        return math.isfinite(w)
    except Exception:
        return False


class Session(object):
    """Track one fuzzed function, including run count, time limit, and deduplication.

    Duplicate findings keep the first input that triggered the failure.
    """

    def __init__(self, name, seed):
        self.name = name
        self.seed = seed
        self.rng = random.Random("%s|%s" % (seed, name))
        self.start = time.time()
        self.n = 0
        self.errors = 0
        self.bzdury = 0

    def time_elapsed(self):
        return time.time() - self.start > LIMIT_SECONDS

    def error(self, input_value, exc, severity="HIGH"):
        self.errors += 1
        record_finding(self.name, error_key(exc), input_value,
                   "exception escapes function: %s: %s" % (type(exc).__name__, exc), severity)

    def nonsense(self, input_value, description, severity="MEDIUM", key=None):
        self.bzdury += 1
        record_finding(self.name, key or description[:60], input_value, description, severity)

    def finish(self):
        RUNS[self.name] = {
            "przebiegi": self.n,
            "sekundy": round(time.time() - self.start, 2),
            "bledy": self.errors,
            "bzdury": self.bzdury,
        }
        if not self.errors and not self.bzdury:
            OK_FUNCTIONS.append(self.name)


# ---------------------------------------------------------------- generators

EMOJI = "\U0001F525\U0001F9CA☕\U0001F4BB"
CONTROL_CHARS = "".join(chr(c) for c in range(1, 32))

WEIRD_STRINGS = [
    "", " ", "\x00", "a\x00b", CONTROL_CHARS, EMOJI, "ff" + EMOJI + "mpeg",
    "\u202e\u200b bidi", "\\", "/", "../../etc/passwd", "%s %d %.1f",
    "python" * 2000, "A" * 10000, "中文名称", "йцу",
    "NaN", "Infinity", "-0", "1e400", "0x41", "  41  ", "41,5",
    "\n\r\t", "'; DROP TABLE --", "\ud83d".encode("utf-16", "surrogatepass").decode("utf-16", "replace"),
]

WEIRD_NUMBERS = [
    0, 1, -1, 2 ** 31, 2 ** 63, -2 ** 63, 10 ** 400, -10 ** 400,
    0.0, -0.0, 1e-323, 1e308, -1e308, float("inf"), float("-inf"), float("nan"),
    1e9, -1e9, 0.1 + 0.2, 90.0, 85.5, 40.0, -273.15,
]


def random_string(rng):
    r = rng.random()
    if r < 0.4:
        return rng.choice(WEIRD_STRINGS)
    if r < 0.6:
        return "".join(rng.choice("abcXYZ012 ./-_\x00" + EMOJI) for _ in range(rng.randint(0, 40)))
    if r < 0.7:
        return "A" * rng.choice([1000, 10000])
    return rng.choice(["ffmpeg", "python3", "node", "claude", "kernel_task", "x265", "Python"])


def random_number(rng):
    if rng.random() < 0.5:
        return rng.choice(WEIRD_NUMBERS)
    if rng.random() < 0.5:
        return rng.uniform(-1e6, 1e6)
    return rng.randint(-10 ** 6, 10 ** 6)


def random_value(rng, depth=0):
    r = rng.random()
    if depth < 3 and r < 0.10:
        return [random_value(rng, depth + 1) for _ in range(rng.randint(0, 5))]
    if depth < 3 and r < 0.16:
        return {random_string(rng): random_value(rng, depth + 1)
                for _ in range(rng.randint(0, 4))}
    if r < 0.30:
        return random_string(rng)
    if r < 0.75:
        return random_number(rng)
    if r < 0.85:
        return rng.choice([True, False])
    if r < 0.92:
        return None
    return rng.choice([[], {}, [1, 2, 3], ["ffmpeg", ""], [""], [None], {"a": 1}])


# ---------------------------------------------------------------- 1. load_cfg

CFG = os.path.join(TMP, "config.json")

RAW_CONFIGS = [
    "",                                   # Empty file.
    "null",
    "true",
    "[]",
    '"tekst"',
    "{",                                  # Truncated.
    '{"soc_pause_c": 85.0',               # Truncated halfway.
    "\x00\x01\x02\xff\xfe",               # Binary junk.
    '{"poll_seconds": 1e400}',            # Infinity in an integer key.
    '{"batt_pause_c": 1e400}',            # Infinity in a floating-point key.
    '{"batt_pause_c": %s}' % ("9" * 400),  # 400-digit integer.
    '{"poll_seconds": %s}' % ("9" * 400),
    '{"soc_pause_c": NaN, "soc_kill_c": NaN, "soc_resume_c": NaN}',
    '{"cpu_min_percent": NaN}',
    '{"soc_pause_c": Infinity, "soc_kill_c": Infinity}',
    '{"soc_pause_c": -Infinity}',
    '{"never_patterns": [""], "managed_patterns": [""]}',
    '{"soc_kill_c": 10, "soc_pause_c": 90, "soc_resume_c": 95}',   # Reversed thresholds.
    '{"lang": "\\u0000"}',
    '{"never_extra": [null, 1, {}, [], "\\u0000"]}',
    "{" + ",".join('"k%d": %d' % (i, i) for i in range(20000)) + "}",   # Huge config.
]


def write_cfg(text):
    with open(CFG, "w") as f:
        f.write(text)


def check_cfg(s, input_value, cfg):
    """Assert config invariants: complete keys, valid types, finite numbers, rising thresholds."""
    for k, pattern in guard.DEFAULTS.items():
        if k not in cfg:
            s.nonsense(input_value, "load_cfg loses key %s" % k, "HIGH", key="brak-klucza")
            continue
        w = cfg[k]
        if isinstance(pattern, bool) and not isinstance(w, bool):
            s.nonsense(input_value, "key %s has type %s instead of bool" % (k, type(w).__name__),
                     "HIGH", key="bool-zly-typ")
        elif isinstance(pattern, (int, float)) and not isinstance(pattern, bool):
            if isinstance(w, bool) or not isinstance(w, (int, float)):
                s.nonsense(input_value,
                         "numeric key %s got value %r (type %s) and PASSED type validation "
                         "- bool bypasses all checks, so for example {\"poll_seconds\": true} = 1 s loop, "
                         "and {\"soc_pause_c\": true} = pause threshold 1 C" % (k, w, type(w).__name__),
                         "HIGH", key="bool-zamiast-liczby")
            elif not finite_value(w):
                s.nonsense(input_value,
                         "threshold %s = %r (NaN/inf) passes validation - every comparison "
                         "with it is false, guard goes blind without warning" % (k, w),
                         "HIGH", key="nieskonczony-prog")
        elif isinstance(pattern, list) and not isinstance(w, list):
            s.nonsense(input_value, "key %s is not a list" % k, "HIGH", key="nie-lista")
        elif isinstance(pattern, str) and not isinstance(w, str):
            s.nonsense(input_value, "key %s is not a string" % k, "MEDIUM", key="nie-str")
    try:
        if finite_value(cfg["soc_resume_c"]) and finite_value(cfg["soc_pause_c"]):
            if cfg["soc_resume_c"] >= cfg["soc_pause_c"]:
                s.nonsense(input_value, "soc_resume_c >= soc_pause_c after validation (pause/resume loop)",
                         "HIGH", key="progi-resume")
        if finite_value(cfg["soc_pause_c"]) and finite_value(cfg["soc_kill_c"]):
            if cfg["soc_pause_c"] >= cfg["soc_kill_c"]:
                s.nonsense(input_value, "soc_pause_c >= soc_kill_c after validation (SIGTERM at pause threshold)",
                         "HIGH", key="progi-kill")
    except Exception:
        pass
    for k in ("never_patterns", "never_arg_patterns"):
        for name in guard.OWN_NAMES:
            if name not in cfg.get(k, []):
                s.nonsense(input_value, "%s does not contain own name %r - guard can pause itself"
                         % (k, name), "HIGH", key="brak-wlasnej-nazwy")
    for w in cfg.get("never_patterns", []):
        if not isinstance(w, str) or not w.strip():
            s.nonsense(input_value, "empty/non-text pattern in never_patterns: %r" % (w,),
                     "HIGH", key="pusty-wzorzec")


def fuzz_load_cfg(seed, n):
    s = Session("guard.load_cfg", seed)
    keys = list(guard.DEFAULTS)
    for i in range(n):
        if s.time_elapsed():
            break
        s.n += 1
        if i < len(RAW_CONFIGS):
            text = RAW_CONFIGS[i]
        elif i == len(RAW_CONFIGS):
            text = json.dumps({"never_extra": ["x" * 1000] * 10000})     # ~10 MB
        else:
            d = {}
            for k in s.rng.sample(keys, s.rng.randint(1, min(12, len(keys)))):
                d[k] = random_value(s.rng)
            for _ in range(s.rng.randint(0, 3)):
                d[random_string(s.rng)] = random_value(s.rng)
            try:
                text = json.dumps(d, allow_nan=True)
            except Exception:
                continue
        write_cfg(text)
        del guard._zle_typy[:]
        try:
            cfg = guard.load_cfg()
        except Exception as e:
            s.error(text, e)
            continue
        if not isinstance(cfg, dict):
            s.nonsense(text, "load_cfg returned %s instead of dict" % type(cfg).__name__, "HIGH")
            continue
        check_cfg(s, text, cfg)
    write_cfg("{}")
    s.finish()


# ---------------------------------------------------------------- 2. severity

def random_temp(rng, hostile):
    if not hostile:
        return rng.choice([None, -273.15, 0.0, 40.0, 85.0, 90.5, 1e9, -1e9,
                           float("nan"), float("inf"), rng.uniform(-100, 200)])
    return random_value(rng)


def fuzz_severity(seed, n, hostile=False):
    name = "guard.severity" + ("[wrogie typy]" if hostile else "")
    s = Session(name, seed)
    write_cfg("{}")
    base_cfg = guard.load_cfg()
    states = list(guard.LEVELS) + ["", None, "SERIOUS", 3, "\x00"]
    for _ in range(n):
        if s.time_elapsed():
            break
        s.n += 1
        cfg = dict(base_cfg)
        if s.rng.random() < 0.3:
            for k in ("soc_pause_c", "soc_kill_c", "batt_pause_c", "batt_kill_c",
                      "speed_limit_pause", "batt_pct_pause"):
                if s.rng.random() < 0.4:
                    cfg[k] = random_number(s.rng)
        arg = {
            "state": s.rng.choice(states) if hostile else s.rng.choice(list(guard.LEVELS)),
            "temp": random_temp(s.rng, hostile),
            "speed": s.rng.choice([100, 0, -5, 1e9, 60]) if not hostile else random_value(s.rng),
            "soc": random_temp(s.rng, hostile),
            "ac": s.rng.choice([True, False]) if not hostile else random_value(s.rng),
            "pct": s.rng.choice([None, 0, 5, 50, 100, -1, 10 ** 9]) if not hostile
                   else random_value(s.rng),
        }
        try:
            lvl, why = guard.severity(cfg, arg["state"], arg["temp"], arg["speed"],
                                      soc=arg["soc"], ac=arg["ac"], pct=arg["pct"])
        except Exception as e:
            s.error({"cfg_progi": {k: cfg[k] for k in ("soc_pause_c", "soc_kill_c")}, "arg": arg},
                   e, "HIGH" if not hostile else "LOW")
            continue
        if not isinstance(lvl, int) or lvl not in (0, 1, 2, 3):
            s.nonsense(arg, "severity returned level %r (outside 0..3)" % (lvl,), "HIGH",
                     key="poziom-poza-zakresem")
        if not isinstance(why, str):
            s.nonsense(arg, "reason is not text: %r" % (why,), "MEDIUM", key="powod-nie-str")
        soc = arg["soc"]
        if isinstance(soc, float) and math.isfinite(soc) and finite_value(cfg["soc_kill_c"]):
            if soc >= cfg["soc_kill_c"] and lvl != 3:
                s.nonsense(arg, "chip %.1f C >= kill threshold %.1f C, but level = %s"
                         % (soc, cfg["soc_kill_c"], lvl), "HIGH", key="kill-nie-zadzialal")
        if isinstance(soc, float) and math.isnan(soc) and lvl == 0:
            s.nonsense(arg, "chip = NaN treated as cold (level 0, zero warning)",
                     "MEDIUM", key="nan-jak-zimny")
    s.finish()


# ---------------------------------------------------------------- 3. normalize_batt_temp

def fuzz_normalize(seed, n, module, name):
    s = Session(name, seed)
    stale = WEIRD_NUMBERS + WEIRD_STRINGS + [None, True, False, [], {}, b"41", b"", (1,),
                                              "41", "3081", "444", "0", "-5", "1e400"]
    for i in range(n):
        if s.time_elapsed():
            break
        s.n += 1
        if i < len(stale):
            raw = stale[i]
        elif s.rng.random() < 0.5:
            raw = s.rng.uniform(-1e9, 1e9)
        else:
            raw = random_value(s.rng)
        try:
            v = module.normalize_batt_temp(raw)
        except Exception as e:
            # Real callers pass an ioreg string or None; other values probe boundaries.
            s.error(raw, e, "HIGH" if isinstance(raw, (str, bytes, type(None))) else "MEDIUM")
            continue
        if v is None:
            continue
        if not isinstance(v, float) or not math.isfinite(v):
            s.nonsense(raw, "returned %r (non-finite number)" % (v,), "HIGH", key="niesk")
        elif not (5.0 < v <= 100.0):
            s.nonsense(raw, "returned %r - outside declared range 5..100 C" % (v,),
                     "HIGH", key="poza-zakresem")
    s.finish()


# ---------------------------------------------------------------- 4. cpu_with_children

def random_processes(rng, hostile=False):
    amount = rng.choice([0, 1, 2, 5, 30, 200])
    procs = []
    for _ in range(amount):
        pid = rng.choice([rng.randint(-10, 5000), 0, 1, -1, 2 ** 63, rng.randint(1, 50)])
        ppid = rng.choice([rng.randint(-10, 5000), 0, 1, pid, rng.randint(1, 50)])
        cpu = rng.choice([0.0, 1.0, 99.9, -5.0, 1e9, float("nan"), float("inf"),
                          rng.uniform(0, 100)])
        comm = random_string(rng)
        if hostile and rng.random() < 0.2:
            comm = rng.choice([None, 123, [], b"ffmpeg"])
        procs.append((pid, ppid, cpu, comm))
    if amount and rng.random() < 0.3:      # parent<->child cycle
        a, b = procs[0][0], procs[-1][0]
        procs[0] = (a, b, procs[0][2], procs[0][3])
        procs[-1] = (b, a, procs[-1][2], procs[-1][3])
    if amount and rng.random() < 0.2:      # Long chain that tests recursion depth.
        procs = [(i, i - 1, 1.0, "chain") for i in range(1, min(amount, 200) + 1)]
    return procs


def fuzz_cpu_with_children(seed, n):
    s = Session("guard.cpu_with_children", seed)
    for _ in range(n):
        if s.time_elapsed():
            break
        s.n += 1
        procs = random_processes(s.rng, hostile=s.rng.random() < 0.2)
        try:
            total_value = guard.cpu_with_children(procs)
        except Exception as e:
            s.error(procs[:6], e)
            continue
        if not isinstance(total_value, dict):
            s.nonsense(procs[:6], "returned %s instead of dict" % type(total_value).__name__, "HIGH",
                     key="zly-typ-wyniku")
            continue
        # Negative/infinite CPU does not come from `ps`. For such inputs, subtree
        # total can be smaller than own CPU without being a function bug.
        if any(not isinstance(c, (int, float)) or isinstance(c, bool)
               or not finite_value(c) or c < 0 for _p, _pp, c, _c in procs):
            continue
        # Compare to a "last entry wins" map, matching the function's own behavior.
        own = {}
        for pid, ppid, cpu, comm in procs:
            try:
                own[pid] = cpu
            except TypeError:
                pass
        for pid, cpu in own.items():
            if isinstance(cpu, float) and math.isfinite(cpu) and cpu >= 0:
                w = total_value.get(pid)
                if isinstance(w, float) and math.isfinite(w) and w + 1e-6 < cpu:
                    s.nonsense((pid, cpu, w),
                             "subtree total (%r) smaller than process own CPU (%r)" % (w, cpu),
                             "MEDIUM", key="suma-mniejsza")
    s.finish()


# ---------------------------------------------------------------- 5. pick_targets

def fuzz_pick_targets(seed, n):
    s = Session("guard.pick_targets", seed)
    write_cfg("{}")
    base_cfg = guard.load_cfg()
    old_items = (guard.proc_age_seconds, guard.foreground_on_tty, guard.full_args)
    guard.proc_age_seconds = lambda pid: s.rng.choice([0, 5, 130, 10 ** 6])
    guard.foreground_on_tty = lambda pid: s.rng.random() < 0.3
    guard.full_args = lambda pid: random_string(s.rng)
    try:
        for _ in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            cfg = dict(base_cfg)
            if s.rng.random() < 0.3:
                cfg["cpu_min_percent"] = random_number(s.rng)
            if s.rng.random() < 0.2:
                cfg["count_children"] = s.rng.choice([True, False, None, "tak"])
            if s.rng.random() < 0.2:
                cfg["managed_patterns"] = [random_string(s.rng) for _ in range(s.rng.randint(0, 3))]
            procs = random_processes(s.rng, hostile=s.rng.random() < 0.15)
            saferun_map = {}
            for p in procs:
                if s.rng.random() < 0.1:
                    saferun_map[p[0]] = s.rng.choice([p[0], -1, 0, None])
            # list_procs always returns (int, int, float, str). Inputs that break
            # that contract are LOW severity because `ps` cannot produce them.
            per_contract = all(isinstance(p[0], int) and isinstance(p[1], int)
                               and isinstance(p[2], float) and isinstance(p[3], str)
                               for p in procs)
            try:
                out = guard.pick_targets(cfg, procs, saferun_map)
            except Exception as e:
                s.error({"procs": procs[:4], "cpu_min": cfg["cpu_min_percent"],
                        "saferun": dict(list(saferun_map.items())[:3])}, e,
                       "HIGH" if per_contract else "LOW")
                continue
            if not isinstance(out, list):
                s.nonsense(procs[:4], "returned %s instead of list" % type(out).__name__, "HIGH",
                         key="zly-typ-wyniku")
                continue
            for t in out:
                if not (isinstance(t, tuple) and len(t) == 4):
                    s.nonsense(t, "result element is not a 4-tuple", "HIGH", key="nie-4-krotka")
                    continue
                pid, cpu, comm, pgid = t
                if isinstance(pid, int) and pid <= 1:
                    s.nonsense(t, "target list contains PID <= 1 (%r) - signal candidate in init/kernel"
                             % (pid,), "HIGH", key="pid<=1")
                if isinstance(cpu, float) and math.isnan(cpu) and pid not in saferun_map:
                    s.nonsense(t, "process with CPU = NaN passed cpu_min_percent threshold and landed "
                                "on pause list", "MEDIUM", key="nan-przechodzi-prog")
            cpu_list = [t[1] for t in out if isinstance(t[1], (int, float))
                        and not (isinstance(t[1], float) and math.isnan(t[1]))]
            if cpu_list != sorted(cpu_list, reverse=True):
                s.nonsense(cpu_list[:8], "result is not sorted by descending CPU (NaN in CPU "
                                       "breaks sorting - hottest process stops being first)",
                         "LOW", key="brak-sortowania")
    finally:
        guard.proc_age_seconds, guard.foreground_on_tty, guard.full_args = old_items
    s.finish()


# ---------------------------------------------------------------- 6. args_without_paths

def fuzz_args_without_paths(seed, n):
    s = Session("guard.args_without_paths", seed)
    old = guard.full_args
    proby = [
        "", "   ", "\x00", "ffmpeg -i /Users/x/wideo/rec.mkv -c:v libx265 out.mkv",
        "node /Users/x/.vscode/extensions/server.js", "/bin/sleep 10",
        "A" * 100000, EMOJI * 100, CONTROL_CHARS, "python3 " + "../" * 5000 + "a.mp4",
    ]
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            input_path = proby[i] if i < len(proby) else random_string(s.rng)
            guard.full_args = lambda pid, _w=input_path: _w
            try:
                out = guard.args_without_paths(s.rng.randint(-5, 99999))
            except Exception as e:
                s.error(input_path, e)
                continue
            if not isinstance(out, str):
                s.nonsense(input_path, "returned %s instead of str" % type(out).__name__, "HIGH",
                         key="zly-typ-wyniku")
            elif out != out.lower():
                s.nonsense(input_path, "result is not fully lowercase", "LOW", key="wielkosc-liter")
    finally:
        guard.full_args = old
    s.finish()


# ---------------------------------------------------------------- 7. detect_hard_shutdown

HB = os.path.join(TMP, "heartbeat")
CLEAN = os.path.join(TMP, "clean_stop")
HIST = os.path.join(TMP, "history.csv")
EVENTS = os.path.join(TMP, "events.log")
BOOT = int(time.time()) - 3600      # System booted one hour ago.


def fuzz_detect_hard_shutdown(seed, n):
    s = Session("guard.detect_hard_shutdown", seed)
    old_boot, old_log = guard.boot_time, guard.log
    guard.boot_time = lambda: BOOT
    guard.log = lambda msg, tag=None: None
    variants = [
        None,                                        # Missing file.
        "",                                          # Empty.
        "   \n",
        str(BOOT - 600),                             # Classic hard shutdown.
        "%d %s" % (BOOT - 600, time.strftime("%Y-%m-%d %H:%M:%S")),
        str(BOOT + 600),                             # Future heartbeat.
        "0",                                         # Before 1970.
        "-1e18",
        "nan",
        "inf",
        "-inf",
        "1e400",
        "9" * 400,
        "\x00\x01\xff\xfe",
        "smieci bez liczby",
        "2026-08-01 12:00:00",                       # Old text format.
        "1970-01-01 00:00:00",
        "9999-12-31 23:59:59",
        "%d" % (BOOT - 40 * 86400),                  # implausibly old
        "%d obciete" % (BOOT - 600),
    ]
    hist_variants = [
        None,
        "",
        "time,thermal_state,chip_C\n",
        "time,thermal_state,chip_C\n2026-08-01 10:00:00,nominal,55.0\n",
        "\x00\xff" * 100,
        "a,b\n" + "x" * 100000 + "\n",
        ",,,\n,,,\n",
        "time,\n" + "\n".join("," * i for i in range(50)),
    ]
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            hb = variants[i] if i < len(variants) else (
                random_string(s.rng) if s.rng.random() < 0.5
                else str(s.rng.choice([BOOT - 600, BOOT + 1, 0, -1, 1e18])))
            clean_one = s.rng.random() < 0.3
            hv = s.rng.choice(hist_variants)
            # EVENTS too: every fuzzer case must be independent. Otherwise the
            # second case with the same heartbeat hits hard-shutdown deduplication,
            # and the oracle misreads intended behavior as a "missed shutdown".
            for p in (HB, CLEAN, HIST, EVENTS):
                if os.path.exists(p):
                    os.unlink(p)
            if hb is not None:
                with open(HB, "wb") as f:
                    f.write(hb.encode("utf-8", "surrogateescape"))
            if clean_one:
                with open(CLEAN, "w") as f:
                    f.write("x")
                os.utime(CLEAN, (BOOT - 500, BOOT - 500))
            if hv is not None:
                with open(HIST, "wb") as f:
                    f.write(hv.encode("utf-8", "surrogateescape"))
            input_path = {"heartbeat": hb, "clean_stop": clean_one, "history": shorten(hv, 60)}
            try:
                r = guard.detect_hard_shutdown()
            except Exception as e:
                s.error(input_path, e)
                continue
            if r is not None and not isinstance(r, dict):
                s.nonsense(input_path, "returned %s instead of dict/None" % type(r).__name__, "HIGH",
                         key="zly-typ-wyniku")
            # Oracle: an unambiguous hard shutdown must be detected.
            if hb is not None and not clean_one:
                try:
                    epoch = float(hb.split()[0])
                except Exception:
                    epoch = None
                if (epoch is not None and math.isfinite(epoch)
                        and BOOT - 30 * 86400 < epoch < BOOT and r is None):
                    s.nonsense(input_path, "heartbeat %r is before boot and there is no clean_stop, but hard shutdown "
                                  "was NOT reported" % (hb,), "HIGH", key="pad-przeoczony")
                if (epoch is not None and not math.isfinite(epoch) and r is None
                        and hb.strip().lower().startswith("nan")):
                    s.nonsense(input_path, "heartbeat 'nan' silently disables shutdown detection "
                                  "(function exits through its own except)", "LOW", key="nan-puls")
    finally:
        guard.boot_time, guard.log = old_boot, old_log
        for p in (HB, CLEAN, HIST, EVENTS):
            if os.path.exists(p):
                os.unlink(p)
    s.finish()


# ---------------------------------------------------------------- 8. day_stats

LOG = os.path.join(TMP, "guard.log")

# Build entries from the same dictionaries the guard uses so this test does not
# become stale when translations change.
K_PAUSE = "PAUSED %s (pid %d, %.0f%% CPU) - %s"
K_RESUME = "RESUMED %s (pid %d) - %s"
K_KILL = "TERMINATED (SIGTERM) %s (pid %d) - %s"
K_ANNOUNCE = "PAUSE >%d min - terminating job %s (pid %s)"


def _entry(lang, key, args):
    return (guard.DICTS.get(lang, {}).get(key, key)) % args


# Production prepends a language-neutral tag via log(msg, tag=...); the parser
# contract is the tag alone, so fixtures must carry it exactly like real lines.
ENTRIES = {}
for _l in ("en", "pl", "ru", "zh", "es"):
    ENTRIES[_l] = {
        "pauza": "[PAUSE] " + _entry(_l, K_PAUSE, ("ffmpeg", 1, 99, "chip 90 C")),
        "wznow": "[RESUME] " + _entry(_l, K_RESUME, ("ffmpeg", 1, "cooled down")),
        "ubicie": "[KILL] " + _entry(_l, K_KILL, ("ffmpeg", 1, "chip 95 C")),
        "zapowiedz": "[KILL] " + _entry(_l, K_ANNOUNCE, (45, "ffmpeg", 1)),
    }


TRIGGERS = ("[PAUSE]", "[RESUME]", "[KILL]")


def fuzz_day_stats(seed, n):
    s = Session("guard.day_stats", seed)
    today = time.strftime("%Y-%m-%d")
    junk_values = [
        "", "\n", "\x00\xff smieci", "linia bez daty", "2020-01-01 PAUSED x",
        today + " " * 5000 + "PAUSED", "A" * 1000000, today + " PAUSED  RESUMED  SIGTERM",
    ]
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            lines = []
            oczek = {"pauses": 0, "resumes": 0, "kills": 0}
            announcements = 0
            poisoned = False        # Junk that itself contains a parser keyword.
            lang = list(ENTRIES)[i % 5] if i < 40 else s.rng.choice(list(ENTRIES))
            for _ in range(s.rng.randint(0, 20)):
                r = s.rng.random()
                if r < 0.35:
                    lines.append("%s 10:00:00  %s" % (today, ENTRIES[lang]["pauza"]))
                    oczek["pauses"] += 1
                elif r < 0.55:
                    lines.append("%s 10:00:00  %s" % (today, ENTRIES[lang]["wznow"]))
                    oczek["resumes"] += 1
                elif r < 0.70:
                    lines.append("%s 10:00:00  %s" % (today, ENTRIES[lang]["ubicie"]))
                    oczek["kills"] += 1
                elif r < 0.78:
                    lines.append("%s 10:00:00  %s" % (today, ENTRIES[lang]["zapowiedz"]))
                    announcements += 1
                else:
                    x = s.rng.choice(junk_values)
                    lines.append(x)
                    poisoned = poisoned or any(w in x for w in TRIGGERS)
            if i < len(junk_values):
                lines.append(junk_values[i])
                poisoned = poisoned or any(w in junk_values[i] for w in TRIGGERS)
            content = "\n".join(lines) + "\n"
            with open(LOG, "wb") as f:
                f.write(content.encode("utf-8", "surrogateescape"))
            try:
                st = guard.day_stats()
            except Exception as e:
                s.error(shorten(content, 200), e)
                continue
            if not isinstance(st, dict) or set(st) != {"pauses", "resumes", "kills"}:
                s.nonsense(shorten(content, 200), "returned %r" % (st,), "HIGH", key="zly-typ-wyniku")
                continue
            input_path = {"jezyk_logu": lang, "log": shorten(content, 160)}
            if st["pauses"] < oczek["pauses"]:
                s.nonsense(input_path,
                         "language %s: counted %d pauses instead of %d - function searches only "
                         "'PAUZA '/'PAUSED ', so in ru/zh/es daily menu-bar stats are ZERO"
                         % (lang, st["pauses"], oczek["pauses"]), "MEDIUM", key="pauzy-jezyki")
            if st["resumes"] < oczek["resumes"]:
                s.nonsense(input_path,
                         "language %s: counted %d resumes instead of %d (searches only "
                         "'WZNOWIONE'/'RESUMED')" % (lang, st["resumes"], oczek["resumes"]),
                         "MEDIUM", key="wznowienia-jezyki")
            if st["kills"] < oczek["kills"]:
                s.nonsense(input_path, "language %s: counted %d kills instead of %d"
                         % (lang, st["kills"], oczek["kills"]), "MEDIUM", key="ubicia-jezyki")
            if announcements and not poisoned and st["pauses"] > oczek["pauses"]:
                s.nonsense(input_path,
                         "language %s: kill announcement ('PAUZA >45 min - koncze zadanie') was "
                         "counted as PAUSE (%d instead of %d) - elif order means kill entry "
                         "never reaches the kills counter"
                         % (lang, st["pauses"], oczek["pauses"]), "MEDIUM",
                         key="zapowiedz-jako-pauza")
    finally:
        if os.path.exists(LOG):
            os.unlink(LOG)
    s.finish()


# ---------------------------------------------------------------- 9. _loguj_awake

def fuzz_log_awake(seed, n):
    s = Session("guard._loguj_awake", seed)
    old_log = guard.log
    guard.log = lambda msg, tag=None: None
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0}
                                    if s.rng.random() < 0.2 else {})
            msg = random_value(s.rng) if s.rng.random() < 0.3 else random_string(s.rng)
            try:
                guard._loguj_awake(msg)
            except Exception as e:
                s.error(msg, e, "LOW")
    finally:
        guard.log = old_log
    s.finish()


# ---------------------------------------------------------------- 10. heat.stuck

def fuzz_heat_stuck(seed, n):
    s = Session("heat.stuck", seed)
    old = heat.sh
    ps_outputs = [
        "",
        "123 T   01:00 ffmpeg",
        "123 T\n",                                    # Too few fields.
        "  1 TXs  10-01:02:03 kernel_task\n2 S 00:01 launchd\n",
        "-1 T 00:01 " + EMOJI + "\n",
        "abc T 00:01 x\n",
        "999999999999999999999 T 00:01 " + "A" * 5000 + "\n",
        "\x00\xff T 00:01 x\n",
        "\n".join("%d T 00:%02d proc%d" % (i, i % 60, i) for i in range(2000)),
    ]
    states = [
        None, "", "null", "[]", "\"abc\"", "{}", '{"paused": {}}',
        '{"paused": {"123": {"comm": "ffmpeg"}}}',
        '{"paused": [{"pid": 123}]}',
        '{"paused": ["123"]}',
        '{"paused": 5}',
        '{"paused": [1,2,3]}',
        '{"paused": null}',
        "{obciete",
        "\x00\xff",
    ]
    try:
        for i in range(n):
            if s.time_elapsed():
                break
            s.n += 1
            ps = ps_outputs[i] if i < len(ps_outputs) else s.rng.choice(ps_outputs)
            heat.sh = lambda cmd, timeout=15, _o=ps: _o
            st_json = states[i % len(states)] if i < 40 else s.rng.choice(states)
            for file_path in ("state.json", "status.json"):
                p = os.path.join(TMP, file_path)
                if st_json is None:
                    if os.path.exists(p):
                        os.unlink(p)
                else:
                    with open(p, "wb") as f:
                        f.write(st_json.encode("utf-8", "surrogateescape"))
            input_path = {"ps": shorten(ps, 80), "state.json": st_json}
            try:
                with redirect_stdout(io.StringIO()):
                    rc = heat.stuck()
            except Exception as e:
                s.error(input_path, e)
                continue
            if rc != 0:
                s.nonsense(input_path, "returned code %r instead of 0" % (rc,), "LOW", key="zly-kod")
    finally:
        heat.sh = old
        for file_path in ("state.json", "status.json"):
            p = os.path.join(TMP, file_path)
            if os.path.exists(p):
                os.unlink(p)
    s.finish()


# ---------------------------------------------------------------- 11. chip_already_hot

STATUS = os.path.join(TMP, "status.json")

STATUSES = [
    None,                                    # Missing file.
    "",
    "null",
    "[]",
    "[1, 2, 3]",
    '"goraco"',
    "true",
    "123",
    "{",
    "{}",
    '{"level": 0}',
    '{"level": 3}',
    '{"level": "3"}',
    '{"level": null}',
    '{"level": [2]}',
    '{"level": 1, "chip_c": 90}',
    '{"level": 1, "chip_c": "90"}',
    '{"level": 1, "chip_c": NaN}',
    '{"level": 1, "chip_c": Infinity}',
    '{"level": 1, "chip_c": 90, "thresholds": {"pause": 85}}',
    '{"level": 1, "chip_c": 90, "thresholds": []}',
    '{"level": 1, "chip_c": 90, "thresholds": [1]}',
    '{"level": 1, "chip_c": 90, "thresholds": "85"}',
    '{"level": 1, "chip_c": 90, "thresholds": {"pause": null}}',
    '{"level": 1, "chip_c": 90, "thresholds": {"pause": "goraco"}}',
    '{"level": 1, "chip_c": 90, "thresholds": {"pause": 0}}',
    '{"level": 1, "chip_c": 1e400}',
    "\x00\xff\xfe",
]


def fuzz_chip_already_hot(seed, n):
    s = Session("safe-run.chip_already_hot", seed)
    for i in range(n):
        if s.time_elapsed():
            break
        s.n += 1
        if i < len(STATUSES):
            content = STATUSES[i]
        else:
            d = {}
            for k in ("level", "chip_c", "thresholds"):
                if s.rng.random() < 0.8:
                    d[k] = random_value(s.rng)
            try:
                content = json.dumps(d, allow_nan=True)
            except Exception:
                continue
        if os.path.exists(STATUS):
            os.unlink(STATUS)
        if content is not None:
            with open(STATUS, "wb") as f:
                f.write(content.encode("utf-8", "surrogateescape"))
        try:
            r = saferun.chip_already_hot()
        except Exception as e:
            # The guard writes status.json atomically (tmp + os.replace) and always
            # as a dict. These contents imply manual edits, FS damage, or a foreign
            # tool, so severity is MEDIUM even though safe-run tracebacks are serious.
            s.error(content, e, "MEDIUM")
            continue
        if not (isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], bool)
                and isinstance(r[1], str)):
            s.nonsense(content, "returned %r instead of (bool, str)" % (r,), "MEDIUM", key="zly-typ-wyniku")
    if os.path.exists(STATUS):
        os.unlink(STATUS)
    s.finish()


# ---------------------------------------------------------------- 12. max_temp_since / abs_epoch

def fuzz_max_temp_since(seed, n):
    s = Session("safe-run.max_temp_since", seed)
    naglowek = "time,thermal_state,chip_C,gpu_C,battery_C\n"
    variants = [
        "", naglowek, naglowek + "2026-08-01 10:00:00,nominal,80.5,,\n",
        naglowek + "2026-08-01 10:00:00,nominal,nan,,\n",
        naglowek + "2026-08-01 10:00:00,nominal,inf,,\n",
        naglowek + "2026-08-01 10:00:00,nominal,1e400,,\n",
        naglowek + ",,,\n",
        naglowek + "zla data,nominal,80,,\n",
        naglowek + "2026-08-01 10:00:00,nominal," + "9" * 100000 + ",,\n",
        "\x00\xff" * 500,
        naglowek + "\n".join("2026-08-01 10:00:%02d,nominal,%d,," % (i % 60, i) for i in range(500)),
    ]
    for i in range(n):
        if s.time_elapsed():
            break
        s.n += 1
        content = variants[i] if i < len(variants) else s.rng.choice(variants)
        with open(HIST, "wb") as f:
            f.write(content.encode("utf-8", "surrogateescape"))
        t0 = s.rng.choice([0, time.time(), time.time() - 10 ** 9, -1, float("nan")])
        try:
            v = saferun.max_temp_since(t0)
        except Exception as e:
            s.error({"csv": shorten(content, 80), "t0": t0}, e)
            continue
        if v is not None and (not isinstance(v, float) or not math.isfinite(v)):
            s.nonsense({"csv": shorten(content, 80), "t0": t0},
                     "returned %r (non-finite temperature reaches message)" % (v,),
                     "MEDIUM", key="niesk")
    if os.path.exists(HIST):
        os.unlink(HIST)
    s.finish()


def fuzz_time_from(seed, n):
    s = Session("thermal-report.abs_epoch", seed)
    stale = ["", "2026-08-01 10:00:00", "2026-13-45 99:99:99", "0000-00-00 00:00:00",
             "9999-12-31 23:59:59", "1969-12-31 23:59:59", "\x00", "A" * 100000,
             None, 123, [], {}, b"2026-08-01 10:00:00", EMOJI]
    for i in range(n):
        if s.time_elapsed():
            break
        s.n += 1
        x = stale[i] if i < len(stale) else random_value(s.rng)
        try:
            v = treport.abs_epoch(x)
        except Exception as e:
            s.error(x, e)
            continue
        if not isinstance(v, (int, float)):
            s.nonsense(x, "returned %r instead of number" % (v,), "MEDIUM", key="zly-typ-wyniku")
    s.finish()


# ---------------------------------------------------------------- final report

def print_report(seed, n):
    print("=" * 78)
    print("FUZZING coffee-paladin - seed %s, %d random inputs per function" % (seed, n))
    print("working directory (TG_BASE): %s" % TMP)
    print("=" * 78)
    print("\n%-34s %8s %8s %8s %8s" % ("function", "runs", "sec", "errors", "findings"))
    print("-" * 78)
    for name, d in RUNS.items():
        print("%-34s %8d %8.2f %8d %8d"
              % (name, d["przebiegi"], d["sekundy"], d["bledy"], d["bzdury"]))

    print("\n" + "=" * 78)
    items = list(FINDINGS.values())
    if not items:
        print("FINDINGS: none - all functions survived the barrage.")
    else:
        print("FINDINGS (%d distinct; number in parentheses = triggering input count):" % len(items))
        kolejnosc = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        for i, z in enumerate(sorted(items, key=lambda x: (kolejnosc.get(x["powaga"], 9),
                                                           x["funkcja"])), 1):
            print("\n%d. [%s] %s  (x%d)" % (i, z["powaga"], z["funkcja"], z["ile"]))
            print("   what: %s" % z["opis"])
            print("   input: %s" % z["wejscie"])
    print("\n" + "=" * 78)
    clean_run = [n_ for n_ in RUNS if n_ in OK_FUNCTIONS]
    print("CLEAN (%d): %s" % (len(clean_run), ", ".join(clean_run) if clean_run else "-"))
    print("=" * 78)
    return 1 if any(z["powaga"] == "HIGH" for z in items) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260802)
    ap.add_argument("--n", type=int, default=250)
    a = ap.parse_args()
    seed, n = a.seed, a.n
    random.seed(seed)

    try:
        fuzz_load_cfg(seed, n)
        fuzz_severity(seed, n, hostile=False)
        fuzz_severity(seed, n, hostile=True)
        fuzz_normalize(seed, max(n, 300), guard, "guard.normalize_batt_temp")
        fuzz_normalize(seed, max(n, 300), heat, "heat.normalize_batt_temp")
        fuzz_cpu_with_children(seed, n)
        fuzz_pick_targets(seed, n)
        fuzz_args_without_paths(seed, n)
        fuzz_detect_hard_shutdown(seed, n)
        fuzz_day_stats(seed, n)
        fuzz_log_awake(seed, n)
        fuzz_heat_stuck(seed, n)
        fuzz_chip_already_hot(seed, n)
        fuzz_max_temp_since(seed, n)
        fuzz_time_from(seed, n)
        rc = print_report(seed, n)
    except Exception:
        traceback.print_exc()
        rc = 2
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
