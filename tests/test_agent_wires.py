#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wiring the thermal gate into Codex CLI, Gemini CLI and Antigravity.

One contract, three dialects. Under test for every adapter: absence of the
host's config tree means skip (never create it), wiring is idempotent, a
stranger's entries survive wire AND unwire untouched (the file is re-serialised
when ours is appended, so the guarantee is semantic, not byte-level), every
write leaves a timestamped backup, and unwire removes exactly ours. Plus the per-host
traps: Gemini's timeout is in MILLISECONDS and its event is BeforeTool;
Antigravity nests everything under a named top-level key; Codex needs the
^Bash$ regex matcher.

Run with:  python3 tests/test_agent_wires.py
Everything runs against sandbox HOMEs; the real one is never touched.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def run(agent, home, *args):
    wire = os.path.join(SRC, "integrations", agent, "hooks_wire.py")
    env = dict(os.environ, HOME=home)
    env.pop("PATH", None)       # gemini's which() probe must not see a real binary
    env["PATH"] = "/usr/bin:/bin"
    return subprocess.run([sys.executable, wire] + list(args), env=env,
                          capture_output=True, text=True, timeout=30)


print("=== Codex CLI (~/.codex/hooks.json, shared file) ===")
home = tempfile.mkdtemp(prefix="tg-codexwire-")
r = run("codex", home, "hook")
test("1. no ~/.codex: skip, tree not created",
     r.stdout.strip() == "skip" and not os.path.exists(os.path.join(home, ".codex")))
os.makedirs(os.path.join(home, ".codex"))
hooks_path = os.path.join(home, ".codex", "hooks.json")
foreign_entry = {"matcher": ".*", "hooks": [{"type": "command", "command": "echo mine"}]}
json.dump({"hooks": {"PreToolUse": [foreign_entry]}}, open(hooks_path, "w"))
r = run("codex", home, "hook")
data = json.load(open(hooks_path))
pre = data["hooks"]["PreToolUse"]
test("2. our entry is APPENDED after the stranger's, with the verified shape",
     r.stdout.strip() == "ok" and len(pre) == 2 and pre[0] == foreign_entry
     and pre[1]["matcher"] == "^Bash$"
     and pre[1]["hooks"][0]["command"].endswith("coffee-paladin hook-gate")
     and pre[1]["hooks"][0]["timeout"] == 10, repr(pre))
test("3. a backup was written", bool(glob.glob(hooks_path + ".coffee-paladin.*.bak")))
before = open(hooks_path).read()
r = run("codex", home, "hook")
test("4. wiring twice is idempotent", r.stdout.strip() == "ok"
     and open(hooks_path).read() == before)
r = run("codex", home, "unhook")
data = json.load(open(hooks_path))
test("5. unhook removes exactly ours, the stranger survives",
     r.stdout.strip() == "ok" and data["hooks"]["PreToolUse"] == [foreign_entry])
open(hooks_path, "w").write("{broken")
r = run("codex", home, "hook")
test("6. corrupt hooks.json is never 'repaired'",
     r.stdout.strip() == "skip" and open(hooks_path).read() == "{broken")

print("=== Gemini CLI (~/.gemini/settings.json, BeforeTool, ms timeout) ===")
home = tempfile.mkdtemp(prefix="tg-gemwire-")
os.makedirs(os.path.join(home, ".gemini"))
r = run("gemini", home, "hook")
test("7. ~/.gemini without settings.json or a gemini binary = Antigravity's dir: skip",
     r.stdout.strip() == "skip"
     and not os.path.exists(os.path.join(home, ".gemini", "settings.json")))
settings_path = os.path.join(home, ".gemini", "settings.json")
json.dump({"theme": "dark"}, open(settings_path, "w"))
r = run("gemini", home, "hook")
data = json.load(open(settings_path))
group = data["hooks"]["BeforeTool"][0]
test("8. wired under BeforeTool with matcher run_shell_command",
     r.stdout.strip() == "ok" and group["matcher"] == "run_shell_command"
     and group["hooks"][0]["command"].endswith("coffee-paladin hook-gate"),
     repr(data))
test("9. the timeout is in MILLISECONDS (10 would kill the gate instantly)",
     group["hooks"][0]["timeout"] >= 1000, repr(group["hooks"][0]))
test("10. the user's other settings survive", data.get("theme") == "dark")
before = open(settings_path).read()
r = run("gemini", home, "hook")
test("11. idempotent", r.stdout.strip() == "ok" and open(settings_path).read() == before)
r = run("gemini", home, "unhook")
data = json.load(open(settings_path))
test("12. unhook leaves settings.json without our hook but with the theme",
     r.stdout.strip() == "ok" and "hooks" not in data and data.get("theme") == "dark")

print("=== Antigravity (~/.gemini/config/hooks.json, named keys) ===")
home = tempfile.mkdtemp(prefix="tg-agwire-")
r = run("antigravity", home, "hook")
test("13. no ~/.gemini/config: skip, tree not created",
     r.stdout.strip() == "skip" and not os.path.exists(os.path.join(home, ".gemini")))
os.makedirs(os.path.join(home, ".gemini", "config"))
ag_path = os.path.join(home, ".gemini", "config", "hooks.json")
foreign = {"users-own-hook": {"PostToolUse": [{"hooks": [
    {"type": "command", "command": "echo mine"}]}]}}
json.dump(foreign, open(ag_path, "w"))
r = run("antigravity", home, "hook")
data = json.load(open(ag_path))
test("14. our named key is added, matcher run_command",
     r.stdout.strip() == "ok" and "coffee-paladin-gate" in data
     and data["coffee-paladin-gate"]["PreToolUse"][0]["matcher"] == "run_command"
     and data["users-own-hook"] == foreign["users-own-hook"], repr(data))
before = open(ag_path).read()
r = run("antigravity", home, "hook")
test("15. idempotent", r.stdout.strip() == "ok" and open(ag_path).read() == before)
r = run("antigravity", home, "unhook")
data = json.load(open(ag_path))
test("16. unhook deletes exactly our key",
     r.stdout.strip() == "ok" and "coffee-paladin-gate" not in data
     and data["users-own-hook"] == foreign["users-own-hook"])
r = run("antigravity", home, "unhook")
test("17. nothing of ours left: none", r.stdout.strip() == "none")

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
