#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify variant A and keep-awake hold behavior.

Variant A: system indexing daemons such as corespotlightd remain untouchable for
pause and kill because the never list is sacred, but they use a separate demote-only
channel to E-cores. corespotlightd can heat at 215% CPU while "untouchable", and
AGENTS.md correctly forbids weakening never.

Hold behavior: after the last heavy job exits, keep-awake (caffeinate) stays for
keep_awake_hold_s seconds. Without this, gaps between queue files release the sleep
lock, and a Mac with aggressive sleep could sleep in the middle of an overnight queue.
Heat wins: level >=2 releases immediately.

Run with:  python3 tests/test_wariant_a.py
On code before the change, this test fails at import because _DEMOTE_ONLY does not exist.
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import importlib.machinery
import os
import signal
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD_SRC = os.environ.get("TG_TEST_GUARD") or os.path.join(SRC, "guard.py")
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", GUARD_SRC).load_module()

passed = total = 0
children = []


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s %s" % (name, detail))


def child():
    p = subprocess.Popen(["sleep", "300"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    children.append(p)
    return p


logs = []
old_log, old_notify, old_play = g.log, g.notify, g.play_sound
g.log = lambda *a, **k: logs.append(a[0] if a else "")
g.notify = lambda *a, **k: None
g.play_sound = lambda *a, **k: None

try:
    # ------------------------------------------------ 1. demote-only channel in pick_targets
    print("1. pick_targets: system daemon is NOT pause target, IS demote candidate")
    cfg = g.load_cfg()
    cfg["dry_run"] = False
    cfg["cpu_min_percent"] = 10.0
    # (pid, ppid, cpu, comm) - fake pids; pick_targets does not signal.
    procs = [(11111, 1, 200.0, "corespotlightd"),
             (22222, 1, 150.0, "bluetoothd"),          # never, but not system_demote.
             (33333, 1, 120.0, "spotlightknowledged.updater")]
    targets = g.pick_targets(cfg, procs, {})
    target_pids = {c[0] for c in targets}
    demote_pidy = {d[0] for d in g._DEMOTE_ONLY}
    test("corespotlightd outside pause targets", 11111 not in target_pids)
    test("corespotlightd in demote-only channel", 11111 in demote_pidy)
    test("substring: spotlightknowledged.updater also in channel", 33333 in demote_pidy)
    test("bluetoothd COMPLETELY untouchable (neither pause nor demote)",
         22222 not in target_pids and 22222 not in demote_pidy)

    # snapshot carries the channel as element 14, the live-system integration point.
    mig = g.snapshot(cfg)
    test("snapshot returns 14 elements, last is a list", len(mig) == 14
         and isinstance(mig[13], list), repr(len(mig)))

    # ------------------------------------------------ 2. do_demote on the demote-only channel
    print("2. do_demote: own process moves to E-cores and returns; foreign pid does not lie")
    cfg["demote_cpu_percent"] = 10.0
    cfg["demote_after_minutes"] = 0
    cfg["demote_above_c"] = 10.0
    p = child()
    st = {"paused": {}, "demoted": [], "demoted_info": {}}
    hist = {}
    g.do_demote(cfg, st, [(p.pid, 100.0, "sleep", None)], hist, soc_t=50.0)
    test("own process demoted (taskpolicy rc=0)", p.pid in st["demoted"])
    test("name in demoted_info (visible in status.json)",
         st["demoted_info"].get(str(p.pid), {}).get("comm") == "sleep")
    g.do_promote(cfg, st, hist, soc_t=20.0)
    test("after cooling, return to P-cores", p.pid not in st["demoted"])

    # pid taskpolicy will not accept: pid 1 = launchd, foreign owner.
    st2 = {"paused": {}, "demoted": [], "demoted_info": {}}
    logs[:] = []
    g.do_demote(cfg, st2, [(1, 100.0, "launchd", None)], {}, soc_t=50.0)
    test("foreign process: NOT entered into demoted (log does not lie)", 1 not in st2["demoted"])
    test("foreign process: one DEMOTE failed line",
         sum(1 for m in logs if "DEMOTE failed" in str(m)) == 1, repr(logs))
    logs[:] = []
    g.do_demote(cfg, st2, [(1, 100.0, "launchd", None)], {}, soc_t=50.0)
    test("retry silenced (skipped set)",
         not any("DEMOTE failed" in str(m) for m in logs))
    g._demote_nie_da_sie.clear()

    # ------------------------------------------------ 3. keep-awake hold
    print("3. keep-awake: gap between files does NOT release sleep; heat releases IMMEDIATELY")
    cfg["keep_awake_auto"] = True
    cfg["keep_awake_display"] = False
    cfg["keep_awake_hold_s"] = 3600
    cfg["sound"] = False
    job = [(999999, 300.0, "ffmpeg", None)]

    keeps = g.keep_awake_update(cfg, job, lvl=0)
    test("heavy job + cool = wake lock starts", keeps is True)
    keeps = g.keep_awake_update(cfg, [], lvl=0)
    test("job disappears, hold active = wake lock does NOT drop", keeps is True)
    keeps = g.keep_awake_update(cfg, [], lvl=2)
    test("heat during hold = wake lock drops IMMEDIATELY", keeps is False)

    # hold=0 restores old behavior: stop immediately after the job exits.
    cfg["keep_awake_hold_s"] = 0
    g.keep_awake_update(cfg, job, lvl=0)
    keeps = g.keep_awake_update(cfg, [], lvl=0)
    test("hold=0: stop immediately (old behavior)", keeps is False)

    # hold never starts keep-awake; it only extends a live one.
    cfg["keep_awake_hold_s"] = 3600
    keeps = g.keep_awake_update(cfg, [], lvl=0)
    test("hold does not start wake lock from nothing", keeps is False)

finally:
    # keep-awake must not survive the test.
    try:
        g.keep_awake_update({"keep_awake_auto": False, "keep_awake_hold_s": 0,
                             "sound": False}, [], lvl=3)
    except Exception:
        pass
    proc = g._caff.get("proc")
    if proc is not None and proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)
    for p in children:
        try:
            os.kill(p.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            p.wait(timeout=5)
        except Exception:
            pass
    g.log, g.notify, g.play_sound = old_log, old_notify, old_play

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
