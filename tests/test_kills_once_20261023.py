#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One terminated job counts as one kill (23.10).

Two roads counted the same job twice:
1. When the listing after the 20 s grace failed, the entry came back marked term_sent and the
   next do_terminate repeated SIGTERM with everything that belongs to the first one: a second
   [KILL] line, a second kills counter step, a second "terminate" event and a second STOPPED
   notification.
2. The pause-limit notice "PAUSE >N min - terminating job" carried the [KILL] tag itself, and
   the day's statistics count [KILL] lines in guard.log, so every such job counted twice.

Real log(), licznik(), event_jsonl() and day_stats() against an isolated TG_BASE; fake pids
above the macOS pid range (4000000+), with sig and the listings patched, so no real process can
receive a signal.
Run with:  python3 tests/test_kills_once_20261023.py
"""
import ast
import json
import os
import signal
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-kills-once-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_kills_once", os.path.join(SRC, "guard.py"))
NOTIFIED = []
g.notify = lambda cfg, title, text, key="default": NOTIFIED.append(key)
CFG = dict(g.DEFAULTS, notify=False, dry_run=False, demote_at_pause=False)

LSTART = "Thu Oct 22 13:01:57 2026"
BORN = time.mktime(time.strptime(LSTART, "%a %b %d %H:%M:%S %Y"))
P = 4000021

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


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
    sent.append(signal.Signals(s).name)
    return 0


def log_lines():
    try:
        with open(g.LOG_PATH, encoding="utf-8") as f:
            return f.read().splitlines()
    except OSError:
        return []


def terminate_events():
    try:
        with open(g.HISTORY_EVENTS_PATH, encoding="utf-8") as f:
            return [r for r in (json.loads(x) for x in f if x.strip()) if r.get("type") == "terminate"]
    except OSError:
        return []


row = {os.getpid(): (LSTART, "python3", os.getpid(), "S"), P: (LSTART, "sleep", P, "T")}
st = {"paused": {str(P): {"since": g.now() - 9000, "comm": "sleep", "pgid": P, "born": BORN,
                          "boot_session": "boot", "powod": "termika", "manual": False}}}

print("1. one job, two do_terminate calls (the first loses its listing after the grace)")
with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
             patch.object(g, "stopped_now", return_value=({P}, {P})),
             patch.object(g, "process_table", side_effect=[row, {}])):
    g.do_terminate(CFG, st, "paused for longer than 45 min")
test("setup: TERM went, the KILL is owed", sent == ["SIGCONT", "SIGTERM"]
     and st["paused"].get(str(P), {}).get("term_sent"), (sent, st["paused"]))
with Patches(patch.object(g, "alive", return_value=True), patch.object(g, "sig", record),
             patch.object(g, "stopped_now", return_value=(set(), set())),
             patch.object(g, "process_table", side_effect=[row, row])):
    g.do_terminate(CFG, st, "paused for longer than 45 min",
                   only_keys=g.expired_entries(st["paused"], 60, (set(), set())))
test("setup: the second call repeats TERM and sends the KILL",
     sent == ["SIGCONT", "SIGTERM", "SIGCONT", "SIGTERM", "SIGKILL"] and str(P) not in st["paused"],
     (sent, st["paused"]))
lines = log_lines()
kill_lines = [x for x in lines if "[KILL]" in x]
test("kills_total counts the job once", st.get("stats", {}).get("kills") == 1, st.get("stats"))
test("the session counter counts it once", st.get("stats_sesja", {}).get("kills") == 1, st.get("stats_sesja"))
test("guard.log has one [KILL] line", len(kill_lines) == 1, kill_lines)
test("the repeat is logged as a plain line that says the KILL is still owed",
     any("SIGTERM repeated" in x and "[KILL]" not in x for x in lines), lines)
test("one terminate event in history_events.jsonl", len(terminate_events()) == 1, terminate_events())
test("one STOPPED notification", NOTIFIED.count("kill") == 1, NOTIFIED)
test("the day's statistics read from guard.log say 1 kill", g.day_stats().get("kills") == 1, g.day_stats())

print("2. the pause-limit notice in the main loop")
with open(os.path.join(SRC, "guard.py"), encoding="utf-8") as f:
    tree = ast.parse(f.read())
NOTICE = "PAUSE >%d min - terminating job %s (pid %s)"
notices = [node for node in ast.walk(tree)
           if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "log"
           and node.args and any(isinstance(c, ast.Constant) and c.value == NOTICE for c in ast.walk(node.args[0]))]
test("the notice is logged in exactly one place", len(notices) == 1, len(notices))
# log(msg, tag=None): a tag passed by position counts as much as one passed by name.
test("and carries no tag, so the TERMINATED line that follows is the only kill",
     notices and len(notices[0].args) < 2 and not any(k.arg == "tag" for k in notices[0].keywords),
     (len(notices[0].args), [k.arg for k in notices[0].keywords]) if notices else None)

print("3. what the counter means, said where readers look")
m = load_source("metrics_kills_once", os.path.join(SRC, "thermal-metrics"))
reg = m.Registry()
m.collect(reg, {"epoch": time.time(), "stats_total": {"kills": 1}}, os.path.join(BASE, "status.json"),
          {"host": "test"})
help_line = next((x for x in reg.render().splitlines() if x.startswith("# HELP coffee_paladin_kills_total")), "")
test("the kills_total HELP says terminations started, once per job",
     "Terminations started" in help_line and "once per job" in help_line, help_line)
with open(os.path.join(SRC, "docs", "spec", "metrics-v1.md"), encoding="utf-8") as f:
    spec = f.read()
row_md = next((x for x in spec.splitlines() if x.startswith("| `coffee_paladin_kills_total`")), "")
test("metrics-v1.md says the same", "terminations started" in row_md and "once per job" in row_md, row_md)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
