#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One process listing per cycle for every paused entry, not one ps per entry (22.10).

Found in review: on every hot cycle reassert_paused forked one identity ps per paused entry,
do_terminate up to three per entry and do_resume three per entry. The identity check stays
the same: a pid missing from the listing gets one targeted read of its own, and a listing
that failed is "unknown" for every entry (SIGCONT still goes, STOP and TERM wait).

Run with:  python3 tests/test_jeden_ps_20261022.py
Isolated TG_BASE; the only processes signalled are the ones this test starts (symlinks to
/bin/sleep in a temp dir, each in its own session).
"""
import os
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg-jeden-ps-")
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_jeden_ps", os.path.join(SRC, "guard.py"))
LINES = []
g.log = lambda msg, tag=None: LINES.append(msg)
g.notify = lambda *a, **k: None
CFG = dict(g.DEFAULTS, notify=False, dry_run=False, demote_at_pause=False)

BIN = tempfile.mkdtemp(prefix="tg-jeden-ps-bin-")
SLEEP = os.path.join(BIN, "jobsleep")
os.symlink("/bin/sleep", SLEEP)
N = 10
CHILDREN = []
REAL_RUN = g.run

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def stat(pid):
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()


class PsCount:
    """Count every ps the guard forks through run(), direct or through /usr/bin/env."""

    def __enter__(self):
        self.calls = []

        def counted(cmd, timeout=10):
            if "ps" in cmd[:4]:
                self.calls.append(" ".join(cmd))
            return REAL_RUN(cmd, timeout)
        g.run = counted
        return self

    def __exit__(self, *a):
        g.run = REAL_RUN


def batch():
    kids = []
    for _ in range(N):
        p = subprocess.Popen([SLEEP, "300"], start_new_session=True)
        CHILDREN.append(p)
        kids.append(p)
    time.sleep(0.4)
    st = {"paused": {}, "demoted": [], "demoted_info": {}}
    g.do_pause(CFG, st, [(p.pid, 90.0, "jobsleep", p.pid) for p in kids], "heat")
    time.sleep(0.2)
    return kids, st


try:
    print("1. reassert_paused: one ps for %d entries" % N)
    kids, st = batch()
    test("all %d children are paused with an identity" % N,
         len(st["paused"]) == N and all(v.get("born") for v in st["paused"].values()), st["paused"])
    os.kill(kids[0].pid, signal.SIGCONT)        # woken outside the guard, as a human would
    time.sleep(0.2)
    with PsCount() as count:
        g.reassert_paused(CFG, st)
    time.sleep(0.2)
    test("one ps for the whole cycle", len(count.calls) <= 1, count.calls)
    test("the woken child is stopped again", stat(kids[0].pid).startswith("T"), stat(kids[0].pid))
    test("every entry is kept", len(st["paused"]) == N, list(st["paused"]))

    print("2. do_resume: no identity re-read per entry")
    with PsCount() as count:
        g.do_resume(CFG, st, "cool", after_cooling=True)
    time.sleep(0.2)
    test("at most one listing plus one post-SIGCONT state read per entry",
         len(count.calls) <= N + 1, (len(count.calls), count.calls[:4]))
    test("every child runs again", not any(stat(p.pid).startswith("T") for p in kids),
         [stat(p.pid) for p in kids])
    test("flap memory still carries the start time",
         all(st["_last_resume"].get(str(p.pid), {}).get("born") for p in kids), st.get("_last_resume"))

    print("3. do_terminate: a constant number of ps, not one per entry")
    kids, st = batch()
    with PsCount() as count, patch.object(g.time, "sleep", lambda s: None):
        g.do_terminate(CFG, st, "critical")
    test("stopped_now plus one listing before and one after the grace",
         len(count.calls) <= 3, (len(count.calls), count.calls[:5]))
    for p in kids:
        p.wait(timeout=5)
    test("every child was terminated", all(p.returncode is not None for p in kids))

    print("4. three states from one listing")
    kids, st = batch()
    victim = kids[0].pid
    sent = []
    real_sig = g.sig

    def record(pid, pgid, s):
        sent.append((pid, s))
        return real_sig(pid, pgid, s)

    def without_victim(cmd, timeout=10):
        out = REAL_RUN(cmd, timeout)
        if "lstart=" in ",".join(cmd) and "-p" not in cmd:
            out = "\n".join(line for line in out.splitlines()
                            if not line.strip().startswith("%d " % victim))
        return out

    with patch.object(g, "sig", record), patch.object(g, "run", without_victim), \
            patch.object(g, "event_jsonl"):
        g.reassert_paused(CFG, st)
    test("a live pid missing from the listing is read on its own and still stopped",
         any(pid == victim for pid, _s in sent), sent)
    test("and its entry is kept", str(victim) in st["paused"], list(st["paused"]))
    test("every entry is signalled", len({pid for pid, _s in sent}) == N, sent)
    sent[:] = []
    before = len(st["paused"])
    with patch.object(g, "sig", record), patch.object(g, "run", lambda cmd, timeout=10: ""):
        g.reassert_paused(CFG, st)
        test("a failed listing: no STOP for anyone", not sent, sent)
        test("and every entry stays", len(st["paused"]) == before, list(st["paused"]))
        g.do_terminate(CFG, st, "critical")
        test("a failed listing: no TERM for anyone", not sent, sent)
        g.do_resume(CFG, st, "cool")
    test("a failed listing: SIGCONT still goes to every entry",
         len([1 for _pid, s in sent if s == signal.SIGCONT]) == before, sent)
    os.kill(victim, signal.SIGCONT)
finally:
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if BIN in line:
            pid = int(line.split(None, 1)[0])
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
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    left = [line for line in out.splitlines() if BIN in line]
    test("no test process left behind", not left, left)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
