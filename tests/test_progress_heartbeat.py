#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The progress heartbeat: $PALADIN_PROGRESS plumbing and the stall advisory.

Field failure this replaces: monitors guessing "stalled" thresholds by eye
(15, then 5, then 20 minutes against 21-84 minute encodes) produced three
false alarms in one day, and one of them removed a CPU cap with kill -CONT.
The contract: safe-run hands every job a file path in $PALADIN_PROGRESS and
touches it once at start; a job that DECLARED --progress-interval and went
3x quiet earns exactly one advisory (log + notify) - the guard never signals
a job over progress. No declaration, no verdict.

Run with:  python3 tests/test_progress_heartbeat.py
Uses live processes in a temporary TG_BASE; does not touch ~/.coffee-paladin.
"""
import importlib.machinery
import json
import os
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-progress-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
json.dump({}, open(os.path.join(BASE, "config.json"), "w"))

FAKE_BIN = os.path.join(BASE, "bin")
os.makedirs(FAKE_BIN)
with open(os.path.join(FAKE_BIN, "launchctl"), "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(os.path.join(FAKE_BIN, "launchctl"), 0o755)
ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en",
           PATH=FAKE_BIN + os.pathsep + os.environ.get("PATH", ""))

g = importlib.machinery.SourceFileLoader("hb_guard", os.path.join(SRC, "guard.py")).load_module()
g.notify = lambda *a, **k: None

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


print("=== safe-run hands the job a heartbeat file ===")
marker = os.path.join(BASE, "seen_env")
r = subprocess.run([sys.executable, os.path.join(SRC, "safe-run"), "--allow-hot",
                    "--name", "hb-env", "--hours", "1", "--",
                    "sh", "-c", 'echo "$PALADIN_PROGRESS" > %s; touch "$PALADIN_PROGRESS"' % marker],
                   env=ENV, capture_output=True, text=True, timeout=60)
seen = open(marker).read().strip() if os.path.exists(marker) else ""
test("1. $PALADIN_PROGRESS is exported and points into progress/",
     seen.startswith(os.path.join(BASE, "progress")), repr(seen))
test("2. the heartbeat file is cleaned up after the job", not os.path.exists(seen), seen)

print("=== registration carries the declaration ===")
p = subprocess.Popen([sys.executable, os.path.join(SRC, "safe-run"), "--allow-hot",
                      "--name", "hb-reg", "--hours", "1", "--progress-interval", "2",
                      "--", "sleep", "30"], env=ENV, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
reg = None
for _ in range(40):
    time.sleep(0.25)
    md = os.path.join(BASE, "managed")
    for fn in (os.listdir(md) if os.path.isdir(md) else []):
        if not fn.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(md, fn)))
        except Exception:
            continue
        if d.get("name") == "hb-reg":
            reg = d
            break
    if reg:
        break
test("3. managed entry has progress_path and interval",
     bool(reg) and reg.get("progress_interval_s") == 2
     and str(reg.get("progress_path", "")).startswith(os.path.join(BASE, "progress")),
     str(reg))

print("=== saferun_jobs: age, verdicts, resilience ===")
jobs = {j["name"]: j for j in g.saferun_jobs()}
j = jobs.get("hb-reg", {})
test("4. fresh heartbeat: small age, not stalled",
     j.get("progress_age_s") is not None and j["progress_age_s"] <= 3
     and j.get("progress_stalled") is False, str(j))

past = time.time() - 60
os.utime(reg["progress_path"], (past, past))
j = {x["name"]: x for x in g.saferun_jobs()}["hb-reg"]
test("5. 60 s of silence at a 2 s declaration = stalled",
     j.get("progress_stalled") is True and 55 <= j["progress_age_s"] <= 65, str(j))

reg2 = dict(reg, progress_interval_s=None)
json.dump(reg2, open(os.path.join(BASE, "managed", "%d.json" % reg["pid"]), "w"))
j = {x["name"]: x for x in g.saferun_jobs()}["hb-reg"]
test("6. no declaration: age reported, never a stall verdict",
     j.get("progress_stalled") is False and j.get("progress_age_s") is not None, str(j))

reg3 = dict(reg, progress_interval_s="junk", progress_path=12345)
json.dump(reg3, open(os.path.join(BASE, "managed", "%d.json" % reg["pid"]), "w"))
j = {x["name"]: x for x in g.saferun_jobs()}["hb-reg"]
test("7. junk declaration fields degrade to None, no crash",
     j.get("progress_stalled") is False and j.get("progress_age_s") is None, str(j))
json.dump(reg, open(os.path.join(BASE, "managed", "%d.json" % reg["pid"]), "w"))

print("=== the advisory: one sentence, no signals ===")
os.utime(reg["progress_path"], (past, past))
notes = []
g.notify = lambda cfg, title, text, key="": notes.append((title, key))
stat_before = subprocess.run(["ps", "-o", "stat=", "-p", str(reg["pid"])],
                             capture_output=True, text=True).stdout.strip()
jobs_now = g.saferun_jobs()
now = time.time()
for job in jobs_now:
    if not job.get("progress_stalled"):
        g._stall_said.pop(job["pid"], None)
        continue
    if now - g._stall_said.get(job["pid"], 0) < 1800:
        continue
    g._stall_said[job["pid"]] = now
    g.notify({}, "Thermal guard: job may be stalled", "x", key="stall")
test("8. stalled job earns exactly one advisory",
     [k for _, k in notes] == ["stall"], str(notes))
stat_after = subprocess.run(["ps", "-o", "stat=", "-p", str(reg["pid"])],
                            capture_output=True, text=True).stdout.strip()
test("9. the job was not signaled (state unchanged)",
     stat_before and stat_before == stat_after, "%r -> %r" % (stat_before, stat_after))

print("=== status CLI prints the advisory line ===")
out = subprocess.run([sys.executable, os.path.join(SRC, "guard.py"), "status"],
                     env=ENV, capture_output=True, text=True, timeout=60).stdout
test("10. 'stalled?' line with minutes and the declared interval",
     "stalled? hb-reg" in out and "declared every 2 s" in out, out[-300:])

try:
    os.killpg(os.getpgid(p.pid), 15)
except Exception:
    pass

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
