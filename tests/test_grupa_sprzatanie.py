#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify safe-run process-group cleanup on exit and the --grace window.

If a safe-run leader receives SIGTERM from outside as a single pid, not killpg,
safe-run can exit and unregister the job while a child process remains in the group.
That child then runs without a time budget and without registration until manually
killed. This test recreates that layout with live processes and verifies group
cleanup catches it.

Run with:  python3 tests/test_grupa_sprzatanie.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import importlib.machinery
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
sr = importlib.machinery.SourceFileLoader("sr", os.path.join(SRC, "safe-run")).load_module()
json.dump({}, open(os.path.join(BASE, "config.json"), "w"))

passed = 0
total = 0
tracked_groups = {}
real_alive_in_group = sr.alive_in_group
process_table_available = real_alive_in_group(os.getpid()) is not None


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


def tracked_alive_in_group(pgid):
    if process_table_available:
        return real_alive_in_group(pgid)
    known = tracked_groups.get(pgid)
    if known is None:
        return None
    alive = []
    for pid in sorted(known):
        try:
            os.kill(pid, 0)
            if os.getpgid(pid) == pgid:
                alive.append(pid)
        except OSError:
            pass
    return alive


sr.alive_in_group = tracked_alive_in_group


def tracked_group(script):
    child_file = os.path.join(BASE, "child-%d.pid" % len(tracked_groups))
    env = dict(os.environ, TG_CHILD_PID=child_file)
    p = subprocess.Popen(["/bin/sh", "-c", script], preexec_fn=os.setsid, env=env)
    deadline = time.time() + 5.0
    child = None
    while time.time() < deadline:
        try:
            with open(child_file) as f:
                child = int(f.read().strip())
            break
        except (OSError, ValueError):
            time.sleep(0.05)
    tracked_groups[p.pid] = {p.pid}
    if child is not None:
        tracked_groups[p.pid].add(child)
    return p


def group_with_grandchild():
    """Start a leader in its own group with a background child in the same group."""
    if process_table_available:
        p = subprocess.Popen(["/bin/sh", "-c", "sleep 300 & exec sleep 300"],
                             preexec_fn=os.setsid)
    else:
        p = tracked_group('sleep 300 & echo $! > "$TG_CHILD_PID"; exec sleep 300')
    time.sleep(0.3)                       # Let sh start the background child.
    return p


print("safe-run: group cleanup + --grace")

# --- parser ---
argv0 = sys.argv
sys.argv = ["safe-run", "--", "true"]
opt, _ = sr.parse()
test("default grace = 30 s (existing behavior)", opt["grace"] == 30.0, str(opt))
sys.argv = ["safe-run", "--grace", "120", "--", "true"]
opt, _ = sr.parse()
test("--grace 120 sets the grace window", opt["grace"] == 120.0, str(opt))
sys.argv = ["safe-run", "--grace", "999999", "--", "true"]
opt, _ = sr.parse()
test("grace is capped at 1 h", opt["grace"] == 3600.0, str(opt))
sys.argv = argv0

# --- live processes in group ---
p = group_with_grandchild()
pids = sr.alive_in_group(p.pid)
test("sees leader and grandchild in group (>= 2 pids)", len(pids) >= 2, str(pids))
test("does not see US in the group", os.getpid() not in pids, str(pids))

# --- Reproduce single-pid leader termination while the grandchild remains ---
os.kill(p.pid, signal.SIGTERM)
p.wait()
time.sleep(0.3)
orphans = sr.alive_in_group(p.pid)
test("after leader dies, orphan grandchild is ALIVE in the group (incident repro)",
     len(orphans) >= 1, str(orphans))

t0 = time.time()
sr.sweep_group(p.pid, grace=5.0)
timestamp = time.time() - t0
test("sweep_group kills the orphan", sr.alive_in_group(p.pid) == [],
     str(sr.alive_in_group(p.pid)))
test("sleep dies on SIGTERM - without waiting the whole grace window", timestamp < 4.0,
     "%.1f s" % timestamp)

# --- Frozen orphan (state T): CONT before TERM, or the signal stays pending ---
p = group_with_grandchild()
os.kill(p.pid, signal.SIGTERM)
p.wait()
time.sleep(0.3)
orphans = sr.alive_in_group(p.pid)
for pid in orphans:
    os.kill(pid, signal.SIGSTOP)
sr.sweep_group(p.pid, grace=5.0)
test("frozen orphan also dies (CONT before TERM)",
     sr.alive_in_group(p.pid) == [], str(sr.alive_in_group(p.pid)))

# --- Stubborn process that ignores SIGTERM receives SIGKILL after the grace window ---
if process_table_available:
    p = subprocess.Popen(["/bin/sh", "-c", "trap '' TERM; sleep 300"],
                         preexec_fn=os.setsid)
else:
    p = tracked_group('trap "" TERM; sleep 300 & echo $! > "$TG_CHILD_PID"; wait')
time.sleep(0.3)
t0 = time.time()
sr.sweep_group(p.pid, grace=2.0)
p.wait()
timestamp = time.time() - t0
test("SIGTERM-ignoring process dies from SIGKILL after the grace window",
     sr.alive_in_group(p.pid) == [] and 1.5 <= timestamp < 8.0,
     "%.1f s, alive=%s" % (timestamp, sr.alive_in_group(p.pid)))

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
