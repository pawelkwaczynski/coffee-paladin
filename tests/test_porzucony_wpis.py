#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""do_resume says it when a paused entry's process is already gone.

On 23.08 the last paused encoder had a PAUSE line and no RESUME line at daemon
shutdown; the only silent path was a dead pid. Isolated TG_BASE, no real daemon.
Run with: python3 tests/test_porzucony_wpis.py
"""
import importlib.machinery
import json
import os
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="drop_")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


lines = []
g.log = lambda msg, tag=None: lines.append(msg)
g.notify = lambda *a, **k: None

dead = subprocess.Popen(["sleep", "60"])
dead.kill()
dead.wait()
live = subprocess.Popen(["sleep", "60"])
os.kill(live.pid, 19)                       # SIGSTOP, as the guard would
time.sleep(0.2)

st = {"paused": {
    str(dead.pid): {"since": time.time() - 42, "comm": "ffmpeg", "pgid": dead.pid,
                    "powod": "termika", "manual": False},
    str(live.pid): {"since": time.time() - 5, "comm": "sleep", "pgid": live.pid,
                    "powod": "termika", "manual": False},
}}
cfg = dict(g.DEFAULTS)
g.do_resume(cfg, st, "guard is shutting down")

test("the dead entry is gone from state", str(dead.pid) not in st["paused"], st["paused"])
test("the live one was resumed and is gone too", str(live.pid) not in st["paused"], st["paused"])
dropped = [l for l in lines if l.startswith("dropped pause entry for ffmpeg")]
test("one log line names the dropped entry", len(dropped) == 1, lines)
test("the live job got a RESUME line, not a drop line",
     any(l.startswith("RESUMED sleep") for l in lines)
     and not any("dropped pause entry for sleep" in l for l in lines), lines)
ev_path = os.path.join(BASE, "history_events.jsonl")
events = [json.loads(l) for l in open(ev_path)] if os.path.exists(ev_path) else []
drops = [e for e in events if e.get("type") == "pause_entry_dropped"]
test("one JSONL event with pid, reason and pause length",
     len(drops) == 1 and drops[0].get("pid") == dead.pid
     and drops[0].get("reason") == "process_gone" and drops[0].get("pause_s", 0) >= 40, drops)
live.kill()
live.wait()
print("\n%d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
