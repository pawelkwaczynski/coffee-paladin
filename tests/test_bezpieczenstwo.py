#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify security contracts for pgid, untouchable matching, and ntfy topic handling.

  * item 10 - `pgid` from managed/ used to be copied from the file literally.
    Registration is ordinary JSON on disk, so {"pid": A, "pgid": B} sent
    SIGSTOP/SIGKILL to group B, not to the registered job. The writer was not
    checked either.
  * item 11 - untouchable lists match by substring, so `mds_solver` is untouchable
    because of `mds`. Do not narrow the match: the risk is asymmetric. False
    protection means a hot Mac; lost protection means a frozen AI agent. The match
    must no longer be silent.
  * item 12 - the ntfy topic used to sit in the `curl` URL argv, visible in `ps`
    to every user on the machine. The topic is the only protection on that channel.

Run with:  python3 tests/test_bezpieczenstwo.py
Does not touch the real ~/.coffee-paladin.
"""
import importlib.machinery
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-bezp-")
os.environ["TG_BASE"] = BASE
os.environ.setdefault("TG_LANG", "en")
os.makedirs(os.path.join(BASE, "managed"), exist_ok=True)

g = importlib.machinery.SourceFileLoader("bz_guard", os.path.join(SRC, "guard.py")).load_module()

results = []


def test(name, condition, detail=""):
    results.append(bool(condition))
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           ("  -> " + detail) if detail and not condition else ""))


def register(pid, pgid, prawa=0o600, started=None):
    p = os.path.join(BASE, "managed", "%d.json" % pid)
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump({"pid": pid, "pgid": pgid,
                   "started": started if started is not None else time.time() - 1}, f)
    os.chmod(p, prawa)
    return p


# ---------------------------------------------------------------- item 10
print("=== item 10: take pgid from the KERNEL, not from the file ===")
# start_new_session gives a private process group; otherwise pgid equals ours.
victim = subprocess.Popen(["sleep", "300"], start_new_session=True)
real_value = os.getpgid(victim.pid)
foreign = os.getpgid(0)
register(victim.pid, foreign)              # Foreign pgid in the file.
res, _ = g.managed_pids_from_saferun()
test("1. guard uses the process's REAL pgid, not the one from the file",
     res.get(victim.pid) == real_value,
     "read %s, real %s, substituted %s" % (res.get(victim.pid), real_value, foreign))
test("2. ...so the signal does NOT go to the substituted group",
     res.get(victim.pid) != foreign or real_value == foreign)

second = subprocess.Popen(["sleep", "300"], start_new_session=True)
path = register(second.pid, os.getpgid(second.pid), prawa=0o666)
res, _ = g.managed_pids_from_saferun()
test("3. world-writable registration is IGNORED", second.pid not in res,
     "0666 file was accepted")
os.chmod(path, 0o600)
res, _ = g.managed_pids_from_saferun()
test("4. the same registration with 0600 permissions is accepted", second.pid in res,
     "blocking our own valid jobs")

victim.kill(); victim.wait()
second.kill(); second.wait()
for n in os.listdir(os.path.join(BASE, "managed")):
    os.remove(os.path.join(BASE, "managed", n))

# ---------------------------------------------------------------- item 11
print("\n=== item 11: substring protection REMAINS, but stops being silent ===")
cfg = g.load_cfg()
cfg["cpu_min_percent"] = 10
cfg["manage_unknown_heavy"] = True
g.args_without_paths = lambda pid: "x"
g.foreground_on_tty = lambda pid: False
g.proc_age_seconds = lambda pid: 9999
g.cpu_with_children = lambda procs: {}
g._UNTOUCHABLE_SUBSTRINGS.clear()
if os.path.exists(g.LOG_PATH):
    os.remove(g.LOG_PATH)

procs = [(4001, 1, 90.0, "mds_solver"), (4002, 1, 85.0, "sshd-worker"),
         (4003, 1, 95.0, "ffmpeg"), (4004, 1, 88.0, "mds")]
targets = [c[2] for c in g.pick_targets(cfg, procs, {})]
log = io.open(g.LOG_PATH, encoding="utf-8", errors="replace").read() if os.path.exists(g.LOG_PATH) else ""

test("5. protection was NOT weakened - mds_solver remains untouchable",
     "mds_solver" not in targets, "cele: %s" % targets)
test("6. sshd-worker also untouchable", "sshd-worker" not in targets, "cele: %s" % targets)
test("7. plain encoder still pausable", "ffmpeg" in targets, "cele: %s" % targets)
test("8. log SAYS why hot mds_solver is skipped",
     "mds_solver" in log and "untouchable" in log,
     "missing log explanation - user gets silence")
test("9. with a FULL match (mds), there is no log noise",
     "mds uses" not in log, "also logging obvious cases")

# ---------------------------------------------------------------- item 12
print("\n=== item 12: ntfy topic must not be visible in ps ===")
BIN = os.path.join(BASE, "bin")
os.makedirs(BIN, exist_ok=True)
with io.open(os.path.join(BIN, "curl"), "w", encoding="utf-8") as f:
    f.write('#!/bin/sh\nprintf "%s\\n" "$*" > "$0.argv"\ncat > "$0.stdin"\n')
os.chmod(os.path.join(BIN, "curl"), 0o755)
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]

SUBJECT = "sekretny_temat_ABC123"
cfg = g.load_cfg()
cfg["notify"] = True
cfg["ntfy_topic"] = SUBJECT
g.push(cfg, "Cooling alarm", "chip 98.7 C, fans 0 rpm")
# `push` starts curl in the background, so wait for the file, not for fixed time.
# A fixed `sleep(0.8)` passed on a slow Mac, but under the full test suite with a
# CPU limiter the stub sometimes had not written yet, causing FileNotFoundError.
# A flaky test damages the gate just like a test that never fails.
_argv_path = os.path.join(BIN, "curl.argv")
_stdin_path = os.path.join(BIN, "curl.stdin")
_end = time.time() + 20.0
while time.time() < _end:
    if os.path.exists(_argv_path) and os.path.exists(_stdin_path):
        break
    time.sleep(0.05)
argv = io.open(_argv_path, encoding="utf-8").read() if os.path.exists(_argv_path) else ""
stdin = io.open(_stdin_path, encoding="utf-8").read() if os.path.exists(_stdin_path) else ""
test("9b. curl stub was actually started (otherwise the rest proves nothing)",
     bool(argv), "curl.argv was not created within 20 s - the check below would be falsely green")

test("10. topic is NOT in argv (so it is not in ps)", SUBJECT not in argv,
     "argv: %s" % argv.strip()[:110])
test("11. alert body is not in argv either", "98.7" not in argv,
     "argv: %s" % argv.strip()[:110])
test("12. topic goes through stdin, so push still WORKS", SUBJECT in stdin,
     "stdin: %s" % stdin.strip()[:110])
test("13. body and title arrive in the request body", "98.7" in stdin and "Cooling alarm" in stdin,
     "stdin: %s" % stdin.strip()[:110])

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(results)
print("\nRESULT: %d/%d" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
