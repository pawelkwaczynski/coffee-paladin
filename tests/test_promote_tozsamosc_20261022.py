#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Promotion checks who holds a demoted pid before taskpolicy -B (22.10).

Found in review: do_promote and the shutdown undo ran `taskpolicy -B` on every pid in
st['demoted'] with only alive() as a check, the shutdown left st['demoted'] in place, and the
startup branch for state from before boot cleared only 'paused'. A stale note promoted a
process somebody else had put in the background, and the log named a different program.

Run with:  python3 tests/test_promote_tozsamosc_20261022.py
Isolated TG_BASE; the daemon runs from this tree in watch-only mode. The only processes
touched are symlinks to /bin/sleep that this test starts and backgrounds itself.
"""
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-promote-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_promote_tozsamosc", os.path.join(SRC, "guard.py"))
LINES = []
g.log = lambda msg, tag=None: LINES.append(msg)
g.notify = lambda *a, **k: None
g.event_jsonl = lambda *a, **k: None
CFG = dict(g.DEFAULTS, notify=False, dry_run=False)

BIN = tempfile.mkdtemp(prefix="tg-promote-bin-")
SLEEP = os.path.join(BIN, "jobsleep")
os.symlink("/bin/sleep", SLEEP)
CHILDREN = []
STALE_BORN = 1700000000.0      # November 2023: no live test child started then

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def pri(pid):
    out = subprocess.run(["ps", "-o", "pri=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return int(out) if out else None


def backgrounded():
    """A sleep child this test starts and puts in the background itself, not the guard."""
    p = subprocess.Popen([SLEEP, "300"], start_new_session=True)
    CHILDREN.append(p)
    time.sleep(0.3)
    subprocess.call(["taskpolicy", "-b", "-p", str(p.pid)])
    time.sleep(0.2)
    return p


def wait_for(condition, amount=40.0):
    finish = time.time() + amount
    while time.time() < finish:
        if condition():
            return True
        time.sleep(0.25)
    return False


def run_daemon(state, mtime=None):
    """Start guard.py from this tree on BASE, let it tick, stop it with SIGTERM."""
    for name in ("status.json", "clean_stop", "heartbeat"):
        try:
            os.remove(os.path.join(BASE, name))
        except OSError:
            pass
    with io.open(os.path.join(BASE, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"dry_run": True, "poll_seconds": 1, "notify": False, "sound": False,
                   "soc_pause_c": 200, "soc_kill_c": 250, "batt_pause_c": 200,
                   "keep_awake_auto": False, "fan_check": False}, f)
    with io.open(g.STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f)
    if mtime is not None:
        os.utime(g.STATE_PATH, (mtime, mtime))
    d = subprocess.Popen([sys.executable, os.path.join(SRC, "guard.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=dict(os.environ, TG_BASE=BASE, TG_LANG="en"))
    CHILDREN.append(d)
    started = wait_for(lambda: os.path.exists(os.path.join(BASE, "status.json")))
    time.sleep(1.5)
    with io.open(g.STATE_PATH, encoding="utf-8") as f:
        running = json.load(f)
    d.send_signal(signal.SIGTERM)
    try:
        d.wait(timeout=40)
    except subprocess.TimeoutExpired:
        d.kill()
        d.wait(timeout=5)
    time.sleep(0.3)
    with io.open(g.STATE_PATH, encoding="utf-8") as f:
        after = json.load(f)
    return started, running, after


try:
    boot = g.boot_session_id()

    print("1. do_promote leaves a pid alone when the note names another process")
    p = backgrounded()
    test("the child is in the background (pri 4)", pri(p.pid) == 4, pri(p.pid))
    st = {"paused": {}, "demoted": [p.pid],
          "demoted_info": {str(p.pid): {"comm": "ffmpeg", "born": STALE_BORN, "boot_session": boot}}}
    g.do_promote(CFG, st, {}, 50.0)
    time.sleep(0.2)
    test("a note with another start time does not promote it", pri(p.pid) == 4, pri(p.pid))
    test("and the stale note is forgotten", p.pid not in st["demoted"] and not st["demoted_info"], st)
    test("the log does not claim a PROMOTED ffmpeg", not any(m.startswith("PROMOTED") for m in LINES), LINES)
    st = {"paused": {}, "demoted": [p.pid], "demoted_info": {str(p.pid): {"comm": "ffmpeg"}}}
    g.do_promote(CFG, st, {}, 50.0)
    time.sleep(0.2)
    test("a note from before identities that names ffmpeg does not promote a sleep",
         pri(p.pid) == 4, pri(p.pid))

    print("2. the guard's own demotion records an identity and is undone")
    q = subprocess.Popen([SLEEP, "300"], start_new_session=True)
    CHILDREN.append(q)
    time.sleep(0.3)
    st = {"paused": {}, "demoted": [], "demoted_info": {}}
    g.demote_pid(CFG, st, q.pid, "jobsleep", q.pid, 90.0, 95.0, "DEMOTED jobsleep")
    time.sleep(0.2)
    info = st["demoted_info"].get(str(q.pid), {})
    test("demote_pid records start time, command and boot",
         info.get("born") and info.get("comm") == "jobsleep" and info.get("boot_session") == boot, info)
    test("the child runs in the background", pri(q.pid) == 4, pri(q.pid))
    g.do_promote(CFG, st, {}, 50.0)
    time.sleep(0.2)
    test("the matching identity is promoted", pri(q.pid) == 31 and q.pid not in st["demoted"],
         (pri(q.pid), st["demoted"]))

    print("3. an unreadable identity does not keep a job slowed down")
    subprocess.call(["taskpolicy", "-b", "-p", str(q.pid)])
    st = {"paused": {}, "demoted": [q.pid],
          "demoted_info": {str(q.pid): {"comm": "jobsleep", "born": STALE_BORN, "boot_session": boot}}}
    with patch.object(g, "process_identity", return_value=None):
        g.do_promote(CFG, st, {}, 50.0)
    time.sleep(0.2)
    test("ps gives no answer: promotion goes ahead", pri(q.pid) == 31, pri(q.pid))

    print("4. daemon shutdown undoes only its own demotions and forgets the list")
    a = backgrounded()
    b = backgrounded()
    ident = g.process_identity(a.pid)
    state = {"paused": {}, "demoted": [a.pid, b.pid], "demoted_info": {
        str(a.pid): {"comm": "jobsleep", "born": ident[0] if ident else None, "boot_session": boot},
        str(b.pid): {"comm": "ffmpeg", "born": STALE_BORN, "boot_session": boot}}}
    started, _running, after = run_daemon(state)
    test("the daemon started", started)
    test("its own demotion is undone at shutdown", pri(a.pid) == 31, pri(a.pid))
    test("a note naming another process is not", pri(b.pid) == 4, pri(b.pid))
    test("state.json keeps no demotion after shutdown",
         after.get("demoted") == [] and after.get("demoted_info") == {}, after.get("demoted_info"))

    print("5. startup drops demotions from before boot, even with nothing paused")
    c = backgrounded()
    state = {"paused": {}, "demoted": [c.pid],
             "demoted_info": {str(c.pid): {"comm": "jobsleep"}}}
    started, running, _after = run_daemon(state, mtime=g.boot_time() - 600)
    test("the daemon started", started)
    test("a demotion from before boot is gone from the running state",
         running.get("demoted") == [] and running.get("demoted_info") == {}, running.get("demoted_info"))
    test("and nothing promoted the pid it named", pri(c.pid) == 4, pri(c.pid))
finally:
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if BIN in line:
            try:
                os.kill(int(line.split(None, 1)[0]), signal.SIGKILL)
            except OSError:
                pass
    for p in CHILDREN:
        try:
            if p.poll() is None and p.args[-1].endswith("guard.py"):
                p.send_signal(signal.SIGTERM)
            p.wait(timeout=40)
        except Exception:
            pass
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    left = [line for line in out.splitlines() if BIN in line]
    left += ["daemon pid %d" % p.pid for p in CHILDREN if p.poll() is None]
    test("no test process left behind", not left, left)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
