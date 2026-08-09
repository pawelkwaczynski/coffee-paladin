#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure config.json cannot blind a guard that still reports itself alive.

Two real failure modes are covered:

1. Wrong type. A typo in a number ("cpu_min_percent": "dwadziescia") raised TypeError
   in every loop cycle. The exception was caught, so the daemon stayed alive, but
   status.json stopped updating, nothing was paused, and `heat` reported that
   coffee-paladin was running. The guard was alive and blind.

2. Empty string on an untouchable list. "" matches every process name because
   "" in "cokolwiek" is True, so one blank line in never_extra made every process
   ineligible for pause, with no warning.

Run with:  python3 tests/test_config_odporny.py
Runs in a temporary directory and does not touch the real ~/.coffee-paladin.
"""
import importlib.machinery
import json
import os
import shutil
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

PROCS = [(9991, 1, 600.0, "ffmpeg"), (9992, 1, 300.0, "blender")]
zaliczone = 0
wszystkie = 0


def test(nazwa, warunek, szczegol=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s  -> %s" % (nazwa, szczegol))


def ustaw(cfg):
    json.dump(cfg, open(os.path.join(BASE, "config.json"), "w"))
    return g.load_cfg()


print("config.json cannot blind the guard")

# --- 1. A bad type does not crash the loop ---
for klucz, smiec in [("cpu_min_percent", "dwadziescia"), ("soc_pause_c", None),
                     ("poll_seconds", []), ("job_cpu_percent", {"a": 1}),
                     ("notify", "tak"), ("never_extra", "ffmpeg")]:
    cfg = ustaw({klucz: smiec})
    try:
        cele = g.pick_targets(cfg, PROCS, {})
        test("bad type in %r does not crash target selection" % klucz, True)
    except Exception as e:
        test("bad type in %r does not crash target selection" % klucz, False,
             "%s: %s" % (type(e).__name__, e))

cfg = ustaw({"cpu_min_percent": "dwadziescia"})
test("bad number falls back to the default",
     isinstance(cfg["cpu_min_percent"], (int, float)),
     "type: %s" % type(cfg["cpu_min_percent"]).__name__)

cfg = ustaw({"notify": "tak"})
test("bad bool falls back to the default", cfg["notify"] is g.DEFAULTS["notify"],
     "value: %r" % cfg["notify"])

cfg = ustaw({"soc_pause_c": "88"})
test("number supplied as text is cast, not rejected",
     abs(float(cfg["soc_pause_c"]) - 88.0) < 0.01, "value: %r" % cfg["soc_pause_c"])

# --- 2. An empty string does not blind the guard ---
for klucz in ("never_extra", "never_patterns", "never_arg_patterns"):
    cfg = ustaw({klucz: [""]})
    cele = g.pick_targets(cfg, PROCS, {})
    test("empty string in %s does not remove all candidates" % klucz,
         len(cele) == 2, "candidates: %d" % len(cele))

cfg = ustaw({"never_extra": ["", "   ", None, 7, "blender"]})
cele = g.pick_targets(cfg, PROCS, {})
test("junk in list filtered out, real entry WORKS",
     len(cele) == 1 and cele[0][2] == "ffmpeg",
     "candidates: %s" % [c[2] for c in cele])

# --- 3. The guard's own process names are always protected ---
cfg = ustaw({"never_patterns": ["cokolwiek"]})
test("own names are appended despite the user's own list",
     all(n in cfg["never_patterns"] for n in g.WLASNE_NAZWY),
     "list: %s" % cfg["never_patterns"])

# --- 4. Unknown keys survive for forward compatibility ---
cfg = ustaw({"klucz_z_przyszlosci": {"a": [1, 2]}})
test("unknown key is not removed", cfg.get("klucz_z_przyszlosci") == {"a": [1, 2]},
     "value: %r" % cfg.get("klucz_z_przyszlosci"))

# --- 5. Thresholds must increase: resume < pause < kill ---
cfg = ustaw({"soc_resume_c": 95, "soc_pause_c": 85})
test("resume >= pause is lowered (otherwise every cycle oscillates)",
     cfg["soc_resume_c"] < cfg["soc_pause_c"],
     "r=%s p=%s" % (cfg["soc_resume_c"], cfg["soc_pause_c"]))

cfg = ustaw({"soc_pause_c": 85, "soc_kill_c": 80})
test("kill <= pause is raised (otherwise SIGTERM at a healthy 82 C)",
     cfg["soc_pause_c"] < cfg["soc_kill_c"],
     "p=%s k=%s" % (cfg["soc_pause_c"], cfg["soc_kill_c"]))

cfg = ustaw({"soc_resume_c": 70, "soc_pause_c": 85, "soc_kill_c": 92})
test("valid thresholds stay untouched",
     (cfg["soc_resume_c"], cfg["soc_pause_c"], cfg["soc_kill_c"]) == (70.0, 85.0, 92.0),
     "%s" % [cfg["soc_resume_c"], cfg["soc_pause_c"], cfg["soc_kill_c"]])

# --- 6. Untouchable patterns match process identity, not data paths ---
wzorce = [w.lower() for w in g.load_cfg()["never_arg_patterns"]]


def chroniony(cmd):
    """Call the real guard.args_bez_sciezek, not a local copy.

    A previous local copy drifted from production: it always used argv[1], while
    production uses the first non-flag argument. A test against the copy can pass
    while production is broken, so it tests nothing.
    """
    stary = g.full_args
    g.full_args = lambda pid, _w=cmd: _w
    try:
        args = g.args_bez_sciezek(1)
    finally:
        g.full_args = stary
    return any(w in args for w in wzorce)


for opis, cmd, oczekiwane in [
    ("video in a directory with 'claude' in the name is pausable",
     "ffmpeg -i /Users/x/Desktop/claude_brain/wideo/rec.mkv out.mp4", False),
    ("extension outside the list (.braw) is also pausable",
     "x265 -y -i /Users/x/cursor_projekt/rec.braw -o out.mp4", False),
    ("space in path does not make it untouchable",
     "ffmpeg -i /Users/x/Desktop/claude brain/rec.mkv out.mp4", False),
    ("directory as an argument does not make it untouchable",
     "ffmpeg -y -i in.mp4 /Users/x/Desktop/mcp_dane/out/", False),
    ("agent in a file with a data extension KEEPS protection",
     "python3 /Users/x/claude/agent.pt", True),
    ("mcp server as a module keeps protection",
     "python3 -m mcp.server", True),
    ("MCP server remains untouchable", "node /opt/claude/mcp-server.js", True),
    ("claude agent remains untouchable", "/usr/local/bin/claude --resume", True),
    ("language server remains untouchable",
     "node /usr/lib/node_modules/typescript-language-server/lib/cli.js", True),
    ("VS Code extension remains untouchable",
     "python3 /Users/x/.vscode/extensions/foo/run.py", True),
    # A hard-coded interpreter version list ended at python3.13. With python3.14,
    # an agent launched under the full name lost protection.
    ("agent under python3.14 (version outside hard-coded list) KEEPS protection",
     "python3.14 /Users/x/claude/agent.py", True),
    ("agent under /opt/homebrew/bin/python3.14 KEEPS protection",
     "/opt/homebrew/bin/python3.14 /Users/x/.vscode/extensions/foo/run.py", True),
    ("agent under a future version (python3.20) KEEPS protection",
     "python3.20 -m mcp.server", True),
    ("agent under node20 KEEPS protection", "node20 /opt/claude/mcp-server.js", True),
    # Countercase: broadening the interpreter list must not make a plain encoder
    # untouchable.
    ("video processed by python3.14 is still pausable",
     "python3.14 /Users/x/skrypty/kompresor.py /Users/x/Desktop/claude_brain/rec.mkv", False),
]:
    test(opis, chroniony(cmd) is oczekiwane, "cmd: %s" % cmd[:60])

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
