#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Czy config.json moze OSLEPIC strażnika, ktory dalej melduje, ze dziala.

Dwa realne sposoby (znalezione 02.08.2026 przez recenzenta bezpieczenstwa):

1. ZLY TYP. Jedna literowka w liczbie ("cpu_min_percent": "dwadziescia") wywalala
   TypeError w kazdym cyklu petli. Wyjatek byl lapany, wiec demon zyl - ale
   status.json przestawal byc zapisywany, nic nie bylo pauzowane, a `heat`
   pokazywal "coffee-paladin: dziala". Straznik zywy i slepy.

2. PUSTY STRING na liscie nietykalnych. "" pasuje do KAZDEJ nazwy procesu
   (bo "" in "cokolwiek" == True), wiec jedna pusta linia w never_extra
   sprawiala, ze zaden proces nie byl juz kandydatem do pauzy. Bez ostrzezenia.

Uruchomienie:  python3 tests/test_config_odporny.py
Pracuje w katalogu tymczasowym - nie dotyka prawdziwego ~/.coffee-paladin.
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

# --- 1. zly typ nie wywala petli ---
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

# --- 2. pusty string nie oslepia ---
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

# --- 3. wlasne nazwy zawsze chronione ---
cfg = ustaw({"never_patterns": ["cokolwiek"]})
test("wlasne nazwy sa dopisywane mimo wlasnej listy uzytkownika",
     all(n in cfg["never_patterns"] for n in g.WLASNE_NAZWY),
     "lista: %s" % cfg["never_patterns"])

# --- 4. nieznane klucze przezywaja (kompatybilnosc w przod) ---
cfg = ustaw({"klucz_z_przyszlosci": {"a": [1, 2]}})
test("nieznany klucz nie jest kasowany", cfg.get("klucz_z_przyszlosci") == {"a": [1, 2]},
     "wartosc: %r" % cfg.get("klucz_z_przyszlosci"))

# --- 5. progi musza rosnac: wznowienie < pauza < ubicie ---
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

# --- 6. wzorce nietykalnych dopasowuja TOZSAMOSC procesu, nie sciezke do danych ---
wzorce = [w.lower() for w in g.load_cfg()["never_arg_patterns"]]


def chroniony(cmd):
    zostaw = [a for a in cmd.split()
              if not ("/" in a and os.path.splitext(a)[1].lower() in g.ROZSZERZENIA_DANYCH)]
    return any(w in " ".join(zostaw).lower() for w in wzorce)


for opis, cmd, oczekiwane in [
    ("wideo w katalogu z 'claude' w nazwie jest pauzowalne",
     "ffmpeg -i /Users/x/Desktop/claude_brain/wideo/rec.mkv out.mp4", False),
    ("model .gguf w katalogu 'mcp' jest pauzowalny",
     "python3 run.py --model /Users/x/mcp/modele/qwen.gguf", False),
    ("serwer MCP pozostaje nietykalny", "node /opt/claude/mcp-server.js", True),
    ("agent claude pozostaje nietykalny", "/usr/local/bin/claude --resume", True),
    ("language server pozostaje nietykalny",
     "node /usr/lib/node_modules/typescript-language-server/lib/cli.js", True),
    ("rozszerzenie VS Code pozostaje nietykalne",
     "python3 /Users/x/.vscode/extensions/foo/run.py", True),
]:
    test(opis, chroniony(cmd) is oczekiwane, "cmd: %s" % cmd[:60])

shutil.rmtree(BASE, ignore_errors=True)
print("\nWYNIK: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
