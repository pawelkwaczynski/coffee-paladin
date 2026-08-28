#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Throttle at the first pause: a process the guard freezes for heat comes back on E-cores.

Field data from 23.08.2026: a bare ffmpeg at 1200% CPU was back at pause level 17 s after
every resume, and the re-pause backoff (v3.2.5) turned that into 600 s of pause per 17 s
of work. The pause already names the heater, so it is demoted right there and promotion
keeps its hands off it for one quiet window. Isolated TG_BASE; live pids are sleep children.
Run with: python3 tests/test_demote_przy_pauzie.py
"""
import importlib.machinery
import os
import signal
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="demote_pause_")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

passed = total = 0
logged = []
g.notify = lambda *a, **k: None
g.event_jsonl = lambda *a, **k: None
g.log = lambda msg, *a, **k: logged.append(msg)
children = []


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


def child():
    p = subprocess.Popen(["sleep", "60"])
    children.append(p)
    return p


def state(pid):
    return g.run(["ps", "-o", "stat=", "-p", str(pid)]).strip()


def fresh_st():
    return {"paused": {}, "demoted": [], "demoted_info": {}}


cfg = dict(g.DEFAULTS)
cfg.update({"soc_pause_c": 95.0, "soc_resume_c": 86.0, "min_pause_seconds": 60,
            "repause_window_s": 300, "dry_run": False})

print("A) a thermal pause demotes the process and holds the promotion")
p = child()
st = fresh_st()
g.do_pause(cfg, st, [(p.pid, 1200.0, "ffmpeg", p.pid)], "chip 96 C")
test("process is stopped", state(p.pid).startswith("T"), state(p.pid))
test("and booked as demoted", p.pid in st["demoted"], st["demoted"])
info = st["demoted_info"].get(str(p.pid), {})
test("hold_until is one quiet window ahead",
     290 <= info.get("hold_until", 0) - g.now() <= 300, info)
test("the log says it comes back on E-cores",
     any(m.startswith("DEMOTED ffmpeg") and "at pause" in m for m in logged), logged)
g.do_promote(cfg, st, {}, 60.0)
test("a cool reading inside the window does NOT promote", p.pid in st["demoted"], st["demoted"])
st["demoted_info"][str(p.pid)]["hold_until"] = g.now() - 1
g.do_promote(cfg, st, {}, 60.0)
test("after the window a cool reading promotes", p.pid not in st["demoted"], st["demoted"])
g.do_resume(cfg, st, "test", after_cooling=True)
test("resume still works", not state(p.pid).startswith("T"), state(p.pid))

print("\nB) a second pause of a demoted process does not book it twice")
logged.clear()
p = child()
st = fresh_st()
g.do_pause(cfg, st, [(p.pid, 1200.0, "ffmpeg", p.pid)], "chip 96 C")
g.do_resume(cfg, st, "test", after_cooling=True)
g.do_pause(cfg, st, [(p.pid, 1200.0, "ffmpeg", p.pid)], "chip 96 C")
test("one demotion entry", st["demoted"].count(p.pid) == 1, st["demoted"])
test("one DEMOTED line", sum(1 for m in logged if m.startswith("DEMOTED")) == 1, logged)
test("re-pause backoff untouched: second pause holds longer than base",
     st["paused"][str(p.pid)]["hold_s"] > 60, st["paused"][str(p.pid)])

print("\nC) where the throttle must NOT apply")
for label, kwargs, setup in (
        ("manual freeze from the menu bar", {"manual": True}, None),
        ("battery pause", {"battery_reason": True}, None),
        ("safe-run --normal job (all cores by the user's word)", {}, "normal"),
        ("toggle demote_at_pause off", {}, "toggle"),
        ("dry_run: watch-only", {}, "dry")):
    p = child()
    st = fresh_st()
    c = dict(cfg)
    g._SAFERUN_NORMAL.clear()
    if setup == "normal":
        g._SAFERUN_NORMAL.add(p.pid)
    if setup == "toggle":
        c["demote_at_pause"] = False
    if setup == "dry":
        c["dry_run"] = True
    g.do_pause(c, st, [(p.pid, 1200.0, "ffmpeg", p.pid)], "chip 96 C", **kwargs)
    test("%s: not demoted" % label, p.pid not in st["demoted"], st["demoted"])
g._SAFERUN_NORMAL.clear()

print("\nD) (control) the old five-minute path still demotes and promotes through the helper")
p = child()
st = fresh_st()
hist = {p.pid: 10 * 60.0}
g.do_demote(cfg, st, [(p.pid, 90.0, "python3", p.pid)], hist, 95.0)
test("five-minute path demotes", p.pid in st["demoted"], st["demoted"])
test("without a hold: promotes at the first cool reading",
     (g.do_promote(cfg, st, hist, 60.0), p.pid not in st["demoted"])[1], st["demoted"])

for p in children:
    try:
        os.kill(p.pid, signal.SIGCONT)
        p.kill()
        p.wait()
    except Exception:
        pass
print("\n%d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
