#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wiring the pre-exec gate into Claude Code's hooks section.

The hooks section is a hand-curated LIST, so the contract differs from the
statusLine key: our single entry is APPENDED, recognised later by its command
string, and every foreign entry - including other PreToolUse groups and whole
other event sections - survives wire and unwire with its content intact. A
dangling entry (script gone, hook stays) or a clobbered foreign hook are both
field failures we already paid for once.

Run with:  python3 tests/test_hook_wire.py
Runs against a sandbox HOME; the real one is never touched.
"""
import json
import os
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIRE = os.path.join(SRC, "integrations", "claude-code", "settings_wire.py")

HOME2 = tempfile.mkdtemp(prefix="tg-hookwire-")
ENV = dict(os.environ, HOME=HOME2)
SET = os.path.join(HOME2, ".claude", "settings.json")

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def wire(*args):
    return subprocess.run([sys.executable, WIRE, *args], env=ENV,
                          capture_output=True, text=True).stdout.strip()


def our_entries():
    s = json.load(open(SET))
    out = []
    for g in (s.get("hooks", {}).get("PreToolUse") or []):
        for h in g.get("hooks") or []:
            if "hook-gate" in str(h.get("command", "")):
                out.append(h)
    return out


test("1. no ~/.claude: hook wiring skips, nothing created",
     wire("hook") == "skip" and not os.path.isdir(os.path.join(HOME2, ".claude")))

os.makedirs(os.path.dirname(SET))
FOREIGN = {
    "model": "Fable",
    "hooks": {
        "PreToolUse": [{"matcher": "Write|Edit",
                        "hooks": [{"type": "command", "command": "/opt/mine/lint.sh"}]}],
        "PostToolUse": [{"matcher": "Bash",
                         "hooks": [{"type": "command", "command": "/opt/mine/audit.sh"}]}],
    },
}
json.dump(FOREIGN, open(SET, "w"), indent=2)
test("2. wiring appends our entry next to foreign hooks",
     wire("hook") == "ok" and len(our_entries()) == 1)
after = json.load(open(SET))
test("3. the foreign PreToolUse group survives with its content",
     after["hooks"]["PreToolUse"][0] == FOREIGN["hooks"]["PreToolUse"][0], str(after))
test("4. other event sections and keys are untouched",
     after["hooks"]["PostToolUse"] == FOREIGN["hooks"]["PostToolUse"]
     and after["model"] == "Fable")
test("5. wiring twice stays idempotent",
     wire("hook") == "ok" and len(our_entries()) == 1)
test("6. unhook removes only our entry",
     wire("unhook") == "ok" and len(our_entries()) == 0
     and json.load(open(SET))["hooks"]["PreToolUse"] == FOREIGN["hooks"]["PreToolUse"])
test("7. unhook again reports none", wire("unhook") == "none")

json.dump({"model": "Fable"}, open(SET, "w"))
test("8. wiring into settings with no hooks section creates just ours",
     wire("hook") == "ok" and len(our_entries()) == 1
     and json.load(open(SET))["model"] == "Fable")
test("9. ...and unhook removes the empty scaffolding it created",
     wire("unhook") == "ok" and "hooks" not in json.load(open(SET)))

json.dump({"hooks": "not a dict"}, open(SET, "w"))
test("10. an unrecognised hooks shape is refused, not repaired",
     wire("hook") == "foreign" and json.load(open(SET))["hooks"] == "not a dict")

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
