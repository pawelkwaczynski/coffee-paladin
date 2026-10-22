#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Four review blockers on the protected-apps and identity commits (22.10), each against the real code.

1. A protected app inside a job's process group (OBS started by a script under safe-run) was frozen
   with the job, because sig() signals the whole group with killpg.
2. The default list missed apps installed on the owner's Mac and named Loopback wrongly; a custom
   protected_apps silently dropped every default.
3. An unknown CPU limit was written to history.csv as the word "None".
4. Polish pressure names did not agree with "presja termiczna" (feminine).
Plus: one failed path read no longer strips protection for good, and do_pause signals after one
identity read.

Run with:  python3 tests/test_blokery_20261022.py
Isolated TG_BASE; the only processes signalled are the ones this test starts (symlinks to /bin/sleep).
"""
import os
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg-blokery-")
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_blokery", os.path.join(SRC, "guard.py"))
os.environ["TG_LANG"] = "pl"
g_pl = load_source("guard_blokery_pl", os.path.join(SRC, "guard.py"))
h_pl = load_source("heat_blokery_pl", os.path.join(SRC, "heat"))
os.environ["TG_LANG"] = "en"

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def stat(pid):
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()


print("1. protected app inside a job group")
root = tempfile.mkdtemp(prefix="tg-blokery-bin-")
obs_dir = os.path.join(root, "OBS.app", "Contents", "MacOS")
os.makedirs(obs_dir)
obs = os.path.join(obs_dir, "OBS")
job = os.path.join(root, "jobrunner")
os.symlink("/bin/sleep", obs)
os.symlink("/bin/sleep", job)
leader = subprocess.Popen(["/bin/sh", "-c", '"$1" 301 & exec "$2" 300', "sh", obs, job], start_new_session=True)
try:
    time.sleep(0.6)
    pgid = os.getpgid(leader.pid)
    members = g.group_members(pgid)
    obs_pid = next((m for m in members if g.exe_path(m) == obs), None)
    test("the fake OBS is in the job group", obs_pid is not None, members)
    g._PROTECTED_NAMES["names"] = g.protected_names(dict(g.DEFAULTS))
    with patch.object(g, "log"):
        rc = g.sig(leader.pid, pgid, signal.SIGSTOP)
    time.sleep(0.2)
    test("the job is stopped", rc == 0 and stat(leader.pid).startswith("T"), (rc, stat(leader.pid)))
    test("the protected app in its group is NOT stopped", obs_pid and not stat(obs_pid).startswith("T"),
         stat(obs_pid) if obs_pid else None)
    g.sig(leader.pid, pgid, signal.SIGCONT)
    time.sleep(0.2)
    test("SIGCONT resumes the group", not stat(leader.pid).startswith("T"), stat(leader.pid))
    with patch.object(g, "group_members", return_value=[]), patch.object(g, "log"):
        g.sig(leader.pid, pgid, signal.SIGSTOP)
    time.sleep(0.2)
    test("ps cannot list the group: killpg as before (the pause is not lost)",
         stat(leader.pid).startswith("T"), stat(leader.pid))
    g.sig(leader.pid, pgid, signal.SIGCONT)
finally:
    try:
        os.killpg(os.getpgid(leader.pid), signal.SIGKILL)
    except OSError:
        pass
    leader.wait(timeout=5)
time.sleep(0.2)
left = subprocess.run(["pgrep", "-f", root], capture_output=True, text=True).stdout.split()
test("no test process left behind", not left, left)

print("2. protected list")
cfg = dict(g.DEFAULTS)
for path in ("/Applications/Loopback.app/Contents/MacOS/Loopback", "/Applications/Cap.app/Contents/MacOS/cap-muxer",
             "/Applications/WhatsApp.app/Contents/MacOS/WhatsApp",
             "/System/Applications/Phone.app/Contents/MacOS/Phone"):
    test("protected: %s" % [x for x in path.split("/") if x.endswith(".app")][0], g.bundle_protected(path, g.protected_names(cfg)), path)
test("an ordinary app is not protected",
     not g.bundle_protected("/Applications/Foo.app/Contents/MacOS/Foo", g.protected_names(cfg)))
extra = dict(cfg, protected_apps_extra=["Foo"])
test("protected_apps_extra adds to the defaults",
     g.bundle_protected("/Applications/Foo.app/Contents/MacOS/Foo", g.protected_names(extra))
     and g.bundle_protected("/Applications/zoom.us.app/Contents/MacOS/zoom.us", g.protected_names(extra)))
only = dict(cfg, protected_apps=[], protected_apps_extra=["Foo"])
test("protected_apps: [] drops the defaults, extra still applies",
     not g.bundle_protected("/Applications/zoom.us.app/Contents/MacOS/zoom.us", g.protected_names(only))
     and g.bundle_protected("/Applications/Foo.app/Contents/MacOS/Foo", g.protected_names(only)))

print("3. unknown CPU limit in history.csv")
row = g.hist_row("nominal", None, 60.0, 30.0, [], 80, True, None, 1.0, 0, None)
test("the cpu_limit cell is empty, not 'None'", "None" not in [str(c) for c in row] and "" in row, row)

print("4. Polish pressure names")
for key, word in (("nominal", "nominalna"), ("moderate", "umiarkowana"), ("heavy", "wysoka"),
                  ("trapping", "ograniczająca"), ("sleeping", "usypiająca")):
    test("guard pl %s -> %s" % (key, word), g_pl.T(key) == word, g_pl.T(key))
    test("heat pl %s -> %s" % (key, word), h_pl.T(key) == word, h_pl.T(key))

print("5. a failed path read is asked again")
g._EXE_CACHE.clear()
answers = iter(["", "/Applications/zoom.us.app/Contents/MacOS/zoom.us"])
with patch.object(g, "run", side_effect=lambda cmd, timeout=10: next(answers)):
    first, second = g.exe_path(4242), g.exe_path(4242)
test("an empty read is not cached", first == "" and second.endswith("zoom.us"), (first, second))

print("6. do_pause signals after one identity read")
sent = []
reads = iter([(1700000000.0, "ffmpeg", 4343), None])
with patch.object(g, "process_identity", side_effect=lambda pid: next(reads)), \
        patch.object(g, "boot_session_id", return_value="boot"), \
        patch.object(g, "sig", side_effect=lambda p, pg, s: sent.append(s) or 0), \
        patch.object(g, "notify"), patch.object(g, "log"), patch.object(g, "event_jsonl"), \
        patch.object(g, "protected_app", return_value=False):
    st = {"paused": {}}
    g.do_pause(dict(g.DEFAULTS, demote_at_pause=False, dry_run=False), st, [(4343, 90.0, "ffmpeg", 4343)], "test")
test("SIGSTOP is sent even if a second read would fail", sent == [signal.SIGSTOP] and "4343" in st["paused"],
     (sent, list(st["paused"])))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
