#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bezpieczenstwo: pgid, listy nietykalnych, wyciek tematu ntfy (pozycje 10, 11, 12).

  * poz. 10 - `pgid` z managed/ byl przepisywany z pliku DOSLOWNIE. Rejestracja to
    zwykly JSON na dysku, wiec plik {"pid": A, "pgid": B} kierowal SIGSTOP/SIGKILL
    do grupy B - czyli NIE do zarejestrowanego zadania. Do tego nikt nie sprawdzal,
    kto ten plik napisal.
  * poz. 11 - listy nietykalnych dopasowuja po PODCIAGU, wiec `mds_solver` jest
    nietykalny przez `mds`. Dopasowania NIE zawezamy (asymetria ryzyka: falszywa
    ochrona = goracy Mac, utrata ochrony = zamrozony agent AI), ale przestaje ono
    byc CICHE.
  * poz. 12 - temat ntfy siedzial w URL-u w argv `curl`, czyli byl widoczny w `ps`
    dla kazdego uzytkownika maszyny. Temat jest JEDYNYM zabezpieczeniem tego kanalu.

Uruchomienie:  python3 tests/test_bezpieczenstwo.py
Nie dotyka prawdziwego ~/.coffee-paladin.
"""
import importlib.machinery
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-bezp-")
os.environ["TG_BASE"] = BASE
os.environ.setdefault("TG_LANG", "en")
os.makedirs(os.path.join(BASE, "managed"), exist_ok=True)

g = importlib.machinery.SourceFileLoader("bz_guard", os.path.join(SRC, "guard.py")).load_module()

wyniki = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


def rejestruj(pid, pgid, prawa=0o600, started=None):
    p = os.path.join(BASE, "managed", "%d.json" % pid)
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump({"pid": pid, "pgid": pgid,
                   "started": started if started is not None else time.time() - 1}, f)
    os.chmod(p, prawa)
    return p


# ---------------------------------------------------------------- poz. 10
print("=== poz. 10: pgid bierzemy z JADRA, nie z pliku ===")
# start_new_session: wlasna grupa procesow, inaczej pgid nie rozni sie od naszego
ofiara = subprocess.Popen(["sleep", "300"], start_new_session=True)
prawdziwy = os.getpgid(ofiara.pid)
cudzy = os.getpgid(0)
rejestruj(ofiara.pid, cudzy)              # w pliku CUDZE pgid
res, _ = g.managed_pids_from_saferun()
test("1. guard uzywa PRAWDZIWEGO pgid procesu, nie tego z pliku",
     res.get(ofiara.pid) == prawdziwy,
     "odczytal %s, prawdziwe %s, podstawione %s" % (res.get(ofiara.pid), prawdziwy, cudzy))
test("2. ...czyli sygnal NIE poleci do podstawionej grupy",
     res.get(ofiara.pid) != cudzy or prawdziwy == cudzy)

drugi = subprocess.Popen(["sleep", "300"], start_new_session=True)
sciezka = rejestruj(drugi.pid, os.getpgid(drugi.pid), prawa=0o666)
res, _ = g.managed_pids_from_saferun()
test("3. rejestracja zapisywalna dla innych jest IGNOROWANA", drugi.pid not in res,
     "plik 0666 zostal przyjety")
os.chmod(sciezka, 0o600)
res, _ = g.managed_pids_from_saferun()
test("4. ta sama rejestracja z prawami 0600 jest przyjeta", drugi.pid in res,
     "blokujemy wlasne, poprawne zadania")

ofiara.kill(); ofiara.wait()
drugi.kill(); drugi.wait()
for n in os.listdir(os.path.join(BASE, "managed")):
    os.remove(os.path.join(BASE, "managed", n))

# ---------------------------------------------------------------- poz. 11
print("\n=== poz. 11: ochrona po podciagu ZOSTAJE, ale przestaje milczec ===")
cfg = g.load_cfg()
cfg["cpu_min_percent"] = 10
cfg["manage_unknown_heavy"] = True
g.args_bez_sciezek = lambda pid: "x"
g.pierwszoplanowy_na_tty = lambda pid: False
g.proc_age_seconds = lambda pid: 9999
g.cpu_z_dziecmi = lambda procs: {}
g._NIETYKALNI_PODCIAG.clear()
if os.path.exists(g.LOG_PATH):
    os.remove(g.LOG_PATH)

procs = [(4001, 1, 90.0, "mds_solver"), (4002, 1, 85.0, "sshd-worker"),
         (4003, 1, 95.0, "ffmpeg"), (4004, 1, 88.0, "mds")]
cele = [c[2] for c in g.pick_targets(cfg, procs, {})]
log = io.open(g.LOG_PATH, encoding="utf-8", errors="replace").read() if os.path.exists(g.LOG_PATH) else ""

test("5. ochrona NIE zostala oslabiona - mds_solver dalej nietykalny",
     "mds_solver" not in cele, "cele: %s" % cele)
test("6. sshd-worker tez nietykalny", "sshd-worker" not in cele, "cele: %s" % cele)
test("7. zwykly enkoder nadal pauzowalny", "ffmpeg" in cele, "cele: %s" % cele)
test("8. log MOWI, dlaczego goracy mds_solver jest pomijany",
     "mds_solver" in log and "untouchable" in log,
     "brak wyjasnienia w logu - uzytkownik dostaje cisze")
test("9. przy PELNYM dopasowaniu (mds) nie ma halasu w logu",
     "mds uses" not in log, "logujemy takze oczywiste przypadki")

# ---------------------------------------------------------------- poz. 12
print("\n=== poz. 12: temat ntfy nie moze byc widoczny w ps ===")
BIN = os.path.join(BASE, "bin")
os.makedirs(BIN, exist_ok=True)
with io.open(os.path.join(BIN, "curl"), "w", encoding="utf-8") as f:
    f.write('#!/bin/sh\nprintf "%s\\n" "$*" > "$0.argv"\ncat > "$0.stdin"\n')
os.chmod(os.path.join(BIN, "curl"), 0o755)
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]

TEMAT = "sekretny_temat_ABC123"
cfg = g.load_cfg()
cfg["notify"] = True
cfg["ntfy_topic"] = TEMAT
g.push(cfg, "Cooling alarm", "chip 98.7 C, fans 0 rpm")
# `push` uruchamia curla W TLE, wiec czekamy na PLIK, nie na staly czas. Sztywne
# `sleep(0.8)` wystarczalo na wolnym Macu, ale w pelnej baterii testow pod limiterem
# CPU atrapa nie zdazyla zapisac i test wywalal sie na FileNotFoundError - dwa razy
# w bramce wydania 03.08. Test, ktory czasem pada bez powodu, psuje bramke tak samo
# jak test, ktory nie pada nigdy.
_argv_path = os.path.join(BIN, "curl.argv")
_stdin_path = os.path.join(BIN, "curl.stdin")
_koniec = time.time() + 20.0
while time.time() < _koniec:
    if os.path.exists(_argv_path) and os.path.exists(_stdin_path):
        break
    time.sleep(0.05)
argv = io.open(_argv_path, encoding="utf-8").read() if os.path.exists(_argv_path) else ""
stdin = io.open(_stdin_path, encoding="utf-8").read() if os.path.exists(_stdin_path) else ""
test("9b. atrapa curla w ogole zostala uruchomiona (inaczej reszta nic nie dowodzi)",
     bool(argv), "curl.argv nie powstal w 20 s - test ponizej bylby falszywie zielony")

test("10. tematu NIE MA w argv (czyli nie ma go w ps)", TEMAT not in argv,
     "argv: %s" % argv.strip()[:110])
test("11. tresci alertu tez nie ma w argv", "98.7" not in argv,
     "argv: %s" % argv.strip()[:110])
test("12. temat idzie stdin-em, czyli push nadal DZIALA", TEMAT in stdin,
     "stdin: %s" % stdin.strip()[:110])
test("13. tresc i tytul dochodza w ciele", "98.7" in stdin and "Cooling alarm" in stdin,
     "stdin: %s" % stdin.strip()[:110])

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(wyniki)
print("\nWYNIK: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
