#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Signal decisions when the one-per-cycle process listing is cut short or fails (22.10).

Found in review, four holes:
1. A listing cut short after this process's own row made every later paused pid look
   gone, so its entry was dropped as a reused pid and its group stayed stopped.
2. A dead leader's group SIGCONT that failed with EPERM still deleted the entry.
3. With stopped_now() fine and the listing failed, a reaped leader's group got SIGTERM
   with no identity check at all.
4. After SIGTERM the entry was gone; if the listing after the grace failed, the SIGKILL
   was skipped and nothing was left to try again.

Fault injection only: fake pids above the macOS pid range (4000000+), with os.kill,
os.killpg, sig and the listings patched, so no real process can receive a signal.
Run with:  python3 tests/test_lista_niepelna_20261022.py
"""
import errno
import os
import signal
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg-lista-niepelna-")
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_lista_niepelna", os.path.join(SRC, "guard.py"))
LINES = []
g.log = lambda msg, tag=None: LINES.append(msg)
g.notify = lambda *a, **k: None
g.event_jsonl = lambda *a, **k: None
CFG = dict(g.DEFAULTS, notify=False, dry_run=False, demote_at_pause=False)

LSTART = "Thu Oct 22 13:01:57 2026"
BORN = time.mktime(time.strptime(LSTART, "%a %b %d %H:%M:%S %Y"))
SELF = {os.getpid(): (LSTART, "python3", os.getpid(), "S")}
P, KID = 4000001, 4000002

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def entry(pid=P, born=BORN):
    return {str(pid): {"since": g.now() - 9000, "comm": "sleep", "pgid": pid, "born": born,
                       "boot_session": "boot", "powod": "termika", "manual": False}}


def no_such(*_a):
    raise ProcessLookupError(errno.ESRCH, "No such process")


def common():
    return [patch.object(g, "boot_session_id", return_value="boot"),
            patch.object(g, "protected_app", return_value=False),
            patch.object(g.time, "sleep", lambda s: None)]


class Patches:
    def __init__(self, *ps):
        self.ps = list(ps) + common()

    def __enter__(self):
        for p in self.ps:
            p.start()

    def __exit__(self, *a):
        for p in reversed(self.ps):
            p.stop()


sent = []


def record(pid, pgid, s):
    sent.append(signal.Signals(s).name)
    return 0


print("1. a listing cut short after our own row")


def targeted(cmd, timeout=10):
    """The one targeted read a missing pid gets: identity, group state, post-CONT state."""
    if "-p" in cmd and "lstart=,pgid=,comm=" in cmd:
        return "%s %d sleep\n" % (LSTART, P)
    if "-g" in cmd:
        return "T\nT\n"
    return "S\n"


st = {"paused": entry()}
sent[:] = []
with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
             patch.object(g, "process_table", return_value=dict(SELF)),
             patch.object(g, "run", targeted)):
    g.reassert_paused(CFG, st)
test("the paused pid missing from the listing is read on its own and still stopped",
     sent == ["SIGSTOP"] and str(P) in st["paused"], (sent, list(st["paused"])))
st = {"paused": entry(born=BORN - 500)}
sent[:] = []
with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
             patch.object(g, "process_table", return_value=dict(SELF)),
             patch.object(g, "run", targeted)):
    g.reassert_paused(CFG, st)
test("a targeted read that shows another process still drops it, no signal",
     sent == [] and str(P) not in st["paused"], (sent, list(st["paused"])))
st = {"paused": entry()}
cont = []
with Patches(patch.object(g.os, "kill", no_such),
             patch.object(g.os, "killpg", lambda pg, s: cont.append((pg, s))),
             patch.object(g, "process_table", return_value=dict(SELF)),
             patch.object(g, "run", targeted)):
    g.do_resume(CFG, st, "cool")
test("a dead leader whose group the listing lost: the group still gets SIGCONT",
     cont == [(P, signal.SIGCONT)], cont)

print("2. the group SIGCONT of a dead leader fails with EPERM")


def eperm(pg, s):
    raise PermissionError(errno.EPERM, "Operation not permitted")


stopped_kid = dict(SELF)
stopped_kid[KID] = (LSTART, "sleep", P, "T")
st = {"paused": entry()}
with Patches(patch.object(g.os, "kill", no_such), patch.object(g.os, "killpg", eperm),
             patch.object(g, "process_table", return_value=stopped_kid)):
    g.do_resume(CFG, st, "cool")
test("the entry stays for the next attempt", str(P) in st["paused"], list(st["paused"]))
with Patches(patch.object(g.os, "kill", no_such), patch.object(g.os, "killpg", no_such),
             patch.object(g, "process_table", return_value=stopped_kid)):
    g.do_resume(CFG, st, "cool")
test("ESRCH (the group is gone) still drops it", str(P) not in st["paused"], list(st["paused"]))

print("3. stopped_now() works, the listing fails, the leader was reaped")
st = {"paused": entry()}
sent[:] = []
with Patches(patch.object(g, "alive", return_value=False), patch.object(g, "sig", record),
             patch.object(g, "stopped_now", return_value=({KID}, {P})),
             patch.object(g, "process_table", return_value={})):
    g.do_terminate(CFG, st, "paused too long")
test("no SIGTERM or SIGKILL without a readable listing",
     "SIGTERM" not in sent and "SIGKILL" not in sent, sent)
test("the entry stays for the next cycle", str(P) in st["paused"], list(st["paused"]))

print("4. the listing after the 20 s grace fails")
row = dict(SELF)
row[P] = (LSTART, "sleep", P, "T")
st = {"paused": entry()}
sent[:] = []
with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
             patch.object(g, "stopped_now", return_value=({P}, {P})),
             patch.object(g, "process_table", side_effect=[row, {}])):
    g.do_terminate(CFG, st, "paused too long")
test("TERM went, the KILL waits for a readable listing",
     sent == ["SIGCONT", "SIGTERM"], sent)
test("the entry is kept, so the KILL is not forgotten", str(P) in st["paused"], list(st["paused"]))
sent[:] = []
running = (set(), set())       # the TERM-ignoring job runs after the SIGCONT
with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
             patch.object(g, "stopped_now", return_value=running),
             patch.object(g, "process_table", side_effect=[row, row])):
    expired = g.expired_entries(st["paused"], 60, running)
    test("the kept entry is due again although its job runs", expired == [str(P)], expired)
    test("and is not taken for a job resumed outside the guard",
         g.stale_entries(st["paused"], running) == [], g.stale_entries(st["paused"], running))
    g.do_terminate(CFG, st, "paused too long", only_keys=expired)
test("the next do_terminate repeats TERM and sends the KILL",
     sent == ["SIGCONT", "SIGTERM", "SIGKILL"] and str(P) not in st["paused"], (sent, list(st["paused"])))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
