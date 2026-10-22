#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A fleet snapshot macOS will not let the daemon replace (22.10).

Field data from the owner's Mac: since the first write after the 25.09 system update every
fleet_write ended in `PermissionError: [Errno 1] ... '.<host>.<random>.tmp' -> '<host>.json'`.
The temporary file is created fine; replacing the existing snapshot is refused (in iCloud
Drive the refusal comes from the privacy layer, which cannot ask a background process).
guard.log got a SWALLOWED line every ten minutes (1042 of them), the machine stopped
reporting, and the folder still held 23 conflict copies "<host> 2.json" .. "25.json" that
`fleet` listed as 23 more machines.

Here the refusal is reproduced with the user-immutable flag on the snapshot, which gives the
caller the same EPERM from os.replace while mkstemp in the folder keeps working.

  1. the failure is logged once per distinct cause, then at most once a day, SWALLOWED first
  2. a refused replace falls back to "<host>.fallback.json"; no temporary file is left behind
  3. the refused name is retried hourly, not every cycle; when it works again the fallback goes
  4. both names refused: nothing left behind, and no new temporary file until the next try
  5. fleet shows one row per machine: the "host" field (and serial) decide, the newest wins,
     and the folded files are counted, not hidden silently
  6. uninstall.sh removes this Mac's snapshot under both names (it looked for the network host
     name, which on the owner's Mac is not the name the guard publishes under)

Run with:  python3 tests/test_fleet_eperm_20261022.py
Isolated TG_BASE and, for uninstall.sh's snippet, a sandbox HOME; never writes to iCloud or the
real ~/.coffee-paladin.
"""
import re
import errno
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg-fleet-eperm-")
os.environ["TG_LANG"] = "en"
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_fleet_eperm", os.path.join(SRC, "guard.py"))
fleet = load_source("fleet_eperm", os.path.join(SRC, "fleet"))

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def lock(path, on):
    subprocess.run(["chflags", "uchg" if on else "nouchg", path], capture_output=True)


def tmps(d):
    return [n for n in os.listdir(d) if n.endswith(".tmp")]


def read(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return {}


class Clock:
    t = 2000000000.0

    def __call__(self):
        return self.t


clock = Clock()
host = g.hostname()
D = tempfile.mkdtemp(prefix="tg-fleet-eperm-dir-")
CFG = {"fleet_dir": D}
primary = os.path.join(D, "%s.json" % host)
fallback = os.path.join(D, "%s.fallback.json" % host)
lines = []
locked_files = []
try:
    with patch.object(g, "now", clock), patch.object(g, "log", side_effect=lambda m, tag=None: lines.append(m)):
        print("1. one line per cause, then at most one a day")
        g._SILENT_FAILURES.clear()
        real_replace = os.replace

        def no_space(src, dst):
            raise OSError(errno.ENOSPC, "No space left on device", src, None, dst)

        with patch.object(g.os, "replace", no_space):
            for _ in range(200):                # 200 cycles 7.5 s apart: 25 minutes
                g.fleet_write(CFG, {"chip_c": 60.0})
                clock.t += 7.5
        swallowed = [m for m in lines if "fleet_write" in m]
        test("200 failing cycles in 25 min log ONE line", len(swallowed) == 1, swallowed)
        test("...and it keeps the SWALLOWED marker", swallowed and swallowed[0].startswith("SWALLOWED in fleet_write"),
             swallowed[:1])
        test("...while every failure is still counted", g._SILENT_FAILURES.get("fleet_write") == 200,
             g._SILENT_FAILURES.get("fleet_write"))
        test("no temporary file is left after 200 failures", tmps(D) == [], tmps(D))
        clock.t += 86400
        with patch.object(g.os, "replace", no_space):
            g.fleet_write(CFG, {"chip_c": 60.0})
            g.fleet_write(CFG, {"chip_c": 60.0})
        test("a day later the same cause is logged once more", len([m for m in lines if "fleet_write" in m]) == 2,
             len([m for m in lines if "fleet_write" in m]))

        print("2. a refused replace falls back to a second name")
        g.fleet_write(CFG, {"chip_c": 61.0})
        test("a healthy write lands under <host>.json", read(primary).get("chip_c") == 61.0, read(primary))
        lock(primary, True)
        locked_files.append(primary)
        n_before = len(lines)
        clock.t += 60
        g.fleet_write(CFG, {"chip_c": 62.0})
        test("EPERM on <host>.json: the snapshot is published as <host>.fallback.json",
             read(fallback).get("chip_c") == 62.0, sorted(os.listdir(D)))
        test("the locked snapshot is left as it was", read(primary).get("chip_c") == 61.0, read(primary))
        test("no temporary file is left behind", tmps(D) == [], tmps(D))
        new = [m for m in lines[n_before:] if "fleet_write" in m]
        test("the refusal is a NEW cause, so it is logged at once", len(new) == 1 and "PermissionError" in new[0], new)

        print("3. the refused name is retried hourly, then the fallback goes")
        targets = []

        def spy(src, dst):
            targets.append(os.path.basename(dst))
            return real_replace(src, dst)

        with patch.object(g.os, "replace", spy):
            for i in range(10):
                clock.t += 60
                g.fleet_write(CFG, {"chip_c": 63.0 + i})
        test("within the hour <host>.json is not touched again", host + ".json" not in targets, targets)
        test("...and the fallback keeps the fresh data", read(fallback).get("chip_c") == 72.0, read(fallback))
        test("still no temporary file", tmps(D) == [], tmps(D))
        n_before = len(lines)
        clock.t += 3600
        g.fleet_write(CFG, {"chip_c": 73.0})
        test("an hour later it is tried again; still refused -> fallback, and no new log line",
             read(fallback).get("chip_c") == 73.0 and not [m for m in lines[n_before:] if "fleet_write" in m],
             (read(fallback), lines[n_before:]))
        lock(primary, False)
        clock.t += 3601
        g.fleet_write(CFG, {"chip_c": 74.0})
        test("once the file can be replaced again, <host>.json gets the snapshot", read(primary).get("chip_c") == 74.0,
             read(primary))
        test("...and the fallback is removed", not os.path.exists(fallback), sorted(os.listdir(D)))

        print("4. both names refused")
        lock(primary, True)
        open(fallback, "w").write('{"chip_c": 1.0}')
        lock(fallback, True)
        locked_files.append(fallback)
        clock.t += 3601
        g._SILENT_FAILURES.clear()
        g.fleet_write(CFG, {"chip_c": 75.0})
        test("nothing published, nothing left behind", tmps(D) == [] and read(primary).get("chip_c") == 74.0
             and read(fallback).get("chip_c") == 1.0, (tmps(D), read(primary), read(fallback)))
        test("the failure is recorded", g._SILENT_FAILURES.get("fleet_write", 0) >= 1, dict(g._SILENT_FAILURES))
        created = []
        real_mkstemp = g.tempfile.mkstemp
        with patch.object(g.tempfile, "mkstemp", side_effect=lambda **kw: created.append(1) or real_mkstemp(**kw)):
            clock.t += 60
            g.fleet_write(CFG, {"chip_c": 76.0})
        test("with both names refused the next cycles do not even create a temporary file", created == [], created)
finally:
    for p in locked_files:
        lock(p, False)

print("5. fleet: one row per machine")
F = tempfile.mkdtemp(prefix="tg-fleet-eperm-read-")
now = time.time()


def snap(name, hostname, age_s, serial=None, chip=50.0):
    d = {"host": hostname, "epoch": now - age_s, "chip_c": chip, "level": 0}
    if serial:
        d["serial"] = serial
    with open(os.path.join(F, name), "w") as f:
        json.dump(d, f)


snap("Pawel_s MacBook Pro.json", "MacbookPro", 27 * 86400, "S1", chip=40.0)
snap("Pawel_s MacBook Pro 2.json", "MacbookPro", 35 * 86400, "S1")
snap("Pawel_s MacBook Pro 17.json", "MacbookPro", 34 * 86400, "S1")
snap("Pawel_s MacBook Pro.fallback.json", "MacbookPro", 30, "S1", chip=77.0)
snap("Neo.json", "macbook-neo", 6 * 86400, "S2", chip=55.0)
snap("Pawe__s MacBook.json", "macbook-neo", 16 * 86400, "S2")
snap("Twin-a.json", "Studio", 20, "SA")
snap("Twin-b.json", "Studio", 25, "SB")
with open(os.path.join(F, "broken.json"), "w") as f:
    f.write("{not json")
open(os.path.join(F, "evicted.json.icloud"), "w").close()
hosts = fleet.load_hosts(F)
names = sorted(h["host"] for h in hosts)
test("10 files, 6 rows: copies folded by the host field, not the file name", len(hosts) == 6, names)
mbp = [h for h in hosts if h["host"] == "MacbookPro"]
test("the newest MacbookPro snapshot wins (the fallback, 30 s old)",
     len(mbp) == 1 and mbp[0].get("chip_c") == 77.0 and mbp[0]["_age"] < 120, mbp)
neo = [h for h in hosts if h["host"] == "macbook-neo"]
test("a renamed file of the same Mac is folded too, newest kept", len(neo) == 1 and neo[0].get("chip_c") == 55.0, neo)
test("two Macs that share a label but not a serial stay two rows",
     len([h for h in hosts if h["host"] == "Studio"]) == 2, names)
test("an unreadable file and an evicted one are still listed (they have no host field to fold by)",
     any(h.get("_bad") for h in hosts) and any(h["host"] == "evicted" for h in hosts), names)
test("the kept rows say how many files were folded into them",
     mbp and mbp[0].get("_duplicates") == 3 and neo and neo[0].get("_duplicates") == 1,
     [(h["host"], h.get("_duplicates")) for h in hosts])
buf = io.StringIO()
with redirect_stdout(buf):
    fleet.render(F)
out = buf.getvalue()
test("the table counts 6 machines", "FLEET: 6 machine(s)" in out, out[:200])
test("and says that 4 older snapshot files are not shown", "4 older snapshot file(s)" in out, out[-400:])

print("6. uninstall.sh removes this Mac's snapshot under both names")
script = open(os.path.join(SRC, "uninstall.sh"), encoding="utf-8").read()
blocks = [b for b in re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", script, re.S) if "fleet_dir" in b]
home = tempfile.mkdtemp(prefix="tg-fleet-eperm-home-")
U = tempfile.mkdtemp(prefix="tg-fleet-eperm-uninst-")
os.makedirs(os.path.join(home, ".coffee-paladin"))
json.dump({"fleet_dir": U}, open(os.path.join(home, ".coffee-paladin", "config.json"), "w"))
for n in (host + ".json", host + ".fallback.json", host + " 2.json", "Other Mac.json"):
    open(os.path.join(U, n), "w").write("{}")
r = subprocess.run(["/usr/bin/python3", "-"], input=blocks[0] if blocks else "", text=True,
                   capture_output=True, env=dict(os.environ, HOME=home), timeout=30)
left = sorted(os.listdir(U))
test("the snippet is found in uninstall.sh", len(blocks) == 1, len(blocks))
test("<host>.json and <host>.fallback.json are removed", host + ".json" not in left and
     host + ".fallback.json" not in left, (left, r.stderr[-200:]))
test("a conflict copy and another Mac's snapshot are left alone (no deleting by pattern)",
     host + " 2.json" in left and "Other Mac.json" in left, left)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
