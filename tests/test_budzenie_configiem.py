#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure the protection switch reacts immediately, not after a full loop tick.

The daemon's interruptible sleep woke on the stop flag, a `command` file, and changes
to `awake.json`, but not on changes to `config.json`. The protection switch (`dry_run`)
is stored in config because the menu bar writes it through `GuardCfg.set`. As the only
manual action without a wake path, it waited for the whole tick; at a 30 s interval that
looked like a stuck switch.

This test measures reaction time in a real daemon with a 20 s interval. It does not grep
code or logs for strings. Before the fix the reaction took ~20 s; after it is below one
second.

The daemon runs isolated under TG_BASE and in watch-only mode, so it does not touch user
processes or the real ~/.coffee-paladin.

Run with:  python3 tests/test_budzenie_configiem.py
"""
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-budzenie-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"

INTERVAL = 20.0          # Large enough to distinguish "now" from "after one tick".
FAST_THRESHOLD = 5.0        # Well below INTERWAL, still 4x above the real reaction.

results = []
CHILDREN = []


def test(name, condition, detail=""):
    results.append(bool(condition))
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           ("  -> " + detail) if detail and not condition else ""))


def file_path(n):
    return os.path.join(BASE, n)


def write_config(**keys):
    d = {"dry_run": True, "poll_seconds": INTERVAL, "notify": False, "sound": False,
         "soc_pause_c": 200, "soc_kill_c": 250, "batt_pause_c": 200,
         "keep_awake_auto": False, "fan_check": False}
    d.update(keys)
    with io.open(file_path("config.json"), "w", encoding="utf-8") as f:
        json.dump(d, f)


def log_text():
    try:
        return io.open(file_path("guard.log"), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def wait_for(condition, amount=40.0, step=0.2):
    finish = time.time() + amount
    while time.time() < finish:
        if condition():
            return True
        time.sleep(step)
    return False


print("=== daemon with %d s interval ===" % INTERVAL)
write_config()
daemon = subprocess.Popen([sys.executable, os.path.join(SRC, "guard.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         env=dict(os.environ, TG_BASE=BASE, TG_LANG="en"))
CHILDREN.append(daemon)

test("1. daemon started", wait_for(lambda: os.path.exists(file_path("status.json"))),
     "no status.json after 40 s")

# Wait until the loop sleeps after its first full tick; otherwise this measures the
# remainder of the first pass instead of the reaction to the config change.
time.sleep(3.0)

print("\n=== protection switch: dry_run true -> false ===")
t0 = time.time()
write_config(dry_run=False)
noticed = wait_for(lambda: "CONFIG CHANGED" in log_text(), amount=INTERVAL + 15)
reakcja = time.time() - t0

test("2. daemon noticed the config change at all", noticed,
     "no CONFIG CHANGED entry after %.0f s" % (INTERVAL + 15))
test("3. reacted FASTER than one loop tick (%.1f s < %.0f s)" % (reakcja, FAST_THRESHOLD),
     noticed and reakcja < FAST_THRESHOLD,
     "reaction after %.1f s - loop waited for the full tick (%.0f s)" % (reakcja, INTERVAL))
test("4. ...and actually switched into protection mode",
     wait_for(lambda: json.load(io.open(file_path("status.json"),
                                         encoding="utf-8")).get("dry_run") is False, amount=10),
     "status.json still reports watch-only mode")

print("\n=== opposite case: WITHOUT a config change the loop does not spin ===")
# If wake-up were broken the other way, for example comparison always differed, the
# daemon would spin through ticks and burn CPU. With a 20 s interval, it should not
# complete a single new tick in 6 seconds.
mtime_before = os.path.getmtime(file_path("status.json"))
time.sleep(6.0)
mtime_after = os.path.getmtime(file_path("status.json"))
test("5. without a config change status is NOT rewritten continuously",
     mtime_after == mtime_before,
     "status.json changed within 6 s at %.0f s interval - loop is not sleeping" % INTERVAL)

print("\n=== cleanup ===")
daemon.send_signal(signal.SIGTERM)
try:
    daemon.wait(timeout=40)
except subprocess.TimeoutExpired:
    daemon.kill()
    daemon.wait(timeout=10)
test("6. daemon shut down cleanly", os.path.exists(file_path("clean_stop")),
     "no clean_stop")

for p in CHILDREN:
    if p.poll() is None:
        p.kill()
shutil.rmtree(BASE, ignore_errors=True)

print("\nRESULT: %d/%d" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
