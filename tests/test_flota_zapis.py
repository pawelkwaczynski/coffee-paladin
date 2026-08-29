#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One unwritable temporary file must not stop a machine from reporting for ever.

Observed on a live Mac, 29.08.2026. `fleet_write` wrote through a fixed temporary name,
`.<host>.tmp`, in an iCloud Drive folder. One rename failed and left that file behind; the
leftover picked up a `com.apple.macl` entry, after which the daemon got EPERM on both
`open()` and `unlink()` of that exact path. Every publish for the next 35 minutes then
failed on the same file, and nothing said so: `status.json` was refreshed every three
seconds, the daemon was healthy by every other measure, and only the fleet table said "not
reporting" - with no way to tell which of the two was lying.

Two independent defects, so two independent guarantees, because either alone still fails:
  - a unique temporary name per write, so a stuck file cannot be inherited by the next one;
  - the failure is recorded through `silent_failure`, so it stops being invisible.

Cases:
  1. normal write -> snapshot published
  2. an immutable leftover blocking the OLD fixed name -> publish still succeeds
  3. ...and the leftover is not silently swallowed into the published snapshot
  4. a write failure is recorded in _SILENT_FAILURES, not discarded
  5. countercase: a healthy write records NO failure (or the check above proves nothing)
  6. leftovers older than an hour are swept; fresh ones and unremovable ones are left alone

Run with:  python3 tests/test_flota_zapis.py
Does not touch the real ~/.coffee-paladin and never writes to iCloud.
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-flota-zapis-")
os.environ["TG_BASE"] = BASE
FLEET = os.path.join(BASE, "flota")
os.makedirs(FLEET)

results = []


def test(name, condition, detail=""):
    results.append(bool(condition))
    print("%s %s%s" % ("[OK]  " if condition else "[FAIL]", name,
                       ("  <- " + detail) if (detail and not condition) else ""))


loader = importlib.machinery.SourceFileLoader("g_flota", os.path.join(SRC, "guard.py"))
spec = importlib.util.spec_from_loader("g_flota", loader)
g = importlib.util.module_from_spec(spec)
loader.exec_module(g)

CFG = {"fleet_dir": FLEET}
SNAP = {"chip_c": 70.0, "level": 0}
published = os.path.join(FLEET, "%s.json" % g.hostname())


def immutable(path, on):
    """macOS user-immutable flag: the closest reproduction of the observed EPERM."""
    subprocess.run(["chflags", "uchg" if on else "nouchg", path], capture_output=True)


# ---------------------------------------------------------------- 1
g._SILENT_FAILURES.clear()
g.fleet_write(CFG, SNAP)
test("1. a normal write publishes the snapshot", os.path.exists(published))
first = json.load(open(published)) if os.path.exists(published) else {}

# ---------------------------------------------------------------- 5 (before 4 dirties it)
test("5. countercase: a healthy write records no failure",
     "fleet_write" not in g._SILENT_FAILURES,
     "failures=%r" % (dict(g._SILENT_FAILURES),))

# ---------------------------------------------------------------- 2, 3
# Exactly the file the old code would have reused, made unwritable the way iCloud made it.
stuck = os.path.join(FLEET, ".%s.tmp" % g.hostname())
with open(stuck, "w") as f:
    json.dump({"stale": True, "serial": "SHOULD-NOT-BE-PUBLISHED"}, f)
immutable(stuck, True)

os.unlink(published)
g._SILENT_FAILURES.clear()
try:
    g.fleet_write(CFG, {"chip_c": 81.0, "level": 1})
    ok2 = os.path.exists(published)
    detail2 = ""
except Exception as e:                       # the guard must never be taken down by this
    ok2, detail2 = False, "wyjatek: %r" % (e,)
test("2. a blocked leftover does not stop the machine from reporting", ok2, detail2)

if ok2:
    got = json.load(open(published))
    test("3. and the published snapshot is the new one, not the stuck file",
         got.get("chip_c") == 81.0 and got.get("serial") != "SHOULD-NOT-BE-PUBLISHED",
         "chip_c=%r serial=%r" % (got.get("chip_c"), got.get("serial")))
else:
    test("3. and the published snapshot is the new one, not the stuck file", False,
         "nie opublikowano niczego")

# ---------------------------------------------------------------- 4
# A folder that cannot be written to at all: the failure must be recorded, not discarded.
blocked = os.path.join(BASE, "flota-zablokowana")
os.makedirs(blocked)
os.chmod(blocked, 0o500)                     # readable, not writable
g._SILENT_FAILURES.clear()
try:
    g.fleet_write({"fleet_dir": blocked}, SNAP)
    survived = True
except Exception as e:
    survived = False
    print("   (fleet_write podnioslo wyjatek: %r)" % (e,))
test("4. a write failure is recorded instead of vanishing",
     survived and g._SILENT_FAILURES.get("fleet_write", 0) >= 1,
     "survived=%s failures=%r" % (survived, dict(g._SILENT_FAILURES)))
os.chmod(blocked, 0o700)

# ---------------------------------------------------------------- 6
old_tmp = os.path.join(FLEET, ".ancient-host.tmp")
with open(old_tmp, "w") as f:
    f.write("{}")
os.utime(old_tmp, (time.time() - 7200, time.time() - 7200))
fresh_tmp = os.path.join(FLEET, ".fresh-host.tmp")
with open(fresh_tmp, "w") as f:
    f.write("{}")
g._fleet_sweep_tmp(FLEET)
test("6. an hour-old leftover is swept, a fresh one survives",
     not os.path.exists(old_tmp) and os.path.exists(fresh_tmp),
     "stary istnieje=%s swiezy istnieje=%s" % (os.path.exists(old_tmp),
                                               os.path.exists(fresh_tmp)))
test("6b. an unremovable leftover is left alone rather than crashing the sweep",
     os.path.exists(stuck))

# ---------------------------------------------------------------- exit
immutable(stuck, False)
shutil.rmtree(BASE, ignore_errors=True)
print("\n%d/%d passed" % (results.count(True), len(results)))
sys.exit(1 if results.count(False) else 0)
