#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The published data format (docs/spec, 22.10) must list everything the code writes.

The spec is what an outside reader builds on: a Grafana panel, an evidence parser, a fleet
script. A spec that misses a field the daemon has started writing, or still lists one it
dropped, sends that reader wrong. So the names here come from the CODE, never from a list
kept by hand next to it:

1. history_events.jsonl: every event_jsonl() type and field in guard.py and safe-run
2. events.log: every record_event() type and context key in guard.py
3. status.json: every key status_write() can write, from its source and from a real call
4. history.csv: the header, column by column, in order
5. thermal-metrics: every metric it prints for a complete snapshot and a fleet folder
6. fleet snapshot: every field fleet_write() adds to status.json
7. the versioning rule for event records (23.10): no `v` field means version 1

Metrics listed under "Added in this version" may be missing from the code: the spec names
them before the release that prints them.

Run with:  python3 tests/test_spec_20261022.py
Isolated TG_BASE; starts no daemon and signals nothing.
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-spec-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def read(rel):
    with open(os.path.join(SRC, rel), encoding="utf-8") as f:
        return f.read()


def spec_tables(rel):
    """{(h2, h3): [(name, row)]}: the backticked first cell of every table row, in order."""
    try:
        text = read(rel)
    except OSError:
        return {}
    out, h2, h3 = {}, "", ""
    for line in text.splitlines():
        if line.startswith("## "):
            h2, h3 = line[3:].strip(), ""
        elif line.startswith("### "):
            h3 = line[4:].strip()
        else:
            m = re.match(r"\|\s*`([^`]+)`\s*\|", line)
            if m:
                out.setdefault((h2, h3), []).append((m.group(1), line))
    return out


def names(tables, h2, h3=None):
    return {n for (a, b), rows in tables.items() if a == h2 and (h3 is None or b == h3) for n, _ in rows}


def calls(rel, func):
    """[(literal first argument or None, Call node)] for every call of `func` in a source file."""
    out = []
    for node in ast.walk(ast.parse(read(rel))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == func:
            first = node.args[0] if node.args else None
            literal = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
            out.append((literal, node))
    return out


def function(rel, name):
    for node in ast.walk(ast.parse(read(rel))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def dict_keys(node):
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def assigned_keys(fn, var):
    """Literal keys of every `var["key"] = ...` inside a function."""
    out = set()
    for node in ast.walk(fn) if fn else ():
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == var:
                    key = getattr(t.slice, "value", t.slice)   # 3.8 wraps it in ast.Index
                    key = key.value if isinstance(key, ast.Constant) else key
                    if isinstance(key, str):
                        out.add(key)
    return out


EVENTS = "docs/spec/events-v1.md"
METRICS = "docs/spec/metrics-v1.md"
ev = spec_tables(EVENTS)
mt = spec_tables(METRICS)
test("both spec documents exist and have tables", ev and mt, (EVENTS, METRICS))


def spec_types(h2):
    """Event types are the backticked level-3 headings of one stream's section."""
    return {re.sub(r"`", "", b) for (a, b) in ev if a == h2 and b.startswith("`")}


print("1. history_events.jsonl")
H2 = "1. history_events.jsonl"
common = names(ev, H2, "Common fields")
written = {}
dynamic = []
for rel in ("guard.py", "safe-run"):
    for etype, node in calls(rel, "event_jsonl"):
        if etype is None:
            dynamic.append("%s:%d" % (rel, node.lineno))
            continue
        written.setdefault(etype, set()).update(k.arg for k in node.keywords if k.arg)
test("every event_jsonl() call names its type as a literal (else it cannot be checked)", not dynamic, dynamic)
test("the code writes events at all (the source scan works)", len(written) >= 8, sorted(written))
listed = spec_types(H2)
test("every event type the code writes is in the spec", set(written) <= listed, sorted(set(written) - listed))
test("every event type in the spec is still written (a removal bumps the version)",
     listed <= set(written), sorted(listed - set(written)))
missing, stale = [], []
for etype, fields in sorted(written.items()):
    documented = names(ev, H2, "`%s`" % etype)
    missing += ["%s.%s" % (etype, f) for f in fields - documented - common]
    stale += ["%s.%s" % (etype, f) for f in documented - fields]
test("every field the code writes is in its event's table", not missing, missing)
test("every field in an event's table is still written", not stale, stale)
test("the common fields are listed", {"time", "epoch", "type", "source"} <= common, sorted(common))

print("2. events.log")
H2 = "2. events.log"
written = {}
dynamic = []
for etype, node in calls("guard.py", "record_event"):
    context = node.args[2] if len(node.args) > 2 else next(
        (k.value for k in node.keywords if k.arg == "context"), None)
    if etype is None or (context is not None and not isinstance(context, ast.Dict)):
        dynamic.append("guard.py:%d" % node.lineno)
        continue
    written.setdefault(etype, set()).update(
        "context." + k for k in (dict_keys(context) if context is not None else ()))
test("every record_event() call has a literal type and context (else it cannot be checked)", not dynamic, dynamic)
listed = spec_types(H2)
test("every black-box event type the code writes is in the spec", set(written) <= listed,
     sorted(set(written) - listed))
test("every black-box event type in the spec is still written", listed <= set(written),
     sorted(listed - set(written)))
missing, stale = [], []
for etype, keys in sorted(written.items()):
    documented = names(ev, H2, "`%s`" % etype)
    missing += ["%s %s" % (etype, k) for k in keys - documented]
    stale += ["%s %s" % (etype, k) for k in documented - keys]
test("every context key the code writes is in its event's table", not missing, missing)
test("every context key in an event's table is still written", not stale, stale)
test("the black-box common fields are listed",
     {"time", "epoch", "detected_at", "type", "description", "synthetic", "context"}
     <= names(ev, H2, "Common fields"), sorted(names(ev, H2, "Common fields")))

print("3. status.json")
g = load_source("guard_spec", os.path.join(SRC, "guard.py"))
H2 = "1. status.json"
rows = dict(r for (a, _b), rs in mt.items() if a == H2 for r in rs)
top = {n for n in rows if "." not in n}
src_keys, nested = set(), set()
fn = function("guard.py", "status_write")
for node in ast.walk(fn) if fn else ():
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "data" for t in node.targets) \
            and isinstance(node.value, ast.Dict):
        src_keys |= dict_keys(node.value)
        for k, v in zip(node.value.keys, node.value.values):
            for sub in ast.walk(v):
                if isinstance(sub, ast.Dict):
                    nested |= {"%s.%s" % (k.value, s) for s in dict_keys(sub)}
src_keys |= assigned_keys(fn, "data")
test("the status_write() source scan finds the snapshot", len(src_keys) >= 40, len(src_keys))

# A real call, with every optional part present: two hundred history rows so chip_profile
# is not null, a pause, a demotion, counters and the admission block.
soc = {"cpu": 71.0, "gpu": 66.0, "fans": [2100, 2300], "watts": 18.5,
       "ram_used": 20.0, "ram_total": 48.0, "swap_used": 1.0}
for i in range(210):
    g.hist_write(g.hist_row("nominal", soc, 60.0 + i % 30, 31.0, soc["fans"], 80, True, 100, 2.5, 0,
                            (4242, 120.0, "ffmpeg", 4242)))
st = {"paused": {"4242": {"comm": "ffmpeg", "since": time.time() - 30, "powod": "termika",
                          "manual": False, "pgid": 4242}},
      "demoted_info": {"4243": {"comm": "x265"}},
      "stats": {"since": time.time() - 3600, "pauses": 1, "resumes": 1, "kills": 1, "awake_released_hot": 1},
      "_prog_pauza": 85.0, "_prog_wznowienia": 76.0, "_prog_ubicie": 90.0,
      "_admission": g.admission_update(dict(g.DEFAULTS), 60.0, 0, 1.0)}
g._ostatnio_odrzucone["v"] = []          # set by load_cfg() in the daemon
with patch.object(g, "thermal_pressure", return_value=(1, "moderate")), patch.object(g, "log"):
    snap = g.status_write("fair", 31.0, soc, 71.0, True, 80, 100, 2.5, 1, "chip 71.0 C",
                          [(4242, 120.0, "ffmpeg", 4242)], st, (500.0, 1000.0, 50.0))
code_keys = src_keys | set(snap)
test("a real snapshot has the optional parts (profile, admission)",
     snap.get("chip_profile") and "admission" in snap and "queued_count" in snap,
     sorted(k for k in ("chip_profile", "admission", "queued_count") if not snap.get(k)))
test("every status.json field the code writes is in the spec", code_keys <= top, sorted(code_keys - top))
test("every status.json field in the spec is still written", top <= code_keys, sorted(top - code_keys))
undocumented = [n for n in sorted(nested) if n not in rows
                and "`%s`" % n.split(".", 1)[1] not in rows.get(n.split(".", 1)[0], "")]
test("every nested field status_write() builds is in the spec", not undocumented, undocumented)

print("4. history.csv")
header = g.HIST_HEADER.strip().split(",")
columns = [n for (a, _b), rs in mt.items() if a == "2. history.csv" for n, _ in rs]
test("the spec lists the history.csv columns exactly, in order", columns == header,
     {"code": header, "spec": columns})

print("5. thermal-metrics")
H2 = "3. thermal-metrics"
pending = names(mt, H2, "Added in this version")
listed = names(mt, H2)
fleet_dir = os.path.join(BASE, "fleet")
g._hostname_cache["v"] = "spec-host"
g.fleet_write({"fleet_dir": fleet_dir}, snap)
with open(os.path.join(fleet_dir, "broken.json"), "w") as f:
    f.write("{not json")
p = subprocess.run([sys.executable, os.path.join(SRC, "thermal-metrics"), "--dir", fleet_dir],
                   capture_output=True, text=True, timeout=60, env=dict(os.environ, TG_BASE=BASE))
printed = set(re.findall(r"^# TYPE (\S+) ", p.stdout, re.M))
test("thermal-metrics runs and prints metrics", p.returncode == 0 and len(printed) >= 30,
     (p.returncode, p.stderr[-300:], len(printed)))
static = set()
for node in ast.walk(ast.parse(read("thermal-metrics"))):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add" \
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "reg" \
            and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        static.add("coffee_paladin_" + node.args[0].value)
test("every metric thermal-metrics prints is in the spec", printed <= listed, sorted(printed - listed))
test("every literal metric name in the source is in the spec", static <= listed, sorted(static - listed))
test("every metric in the spec is still printed, except those not released yet",
     listed - pending <= printed, sorted(listed - pending - printed))
test("the gauge announced for the next release is listed under 'Added in this version'",
     "coffee_paladin_thermal_pressure_level" in pending, sorted(pending))

print("6. fleet snapshot")
added = assigned_keys(function("guard.py", "fleet_write"), "out")
try:
    with open(os.path.join(fleet_dir, "spec-host.json")) as f:
        added |= set(json.load(f)) - set(snap)
except (OSError, ValueError):
    pass
listed = names(mt, "4. Fleet snapshot")
test("the fleet_write() scan finds its fields", {"host", "guard_version", "epoch"} <= added, sorted(added))
test("every field the fleet snapshot adds is in the spec", added <= listed, sorted(added - listed))
test("every fleet field in the spec is still written", listed <= added, sorted(listed - added))

print("7. versioning of event records")
# 23.10: records carry no version field, and the rule for telling versions apart in a mixed
# file (safe-run from an older release next to a newer daemon) must stay written down.
compat = read(EVENTS).split("## Compatibility", 1)[-1].split("\n## ", 1)[0]
compat = " ".join(compat.split())
test("events-v1.md: a record without a `v` field is version 1",
     "A record without a `v` field is version 1" in compat, compat)
test("events-v1.md: an incompatible version 2 would say so with a `v` field",
     re.search(r"incompatible version 2 .*with a `v` field", compat) is not None, compat)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
