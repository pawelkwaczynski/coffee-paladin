#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prometheus output: one scrape must never be poisoned by one machine.

Prometheus rejects an ENTIRE scrape on a single malformed line, so in a fleet the failure
mode is not "one host looks wrong", it is "the whole rack disappears from the dashboard".
Every case below is paired with the countercase, because publishing a wrong number is worse
than publishing none: a machine that is off must not draw a calm line, and a sensor that
said nothing must not read as zero degrees.

Cases:
  1. many hosts -> HELP and TYPE appear exactly once per metric name
  2. the local machine and its own fleet snapshot -> ONE host, not two
  3. a host name with a quote and a backslash -> escaped, output still parses
  4. missing/NaN/None readings -> no sample at all (not a zero)
  5. age just over the fleet threshold -> up=0 but readings still published
  6. age far over -> readings dropped, up and age still published
  7. epoch in the future -> age is not negative
  8. broken fleet file -> host present at up=0, never silently missing
  9. --output -> complete file, 0644, no leftover temporary files
 10. counters are typed as counters, not gauges

Run with:  python3 tests/test_metryki.py
Does not touch the real ~/.coffee-paladin.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(SRC, "thermal-metrics")
BASE = tempfile.mkdtemp(prefix="tg-metryki-")
FLEET_DIR = os.path.join(BASE, "flota")
os.makedirs(FLEET_DIR)

results = []


def test(name, condition, detail=""):
    results.append(bool(condition))
    print("%s %s%s" % ("[OK]  " if condition else "[FAIL]", name,
                       ("  <- " + detail) if (detail and not condition) else ""))


def snapshot(**over):
    """A snapshot shaped like the guard's, fresh unless the test says otherwise."""
    snap = {
        "epoch": round(time.time(), 3),
        "chip_c": 71.5, "gpu_c": 68.0, "battery_c": 30.1, "battery_pct": 80,
        "chip_sensor": True, "chip_stale": False, "fans": [2100, 2200],
        "watts": 18.5, "on_ac": True, "load1": 3.2, "cpu_limit": 100, "level": 0,
        "ram_used_gb": 20.0, "ram_total_gb": 48.0, "swap_used_gb": 1.0,
        "disk_used_gb": 500, "disk_total_gb": 1000,
        "thresholds": {"pause": 95.0, "resume": 88.0, "kill": 103.0},
        "paused": [], "demoted": [], "freeze_candidates": [], "unpausable": [],
        "heavy_count": 1, "keep_awake": True, "manual_pause": False, "dry_run": False,
        "stats_total": {"pauses": 12, "resumes": 11, "kills": 1, "awake_released_hot": 3},
        "chip_profile": {"samples": 900, "p50": 60.0, "p90": 88.0, "p99": 97.0,
                         "max": 99.5},
        "guard_version": "3.3.3",
    }
    snap.update(over)
    return snap


def write_cfg(**over):
    cfg = {"fleet_dir": FLEET_DIR, "fleet_label": "local-box"}
    cfg.update(over)
    with open(os.path.join(BASE, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def write_status(snap):
    with open(os.path.join(BASE, "status.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f)


def write_host(name, snap):
    with open(os.path.join(FLEET_DIR, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(snap, f)


def run(*args):
    env = dict(os.environ, TG_BASE=BASE)
    p = subprocess.run([sys.executable, TOOL] + list(args), capture_output=True,
                       text=True, env=env, timeout=60)
    return p.stdout, p.stderr, p.returncode


SERIES = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})? (-?[0-9.eE+]+)$')


def parse(text):
    """Parse the exposition the way a strict scraper would; raise on anything it rejects."""
    helps, types, samples = {}, {}, []
    for i, line in enumerate(text.splitlines(), 1):
        if not line:
            continue
        if line.startswith("# HELP "):
            name = line.split(" ", 3)[2]
            if name in helps:
                raise ValueError("duplicate HELP for %s at line %d" % (name, i))
            helps[name] = line.split(" ", 3)[3] if len(line.split(" ", 3)) > 3 else ""
            continue
        if line.startswith("# TYPE "):
            parts = line.split(" ", 3)
            name = parts[2]
            if name in types:
                raise ValueError("duplicate TYPE for %s at line %d" % (name, i))
            types[name] = parts[3]
            continue
        if line.startswith("#"):
            continue
        m = SERIES.match(line)
        if not m:
            raise ValueError("unparseable line %d: %r" % (i, line))
        if m.group(1) not in types:
            raise ValueError("series without TYPE at line %d: %s" % (i, m.group(1)))
        samples.append((m.group(1), m.group(2) or "", float(m.group(3))))
    return helps, types, samples


def hosts_of(samples, metric):
    out = []
    for name, labels, _ in samples:
        if name == metric:
            m = re.search(r'host="((?:[^"\\]|\\.)*)"', labels)
            out.append(m.group(1) if m else None)
    return out


def value_of(samples, metric, host=None):
    for name, labels, value in samples:
        if name != metric:
            continue
        if host is None or ('host="%s"' % host) in labels:
            return value
    return None


# ---------------------------------------------------------------- 1, 2, 10
write_cfg()
write_status(snapshot())
# The same machine also publishes into the shared folder, under the name the guard uses.
write_host("local-box", snapshot(host="local-box", chip_c=71.5))
write_host("rack-02", snapshot(host="rack-02", chip_c=80.0))
write_host("rack-03", snapshot(host="rack-03", chip_c=90.0))

out, err, rc = run("--fleet")
try:
    helps, types, samples = parse(out)
    parsed = True
    problem = ""
except ValueError as e:
    helps, types, samples, parsed, problem = {}, {}, [], False, str(e)

test("1. many hosts still parse, one HELP/TYPE per metric", parsed, problem)
test("1b. the fleet really is in there (>=3 metrics, >=10 samples)",
     len(types) >= 3 and len(samples) >= 10, "types=%d samples=%d" % (len(types), len(samples)))

up_hosts = hosts_of(samples, "coffee_paladin_up")
test("2. local machine counted once, not twice",
     sorted(up_hosts) == ["local-box", "rack-02", "rack-03"],
     "hosts=%r" % (sorted(up_hosts),))

test("10. counters are typed as counters",
     types.get("coffee_paladin_pauses_total") == "counter"
     and types.get("coffee_paladin_chip_celsius") == "gauge",
     "pauses=%r chip=%r" % (types.get("coffee_paladin_pauses_total"),
                            types.get("coffee_paladin_chip_celsius")))

# ---------------------------------------------------------------- 3
odd = 'rack "04" \\ back\\slash'
write_host("rack-04", snapshot(host=odd))
out, _, _ = run("--fleet")
try:
    _, _, samples3 = parse(out)
    ok3, why3 = True, ""
except ValueError as e:
    samples3, ok3, why3 = [], False, str(e)
test("3. a host name with a quote and a backslash does not break the scrape", ok3, why3)
test("3b. and it is escaped, not dropped",
     any('\\"04\\"' in labels for name, labels, _ in samples3
         if name == "coffee_paladin_up"),
     "labels=%r" % ([labels for name, labels, _ in samples3
                     if name == "coffee_paladin_up"],))
os.unlink(os.path.join(FLEET_DIR, "rack-04.json"))

# ---------------------------------------------------------------- 4
# A dead sensor must produce NO sample. Zero would draw a machine at 0 C, which reads as
# "ice cold and safe" on every dashboard and in every alert rule.
write_status(snapshot(chip_c=None, gpu_c=float("nan"), watts="n/a"))
out, _, _ = run()
_, types4, samples4 = parse(out)
test("4. a null reading produces no sample at all",
     value_of(samples4, "coffee_paladin_chip_celsius") is None
     and value_of(samples4, "coffee_paladin_gpu_celsius") is None
     and value_of(samples4, "coffee_paladin_power_watts") is None,
     "chip=%r gpu=%r watts=%r" % (value_of(samples4, "coffee_paladin_chip_celsius"),
                                  value_of(samples4, "coffee_paladin_gpu_celsius"),
                                  value_of(samples4, "coffee_paladin_power_watts")))
test("4b. countercase: a real zero IS published",
     value_of(samples4, "coffee_paladin_level") == 0.0,
     "level=%r" % (value_of(samples4, "coffee_paladin_level"),))

# ---------------------------------------------------------------- 5, 6, 7
write_status(snapshot())
for name in os.listdir(FLEET_DIR):
    os.unlink(os.path.join(FLEET_DIR, name))
# 6 min: past the 300 s "not reporting" line that `fleet` draws, but a user is allowed to
# set a 5-minute measurement interval, so the readings must survive a couple of cycles.
write_host("slow", snapshot(host="slow", epoch=time.time() - 360, chip_c=77.7))
# 3 h: the machine may be off. Republishing its last temperature every minute would draw a
# flat, healthy line for a Mac nobody has touched since morning.
write_host("dead", snapshot(host="dead", epoch=time.time() - 3 * 3600, chip_c=88.8))
# Clock skew on a remote Mac must not produce a negative age.
write_host("future", snapshot(host="future", epoch=time.time() + 7200, chip_c=66.6))
out, _, _ = run("--fleet")
_, _, s5 = parse(out)

test("5. just past the fleet threshold: up=0 but the reading is still there",
     value_of(s5, "coffee_paladin_up", "slow") == 0
     and value_of(s5, "coffee_paladin_chip_celsius", "slow") == 77.7,
     "up=%r chip=%r" % (value_of(s5, "coffee_paladin_up", "slow"),
                        value_of(s5, "coffee_paladin_chip_celsius", "slow")))
test("6. long dead: the temperature is dropped, up and age remain",
     value_of(s5, "coffee_paladin_chip_celsius", "dead") is None
     and value_of(s5, "coffee_paladin_up", "dead") == 0
     and value_of(s5, "coffee_paladin_snapshot_age_seconds", "dead") > 3000,
     "chip=%r up=%r age=%r" % (value_of(s5, "coffee_paladin_chip_celsius", "dead"),
                               value_of(s5, "coffee_paladin_up", "dead"),
                               value_of(s5, "coffee_paladin_snapshot_age_seconds", "dead")))
test("7. a future timestamp gives age 0, never a negative number",
     value_of(s5, "coffee_paladin_snapshot_age_seconds", "future") == 0,
     "age=%r" % (value_of(s5, "coffee_paladin_snapshot_age_seconds", "future"),))

# ---------------------------------------------------------------- 8
with open(os.path.join(FLEET_DIR, "corrupt.json"), "w", encoding="utf-8") as f:
    f.write('{"chip_c": 91.2, "epoch"')       # truncated mid-sync
with open(os.path.join(FLEET_DIR, "listnot.json"), "w", encoding="utf-8") as f:
    f.write('[1, 2, 3]')                       # valid JSON, wrong shape
out, _, _ = run("--fleet")
try:
    _, _, s8 = parse(out)
    ok8, why8 = True, ""
except ValueError as e:
    s8, ok8, why8 = [], False, str(e)
test("8. a broken snapshot does not break the scrape", ok8, why8)
test("8b. and the machine is still listed, at up=0",
     value_of(s8, "coffee_paladin_up", "corrupt") == 0
     and value_of(s8, "coffee_paladin_up", "listnot") == 0,
     "corrupt=%r listnot=%r" % (value_of(s8, "coffee_paladin_up", "corrupt"),
                                value_of(s8, "coffee_paladin_up", "listnot")))

# ---------------------------------------------------------------- 9
target = os.path.join(BASE, "out", "coffee_paladin.prom")
os.makedirs(os.path.dirname(target))
out, err, rc = run("--output", target)
written = open(target, encoding="utf-8").read()
mode = os.stat(target).st_mode & 0o777
leftovers = [n for n in os.listdir(os.path.dirname(target))
             if n.startswith(".thermal-metrics-")]
test("9. --output writes the whole document and prints nothing",
     rc == 0 and out == "" and written.startswith("# HELP") and written.endswith("\n"),
     "rc=%d stdout=%r tail=%r" % (rc, out[:40], written[-20:]))
test("9b. the collector, running as another user, can read it", mode == 0o644,
     "mode=%o" % mode)
test("9c. no temporary files left behind", leftovers == [], "leftovers=%r" % leftovers)
try:
    parse(written)
    ok9d, why9d = True, ""
except ValueError as e:
    ok9d, why9d = False, str(e)
test("9d. the written file parses too", ok9d, why9d)

# ---------------------------------------------------------------- exit
shutil.rmtree(BASE, ignore_errors=True)
bad = results.count(False)
print("\n%d/%d passed" % (results.count(True), len(results)))
sys.exit(1 if bad else 0)
