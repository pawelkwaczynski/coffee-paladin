#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Keep safe-run's messages out of a job's byte stream.

Run with:  python3 tests/test_safe_run_stdout.py
Uses an isolated TG_BASE and a no-op launchctl; never starts the real guard.
"""
import json
import os
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAFE_RUN = os.path.join(SRC, "safe-run")
BASE = tempfile.mkdtemp(prefix="tg-stdout-")
FAKE_BIN = os.path.join(BASE, "bin")
os.makedirs(FAKE_BIN)
# 21.10: TG_BASE isolates files but not launchd; a normal run may try to
# kickstart the real guard when no fresh snapshot is available.
with open(os.path.join(FAKE_BIN, "launchctl"), "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(os.path.join(FAKE_BIN, "launchctl"), 0o755)
ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en",
           PATH=FAKE_BIN + os.pathsep + os.environ.get("PATH", ""))
ENV.pop("TG_SAFE_RUN_PGID", None)
STATUS = os.path.join(BASE, "status.json")
PAYLOAD = b"A\x00B\n"
JOB = ["--", "/usr/bin/printf", "A\\000B\\n"]

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def run(options=(), nested=False):
    env = dict(ENV)
    if nested:
        env["TG_SAFE_RUN_PGID"] = "12345"
    return subprocess.run([sys.executable, SAFE_RUN] + list(options) + JOB,
                          env=env, capture_output=True, timeout=60)


with open(STATUS, "w") as f:
    json.dump({"level": 0, "chip_c": 45.0,
               "thresholds": {"pause": 85.0, "resume": 76.0}}, f)

# 21.10: printf's NUL byte exposes any wrapper status mixed into a pipeline.
r = run(["--normal", "--allow-sleep"])
test("normal run preserves exact stdout bytes", r.returncode == 0 and r.stdout == PAYLOAD,
     "rc=%s stdout=%r stderr=%r" % (r.returncode, r.stdout, r.stderr[-200:]))
test("normal run reports its summary on stderr", b"exit code 0" in r.stderr,
     repr(r.stderr[-200:]))

r = run(["--normal", "--allow-sleep", "--cpu-limit", "50"])
test("CPU-limited run preserves exact stdout bytes", r.returncode == 0 and r.stdout == PAYLOAD,
     "rc=%s stdout=%r stderr=%r" % (r.returncode, r.stdout, r.stderr[-200:]))

r = run(nested=True)
test("nested run preserves exact stdout bytes", r.returncode == 0 and r.stdout == PAYLOAD,
     "rc=%s stdout=%r stderr=%r" % (r.returncode, r.stdout, r.stderr[-200:]))
test("nested notice goes to stderr", b"already inside a supervised job" in r.stderr,
     repr(r.stderr[-200:]))

with open(STATUS, "w") as f:
    json.dump({"level": 2, "chip_c": 92.0,
               "thresholds": {"pause": 85.0, "resume": 76.0}}, f)
r = run(["--normal", "--allow-sleep"])
test("refusal has empty stdout and a reason on stderr",
     r.returncode == 3 and r.stdout == b"" and b"REFUSING TO START" in r.stderr
     and b"chip 92.0" in r.stderr,
     "rc=%s stdout=%r stderr=%r" % (r.returncode, r.stdout, r.stderr[-300:]))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
