#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A job that ends while the CPU limiter is about to stop it is still a success.

limited_wait() polls the job, then sends SIGSTOP to its process group. When the job
exits between the two calls, macOS answers EPERM (not ESRCH) for a group that holds
only the unreaped leader. safe-run died with a PermissionError traceback after a
job that had finished fine, so the wrapper reported a failure and never printed the
exit code. Seen three times in one session with short MLX jobs at --cpu-limit 50.

The window is microseconds wide in real use. Here guard_paused(), the call that sits
inside it, is slowed by 50 ms and the job is timed to exit in the middle of that.
Without the fix every round fails.

Run with:  python3 tests/test_safe_run_race.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import os
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg-race-")
os.environ.pop("TG_SAFE_RUN_PGID", None)      # not a nested run
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

sr = load_source("sr_race", os.path.join(SRC, "safe-run"))

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


real_guard_paused = sr.guard_paused


def slow_guard_paused(pid):
    time.sleep(0.05)
    return real_guard_paused(pid)


sr.guard_paused = slow_guard_paused

PCT = 50
RUN_T = 2.0 * PCT / 100
# The second guard_paused() call starts about 50 ms after the run slice and lasts
# 50 ms; the job exits in its middle.
EXIT_AT = RUN_T + 0.075
ROUNDS = 8


def group_states(pgid):
    out = subprocess.run(["ps", "-g", str(pgid), "-o", "stat="],
                         capture_output=True, text=True).stdout
    return out.split()


def run(cmd):
    proc = subprocess.Popen(cmd, preexec_fn=os.setsid)
    try:
        rc, killed = sr.limited_wait(proc, PCT, time.time() + 30)
        return "rc=%s killed=%s" % (rc, killed), proc
    except Exception as e:
        proc.wait()
        return "%s: %s" % (type(e).__name__, e), proc


print("Job exits between poll() and SIGSTOP (%d rounds)" % ROUNDS)
results = [run(["/bin/sleep", "%.3f" % EXIT_AT])[0] for _ in range(ROUNDS)]
bad = [r for r in results if r != "rc=0 killed=False"]
test("every round returns exit code 0, no exception", not bad, bad[:3])

print("Same, with a live grandchild left in the group")
result, proc = run(["/bin/sh", "-c", "/bin/sleep 3 & exec /bin/sleep %.3f" % EXIT_AT])
states = group_states(proc.pid)
test("returns exit code 0", result == "rc=0 killed=False", result)
test("the grandchild is not left stopped", states and not any(s.startswith("T") for s in states),
     states)
if states:
    os.killpg(proc.pid, 9)

print("Ordinary job under the limiter")
result, _ = run(["/bin/sh", "-c", "exit 3"])
test("a plain exit code still comes through", result == "rc=3 killed=False", result)

print("\n%d/%d passed" % (passed, total))
sys.exit(0 if passed == total else 1)
