#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure paladin data is not readable by other accounts on this Mac.

The data directory used to be created as 0755 and `config.json` as 0644. On a Mac
with multiple accounts, any local user could read `ntfy_topic`, the only protection
for notifications: anyone who knows the topic can read alerts and send fake ones.
`managed/` also contains full job command lines, including project paths and file names.

Run with:  python3 tests/test_uprawnienia.py
Works in a temporary directory and does not touch the real ~/.coffee-paladin.
"""
import importlib.machinery
import json
import os
import shutil
import stat
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


def prawa(p):
    return stat.S_IMODE(os.stat(p).st_mode)


print("data directory permissions")

shutil.rmtree(BASE, ignore_errors=True)
g.ensure_dirs()
test("fresh data directory: 0700", prawa(BASE) == 0o700, oct(prawa(BASE)))
test("fresh managed/: 0700", prawa(g.MANAGED_DIR) == 0o700, oct(prawa(g.MANAGED_DIR)))

# Existing installs with bad permissions must be tightened on startup.
os.chmod(BASE, 0o755)
os.chmod(g.MANAGED_DIR, 0o755)
json.dump({"ntfy_topic": "sekret-123"}, open(g.CFG_PATH, "w"))
os.chmod(g.CFG_PATH, 0o644)
g.ensure_dirs()
test("old install: directory tightened to 0700", prawa(BASE) == 0o700, oct(prawa(BASE)))
test("old install: config tightened to 0600", prawa(g.CFG_PATH) == 0o600, oct(prawa(g.CFG_PATH)))
test("config remains readable by owner after permission change",
     json.load(open(g.CFG_PATH)).get("ntfy_topic") == "sekret-123")

for path, description in ((BASE, "katalog"), (g.CFG_PATH, "config.json")):
    test("%s: no permissions for group or others" % description, not (prawa(path) & 0o077),
         oct(prawa(path)))

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
