#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""An entry that got SIGTERM and still owes its SIGKILL (term_sent) is not a pause (23.10).

do_terminate keeps such an entry when the listing after the 20 s grace fails, so the next
call can finish the job. Three places still treated it as an ordinary pause:

1. reassert_paused (every hot cycle) sent it SIGSTOP, freezing a job in its SIGTERM cleanup.
2. A manual resume from the menu bar resumed it and deleted the entry, so the owed SIGKILL was
   forgotten.
3. status.json listed it in paused_details exactly like a pause; it now says "terminating",
   and the field is absent for an ordinary pause (docs/spec/metrics-v1.md).

Fault injection only: fake pids above the macOS pid range (4000000+), with sig, the listings
and ps patched, so no real process can receive a signal.
Run with:  python3 tests/test_term_sent_20261023.py
"""
import os
import re
import signal
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg-term-sent-")
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_term_sent", os.path.join(SRC, "guard.py"))
LINES = []
g.log = lambda msg, tag=None: LINES.append(msg)
g.notify = lambda *a, **k: None
g.event_jsonl = lambda *a, **k: None
CFG = dict(g.DEFAULTS, notify=False, dry_run=False, demote_at_pause=False)

LSTART = "Thu Oct 22 13:01:57 2026"
BORN = time.mktime(time.strptime(LSTART, "%a %b %d %H:%M:%S %Y"))
SELF = {os.getpid(): (LSTART, "python3", os.getpid(), "S")}
P, Q = 4000011, 4000013          # P owes its KILL, Q is an ordinary pause

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def entry(pid):
    return {"since": g.now() - 9000, "comm": "sleep", "pgid": pid, "born": BORN,
            "boot_session": "boot", "powod": "termika", "manual": False}


class Patches:
    def __init__(self, *ps):
        self.ps = list(ps) + [patch.object(g, "boot_session_id", return_value="boot"),
                              patch.object(g, "protected_app", return_value=False),
                              patch.object(g.time, "sleep", lambda s: None)]

    def __enter__(self):
        for p in self.ps:
            p.start()

    def __exit__(self, *a):
        for p in reversed(self.ps):
            p.stop()


sent = []


def record(pid, pgid, s):
    sent.append((pid, signal.Signals(s).name))
    return 0


row = dict(SELF)
row[P] = (LSTART, "sleep", P, "T")
row[Q] = (LSTART, "sleep", Q, "T")


def owing_state():
    """A real do_terminate whose listing after the grace fails leaves P marked term_sent."""
    st = {"paused": {str(P): entry(P)}}
    with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
                 patch.object(g, "stopped_now", return_value=({P}, {P})),
                 patch.object(g, "process_table", side_effect=[row, {}])):
        g.do_terminate(CFG, st, "paused too long")
    st["paused"][str(Q)] = entry(Q)
    return st


st = owing_state()
test("setup: the entry owing its KILL is kept and marked term_sent",
     st["paused"].get(str(P), {}).get("term_sent"), st["paused"].get(str(P)))

print("1. a hot cycle repeats SIGSTOP")
sent[:] = []
with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
             patch.object(g, "process_table", return_value=row)):
    g.reassert_paused(CFG, st)
test("no SIGSTOP to the entry that owes its KILL", (P, "SIGSTOP") not in sent, sent)
test("control: the ordinary pause gets its SIGSTOP", (Q, "SIGSTOP") in sent, sent)

print("2. manual resume from the menu bar")
st = owing_state()
sent[:] = []
with open(g.COMMAND_PATH, "w") as f:
    f.write("resume")
with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
             patch.object(g, "process_table", return_value=row),
             patch.object(g, "run", return_value="S\n")):
    g.handle_command(CFG, st, [])
test("the entry owing its KILL stays, so the next do_terminate sends it",
     str(P) in st["paused"] and st["paused"][str(P)].get("term_sent"), sorted(st["paused"]))
test("and gets no SIGCONT from the resume", (P, "SIGCONT") not in sent, sent)
test("control: the ordinary pause is resumed and its entry goes",
     (Q, "SIGCONT") in sent and str(Q) not in st["paused"], (sent, sorted(st["paused"])))
only_owing = owing_state()
del only_owing["paused"][str(Q)]
with open(g.COMMAND_PATH, "w") as f:
    f.write("resume")
sent[:] = []
with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
             patch.object(g, "process_table", return_value=row),
             patch.object(g, "run", return_value="S\n")):
    g.handle_command(CFG, only_owing, [])
test("a resume with only that entry left sends nothing and keeps it",
     not sent and str(P) in only_owing["paused"], (sent, only_owing))

print("3. status.json")
st = owing_state()
soc = {"cpu": 71.0, "gpu": 66.0, "fans": [2100], "watts": 18.5, "ram_used": 20.0, "ram_total": 48.0,
       "swap_used": 1.0}
g._ostatnio_odrzucone["v"] = []
with patch.object(g, "thermal_pressure", return_value=(0, "nominal")):
    snap = g.status_write("nominal", 31.0, soc, 71.0, True, 80, 100, 2.5, 2, "chip 71.0 C", [], st)
details = {d.get("pid"): d for d in snap.get("paused_details", [])}
test("the entry owing its KILL says terminating: true", details.get(P, {}).get("terminating") is True,
     details.get(P))
test("an ordinary pause has no terminating field (absent, never false)",
     Q in details and "terminating" not in details[Q], details.get(Q))
test("both are still listed in paused (heat and the menu bar read it unchanged)",
     len(snap.get("paused", [])) == 2, snap.get("paused"))
with open(os.path.join(SRC, "docs", "spec", "metrics-v1.md"), encoding="utf-8") as f:
    spec = f.read()
row_md = next((line for line in spec.splitlines()
               if re.match(r"\|\s*`paused_details\.terminating`\s*\|", line)), "")
test("metrics-v1.md documents paused_details.terminating as a boolean, absent otherwise",
     "boolean" in row_md and "Absent" in row_md, row_md)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
