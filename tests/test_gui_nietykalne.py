#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Desktop apps and macOS services are never frozen by the emergency net (v3.2.6).

The "unknown heavy" net (any owned process above unknown_cpu_percent for
unknown_min_seconds) exists for solvers with unknown names. On 20.08.2026 it froze Google
Chrome 31 times, VTDecoderXPCService while a video played, and contactsd. A window the
user is looking at, stopped for 60-600 s, is the same failure class as a frozen terminal.

Pinned here:
* an unnamed process from an .app bundle is slowed down (taskpolicy -b) and named, never
  paused; a macOS service (/System, /usr/libexec, *.xpc) is named and left alone;
* a named managed pattern still wins (python inside a bundle pauses as before);
* a CLI job outside a bundle still pauses;
* the net closes again in an emergency; `gui_apps_never_pause: false` restores old behaviour;
* immediate demotion does the bookkeeping do_promote relies on.

Run with:  python3 tests/test_gui_nietykalne.py
Does not touch the real ~/.coffee-paladin; it works in a temporary directory.
"""
import importlib.machinery
import os
import signal
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

passed = total = 0
logged = []
g.log = lambda msg, *a, **k: logged.append(msg)
g.notify = lambda *a, **k: None


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


print("A) app_kind classification")
K = g.app_kind
test("Chrome in /Applications", K("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") == "gui")
test("nested helper bundle (Electron/Chrome Helper)",
     K("/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework"
       "/Versions/1/Helpers/Google Chrome Helper (Renderer).app/Contents/MacOS/Google Chrome Helper (Renderer)") == "gui")
test("~/Applications bundle", K("/Users/x/Applications/Arc.app/Contents/MacOS/Arc") == "gui")
test("VTDecoder XPC service is system",
     K("/System/Library/Frameworks/VideoToolbox.framework/Versions/A/XPCServices/"
       "VTDecoderXPCService.xpc/Contents/MacOS/VTDecoderXPCService") == "system")
test("/usr/libexec daemon is system", K("/usr/libexec/contactsd") == "system")
test("solver in ~/bin is a CLI job", K("/Users/x/bin/b3core") is None)
test("Homebrew CLI is a CLI job", K("/opt/homebrew/bin/cargo") is None)
test("unknown path is a CLI job", K("") is None)

print("B) pick_targets routing")
PATHS = {
    100: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    200: "/System/Library/Frameworks/VideoToolbox.framework/Versions/A/XPCServices/"
         "VTDecoderXPCService.xpc/Contents/MacOS/VTDecoderXPCService",
    300: "/Users/x/bin/b3core",
    400: "/Applications/SomeTool.app/Contents/Resources/python3",
}
g.exe_path = lambda pid: PATHS.get(pid, "")
g.proc_age_seconds = lambda pid: 900
g.args_without_paths = lambda pid: ""
g.foreground_on_tty = lambda pid: False
procs = [(100, 1, 93.0, "Google Chrome"), (200, 1, 99.0, "VTDecoderXPCService"),
         (300, 1, 250.0, "b3core"), (400, 1, 120.0, "python3")]
cfg = dict(g.DEFAULTS)
cfg.update({"managed_patterns": ["python3"], "never_patterns": [], "never_extra": [],
            "count_children": False, "cpu_min_percent": 20, "unknown_cpu_percent": 50,
            "unknown_min_seconds": 120, "manage_unknown_heavy": True,
            "gui_apps_never_pause": True, "system_demote_patterns": []})
g._EMERGENCY["on"] = False
targets = g.pick_targets(cfg, procs, {})
pids = [t[0] for t in targets]
test("Chrome is NOT a pause target", 100 not in pids, str(pids))
test("Chrome is on the GUI slow-down list", 100 in [t[0] for t in g._GUI_HOT])
test("VTDecoder is NOT a pause target", 200 not in pids, str(pids))
test("VTDecoder is on the system list (named, left alone)", 200 in [t[0] for t in g._SYSTEM_HOT])
test("unnamed CLI solver still pauses", 300 in pids, str(pids))
test("named managed pattern inside a bundle still pauses (name wins)", 400 in pids, str(pids))

g._EMERGENCY["on"] = True
pids = [t[0] for t in g.pick_targets(cfg, procs, {})]
test("emergency: Chrome is back on the pause list", 100 in pids, str(pids))
test("emergency: VTDecoder too", 200 in pids, str(pids))
g._EMERGENCY["on"] = False

cfg_off = dict(cfg, gui_apps_never_pause=False)
pids = [t[0] for t in g.pick_targets(cfg_off, procs, {})]
test("gui_apps_never_pause=false restores the old net", 100 in pids and 200 in pids, str(pids))

cfg_noun = dict(cfg, manage_unknown_heavy=False)
g.pick_targets(cfg_noun, procs, {})
test("with the net off nothing is classified either",
     not g._GUI_HOT and not g._SYSTEM_HOT)

print("C) say_hot_apps: once per process per window")
logged.clear()
st = {}
gui = [(100, 93.0, "Google Chrome", None)]
sysl = [(200, 99.0, "VTDecoderXPCService", None)]
g.say_hot_apps(cfg, st, gui, sysl)
g.say_hot_apps(cfg, st, gui, sysl)
test("two lines, not four", len(logged) == 2, str(logged))
test("desktop app line says slowed down, never frozen",
     any("Google Chrome" in m and "never frozen" in m for m in logged), str(logged))
test("service line says left alone",
     any("VTDecoderXPCService" in m and "left alone" in m for m in logged), str(logged))

print("D) immediate demotion on a real process")
proc = subprocess.Popen(["sleep", "600"], start_new_session=True)
try:
    st = {"paused": {}, "demoted": [], "demoted_info": {}}
    cfg_d = dict(cfg, dry_run=False, demote_after_minutes=5, demote_cpu_percent=60.0)
    hist = {}
    g.do_demote(cfg_d, st, [(proc.pid, 30.0, "sleep", None)], hist, None, immediate=True)
    test("immediate: demoted without the 5-minute clock, chip reading or CPU floor",
         proc.pid in st["demoted"], str(st))
    test("name recorded for status", st["demoted_info"].get(str(proc.pid), {}).get("comm") == "sleep")
    st2 = {"paused": {}, "demoted": [], "demoted_info": {}}
    g.do_demote(cfg_d, st2, [(proc.pid, 90.0, "sleep", None)], {}, 95.0)
    test("normal path still waits for the clock", proc.pid not in st2["demoted"])
    # do_promote must be able to undo it: cool chip -> taskpolicy -B
    g.do_promote(cfg_d, st, hist, 50.0)
    test("promote restores after cooling", proc.pid not in st["demoted"], str(st))
finally:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGCONT)
    except OSError:
        pass
    proc.kill()
    proc.wait()

print("E) status carries the lists")
st = {"paused": {}, "demoted_info": {}, "_gui_hot": [{"name": "Google Chrome", "cpu": 93}],
      "_system_hot": []}
g._ostatnio_odrzucone["v"] = []   # load_cfg never ran in this test
snap = g.status_write("nominal", 30.0, None, 90.0, True, 80, 100, 1.0, 1, "x", [], st)
test("gui_hot in status.json", snap and snap.get("gui_hot") == [{"name": "Google Chrome", "cpu": 93}],
     str(snap and snap.get("gui_hot")))
test("system_hot present even when empty", snap is not None and snap.get("system_hot") == [])

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
