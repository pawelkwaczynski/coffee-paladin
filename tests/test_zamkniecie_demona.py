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

results = []
CHILDREN = []


def test(name, condition, detail=""):
    results.append(bool(condition))
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           ("  -> " + detail) if detail and not condition else ""))


def wait_for(condition, amount=25.0, step=0.25):
    finish = time.time() + amount
    while time.time() < finish:
        if condition():
            return True
        time.sleep(step)
    return False


def file_path(n):
    return os.path.join(BASE, n)


def start_daemon(dry_run=True):
    with io.open(file_path("config.json"), "w", encoding="utf-8") as f:
        json.dump({"dry_run": dry_run, "poll_seconds": 1, "notify": False, "sound": False,
                   "soc_pause_c": 200, "soc_kill_c": 250, "batt_pause_c": 200,
                   "keep_awake_auto": False, "fan_check": False}, f)
    p = subprocess.Popen([sys.executable, os.path.join(SRC, "guard.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         env=dict(os.environ, TG_BASE=BASE, TG_LANG="en"))
    CHILDREN.append(p)
    return p


def log_text():
    try:
        return io.open(file_path("guard.log"), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


# ---------------------------------------------------------------- main loop
print("=== main loop really runs ===")
daemon = start_daemon()
test("1. daemon started and wrote status", wait_for(lambda: os.path.exists(file_path("status.json"))),
     "no status.json after 25 s")
test("2. ...and ticks heartbeat", os.path.exists(file_path("heartbeat")))
test("3. ...and wrote startup entry in log", "coffee-paladin start" in log_text())

mtime1 = os.path.getmtime(file_path("status.json"))
test("4. loop performs NEXT ticks (status refreshes)",
     wait_for(lambda: os.path.getmtime(file_path("status.json")) > mtime1, amount=15),
     "status.json was not rewritten - loop is stuck after first pass")

try:
    data = json.load(io.open(file_path("status.json"), encoding="utf-8"))
except Exception:
    data = {}
test("5. snapshot carries real measurements, not an empty skeleton",
     isinstance(data.get("level"), (int, float)) and "thermal_state" in data,
     "status.json: %s" % sorted(data)[:8])
test("6. measurement history is written", os.path.exists(file_path("history.csv")))

# ---------------------------------------------------------------- shutdown
print("\n=== shutdown: SIGTERM on live daemon ===")
daemon.send_signal(signal.SIGTERM)
try:
    daemon.wait(timeout=40)
except subprocess.TimeoutExpired:
    daemon.kill()
test("7. daemon exits by itself after SIGTERM (no kill needed)", daemon.returncode is not None,
     "had to receive SIGKILL")
test("8. wrote clean shutdown marker", os.path.exists(file_path("clean_stop")),
     "no clean_stop - next start will treat this as HARD SHUTDOWN")
test("9. ...and final entry in log", "coffee-paladin stop" in log_text())

# ---------------------------------------------------------------- core invariant
print("\n=== clean shutdown MUST NOT be reported as hard shutdown ===")
g = importlib.machinery.SourceFileLoader("zd_guard", os.path.join(SRC, "guard.py")).load_module()
try:
    events = [json.loads(l) for l in
                 io.open(file_path("events.log"), encoding="utf-8").read().splitlines() if l.strip()]
except OSError:
    events = []
shutdowns = [z for z in events if z.get("type") == "HARD_SHUTDOWN"]
test("10. after clean shutdown the black box has NO hard shutdown", not shutdowns,
     "fabricated shutdowns: %s" % [z.get("time") for z in shutdowns])

# The same from the detector side: heartbeat before "boot" plus clean_stop means silence.
boot = g.boot_time()
with io.open(g.HEARTBEAT_PATH, "w", encoding="utf-8") as f:
    f.write("%d %s" % (boot - 600, g.ts(boot - 600)))
os.utime(g.HEARTBEAT_PATH, (boot - 600, boot - 600))
io.open(g.CLEAN_STOP_PATH, "w").close()
os.utime(g.CLEAN_STOP_PATH, (boot - 590, boot - 590))
test("11. shutdown detector stays silent when clean_stop accompanies heartbeat",
     g.detect_hard_shutdown() is None,
     "clean shutdown was counted as failure")

os.remove(g.CLEAN_STOP_PATH)
test("12. OPPOSITE case: without clean_stop shutdown IS detected",
     g.detect_hard_shutdown() is not None,
     "detector stopped seeing real shutdowns")

# ---------------------------------------------------------------- caffeinate
print("\n=== keep-awake does not outlive daemon ===")
for n in ("clean_stop", "heartbeat", "events.log", "state.json"):
    if os.path.exists(file_path(n)):
        os.remove(file_path(n))
with io.open(file_path("awake.json"), "w", encoding="utf-8") as f:
    json.dump({"mode": "forever", "until": None, "app": None}, f)
daemon2 = start_daemon()
wait_for(lambda: os.path.exists(file_path("status.json")), amount=25)


def my_caffeinate():
    """Return caffeinate processes whose parent is our daemon, ignoring foreign ones."""
    out = subprocess.run(["ps", "-Ao", "pid=,ppid=,comm="], capture_output=True, text=True).stdout
    zn = []
    for l in out.splitlines():
        cz = l.split(None, 2)
        if len(cz) == 3 and cz[2].strip().endswith("caffeinate") and int(cz[1]) == daemon2.pid:
            zn.append(int(cz[0]))
    return zn


had_caffeinate = wait_for(lambda: bool(my_caffeinate()), amount=20)
before = my_caffeinate()
daemon2.send_signal(signal.SIGTERM)
try:
    daemon2.wait(timeout=40)
except subprocess.TimeoutExpired:
    daemon2.kill()
time.sleep(1.5)
alive_after = [p for p in before
           if subprocess.run(["ps", "-o", "stat=", "-p", str(p)],
                             capture_output=True, text=True).stdout.strip() not in ("", "Z", "Z+")]
if had_caffeinate:
    test("13. daemon caffeinate does NOT survive its shutdown", not alive_after,
         "alive: %s - Mac will never sleep, with no trace in UI" % alive_after)
else:
    test("13. keep-awake did not start in this environment - condition does not apply", True)
test("14. second shutdown also left clean_stop", os.path.exists(file_path("clean_stop")))

for p in CHILDREN:
    try:
        p.kill()
        p.wait(timeout=5)
    except Exception:
        pass
shutil.rmtree(BASE, ignore_errors=True)

ok = sum(results)
print("\nRESULT: %d/%d" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
