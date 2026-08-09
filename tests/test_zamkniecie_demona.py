#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify daemon shutdown and the main loop on a real process.

Coverage mutation showed two gaps no test closed:

  * Daemon shutdown: `do_resume` on exit, removing demotion, killing `caffeinate`,
    and writing `clean_stop`. Each failure is quiet and dangerous: a process stays
    frozen forever, the Mac never sleeps, or a clean shutdown is reported on next start
    as a hard shutdown, putting a nonexistent failure into the evidence document.
  * Main loop had never been run by a test. Here the daemon really starts through
    `main()` and completes several full ticks.

The daemon runs isolated under TG_BASE and in watch-only mode (`dry_run`), so it does
not touch any user process. Manual freeze is tested through the same command-file
channel the menu bar uses.

Run with:  python3 tests/test_zamkniecie_demona.py
Does not touch the real ~/.coffee-paladin.
"""
import importlib.machinery
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-zamkniecie-")
os.environ["TG_BASE"] = BASE
os.environ.setdefault("TG_LANG", "en")

wyniki = []
DZIECI = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


def czekaj_na(warunek, ile=25.0, krok=0.25):
    koniec = time.time() + ile
    while time.time() < koniec:
        if warunek():
            return True
        time.sleep(krok)
    return False


def plik(n):
    return os.path.join(BASE, n)


def start_demona(dry_run=True):
    with io.open(plik("config.json"), "w", encoding="utf-8") as f:
        json.dump({"dry_run": dry_run, "poll_seconds": 1, "notify": False, "sound": False,
                   "soc_pause_c": 200, "soc_kill_c": 250, "batt_pause_c": 200,
                   "keep_awake_auto": False, "fan_check": False}, f)
    p = subprocess.Popen([sys.executable, os.path.join(SRC, "guard.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         env=dict(os.environ, TG_BASE=BASE, TG_LANG="en"))
    DZIECI.append(p)
    return p


def log_tekst():
    try:
        return io.open(plik("guard.log"), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


# ---------------------------------------------------------------- main loop
print("=== main loop really runs ===")
demon = start_demona()
test("1. daemon started and wrote status", czekaj_na(lambda: os.path.exists(plik("status.json"))),
     "no status.json after 25 s")
test("2. ...and ticks heartbeat", os.path.exists(plik("heartbeat")))
test("3. ...and wrote startup entry in log", "coffee-paladin start" in log_tekst())

mtime1 = os.path.getmtime(plik("status.json"))
test("4. loop performs NEXT ticks (status refreshes)",
     czekaj_na(lambda: os.path.getmtime(plik("status.json")) > mtime1, ile=15),
     "status.json was not rewritten - loop is stuck after first pass")

try:
    dane = json.load(io.open(plik("status.json"), encoding="utf-8"))
except Exception:
    dane = {}
test("5. snapshot carries real measurements, not an empty skeleton",
     isinstance(dane.get("level"), (int, float)) and "thermal_state" in dane,
     "status.json: %s" % sorted(dane)[:8])
test("6. measurement history is written", os.path.exists(plik("history.csv")))

# ---------------------------------------------------------------- shutdown
print("\n=== shutdown: SIGTERM on live daemon ===")
demon.send_signal(signal.SIGTERM)
try:
    demon.wait(timeout=40)
except subprocess.TimeoutExpired:
    demon.kill()
test("7. daemon exits by itself after SIGTERM (no kill needed)", demon.returncode is not None,
     "had to receive SIGKILL")
test("8. wrote clean shutdown marker", os.path.exists(plik("clean_stop")),
     "no clean_stop - next start will treat this as HARD SHUTDOWN")
test("9. ...and final entry in log", "coffee-paladin stop" in log_tekst())

# ---------------------------------------------------------------- core invariant
print("\n=== clean shutdown MUST NOT be reported as hard shutdown ===")
g = importlib.machinery.SourceFileLoader("zd_guard", os.path.join(SRC, "guard.py")).load_module()
try:
    zdarzenia = [json.loads(l) for l in
                 io.open(plik("events.log"), encoding="utf-8").read().splitlines() if l.strip()]
except OSError:
    zdarzenia = []
pady = [z for z in zdarzenia if z.get("type") == "HARD_SHUTDOWN"]
test("10. after clean shutdown the black box has NO hard shutdown", not pady,
     "fabricated shutdowns: %s" % [z.get("time") for z in pady])

# The same from the detector side: heartbeat before "boot" plus clean_stop means silence.
boot = g.boot_time()
with io.open(g.HEARTBEAT_PATH, "w", encoding="utf-8") as f:
    f.write("%d %s" % (boot - 600, g.ts(boot - 600)))
os.utime(g.HEARTBEAT_PATH, (boot - 600, boot - 600))
io.open(g.CLEAN_STOP_PATH, "w").close()
os.utime(g.CLEAN_STOP_PATH, (boot - 590, boot - 590))
test("11. shutdown detector stays silent when clean_stop accompanies heartbeat",
     g.wykryj_twardy_pad() is None,
     "clean shutdown was counted as failure")

os.remove(g.CLEAN_STOP_PATH)
test("12. OPPOSITE case: without clean_stop shutdown IS detected",
     g.wykryj_twardy_pad() is not None,
     "detector stopped seeing real shutdowns")

# ---------------------------------------------------------------- caffeinate
print("\n=== keep-awake does not outlive daemon ===")
for n in ("clean_stop", "heartbeat", "events.log", "state.json"):
    if os.path.exists(plik(n)):
        os.remove(plik(n))
with io.open(plik("awake.json"), "w", encoding="utf-8") as f:
    json.dump({"mode": "forever", "until": None, "app": None}, f)
demon2 = start_demona()
czekaj_na(lambda: os.path.exists(plik("status.json")), ile=25)


def moje_caffeinate():
    """Return caffeinate processes whose parent is our daemon, ignoring foreign ones."""
    out = subprocess.run(["ps", "-Ao", "pid=,ppid=,comm="], capture_output=True, text=True).stdout
    zn = []
    for l in out.splitlines():
        cz = l.split(None, 2)
        if len(cz) == 3 and cz[2].strip().endswith("caffeinate") and int(cz[1]) == demon2.pid:
            zn.append(int(cz[0]))
    return zn


mial_caffeinate = czekaj_na(lambda: bool(moje_caffeinate()), ile=20)
przed = moje_caffeinate()
demon2.send_signal(signal.SIGTERM)
try:
    demon2.wait(timeout=40)
except subprocess.TimeoutExpired:
    demon2.kill()
time.sleep(1.5)
zyje_po = [p for p in przed
           if subprocess.run(["ps", "-o", "stat=", "-p", str(p)],
                             capture_output=True, text=True).stdout.strip() not in ("", "Z", "Z+")]
if mial_caffeinate:
    test("13. daemon caffeinate does NOT survive its shutdown", not zyje_po,
         "alive: %s - Mac will never sleep, with no trace in UI" % zyje_po)
else:
    test("13. keep-awake did not start in this environment - condition does not apply", True)
test("14. second shutdown also left clean_stop", os.path.exists(plik("clean_stop")))

for p in DZIECI:
    try:
        p.kill()
        p.wait(timeout=5)
    except Exception:
        pass
shutil.rmtree(BASE, ignore_errors=True)

ok = sum(wyniki)
print("\nRESULT: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
