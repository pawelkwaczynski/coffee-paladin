#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""safe-run --cores N on a protected app (23.10): protection wins, and every record says so.

Before, `safe-run --cores 1 -- OBS` printed "--cores 1 ... becomes a N% CPU limit" and right
after it "OBS is a protected app - no CPU limit"; the registration and job_start then said
cores=1, cpu_limit_pct=100 with nothing to tell a reader that the declaration was not enforced.

1. A protected command with --cores: no CPU-limit line, the protected-app line once, the summary
   shows all cores and no limit; job_start and managed/<pid>.json carry "protected": true,
   the declared cores and cpu_limit_pct 100.
2. Control: an ordinary command with --cores still gets the CPU-limit line, and its records
   have no "protected" field (absent, never false or null).
3. With admission control on, the protected job still queues with its declared cores and
   starts only once the arbiter admits it.
4. docs/spec/events-v1.md lists `protected` in the job_start table.

Run with:  python3 tests/test_protected_cores_20261023.py
Isolated TG_BASE and a no-op launchctl; the only processes started are safe-run and symlinks to
/bin/sleep, each ending by itself within seconds.
"""
import atexit
import glob
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAFE_RUN = os.path.join(SRC, "safe-run")
BASE = tempfile.mkdtemp(prefix="tg-protected-cores-")
STATUS = os.path.join(BASE, "status.json")
EVENTS = os.path.join(BASE, "history_events.jsonl")
MANAGED = os.path.join(BASE, "managed")
FAKE_BIN = os.path.join(BASE, "bin")
os.makedirs(FAKE_BIN)
with open(os.path.join(FAKE_BIN, "launchctl"), "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(os.path.join(FAKE_BIN, "launchctl"), 0o755)
ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en", SAFE_RUN_ADMIT_POLL="0.2",
           PATH=FAKE_BIN + os.pathsep + os.environ.get("PATH", ""))
for k in ("SAFE_RUN_QUIET", "TG_SAFE_RUN_PGID"):
    ENV.pop(k, None)

root = tempfile.mkdtemp(prefix="tg-protected-cores-bin-")
OBS = os.path.join(root, "OBS.app", "Contents", "MacOS", "OBS")
JOB = os.path.join(root, "jobrunner")
os.makedirs(os.path.dirname(OBS))
os.symlink("/bin/sleep", OBS)
os.symlink("/bin/sleep", JOB)
spawned = []

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def cleanup(p):
    # Only while safe-run is unreaped: then its pid and group number are still ours.
    if p.poll() is not None:
        return
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        p.wait(timeout=5)
    except Exception:
        pass


atexit.register(lambda: [cleanup(p) for p in spawned])


def write_status(extra=None):
    data = {"level": 0, "chip_c": 45.0, "thresholds": {"pause": 85.0, "resume": 76.0}}
    data.update(extra or {})
    with open(STATUS, "w") as f:
        json.dump(data, f)


def write_config(conf):
    with open(os.path.join(BASE, "config.json"), "w") as f:
        json.dump(conf, f)


def last_job_start():
    try:
        with open(EVENTS) as f:
            recs = [json.loads(line) for line in f if line.strip()]
    except OSError:
        return {}
    starts = [r for r in recs if r.get("type") == "job_start"]
    return starts[-1] if starts else {}


def registration_of(command, seconds=8):
    """The job's managed/<pid>.json, read while the job runs (safe-run removes it at the end)."""
    t0 = time.time()
    while time.time() - t0 < seconds:
        for path in glob.glob(os.path.join(MANAGED, "*.json")):
            try:
                with open(path) as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            if d.get("cmd", [None])[0] == command:
                return d
        time.sleep(0.05)
    return None


def run(command, extra=()):
    """safe-run --cores 1 on `command` sleeping 2 s; return (rc, stderr, registration)."""
    p = subprocess.Popen([sys.executable, SAFE_RUN, "--allow-sleep", "--cores", "1"] + list(extra)
                         + ["--", command, "2"], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         start_new_session=True)
    spawned.append(p)
    reg = registration_of(command)
    _out, err = p.communicate(timeout=30)
    return p.returncode, err.decode("utf-8", "replace"), reg


write_config({})
write_status()

print("1. --cores on a protected app")
rc, err, reg = run(OBS)
ev = last_job_start()
test("the job runs", rc == 0, (rc, err))
test("no CPU-limit line for a protected app", "becomes a" not in err, err)
test("the protected-app line is printed once", err.count("OBS is a protected app") == 1, err)
test("the summary shows all cores and no limit", "cores=all, CPU limit=100%" in err, err)
test("job_start says protected, keeps the declared cores, cap 100",
     ev.get("protected") is True and ev.get("cores") == 1 and ev.get("cpu_limit_pct") == 100, ev)
test("managed/<pid>.json says the same",
     reg is not None and reg.get("protected") is True and reg.get("cores") == 1
     and reg.get("cpu_limit_pct") == 100, reg)

print("2. control: --cores on an ordinary command")
rc, err, reg = run(JOB)
ev = last_job_start()
test("the CPU-limit line is still printed", rc == 0 and "becomes a" in err, err)
test("job_start has no protected field", ev and "protected" not in ev and ev.get("cores") == 1
     and ev.get("cpu_limit_pct", 100) < 100, ev)
test("managed/<pid>.json has no protected field", reg is not None and "protected" not in reg, reg)

print("3. admission control on: the protected job still queues with its cores")
write_config({"admission_control": True})
write_status({"admission": {"enabled": True, "budget_cores": 0, "used_cores": 0, "foreign_load": 0,
                            "admitted": [], "queued": []}})
p = subprocess.Popen([sys.executable, SAFE_RUN, "--allow-sleep", "--cores", "1", "--", OBS, "1"],
                     env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
spawned.append(p)
placeholder = os.path.join(MANAGED, "%d.json" % p.pid)
queued = None
t0 = time.time()
while time.time() - t0 < 8 and queued is None:
    try:
        with open(placeholder) as f:
            queued = json.load(f)
    except (OSError, ValueError):
        time.sleep(0.05)
time.sleep(0.6)
started_early = registration_of(OBS, seconds=0.1) is not None
test("the wrapper waits in the queue with its declared cores",
     queued is not None and queued.get("queued") is True and queued.get("cores") == 1, queued)
test("and does not start the job before admission", not started_early and p.poll() is None, p.poll())
write_status({"admission": {"enabled": True, "budget_cores": 1, "used_cores": 0, "foreign_load": 0,
                            "admitted": [p.pid], "queued": []}})
try:
    _out, err = p.communicate(timeout=30)
    err = err.decode("utf-8", "replace")
except subprocess.TimeoutExpired:
    cleanup(p)
    err = "timeout"
ev = last_job_start()
test("admitted, it starts as a protected job with its cores",
     p.returncode == 0 and "admitted" in err and ev.get("protected") is True and ev.get("cores") == 1,
     (p.returncode, err, ev))
write_config({})

print("4. the spec")
with open(os.path.join(SRC, "docs", "spec", "events-v1.md"), encoding="utf-8") as f:
    spec = f.read()
section = spec.split("### `job_start`", 1)[-1].split("\n### ", 1)[0]
row = next((line for line in section.splitlines() if re.match(r"\|\s*`protected`\s*\|", line)), "")
test("events-v1.md lists `protected` in job_start, as a boolean that is otherwise absent",
     "boolean" in row and "absent" in row, row)

for p in spawned:
    cleanup(p)
time.sleep(0.2)
left = subprocess.run(["pgrep", "-f", root], capture_output=True, text=True).stdout.split()
test("no test process left behind", not left, left)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
