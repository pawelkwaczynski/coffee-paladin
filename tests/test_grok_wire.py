#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wiring the thermal gate into Grok Build (integrations/grok/hooks_wire.py).

Contract under test: the paladin owns exactly ONE file in ~/.grok/hooks and
never touches anything else there; no ~/.grok means skip (never create a
config tree the user does not have); wiring is idempotent; unwiring removes
only our file and leaves a stranger's hooks byte for byte.

Run with:  python3 tests/test_grok_wire.py
Everything runs against a sandbox HOME; the real one is never touched.
"""
import json
import os
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIRE = os.path.join(SRC, "integrations", "grok", "hooks_wire.py")

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def run(home, *args):
    return subprocess.run([sys.executable, WIRE] + list(args),
                          env=dict(os.environ, HOME=home),
                          capture_output=True, text=True, timeout=30)


print("=== no Grok on this machine ===")
home = tempfile.mkdtemp(prefix="tg-grokwire-")
r = run(home, "hook")
test("1. no ~/.grok: skip, and the tree is NOT created",
     r.stdout.strip() == "skip" and not os.path.exists(os.path.join(home, ".grok")),
     repr(r.stdout))

print("=== wiring ===")
os.makedirs(os.path.join(home, ".grok"))
r = run(home, "hook")
own = os.path.join(home, ".grok", "hooks", "coffee-paladin.json")
data = json.load(open(own))
groups = data["hooks"]["PreToolUse"]
inner = groups[0]["hooks"][0]
test("2. wire writes our file with the verified shape",
     r.stdout.strip() == "ok" and groups[0]["matcher"] == "Bash"
     and inner["type"] == "command" and inner["command"].endswith("coffee-paladin hook-gate")
     and inner["timeout"] == 10, repr(data))
test("3. the command path is absolute (Grok does not promise tilde expansion)",
     inner["command"].startswith("/"), repr(inner["command"]))
before = open(own).read()
r = run(home, "hook")
test("4. wiring twice is idempotent", r.stdout.strip() == "ok" and open(own).read() == before)
open(own, "w").write("{broken")
r = run(home, "hook")
test("5. our own corrupted file is rewritten, not obeyed",
     r.stdout.strip() == "ok" and bool(json.load(open(own)).get("hooks")),
     repr(open(own).read()[:60]))

print("=== a stranger's hooks are sacred ===")
foreign = os.path.join(home, ".grok", "hooks", "somebody-else.json")
foreign_body = '{"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}'
open(foreign, "w").write(foreign_body)
r = run(home, "unhook")
test("6. unhook removes only our file",
     r.stdout.strip() == "ok" and not os.path.exists(own)
     and open(foreign).read() == foreign_body)
r = run(home, "unhook")
test("7. unhook with nothing of ours: none", r.stdout.strip() == "none")
test("8. ...and the stranger still survives", open(foreign).read() == foreign_body)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
