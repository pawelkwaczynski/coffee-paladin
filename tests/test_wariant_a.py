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

zaliczone = wszystkie = 0
dzieci = []


def test(nazwa, warunek, szczegol=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s %s" % (nazwa, szczegol))


def dziecko():
    p = subprocess.Popen(["sleep", "300"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dzieci.append(p)
    return p


logi = []
stary_log, stary_notify, stary_play = g.log, g.notify, g.play_sound
g.log = lambda *a, **k: logi.append(a[0] if a else "")
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
    cele = g.pick_targets(cfg, procs, {})
    pidy_celow = {c[0] for c in cele}
    demote_pidy = {d[0] for d in g._DEMOTE_ONLY}
    test("corespotlightd outside pause targets", 11111 not in pidy_celow)
    test("corespotlightd in demote-only channel", 11111 in demote_pidy)
    test("substring: spotlightknowledged.updater also in channel", 33333 in demote_pidy)
    test("bluetoothd COMPLETELY untouchable (neither pause nor demote)",
         22222 not in pidy_celow and 22222 not in demote_pidy)

    # snapshot carries the channel as element 14, the live-system integration point.
    mig = g.snapshot(cfg)
    test("snapshot returns 14 elements, last is a list", len(mig) == 14
         and isinstance(mig[13], list), repr(len(mig)))

    # ------------------------------------------------ 2. do_demote on the demote-only channel
    print("2. do_demote: own process moves to E-cores and returns; foreign pid does not lie")
    cfg["demote_cpu_percent"] = 10.0
    cfg["demote_after_minutes"] = 0
    cfg["demote_above_c"] = 10.0
    p = dziecko()
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
    logi[:] = []
    g.do_demote(cfg, st2, [(1, 100.0, "launchd", None)], {}, soc_t=50.0)
    test("foreign process: NOT entered into demoted (log does not lie)", 1 not in st2["demoted"])
    test("foreign process: one DEMOTE failed line",
         sum(1 for m in logi if "DEMOTE failed" in str(m)) == 1, repr(logi))
    logi[:] = []
    g.do_demote(cfg, st2, [(1, 100.0, "launchd", None)], {}, soc_t=50.0)
    test("retry silenced (skipped set)",
         not any("DEMOTE failed" in str(m) for m in logi))
    g._demote_nie_da_sie.clear()

    # ------------------------------------------------ 3. keep-awake hold
    print("3. keep-awake: gap between files does NOT release sleep; heat releases IMMEDIATELY")
    cfg["keep_awake_auto"] = True
    cfg["keep_awake_display"] = False
    cfg["keep_awake_hold_s"] = 3600
    cfg["sound"] = False
    zadanie = [(999999, 300.0, "ffmpeg", None)]

    trzyma = g.keep_awake_update(cfg, zadanie, lvl=0)
    test("heavy job + cool = wake lock starts", trzyma is True)
    trzyma = g.keep_awake_update(cfg, [], lvl=0)
    test("job disappears, hold active = wake lock does NOT drop", trzyma is True)
    trzyma = g.keep_awake_update(cfg, [], lvl=2)
    test("heat during hold = wake lock drops IMMEDIATELY", trzyma is False)

    # hold=0 restores old behavior: stop immediately after the job exits.
    cfg["keep_awake_hold_s"] = 0
    g.keep_awake_update(cfg, zadanie, lvl=0)
    trzyma = g.keep_awake_update(cfg, [], lvl=0)
    test("hold=0: stop immediately (old behavior)", trzyma is False)

    # hold never starts keep-awake; it only extends a live one.
    cfg["keep_awake_hold_s"] = 3600
    trzyma = g.keep_awake_update(cfg, [], lvl=0)
    test("hold does not start wake lock from nothing", trzyma is False)

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
    for p in dzieci:
        try:
            os.kill(p.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            p.wait(timeout=5)
        except Exception:
            pass
    g.log, g.notify, g.play_sound = stary_log, stary_notify, stary_play

print("\nRESULT: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
