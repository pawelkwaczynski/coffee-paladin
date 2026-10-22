#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A paused job group whose leader died, against real processes (22.10).

Found in review: a zombie leader ("<defunct>" in ps) was taken for a reused pid, so its
entry was dropped with no signal and the stopped children of its group stayed in T forever.
A reaped leader ended the same way through "process gone". do_terminate skipped the SIGKILL
when the leader was a zombie, so a child that ignores SIGTERM kept running, and it skipped
the whole group when the leader was already reaped.

Run with:  python3 tests/test_martwy_lider_20261022.py
Isolated TG_BASE; the only processes signalled are the ones this test starts (symlinks to
/bin/sh and /bin/sleep in a temp dir, each job in its own session).
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg-martwy-lider-")
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_martwy_lider", os.path.join(SRC, "guard.py"))
LINES = []
g.log = lambda msg, tag=None: LINES.append(msg)
g.notify = lambda *a, **k: None
CFG = dict(g.DEFAULTS, notify=False, dry_run=False, demote_at_pause=False)

BIN = tempfile.mkdtemp(prefix="tg-martwy-lider-bin-")
SH = os.path.join(BIN, "jobsh")
SLEEP = os.path.join(BIN, "jobsleep")
os.symlink("/bin/sh", SH)
os.symlink("/bin/sleep", SLEEP)
REAL_SLEEP = time.sleep
CHILDREN = []

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def spawn(script):
    p = subprocess.Popen([SH, "-c", script, "jobsh", SLEEP], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    CHILDREN.append(p)
    REAL_SLEEP(0.5)
    return p


def group(pgid):
    """[(pid, stat)] of every process in the group, the zombie leader included."""
    out = subprocess.run(["ps", "-Ao", "pid=,pgid=,stat="], capture_output=True, text=True).stdout
    rows = [line.split(None, 2) for line in out.splitlines()]
    return [(int(r[0]), r[2].strip()) for r in rows if len(r) == 3 and r[1] == str(pgid)]


def stopped(pgid):
    return [pid for pid, s in group(pgid) if s.startswith("T")]


def running(pgid):
    return [pid for pid, s in group(pgid) if not s.startswith("Z")]


def pause(p):
    comm = next(c for pid, _ppid, _cpu, c in g.list_procs() if pid == p.pid)
    st = {"paused": {}, "demoted": [], "demoted_info": {}}
    g.do_pause(CFG, st, [(p.pid, 99.0, comm, p.pid)], "heat")
    REAL_SLEEP(0.3)
    return st


def events():
    try:
        with open(g.HISTORY_EVENTS_PATH) as f:
            return [json.loads(line) for line in f if line.strip()]
    except OSError:
        return []


def nap(_seconds):
    REAL_SLEEP(0.5)   # do_terminate's 20 s grace, shortened


HUP_JOB = "trap '' HUP; \"$1\" 300 & \"$1\" 301 & wait"
TERM_JOB = "(trap '' TERM; exec \"$1\" 300) & exec \"$1\" 299"

try:
    print("1. zombie leader: kept by reassert, its group resumed by do_resume")
    p = spawn(HUP_JOB)
    st = pause(p)
    test("both children are stopped by the pause", len(stopped(p.pid)) >= 2, group(p.pid))
    os.kill(p.pid, signal.SIGKILL)          # killed from outside; its parent (this test) does not wait
    REAL_SLEEP(0.3)
    test("the leader is a zombie", dict(group(p.pid)).get(p.pid, "").startswith("Z"), group(p.pid))
    g.reassert_paused(CFG, st)
    test("reassert keeps the entry (a zombie is not a reused pid)", str(p.pid) in st["paused"], st["paused"])
    g.do_resume(CFG, st, "cool")
    REAL_SLEEP(0.3)
    test("no member left in T after do_resume", not stopped(p.pid), group(p.pid))
    test("the entry is gone once the group was resumed", str(p.pid) not in st["paused"], st["paused"])
    test("no 'another process' line in the log", not any("another process" in m for m in LINES), LINES)
    test("no pid_reused event", not any(e.get("reason") == "pid_reused" for e in events()), events())

    print("2. reaped leader: the loop keeps the entry, do_resume resumes the group")
    p = spawn(HUP_JOB)
    st = pause(p)
    os.kill(p.pid, signal.SIGKILL)
    p.wait(timeout=5)
    REAL_SLEEP(0.3)
    test("the children are still stopped after the leader was reaped", len(stopped(p.pid)) >= 2, group(p.pid))
    gone = getattr(g, "gone_entries", None)
    kept = gone is not None and str(p.pid) not in gone(st["paused"], g.stopped_now())
    test("the main loop's dead-entry cleanup keeps it while its group is stopped", kept,
         "gone_entries missing" if gone is None else gone(st["paused"], g.stopped_now()))
    g.reassert_paused(CFG, st)
    test("reassert keeps the entry", str(p.pid) in st["paused"], st["paused"])
    LINES[:] = []
    g.do_resume(CFG, st, "cool")
    REAL_SLEEP(0.3)
    test("no member left in T after do_resume", not stopped(p.pid), group(p.pid))
    test("the entry is gone once the group was resumed", str(p.pid) not in st["paused"], st["paused"])
    test("the log says the leader is gone and its group was resumed",
         any("process group %d" % p.pid in m for m in LINES), LINES)

    print("3. do_terminate: the leader dies on TERM, a child that ignores TERM gets SIGKILL")
    p = spawn(TERM_JOB)
    st = pause(p)
    test("the job group is stopped", len(stopped(p.pid)) >= 2, group(p.pid))
    with patch.object(g.time, "sleep", nap):
        g.do_terminate(CFG, st, "critical")
    REAL_SLEEP(0.3)
    test("nothing of the group runs any more (only the zombie leader is left)", not running(p.pid), group(p.pid))

    print("4. do_terminate: the leader was reaped before the pause expired")
    p = spawn(TERM_JOB)
    st = pause(p)
    os.kill(p.pid, signal.SIGKILL)
    p.wait(timeout=5)
    REAL_SLEEP(0.3)
    test("the orphaned child is still stopped", stopped(p.pid), group(p.pid))
    with patch.object(g.time, "sleep", nap):
        g.do_terminate(CFG, st, "paused too long")
    REAL_SLEEP(0.3)
    test("the orphaned group was terminated, nothing is left", not group(p.pid), group(p.pid))
    test("the entry is gone", str(p.pid) not in st["paused"], st["paused"])

    print("5. a leader that died with nothing stopped behind it is dropped as gone")
    p = spawn("exec \"$1\" 300")
    st = pause(p)
    os.kill(p.pid, signal.SIGKILL)
    REAL_SLEEP(0.3)
    LINES[:] = []
    g.do_resume(CFG, st, "cool")
    test("the zombie's entry is dropped", str(p.pid) not in st["paused"], st["paused"])
    test("and the log says process gone, not reused",
         any("process gone" in m for m in LINES) and not any("another process" in m for m in LINES), LINES)
finally:
    mine = []
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if BIN in line:
            mine.append(int(line.split(None, 1)[0]))
    for pid in mine:
        for s in (signal.SIGCONT, signal.SIGKILL):
            try:
                os.kill(pid, s)
            except OSError:
                pass
    for p in CHILDREN:
        try:
            p.wait(timeout=5)
        except Exception:
            pass
    REAL_SLEEP(0.3)
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    left = [line for line in out.splitlines() if BIN in line]
    test("no test process left behind", not left, left)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
