#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`coffee-paladin status` must tell a guard pause from the duty limiter.

Field failure this guards against: both look like state T in `ps`, and a
monitor that confused them sent six `kill -CONT` into a healthy speed-limited
queue, briefly removing its CPU cap. The contract: status prints a "paused by
the guard" section with the termination clock, a separate "limited by the duty
cycle" section, keeps its first line parseable (`state=`), and status.json
carries structured `paused_details` plus per-job `cpu_limit_pct`.

Run with:  python3 tests/test_status_pauzy.py
Uses a temporary TG_BASE; reads the real sensors but signals nothing.
"""
import importlib.machinery
import json
import os
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-status-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"

# Shadow launchctl defensively: TG_BASE never isolates it.
FAKE_BIN = os.path.join(BASE, "bin")
os.makedirs(FAKE_BIN)
with open(os.path.join(FAKE_BIN, "launchctl"), "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(os.path.join(FAKE_BIN, "launchctl"), 0o755)
ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en",
           PATH=FAKE_BIN + os.pathsep + os.environ.get("PATH", ""))

passed = 0
total = 0
CHILDREN = []


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def launch():
    # DEVNULL is load-bearing: an inherited stdout pipe kept `tail` waiting for
    # EOF for five minutes after the test itself had finished.
    p = subprocess.Popen(["sleep", "300"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    CHILDREN.append(p)
    return p


json.dump({"max_pause_minutes": 45, "max_pause_minutes_batt": 240},
          open(os.path.join(BASE, "config.json"), "w"))

p_thermal, p_manual, p_batt, p_limited, p_free = (launch() for _ in range(5))
now = time.time()
json.dump({"paused": {
    str(p_thermal.pid): {"since": now - 17 * 60, "powod": "termika",
                         "comm": "ffmpeg", "pgid": p_thermal.pid, "manual": False},
    str(p_manual.pid): {"since": now - 5 * 60, "powod": "termika",
                        "comm": "render", "pgid": p_manual.pid, "manual": True},
    str(p_batt.pid): {"since": now - 30 * 60, "powod": "bateria",
                      "comm": "train", "pgid": p_batt.pid, "manual": False},
}}, open(os.path.join(BASE, "state.json"), "w"))

os.makedirs(os.path.join(BASE, "managed"))
json.dump({"pid": p_limited.pid, "pgid": p_limited.pid, "name": "capped-job",
           "cpu_limit_pct": 80}, open(os.path.join(BASE, "managed", "%d.json" % p_limited.pid), "w"))
json.dump({"pid": p_free.pid, "pgid": p_free.pid, "name": "full-speed",
           "cpu_limit_pct": 100}, open(os.path.join(BASE, "managed", "%d.json" % p_free.pid), "w"))
# The thermal-paused job is ALSO speed-limited: it must appear only under the
# guard-pause section, never under "not a guard pause".
json.dump({"pid": p_thermal.pid, "pgid": p_thermal.pid, "name": "paused-and-capped",
           "cpu_limit_pct": 70}, open(os.path.join(BASE, "managed", "%d.json" % p_thermal.pid), "w"))
# Hand-written registrations: a string cap must normalise, garbage must not
# hide the remaining jobs behind the broad except.
p_strcap, p_garbage = launch(), launch()
json.dump({"pid": p_strcap.pid, "pgid": p_strcap.pid, "name": "string-cap",
           "cpu_limit_pct": "60"}, open(os.path.join(BASE, "managed", "%d.json" % p_strcap.pid), "w"))
json.dump({"pid": p_garbage.pid, "pgid": p_garbage.pid, "name": "garbage-cap",
           "cpu_limit_pct": "abc"}, open(os.path.join(BASE, "managed", "%d.json" % p_garbage.pid), "w"))

out = subprocess.run([sys.executable, os.path.join(SRC, "guard.py"), "status"],
                     env=ENV, capture_output=True, text=True, timeout=60).stdout

print("=== the CLI printout ===")
test("1. first line keeps the parser contract (state=)",
     out.splitlines() and out.splitlines()[0].startswith("state="), out[:120])
test("2. guard-pause section present", "paused by the guard:" in out, out)
test("3. thermal pause shows the termination clock",
     "ffmpeg" in out and "termination in 28 min" in out, out)
test("4. manual freeze promises no automatic termination",
     "render" in out and "no automatic termination" in out, out)
test("5. battery entry uses the SAME limit the daemon enforces now (45 on AC/cool)",
     "train" in out and "termination in 15 min" in out, out)
test("6. duty-cycle section names only the capped job",
     "limited by the safe-run duty cycle" in out and "capped-job" in out
     and "full-speed" not in out.split("limited by")[1], out)
test("7. the duty section says T-blinks are normal", "T-state blinks are normal" in out, out)
duty_part = out.split("limited by")[1] if "limited by" in out else ""
test("7b. a guard-paused job never lands under 'not a guard pause'",
     "paused-and-capped" not in duty_part, out)
test("7c. a string cap normalises, garbage does not hide the other jobs",
     "string-cap" in duty_part and "cap 60%" in duty_part
     and "garbage-cap" not in duty_part, out)

print("=== status.json: structured fields ===")
g = importlib.machinery.SourceFileLoader("st_guard", os.path.join(SRC, "guard.py")).load_module()
g.notify = lambda *a, **k: None
# The daemon loop initialises this before its first status_write; a direct call
# has to do the same.
g._ostatnio_odrzucone["v"] = []
st = g.load_state()
st["_zadania"] = g.saferun_jobs()
g.status_write("nominal", 30.0, None, None, True, 100, 100, 1.0, 0, "", [], st)
snap = json.load(open(os.path.join(BASE, "status.json")))
details = {d["name"]: d for d in snap.get("paused_details", [])}
test("8. paused_details lists all three with reason and age",
     set(details) == {"ffmpeg", "render", "train"}
     and details["ffmpeg"]["reason"] == "termika"
     and details["train"]["reason"] == "bateria"
     and details["render"]["manual"] is True
     and 16 * 60 < details["ffmpeg"]["age_s"] < 18 * 60, str(details))
jobs = {j["name"]: j for j in snap.get("jobs", [])}
test("9. jobs carry cpu_limit_pct and the cpu_limited flag",
     jobs.get("capped-job", {}).get("cpu_limited") is True
     and jobs.get("capped-job", {}).get("cpu_limit_pct") == 80
     and jobs.get("full-speed", {}).get("cpu_limited") is False, str(jobs))
test("10. hand-written caps: string normalised, garbage becomes None not a crash",
     jobs.get("string-cap", {}).get("cpu_limit_pct") == 60
     and jobs.get("garbage-cap", {}).get("cpu_limit_pct") is None
     and jobs.get("garbage-cap", {}).get("cpu_limited") is False, str(jobs))

print("=== pause_limit_min: one formula for the loop and for status ===")
cfg45 = {"max_pause_minutes": 45, "max_pause_minutes_batt": 240,
         "batt_pause_c": 40, "soc_pause_c": 95}
test("11. battery-only situation gets the long limit",
     g.pause_limit_min(cfg45, ac=False, lvl=2, soc_t=50.0, temp=30.0) == 240)
test("12. hot chip keeps the short limit even on battery",
     g.pause_limit_min(cfg45, ac=False, lvl=2, soc_t=94.0, temp=30.0) == 45)
test("13. on AC always the short limit",
     g.pause_limit_min(cfg45, ac=True, lvl=2, soc_t=50.0, temp=30.0) == 45)

print("=== do_pause: structural battery flag, not string sniffing ===")
p_ru = launch()
st_ru = {"paused": {}, "reczna_pauza": False}
cfg_live = g.load_cfg()
cfg_live["dry_run"] = False
g.do_pause(cfg_live, st_ru, [(p_ru.pid, 95.0, "sleep", os.getpgid(p_ru.pid))],
           "какая-то русская причина с батареей", battery_reason=True)
entry = st_ru["paused"].get(str(p_ru.pid), {})
test("14. battery pause classified from the flag, whatever the language says",
     entry.get("powod") == "bateria", str(entry))
g.do_resume(cfg_live, st_ru, "cleanup")

for p in CHILDREN:
    try:
        p.kill()
    except Exception:
        pass

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
