#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""An owed SIGKILL (term_sent) is sent on the next readable cycle and survives a restart (23.10).

do_terminate keeps an entry marked term_sent when the listing after the 20 s grace fails. Two
roads still lost or delayed the KILL it owes:

1. The retry waited for the pause limit, counted from the first SIGSTOP. A job frozen minutes
   before the critical level ran on after its SIGTERM for up to max_pause_minutes, and a child
   that ignores TERM kept heating the Mac: reassert_paused and do_pause both leave the entry
   alone. finish_owed_kills() now sends it on every cycle with a readable listing, whatever the
   age and the level, and the pause-limit road no longer takes such entries.
2. Daemon startup and shutdown called do_resume on everything: SIGCONT, a [RESUME] line that
   the day's statistics count, a pause_end event, and the entry deleted. do_resume now leaves
   term_sent entries for every caller, so the menu bar filter is no longer the only guard.
3. A menu-bar resume with only such entries left said nothing; it now logs why.
4. The specs say what the list and the event really hold: `paused` includes entries being
   terminated, and the terminate event is written when the termination starts.

Fake pids above the macOS pid range (4000000+), with sig, the listings and ps patched, so no
real process can receive a signal; real log(), event_jsonl() and state files in a TG_BASE.
Run with:  python3 tests/test_owed_kill_20261023.py
"""
import ast
import json
import os
import re
import signal
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-owed-kill-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_owed_kill", os.path.join(SRC, "guard.py"))
NOTIFIED = []
g.notify = lambda cfg, title, text, key="default": NOTIFIED.append(key)
CFG = dict(g.DEFAULTS, notify=False, dry_run=False, demote_at_pause=False)

LSTART = "Thu Oct 22 13:01:57 2026"
BORN = time.mktime(time.strptime(LSTART, "%a %b %d %H:%M:%S %Y"))
P, Q = 4000031, 4000033          # P owes its KILL, Q is an ordinary young pause
ROW = {os.getpid(): (LSTART, "python3", os.getpid(), "S"),
       P: (LSTART, "sleep", P, "S"), Q: (LSTART, "sleep", Q, "T")}

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
                              patch.object(g, "alive", return_value=True),
                              patch.object(g, "sig", record),
                              patch.object(g, "run", return_value="S\n"),
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


def entry(pid, age_s):
    return {"since": g.now() - age_s, "comm": "sleep", "pgid": pid, "born": BORN,
            "boot_session": "boot", "powod": "termika", "manual": False}


def young_owing_state():
    """Frozen 3 minutes ago, terminated at the critical level, listing after the grace failed."""
    st = {"paused": {str(P): entry(P, 180)}}
    row = dict(ROW)
    row[P] = (LSTART, "sleep", P, "T")
    with Patches(patch.object(g, "stopped_now", return_value=({P}, {P})),
                 patch.object(g, "process_table", side_effect=[row, {}])):
        g.do_terminate(CFG, st, "CRITICAL")
    st["paused"][str(Q)] = entry(Q, 120)
    return st


def log_text():
    try:
        with open(g.LOG_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def events(kind):
    try:
        with open(g.HISTORY_EVENTS_PATH, encoding="utf-8") as f:
            return [r for r in (json.loads(x) for x in f if x.strip()) if r.get("type") == kind]
    except OSError:
        return []


finish = getattr(g, "finish_owed_kills", None)
owed_kills = getattr(g, "owed_kills", None)

print("1. a young entry owing its KILL, on the next cycle")
st = young_owing_state()
test("setup: P is three minutes into its pause and owes its KILL",
     st["paused"].get(str(P), {}).get("term_sent") and g._pause_age(st["paused"][str(P)]) < 600,
     st["paused"].get(str(P)))
test("setup: the pause-limit road would not take it for another 40 minutes",
     str(P) not in g.expired_entries(st["paused"], 45 * 60, (set(), {Q})), st["paused"])
test("finish_owed_kills and owed_kills exist", callable(finish) and callable(owed_kills))
kills_before = (st.get("stats") or {}).get("kills")
sent[:] = []
if callable(finish) and callable(owed_kills):
    owed = owed_kills(st)
    with Patches(patch.object(g, "stopped_now", return_value=(set(), {Q})),
                 patch.object(g, "process_table", return_value=ROW)):
        finish(CFG, st, (set(), {Q}), owed)
test("P gets SIGCONT, SIGTERM and the owed SIGKILL",
     [s for p, s in sent if p == P] == ["SIGCONT", "SIGTERM", "SIGKILL"], sent)
test("and its entry goes", str(P) not in st["paused"], sorted(st["paused"]))
test("the ordinary young pause gets no signal and stays",
     not [s for p, s in sent if p == Q] and str(Q) in st["paused"], (sent, sorted(st["paused"])))
test("the job is still counted once", (st.get("stats") or {}).get("kills") == kills_before == 1,
     (kills_before, st.get("stats")))

print("2. when it may not act")
for label, stopped, cfg in (("the listing of this cycle failed", None, CFG),
                            ("watch-only mode", (set(), set()), dict(CFG, dry_run=True))):
    st = young_owing_state()
    sent[:] = []
    log_before = log_text()
    if callable(finish) and callable(owed_kills):
        owed = owed_kills(st)
        with Patches(patch.object(g, "stopped_now", return_value=(set(), set())),
                     patch.object(g, "process_table", return_value=ROW)):
            finish(cfg, st, stopped, owed)
    test("%s: no signal, the entry keeps owing" % label,
         callable(finish) and not sent and st["paused"].get(str(P), {}).get("term_sent"), (sent, st["paused"]))
    # A line here would repeat on every cycle for as long as the condition lasts.
    test("%s: and no log line" % label, callable(finish) and log_text() == log_before,
         log_text()[len(log_before):])
st = young_owing_state()
sent[:] = []
if callable(finish) and callable(owed_kills):
    owed = owed_kills(st)
    st["paused"][str(P)]["term_sent"] = owed[str(P)] + 25      # retried and re-marked this cycle
    with Patches(patch.object(g, "stopped_now", return_value=(set(), set())),
                 patch.object(g, "process_table", return_value=ROW)):
        finish(CFG, st, (set(), set()), owed)
test("an entry another do_terminate retried in this cycle waits for the next one (one grace per cycle)",
     callable(finish) and not sent and str(P) in st["paused"], (sent, sorted(st["paused"])))

print("3. the main loop")
with open(os.path.join(SRC, "guard.py"), encoding="utf-8") as f:
    tree = ast.parse(f.read())
main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
parents = {}
for node in ast.walk(main):
    for child in ast.iter_child_nodes(node):
        parents[child] = node


def ancestors(node):
    while node in parents:
        node = parents[node]
        yield node


def mentions_lvl(node):
    return any(isinstance(n, ast.Name) and n.id == "lvl" for n in ast.walk(node))


calls = [n for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
         and n.func.id == "finish_owed_kills"]
test("main() calls finish_owed_kills once", len(calls) == 1, len(calls))
test("on every cycle: not inside a branch on the level",
     calls and not any(isinstance(a, ast.If) and mentions_lvl(a.test) for a in ancestors(calls[0])))
owed_at = [n.lineno for n in ast.walk(main) if isinstance(n, ast.Assign)
           and any(isinstance(t, ast.Name) and t.id == "owed" for t in n.targets)
           and isinstance(n.value, ast.Call) and getattr(n.value.func, "id", "") == "owed_kills"]
crit_at = [n.lineno for n in ast.walk(main) if isinstance(n, ast.If) and mentions_lvl(n.test)
           and any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "do_terminate"
                   for b in n.body for c in ast.walk(b))]
test("owed is taken before the critical branch can retry an entry",
     owed_at and crit_at and owed_at[0] < crit_at[0], (owed_at, crit_at))
expired = [n for n in ast.walk(main) if isinstance(n, ast.Assign)
           and any(isinstance(t, ast.Name) and t.id == "expired_keys" for t in n.targets)
           and any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "expired_entries"
                   for c in ast.walk(n.value))]
test("the pause-limit road leaves term_sent entries to finish_owed_kills",
     len(expired) == 1 and any(isinstance(c, ast.Constant) and c.value == "term_sent"
                               for c in ast.walk(expired[0].value)), len(expired))

print("4. daemon startup and shutdown, on a saved entry")
for reason in ("guard startup - nothing is left frozen", "guard is shutting down"):
    st = young_owing_state()
    g.save_state(st)
    st = g.load_state()
    test("setup (%s): term_sent survives state.json" % reason,
         st["paused"].get(str(P), {}).get("term_sent"), st["paused"].get(str(P)))
    del st["paused"][str(Q)]
    sent[:] = []
    NOTIFIED[:] = []
    log_before = log_text()
    ends_before = len(events("pause_end"))
    with Patches(patch.object(g, "stopped_now", return_value=(set(), set())),
                 patch.object(g, "process_table", return_value=ROW)):
        g.do_resume(CFG, st, g.T(reason))
    new_log = log_text()[len(log_before):]
    test("%s: the entry stays, still owing" % reason,
         st["paused"].get(str(P), {}).get("term_sent"), sorted(st["paused"]))
    test("%s: no SIGCONT, no [RESUME] line, no pause_end event" % reason,
         not sent and "[RESUME]" not in new_log and len(events("pause_end")) == ends_before,
         (sent, new_log, events("pause_end")))
    test("%s: no 'cooled down' notification for a job nobody resumed" % reason,
         "resume" not in NOTIFIED, NOTIFIED)
resumes = [n for n in ast.walk(main) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "do_resume"
           and any(isinstance(c, ast.Constant) and c.value in ("guard startup - nothing is left frozen",
                                                               "guard is shutting down")
                   for c in ast.walk(n))]
test("both paths in main() are that do_resume call, with no only_keys of their own",
     len(resumes) == 2 and not any(k.arg == "only_keys" for n in resumes for k in n.keywords),
     len(resumes))

print("5. a menu-bar resume with only such an entry left")
st = young_owing_state()
del st["paused"][str(Q)]
with open(g.COMMAND_PATH, "w") as f:
    f.write("resume")
sent[:] = []
log_before = log_text()
with Patches(patch.object(g, "stopped_now", return_value=(set(), set())),
             patch.object(g, "process_table", return_value=ROW)):
    g.handle_command(CFG, st, [])
new_log = log_text()[len(log_before):]
test("nothing is sent and the entry stays", not sent and str(P) in st["paused"], (sent, st["paused"]))
test("guard.log says the entry owes its SIGKILL", "owe their SIGKILL" in new_log, new_log)

print("6. the specs")
with open(os.path.join(SRC, "docs", "spec", "metrics-v1.md"), encoding="utf-8") as f:
    metrics = f.read()
paused_row = next((x for x in metrics.splitlines() if re.match(r"\|\s*`paused`\s*\|", x)), "")
test("metrics-v1.md: `paused` also lists entries being terminated, pointing at paused_details.terminating",
     "paused_details.terminating" in paused_row, paused_row)
with open(os.path.join(SRC, "docs", "spec", "events-v1.md"), encoding="utf-8") as f:
    ev = f.read()
term = " ".join(ev.split("### `terminate`", 1)[-1].split("| Field |", 1)[0].split())
test("events-v1.md: terminate is written when the termination starts, not after the process ended",
     "ended a paused process" not in term and "starts ending" in term, term)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
