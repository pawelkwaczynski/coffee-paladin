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


print("config.json nie moze oslepic bezpiecznika")

# --- 1. A bad type does not crash the loop ---
for klucz, smiec in [("cpu_min_percent", "dwadziescia"), ("soc_pause_c", None),
                     ("poll_seconds", []), ("job_cpu_percent", {"a": 1}),
                     ("notify", "tak"), ("never_extra", "ffmpeg")]:
    cfg = ustaw({klucz: smiec})
    try:
        cele = g.pick_targets(cfg, PROCS, {})
        test("zly typ w %r nie wywala wyboru celow" % klucz, True)
    except Exception as e:
        test("zly typ w %r nie wywala wyboru celow" % klucz, False,
             "%s: %s" % (type(e).__name__, e))

cfg = ustaw({"cpu_min_percent": "dwadziescia"})
test("zla liczba wraca do wartosci domyslnej",
     isinstance(cfg["cpu_min_percent"], (int, float)),
     "typ: %s" % type(cfg["cpu_min_percent"]).__name__)

cfg = ustaw({"notify": "tak"})
test("zly bool wraca do wartosci domyslnej", cfg["notify"] is g.DEFAULTS["notify"],
     "wartosc: %r" % cfg["notify"])

cfg = ustaw({"soc_pause_c": "88"})
test("liczba podana jako tekst jest rzutowana, nie odrzucana",
     abs(float(cfg["soc_pause_c"]) - 88.0) < 0.01, "wartosc: %r" % cfg["soc_pause_c"])

# --- 2. An empty string does not blind the guard ---
for klucz in ("never_extra", "never_patterns", "never_arg_patterns"):
    cfg = ustaw({klucz: [""]})
    cele = g.pick_targets(cfg, PROCS, {})
    test("pusty string w %s nie zabiera wszystkich kandydatow" % klucz,
         len(cele) == 2, "kandydatow: %d" % len(cele))

cfg = ustaw({"never_extra": ["", "   ", None, 7, "blender"]})
cele = g.pick_targets(cfg, PROCS, {})
test("smieci na liscie odfiltrowane, prawdziwy wpis DZIALA",
     len(cele) == 1 and cele[0][2] == "ffmpeg",
     "kandydaci: %s" % [c[2] for c in cele])

# --- 3. The guard's own process names are always protected ---
cfg = ustaw({"never_patterns": ["cokolwiek"]})
test("wlasne nazwy sa dopisywane mimo wlasnej listy uzytkownika",
     all(n in cfg["never_patterns"] for n in g.WLASNE_NAZWY),
     "lista: %s" % cfg["never_patterns"])

# --- 4. Unknown keys survive for forward compatibility ---
cfg = ustaw({"klucz_z_przyszlosci": {"a": [1, 2]}})
test("nieznany klucz nie jest kasowany", cfg.get("klucz_z_przyszlosci") == {"a": [1, 2]},
     "wartosc: %r" % cfg.get("klucz_z_przyszlosci"))

# --- 5. Thresholds must increase: resume < pause < kill ---
cfg = ustaw({"soc_resume_c": 95, "soc_pause_c": 85})
test("wznowienie >= pauzy jest obnizane (inaczej mlynek co cykl)",
     cfg["soc_resume_c"] < cfg["soc_pause_c"],
     "r=%s p=%s" % (cfg["soc_resume_c"], cfg["soc_pause_c"]))

cfg = ustaw({"soc_pause_c": 85, "soc_kill_c": 80})
test("ubicie <= pauzy jest podnoszone (inaczej SIGTERM przy zdrowych 82 C)",
     cfg["soc_pause_c"] < cfg["soc_kill_c"],
     "p=%s k=%s" % (cfg["soc_pause_c"], cfg["soc_kill_c"]))

cfg = ustaw({"soc_resume_c": 70, "soc_pause_c": 85, "soc_kill_c": 92})
test("poprawne progi zostaja nietkniete",
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
    ("wideo w katalogu z 'claude' w nazwie jest pauzowalne",
     "ffmpeg -i /Users/x/Desktop/claude_brain/wideo/rec.mkv out.mp4", False),
    ("rozszerzenie spoza listy (.braw) tez jest pauzowalne",
     "x265 -y -i /Users/x/cursor_projekt/rec.braw -o out.mp4", False),
    ("spacja w sciezce nie daje nietykalnosci",
     "ffmpeg -i /Users/x/Desktop/claude brain/rec.mkv out.mp4", False),
    ("katalog jako argument nie daje nietykalnosci",
     "ffmpeg -y -i in.mp4 /Users/x/Desktop/mcp_dane/out/", False),
    ("agent w pliku o rozszerzeniu danych ZACHOWUJE ochrone",
     "python3 /Users/x/claude/agent.pt", True),
    ("serwer mcp jako modul zachowuje ochrone",
     "python3 -m mcp.server", True),
    ("serwer MCP pozostaje nietykalny", "node /opt/claude/mcp-server.js", True),
    ("agent claude pozostaje nietykalny", "/usr/local/bin/claude --resume", True),
    ("language server pozostaje nietykalny",
     "node /usr/lib/node_modules/typescript-language-server/lib/cli.js", True),
    ("rozszerzenie VS Code pozostaje nietykalne",
     "python3 /Users/x/.vscode/extensions/foo/run.py", True),
    # A hard-coded interpreter version list ended at python3.13. With python3.14,
    # an agent launched under the full name lost protection.
    ("agent pod python3.14 (wersja spoza twardej listy) ZACHOWUJE ochrone",
     "python3.14 /Users/x/claude/agent.py", True),
    ("agent pod /opt/homebrew/bin/python3.14 ZACHOWUJE ochrone",
     "/opt/homebrew/bin/python3.14 /Users/x/.vscode/extensions/foo/run.py", True),
    ("agent pod przyszla wersja (python3.20) ZACHOWUJE ochrone",
     "python3.20 -m mcp.server", True),
    ("agent pod node20 ZACHOWUJE ochrone", "node20 /opt/claude/mcp-server.js", True),
    # Countercase: broadening the interpreter list must not make a plain encoder
    # untouchable.
    ("wideo mielone przez python3.14 nadal jest pauzowalne",
     "python3.14 /Users/x/skrypty/kompresor.py /Users/x/Desktop/claude_brain/rec.mkv", False),
]:
    test(opis, chroniony(cmd) is oczekiwane, "cmd: %s" % cmd[:60])

shutil.rmtree(BASE, ignore_errors=True)
print("\nWYNIK: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
