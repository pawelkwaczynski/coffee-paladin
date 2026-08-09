#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify review-round regressions and config-clamp visibility.

1. Startup resume without a measurement. Daemon restart via update or kickstart -k used
   `do_resume("guard startup")` before any measurement, giving a hot job ~15 s of full
   power above threshold. The same `resume_gate` used by the loop now gates startup
   resume.

2. SIGSTOP -> save_state window. State was saved after the signal; a daemon killed in
   that window left a frozen process with no entry, stuck in state T forever. The intent
   entry is now written to disk before the signal and removed if the signal fails
   with ESRCH/EPERM.

3. SIGTERM after a stale snapshot. `ps` from the start of a cycle can be several seconds
   old; manual `kill -CONT` mid-cycle meant SIGTERM to a process already running at full
   speed. `do_terminate` re-checks `entry_stopped` just before firing, and a failed measurement
   (`None`) stops execution entirely.

4. `load_state` trusted format. `paused` as a list or a non-numeric key caused a startup
   crashloop. Type normalization logs and cuts the bad fragment while keeping the rest.

5. One bad entry blinded the limiter. In `safe-run.guard_paused`, a non-numeric `pgid`
   reached the outer `except`, so the whole function reported "nothing is stopped" and
   the limiter resumed a group the guard had just frozen. The fix is local shielding:
   skip only the bad entry, and validate direct pid hits by group to avoid pid reuse.

6. Config clamping was a silent file-memory split. The fix is a notification plus the
   `config_corrections` field in status.json.

Run with:  python3 tests/test_runda3.py
Mutation proof that the test can fail: old code from HEAD~ must fail:
  git show <stary>:guard.py > /tmp/old_guard.py
  TG_TEST_GUARD=/tmp/old_guard.py python3 tests/test_runda3.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import ast
import errno
import importlib.machinery
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import types

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD_SRC = os.environ.get("TG_TEST_GUARD") or os.path.join(SRC, "guard.py")
SAFERUN_SRC = os.environ.get("TG_TEST_SAFERUN") or os.path.join(SRC, "safe-run")
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", GUARD_SRC).load_module()
sr = importlib.machinery.SourceFileLoader("sr", SAFERUN_SRC).load_module()

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


def child(session=False):
    p = subprocess.Popen(["sleep", "300"], start_new_session=session,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    children.append(p)
    return p


def test_cfg():
    c = g.load_cfg()
    c["dry_run"] = False
    c["notify"] = False
    c["sound"] = False
    return c


try:
    # ---------------------------------------------------------------- 1. startup gate
    print("1. startup resume passes through resume_gate (AST on live code)")
    tree = ast.parse(open(GUARD_SRC).read())
    main_fn = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "main")
    hit = False
    for n in ast.walk(main_fn):
        if isinstance(n, ast.If) and "guard startup" in ast.dump(n) \
                and "resume_gate" in ast.dump(n.test):
            hit = True
    test("do_resume('guard startup') is behind resume_gate", hit)

    # ---------------------------------------------------------------- 2. intent entry
    print("2. do_pause: state entry ALREADY EXISTS when signal is sent")
    cfg = test_cfg()
    logs = []
    old_log, old_notify = g.log, g.notify
    g.log = lambda *a, **k: logs.append(a[0] if a else "")
    g.notify = lambda *a, **k: None

    p = child()
    st = {"paused": {}, "demoted": [], "demoted_info": {}}
    kolejnosc = []
    old_sig = g.sig

    def sig_spy(pid, pgid, s):
        kolejnosc.append(str(pid) in st["paused"])
        return 0
    g.sig = sig_spy
    g.do_pause(cfg, st, [(p.pid, 99.0, "sleep", None)], "test")
    test("entry was in place BEFORE the signal", kolejnosc == [True], repr(kolejnosc))
    test("after successful pause the entry remains", str(p.pid) in st["paused"])

    st2 = {"paused": {}, "demoted": [], "demoted_info": {}}
    g.sig = lambda pid, pgid, s: errno.EPERM
    g.do_pause(cfg, st2, [(p.pid, 99.0, "sleep", None)], "test")
    test("EPERM: intent entry removed", str(p.pid) not in st2["paused"])
    test("EPERM: pid in untouchable set", p.pid in g._nie_da_sie)
    g._nie_da_sie.clear()

    st3 = {"paused": {}, "demoted": [], "demoted_info": {}}
    g.sig = lambda pid, pgid, s: errno.ESRCH
    g.do_pause(cfg, st3, [(p.pid, 99.0, "sleep", None)], "test")
    test("ESRCH: intent entry removed", str(p.pid) not in st3["paused"])
    g.sig = old_sig

    # ---------------------------------------------------------------- 3. re-check in do_terminate
    print("3. do_terminate: shoot only what is REALLY stopped NOW")
    shots = []

    def sig_counter(pid, pgid, s):
        shots.append((pid, s))
        return old_sig(pid, pgid, s)

    # a) Process is running, nobody stopped it: entry removed, no signals.
    p_biega = child()
    st = {"paused": {str(p_biega.pid): {"since": g.now(), "comm": "sleep", "pgid": None}},
          "demoted": [], "demoted_info": {}}
    g.sig = sig_counter
    g.do_terminate(cfg, st, "test")
    test("running process did NOT get SIGTERM", not shots, repr(shots))
    test("entry for running process removed", str(p_biega.pid) not in st["paused"])
    test("process survived", p_biega.poll() is None)

    # b) `ps` fails: no decisions, entries stay.
    old_run = g.run
    g.run = lambda *a, **k: ""
    st = {"paused": {str(p_biega.pid): {"since": g.now(), "comm": "sleep", "pgid": None}},
          "demoted": [], "demoted_info": {}}
    shots[:] = []
    result = g.do_terminate(cfg, st, "test")
    test("empty ps: nothing killed, entry remains",
         result is False and str(p_biega.pid) in st["paused"] and not shots)
    g.run = old_run

    # c) Process is stopped: SIGTERM fires, so execution path still works.
    p_stopped = child()
    os.kill(p_stopped.pid, signal.SIGSTOP)
    time.sleep(0.3)
    st = {"paused": {str(p_stopped.pid): {"since": g.now(), "comm": "sleep", "pgid": None}},
          "demoted": [], "demoted_info": {}}
    shots[:] = []
    old_time = g.time
    g.time = types.SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic,
                                   time=time.time)
    g.do_terminate(cfg, st, "test")
    g.time = old_time
    test("stopped process got SIGTERM",
         any(s == signal.SIGTERM for _, s in shots), repr(shots))
    g.sig = old_sig

    # ---------------------------------------------------------------- 4. load_state
    print("4. load_state: type normalization instead of crashloop")
    path = g.STATE_PATH
    with open(path, "w") as f:
        json.dump({"paused": [1, 2, 3], "demoted": {}, "demoted_info": []}, f)
    st = g.load_state()
    test("paused-list (old format) -> empty dict", st["paused"] == {})
    test("demoted with bad type -> empty list", st["demoted"] == [])
    test("demoted_info with bad type -> empty dict", st["demoted_info"] == {})
    with open(path, "w") as f:
        json.dump({"paused": {"abc": {"comm": "x"}, "123": "zly", "456": {"comm": "y"}}}, f)
    st = g.load_state()
    test("non-number key and non-dict entry cut out, healthy entry remains",
         list(st["paused"]) == ["456"], repr(st["paused"]))
    try:
        os.remove(path)
    except OSError:
        pass

    # ---------------------------------------------------------------- 5. guard_paused
    print("5. safe-run.guard_paused: broken entry does not blind, pid reuse does not stop")
    lider = subprocess.Popen(
        ["bash", "-c", "sleep 300 & echo $!; wait"], start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    children.append(lider)
    member = int(lider.stdout.readline().strip())

    def write_state(paused):
        with open(os.path.join(sr.BASE, "state.json"), "w") as f:
            json.dump({"paused": paused}, f)

    # Broken entry (non-numeric pgid) before a healthy entry for our group.
    write_state({str(os.getpid()): {"pgid": "abc", "comm": "smiec"},
                 str(lider.pid): {"pgid": lider.pid, "comm": "bash"}})
    test("broken entry skipped, REAL group pause visible",
         sr.guard_paused(member) is True)
    # pid reuse: entry for our pid but a foreign group must not stop us.
    write_state({str(member): {"pgid": 999999999, "comm": "duch"}})
    test("pid hit with foreign group (pid reuse) = not stopped",
         sr.guard_paused(member) is False)
    # Entry for our pid with matching group still works.
    write_state({str(member): {"pgid": lider.pid, "comm": "bash"}})
    test("pid hit with matching group = stopped", sr.guard_paused(member) is True)
    try:
        os.remove(os.path.join(sr.BASE, "state.json"))
    except OSError:
        pass

    # ---------------------------------------------------------------- 6. rate limit + clamp
    print("6. untouchable once per hour; config clamp visible in status")
    clock = [1000000.0]
    old_now = g.now
    g.now = lambda: clock[0]
    g._UNTOUCHABLE_SUBSTRINGS.clear()
    logs[:] = []
    g._log_untouchable_match("corespotlightd", "spotlight", 200.0)
    clock[0] += 700          # 11:40 later; old 10 min code would already log.
    g._log_untouchable_match("corespotlightd", "spotlight", 200.0)
    test("second entry in the same hour silenced", len(logs) == 1, repr(len(logs)))
    clock[0] += 3600
    g._log_untouchable_match("corespotlightd", "spotlight", 200.0)
    test("after an hour it may log again", len(logs) == 2)
    g.now = old_now
    g._UNTOUCHABLE_SUBSTRINGS.clear()

    notifications = []
    g.notify = lambda cfg, title, content, key="d": notifications.append((key, content))
    with open(g.CFG_PATH, "w") as f:
        json.dump({"soc_pause_c": "goraco"}, f)
    g._ostatnio_odrzucone["v"] = []
    g.load_cfg()
    test("clamp: notification contains correction text",
         any(k == "cfgclamp" and "soc_pause_c" in t for k, t in notifications),
         repr(notifications))
    test("clamp: corrections list for status is non-empty", bool(g._ostatnio_odrzucone["v"]))
    data = g.status_write("nominal", 30.0, None, None, True, 80, 100, 0.5, 0, "",
                          [], {"paused": {}, "demoted_info": {}})
    test("status.json carries config_corrections", bool(data.get("config_corrections")))
    with open(g.CFG_PATH, "w") as f:
        json.dump({}, f)
    g.load_cfg()
    test("fixed file clears corrections list", g._ostatnio_odrzucone["v"] == [])
    try:
        os.remove(g.CFG_PATH)
    except OSError:
        pass
    g.log, g.notify = old_log, old_notify

finally:
    for p in children:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGCONT)
        except OSError:
            pass
        try:
            os.kill(p.pid, signal.SIGCONT)
        except OSError:
            pass
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL) if p.pid == os.getpgid(p.pid) \
                else os.kill(p.pid, signal.SIGKILL)
        except OSError:
            try:
                os.kill(p.pid, signal.SIGKILL)
            except OSError:
                pass
        try:
            p.wait(timeout=5)
        except Exception:
            pass

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
