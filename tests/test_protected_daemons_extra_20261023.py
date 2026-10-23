#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""protected_daemons_extra adds to the protected daemons instead of replacing them (23.10).

One custom name in protected_daemons dropped all five call and screen-capture engines
(FaceTime's avconferenced, replayd...), the same trap protected_apps_extra closed for apps.

1. config.json through the real load_cfg(): the extra list is cleaned like protected_daemons
   and a value of the wrong type falls back to the empty default.
2. protected_daemon_names(): extra adds to the defaults, protected_daemons still replaces them,
   and [] in both still turns the protection off.
3. A daemon named only in protected_daemons_extra is never a pause target, even in an
   emergency, and do_pause refuses it; an ordinary service still is a target (control).
4. README: the config table names both _extra keys and says protected_daemons replaces.

Run with:  python3 tests/test_protected_daemons_extra_20261023.py
Isolated TG_BASE; every process action is mocked, nothing is signalled.
"""
import json
import os
import re
import sys
import tempfile
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-daemons-extra-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_daemons_extra", os.path.join(SRC, "guard.py"))
logs = []
g.log = lambda *a, **k: logs.append(a[0])
g.notify = lambda *a, **k: None
g.args_without_paths = lambda pid: ""
g.foreground_on_tty = lambda pid: False
CFG_PATH = os.path.join(BASE, "config.json")

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def load(conf):
    with open(CFG_PATH, "w") as f:
        json.dump(conf, f)
    return g.load_cfg()


DEFAULT_DAEMONS = {n.casefold() for n in g.DEFAULTS["protected_daemons"]}

print("1. config.json through load_cfg")
test("protected_daemons_extra is a default, an empty list",
     g.DEFAULTS.get("protected_daemons_extra") == [], g.DEFAULTS.get("protected_daemons_extra"))
cfg = load({"protected_daemons_extra": ["mydaemon", "  ", "", 3]})
test("blank and non-string entries are dropped like in protected_daemons",
     cfg.get("protected_daemons_extra") == ["mydaemon"], cfg.get("protected_daemons_extra"))
cfg = load({"protected_daemons_extra": "mydaemon"})
test("a string instead of a list falls back to the empty default",
     cfg.get("protected_daemons_extra") == [], cfg.get("protected_daemons_extra"))

print("2. protected_daemon_names")
cfg = load({"protected_daemons_extra": [" MyDaemon "]})
names = g.protected_daemon_names(cfg)
test("extra adds: the five defaults stay and the new name is in",
     DEFAULT_DAEMONS | {"mydaemon"} == names, sorted(names))
cfg = load({"protected_daemons": ["otherd"], "protected_daemons_extra": ["mydaemon"]})
names = g.protected_daemon_names(cfg)
test("protected_daemons still replaces the defaults, extra adds to that",
     names == {"otherd", "mydaemon"}, sorted(names))
cfg = load({"protected_daemons": [], "protected_daemons_extra": []})
test("[] in both turns the daemon protection off", g.protected_daemon_names(cfg) == frozenset(),
     sorted(g.protected_daemon_names(cfg)))

print("3. a daemon named only in protected_daemons_extra")
cfg = dict(load({"protected_daemons_extra": ["mydaemon"]}), managed_patterns=[], count_children=False,
           cpu_min_percent=20, unknown_cpu_percent=50, unknown_min_seconds=120, dry_run=False)
daemons = {99701: "/usr/libexec/mydaemon", 99702: "/usr/libexec/replayd", 99703: "/usr/libexec/someotherd"}
procs = [(pid, 1, 90.0, os.path.basename(path)) for pid, path in daemons.items()]
with patch.object(g, "exe_path", side_effect=lambda pid: daemons.get(pid, "")), \
        patch.object(g, "proc_age_seconds", return_value=900):
    try:
        g._EMERGENCY["on"] = True
        targets = {t[0] for t in g.pick_targets(cfg, procs, {})}
    finally:
        g._EMERGENCY["on"] = False
    test("emergency: the extra daemon is not a pause target", 99701 not in targets, sorted(targets))
    test("emergency: a default daemon is still protected", 99702 not in targets, sorted(targets))
    test("emergency: an ordinary macOS service still is a target (control)", 99703 in targets, sorted(targets))
    sent = []
    with patch.object(g, "sig", side_effect=lambda *a: sent.append(a) or 0), \
            patch.object(g.subprocess, "call", side_effect=lambda *a, **k: sent.append(a) or 0):
        st = {"paused": {}, "demoted": [], "demoted_info": {}}
        g.do_pause(cfg, st, [(99701, 90.0, "mydaemon", None)], "test")
    test("do_pause refuses the extra daemon", not sent and not st["paused"], (sent, st["paused"]))

print("4. README config table")
with open(os.path.join(SRC, "README.md"), encoding="utf-8") as f:
    readme = f.read()
rows = {m.group(1): m.group(0) for m in re.finditer(r"^\|\s*`([a-z_]+)`\s*\|.*$", readme, re.M)}
test("the table has a protected_daemons_extra row", "protected_daemons_extra" in rows, sorted(rows)[:60])
test("the table has a protected_apps_extra row", "protected_apps_extra" in rows, sorted(rows)[:60])
test("the protected_daemons row says it replaces the default list",
     "replaces" in rows.get("protected_daemons", ""), rows.get("protected_daemons"))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
