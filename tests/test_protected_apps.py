#!/usr/bin/env python3
"""Protected desktop bundle routing, with isolated state and mocked process actions."""
import os
import tempfile

from _load import load_source

os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg-protected-")
os.environ["TG_LANG"] = "en"
g = load_source("protected_guard", os.path.join(os.path.dirname(__file__), "..", "guard.py"))

paths = {
    301: "/Applications/zoom.us.app/Contents/MacOS/zoom.us",
    302: "/Applications/zoom.us.app/Contents/Frameworks/CptHost.app/Contents/MacOS/CptHost",
    303: "/Applications/Foo.app/Contents/MacOS/Foo",
    304: "/System/Applications/FaceTime.app/Contents/MacOS/FaceTime",
}
procs = [(pid, 2, 91.0, name) for pid, name in
         ((301, "zoom.us"), (302, "CptHost"), (303, "Foo"), (304, "FaceTime"))]
g.exe_path = lambda pid: paths.get(pid, "")
g.proc_age_seconds = lambda pid: 900
g.args_without_paths = lambda pid: ""
g.foreground_on_tty = lambda pid: False
g.cpu_with_children = lambda ps: {}
g.thermal_pressure = lambda: None
g.log = lambda *a, **k: logs.append(a[0])
g.notify = lambda *a, **k: None
g.subprocess.call = lambda *a, **k: actions.append(("demote", a[0])) or 0
g.sig = lambda *a: actions.append(("signal", a)) or 0
g.alive = lambda pid: True
g.stopped_now = lambda: ({301, 302, 303}, set())
g.entry_identity_ok = lambda *a, **k: True
g.entry_stopped = lambda *a: True
g.save_state = lambda st: None
g.process_identity = lambda pid: {}
g.event_jsonl = lambda *a, **k: None
g._ostatnio_odrzucone["v"] = []

cfg = dict(g.DEFAULTS, never_patterns=[], never_extra=[], managed_patterns=["zoom.us"],
           count_children=False, cpu_min_percent=20, unknown_cpu_percent=50,
           unknown_min_seconds=120, dry_run=False)
logs, actions = [], []
passed = total = 0


def check(name, ok):
    global passed, total
    total += 1
    passed += bool(ok)
    print("  [%s] %s" % ("PASS" if ok else "FAIL", name))


for emergency in (False, True):
    g._EMERGENCY["on"] = emergency
    targets = g.pick_targets(cfg, procs, {})
    target_pids = {t[0] for t in targets}
    hot_pids = {t[0] for t in g._GUI_HOT}
    check("protected direct and helper absent from pause targets, emergency=%s" % emergency,
          not {301, 302, 304} & target_pids)
    check("protected direct and helper named as hot GUI, emergency=%s" % emergency,
          {301, 302, 304} <= hot_pids)
    check("ordinary GUI routing, emergency=%s" % emergency,
          (303 in target_pids) == emergency and (303 in hot_pids) != emergency)
    st = {"paused": {}, "demoted": [], "demoted_info": {}, "_gui_hot":
          g.gui_hot_status([(pid, 91, name, None) for pid, name in
                            ((301, "zoom.us"), (302, "CptHost"), (303, "Foo"),
                             (304, "FaceTime"))])}
    snap = g.status_write("nominal", None, None, 85.0, True, 80, 100, 1, 2, "hot", targets, st)
    check("status flags protected bundles, emergency=%s" % emergency,
          all(x["protected"] for x in snap["gui_hot"][:2]) and
          not snap["gui_hot"][2]["protected"] and snap["gui_hot"][3]["protected"])
    g.say_hot_apps(cfg, st, g._GUI_HOT, [], gap_s=0)
    check("protected bundles named in log, emergency=%s" % emergency,
          any("zoom.us" in x and "protected app" in x for x in logs))
    before = len(logs)
    g.say_hot_apps(cfg, st, g._GUI_HOT, [])
    check("hot app log is rate limited, emergency=%s" % emergency, len(logs) == before)
    actions.clear()
    g.do_demote(cfg, st, g._GUI_HOT, {}, 90.0, immediate=True)
    check("protected bundles never demoted, emergency=%s" % emergency,
          all("301" not in str(a) and "302" not in str(a) for a in actions))
    actions.clear()
    g.do_pause(cfg, st, [(301, 91, "zoom.us", None), (302, 91, "CptHost", None)], "hot")
    check("direct pause rejects protected bundles, emergency=%s" % emergency,
          not actions and not st["paused"])
    if emergency:
        g.do_pause(cfg, st, [(303, 91, "Foo", None)], "hot")
        check("ordinary GUI receives emergency pause", any(a[0] == "signal" for a in actions))
        actions.clear()
        st["paused"].clear()
    st["paused"] = {"301": {"comm": "zoom.us", "pgid": None}}
    g.do_terminate(cfg, st, "hot")
    check("termination rejects protected bundle, emergency=%s" % emergency,
          not actions)

g._EMERGENCY["on"] = False
g.pick_targets(cfg, procs, {})
actions.clear()
g.do_demote(cfg, {"demoted": [], "demoted_info": {}}, g._GUI_HOT, {}, 90.0, immediate=True)
check("ordinary hot GUI is demoted", any(a[0] == "demote" and "303" in a[1] for a in actions))

empty = dict(cfg, protected_apps=[], managed_patterns=[])
g._EMERGENCY["on"] = False
g.pick_targets(empty, procs, {})
check("empty list makes zoom ordinary GUI", 301 in {t[0] for t in g._GUI_HOT}
      and 301 not in g._PROTECTED_HOT)
g._EMERGENCY["on"] = True
check("empty list permits emergency pause", 301 in {t[0] for t in g.pick_targets(empty, procs, {})})
check("bundle name matching ignores case", g.protected_app(dict(cfg, protected_apps=["ZOOM.US"]), 301))
check("bundle matching is exact", not g.protected_app(dict(cfg, protected_apps=["zoom"]), 301))
check("custom list replaces defaults", not g.protected_app(dict(cfg, protected_apps=["Foo"]), 301)
      and g.protected_app(dict(cfg, protected_apps=["Foo"]), 303))

print("RESULT: %d/%d" % (passed, total))
raise SystemExit(0 if passed == total else 1)
