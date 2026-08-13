#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the exit-code contract of the safe-run time budget.

A budget kill used to exit as 128+signal, indistinguishable from a crash or an
external kill. The contract under test: budget exhaustion exits 124 (the
timeout(1) convention), regardless of how the child dies during cleanup; every
other ending keeps its old code.

Run with:  python3 tests/test_budget_exit.py
Uses live processes in a temporary TG_BASE; does not touch ~/.coffee-paladin.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAFE_RUN = os.path.join(SRC, "safe-run")
BASE = tempfile.mkdtemp()
json.dump({}, open(os.path.join(BASE, "config.json"), "w"))
# TG_BASE does not isolate launchctl (services are per-user, not per-HOME), and
# safe-run kickstarts the daemon when it looks dead. Shadow launchctl with a
# no-op so the test can never start or restart the real guard.
FAKE_BIN = os.path.join(BASE, "bin")
os.makedirs(FAKE_BIN)
with open(os.path.join(FAKE_BIN, "launchctl"), "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(os.path.join(FAKE_BIN, "launchctl"), 0o755)
ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en",
           PATH=FAKE_BIN + os.pathsep + os.environ.get("PATH", ""))

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def run(args, timeout=60):
    return subprocess.run(
        [sys.executable, SAFE_RUN, "--allow-hot", "--name", "budget-test"] + args,
        env=ENV, capture_output=True, text=True, timeout=timeout)


# 1. Budget fires on a SIGTERM-ignoring child: 124, not 128+SIGKILL (137).
r = run(["--hours", "0.001", "--grace", "1", "--",
         sys.executable, "-c",
         "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)"])
test("1. TERM-ignoring child under budget -> 124", r.returncode == 124,
     "rc=%s out=%s" % (r.returncode, r.stdout[-300:]))
test("2. budget ending is announced", "TIME BUDGET" in r.stdout, r.stdout[-300:])

# 2. A polite child that exits 0 on SIGTERM is still a budget ending: 124, not 0.
r = run(["--hours", "0.001", "--grace", "5", "--",
         sys.executable, "-c",
         "import signal,sys,time; signal.signal(signal.SIGTERM, lambda *a: sys.exit(0)); time.sleep(120)"])
test("3. child exiting 0 on TERM under budget -> still 124", r.returncode == 124,
     "rc=%s" % r.returncode)

# 3. An external SIGTERM (no budget involved) keeps the signal convention: 143.
p = subprocess.Popen(
    [sys.executable, SAFE_RUN, "--allow-hot", "--name", "budget-test", "--hours", "1",
     "--grace", "1", "--", "sleep", "120"],
    env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(3)  # let the job register and start
os.kill(p.pid, signal.SIGTERM)
p.wait(timeout=30)
test("4. external kill -> 143, not 124", p.returncode == 143, "rc=%s" % p.returncode)

# 4. A child that itself exits 124 passes through without the budget label.
r = run(["--hours", "1", "--", sys.executable, "-c", "raise SystemExit(124)"])
test("5. child's own 124 passes through", r.returncode == 124, "rc=%s" % r.returncode)
test("6. ...without the budget label",
     "terminated by the time budget" not in r.stdout, r.stdout[-300:])

# 5. A clean, fast child still exits 0.
r = run(["--hours", "1", "--", "true"])
test("7. clean job -> 0", r.returncode == 0, "rc=%s" % r.returncode)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
