#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flap damping and the resume window (v3.2.5).

Field data from 20.08.2026: 366 pauses in one day, 163 of 169 pause->resume cycles
exactly 60 s long, the chip back at 101 C within 30 s of every resume. The guard was
cycling a GPU job at a fixed duty, not cooling anything, and a pulsing LLM load flickered
the level 0/1/0/1 between single readings. Three fixes, pinned here:

1. The resume gate uses the MEDIAN of the last N chip readings; one cool reading inside
   a hot window does not open it, and the window only ever tightens the gate.
2. A process paused again inside `repause_window_s` holds twice as long as last time,
   up to `repause_backoff_max_s`; a quiet window resets it. The count is logged.
3. hook-gate ignores heredoc bodies: writing a script that mentions ffmpeg is a write.

Run with:  python3 tests/test_tlumienie_migotania.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import importlib.machinery
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

passed = total = 0
logged = []
g.notify = lambda *a, **k: None
g.event_jsonl = lambda *a, **k: None
_real_log = g.log
g.log = lambda msg, *a, **k: logged.append(msg)


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


cfg = dict(g.DEFAULTS)
cfg.update({"soc_pause_c": 95.0, "soc_resume_c": 86.0, "batt_pause_c": 40.0,
            "batt_resume_c": 36.0, "min_pause_seconds": 60, "repause_window_s": 300,
            "repause_backoff_max_s": 600, "resume_window_polls": 4, "dry_run": False})

print("A) resume window median")
st = {"paused": {}}
for t in (101.0, 101.5, 100.0):
    g.resume_gate(cfg, st, 30.0, t, "nominal")
test("hot window, one cool reading: gate stays closed",
     g.resume_gate(cfg, st, 30.0, 61.0, "nominal") is False,
     "median %s" % g.chip_window_median(st))
test("window keeps only N readings", len(st["_chip_window"]) == 4)
for t in (60.0, 62.0, 61.0):
    g.resume_gate(cfg, st, 30.0, t, "nominal")
test("cool window opens the gate", g.resume_gate(cfg, st, 30.0, 61.0, "nominal") is True)
test("missing reading ages the window by one instead of entering it",
     g.resume_gate(cfg, st, 30.0, None, "nominal") is True and len(st["_chip_window"]) == 3)
st2 = {"paused": {}}
test("empty window, cool chip: open (no regression for first poll)",
     g.resume_gate(cfg, st2, 30.0, 70.0, "nominal") is True)
test("median of even window is the mean of the middle pair",
     g.chip_window_median({"_chip_window": [1.0, 4.0, 2.0, 3.0]}) == 2.5)

print("B) re-pause backoff")
st = {"paused": {}}
test("first pause: base hold, no flap", g.repause_hold_s(cfg, st, "1") == (60, 0))
st["_last_resume"] = {"1": {"at": g.now() - 30, "hold": 60, "flaps": 0}}
test("re-pause inside window: doubled", g.repause_hold_s(cfg, st, "1") == (120, 1))
st["_last_resume"]["1"] = {"at": g.now() - 30, "hold": 480, "flaps": 4}
test("capped at repause_backoff_max_s", g.repause_hold_s(cfg, st, "1") == (600, 5))
st["_last_resume"]["1"] = {"at": g.now() - 301, "hold": 480, "flaps": 4}
test("quiet window resets to base", g.repause_hold_s(cfg, st, "1") == (60, 0))
test("other pid unaffected", g.repause_hold_s(cfg, st, "2") == (60, 0))
cfg0 = dict(cfg, repause_window_s=0)
st["_last_resume"]["1"] = {"at": g.now(), "hold": 60, "flaps": 0}
test("repause_window_s=0 disables damping", g.repause_hold_s(cfg0, st, "1") == (60, 0))

print("C) do_pause / do_resume carry the hold through a real process")
proc = subprocess.Popen(["sleep", "600"], start_new_session=True)
try:
    st = {"paused": {}}
    target = [(proc.pid, 150.0, "sleep", None)]
    g.do_pause(cfg, st, target, "chip 101.0 C")
    key = str(proc.pid)
    test("first pause writes hold_s=base, flaps=0",
         st["paused"][key]["hold_s"] == 60 and st["paused"][key]["flaps"] == 0)
    test("no flapping line on first pause", not any("flapping" in m for m in logged))
    g.do_resume(cfg, st, "conditions are back to normal", after_cooling=True)
    test("resume remembers the pause", key in st.get("_last_resume", {}))
    logged.clear()
    g.do_pause(cfg, st, target, "chip 101.0 C")
    test("second pause within window holds 120 s", st["paused"][key]["hold_s"] == 120,
         str(st["paused"].get(key)))
    test("flapping said out loud with count",
         any("flapping" in m and "1 time" in m and "120 s" in m for m in logged), str(logged))
    g.do_resume(cfg, st, "conditions are back to normal", after_cooling=True)
    g.do_pause(cfg, st, target, "chip 101.0 C")
    test("third pause holds 240 s", st["paused"][key]["hold_s"] == 240)
    g.do_resume(cfg, st, "x")
finally:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGCONT)
    except OSError:
        pass
    proc.kill()
    proc.wait()

print("C2) state across a daemon restart")

json.dump({"paused": {}, "_chip_window": [101.0, 101.0, 101.0],
           "_last_resume": {"7": {"at": 1.0, "hold": 120, "flaps": 1}, "bad": "x"}},
          open(g.STATE_PATH, "w"))
loaded = g.load_state()
test("chip window does not survive restart", "_chip_window" not in loaded)
test("flap memory survives restart, malformed entries dropped",
     loaded["_last_resume"] == {"7": {"at": 1.0, "hold": 120, "flaps": 1}})
json.dump({"paused": {}, "_last_resume": "junk"}, open(g.STATE_PATH, "w"))
test("junk flap memory becomes empty dict", g.load_state()["_last_resume"] == {})

print("D) hook-gate and heredocs")
hit = g._hook_command_hit
H = g.HOOK_HEAVY_DEFAULT
F = "ffmpeg"
test("quoted heredoc body mentioning a heavy tool is a write",
     hit("cat > run.sh <<'EOF'\n%s -i a.mov b.mp4\nEOF\nchmod +x run.sh" % F, H) is None)
test("unquoted body: $(...) still executes, still blocked",
     hit("cat <<EOF\n$(%s -i a b)\nEOF" % F, H) == F)
test("unquoted body: backticks still execute, still blocked",
     hit("cat <<EOF\n`%s -i a b`\nEOF" % F, H) == F)
test("unquoted body without substitution is data",
     hit("cat <<EOF\n%s -i a b\nEOF" % F, H) is None)
test("<<EOF inside a string cannot swallow the real command after it",
     hit("python3 -c 'print(\"<<EOF\")'\n%s -i a b" % F, H) == F)
test("here-string <<< is not a heredoc", hit("cat <<<EOF\n%s -i a b" % F, H) == F)
test("two heredocs on one line", hit("cat <<'A' <<'B'\n%s x\nA\nx265 y\nB\necho ok" % F, H) is None)
test("<<- strips leading tabs before the terminator", hit("cat <<-'T'\n\tx265 in\n\tT", H) is None)
test("<<- with spaces is unterminated in a shell: nothing dropped, fail-closed",
     hit("cat <<-'T'\n  x265 in\n  T\n", H) == "x265")
test("backslash-quoted tag", hit("cat <<\\EOF\n%s a\nEOF" % F, H) is None)
test("tag with a dash", hit("cat <<'END-TAG'\n%s a\nEND-TAG" % F, H) is None)
test("command AFTER the heredoc still counts", hit("cat <<'EOF'\nn\nEOF\n%s -i a b" % F, H) == F)
test("bare heavy tool still blocked", hit("%s -i a.mov b.mp4" % F, H) == F)
test("safe-run still passes", hit("safe-run -- %s -i a b" % F, H) is None)
test("grep of a heavy name is grep", hit("ps aux | grep whisper", H) is None)

print("E) Codex round: what must NOT take part in flap damping")
st = {"paused": {}}
for t in (101.0, 101.0, 101.0, 101.0):
    g.resume_gate(cfg, st, 30.0, t, "nominal")
for _ in range(4):
    g.resume_gate(cfg, st, 30.0, None, "nominal")
test("four missing readings empty a hot window (no SIGTERM on history alone)",
     st["_chip_window"] == [] and g.resume_gate(cfg, st, 30.0, None, "nominal") is True)
st = {"paused": {}, "_last_resume": {"1": {"at": g.now() + 3600, "hold": 480, "flaps": 4}}}
test("clock stepped backwards: fresh start, no inherited hold",
     g.repause_hold_s(cfg, st, "1") == (60, 0))
json.dump({"max_pause_minutes": 10, "repause_backoff_max_s": 3600, "min_pause_seconds": 60},
          open(g.CFG_PATH, "w"))
c2 = g.load_cfg()
test("backoff cap is clamped to a third of the SIGTERM deadline",
     c2["repause_backoff_max_s"] <= 200, str(c2.get("repause_backoff_max_s")))
proc = subprocess.Popen(["sleep", "600"], start_new_session=True)
time.sleep(1.5)          # ps etime has one-second resolution; a 0 s old process has no identity
try:
    st = {"paused": {}, "_last_resume": {str(proc.pid): {"at": g.now() - 10, "hold": 60,
                                                        "flaps": 0, "born": 12345}}}
    test("pid reused by a different process: fresh start",
         g.repause_hold_s(cfg, st, str(proc.pid)) == (60, 0))
    st["_last_resume"][str(proc.pid)]["born"] = g.proc_start_epoch(proc.pid)
    test("same process identity: backoff applies",
         g.repause_hold_s(cfg, st, str(proc.pid)) == (120, 1))
    st = {"paused": {}}
    key = str(proc.pid)
    target = [(proc.pid, 150.0, "sleep", None)]
    g.do_pause(cfg, st, target, "manual", manual=True)
    g.do_resume(cfg, st, "manual resume")
    test("manual freeze/resume leaves no flap memory", key not in st.get("_last_resume", {}))
    g.do_pause(cfg, st, target, "battery 11%", battery_reason=True)
    g.do_resume(cfg, st, "conditions are back to normal", after_cooling=True)
    test("battery pause leaves no flap memory", key not in st.get("_last_resume", {}))
    g.do_pause(cfg, st, target, "chip 101 C")
    g.do_resume(cfg, st, "guard startup - nothing is left frozen")
    test("startup/shutdown resume (not after cooling) leaves no flap memory",
         key not in st.get("_last_resume", {}))
    g.do_pause(cfg, st, target, "chip 101 C")
    g.do_resume(cfg, st, "conditions are back to normal", after_cooling=True)
    g.do_pause(cfg, st, target, "battery 9%", battery_reason=True)
    test("battery pause after a thermal flap does not inherit the hold",
         st["paused"][key]["hold_s"] == 60 and st["paused"][key]["flaps"] == 0)
    g.do_resume(cfg, st, "x")
finally:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGCONT)
    except OSError:
        pass
    proc.kill()
    proc.wait()

print("\n%d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
