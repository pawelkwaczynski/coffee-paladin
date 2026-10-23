#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""install.sh wires Copilot CLI only where the `copilot` command exists; uninstall.sh unwires (23.10).

A ~/.copilot directory is left behind by the IDE extension, and VS Code reads ~/.copilot/hooks
through a harness of its own, so the directory is no proof that Copilot CLI is installed. The
install step must look for the command on PATH and never run it. The command is no proof either
(AWS Copilot CLI installs a `copilot` too), so it also takes a trace only GitHub's CLI leaves,
session-state/ or command-history-state/. An earlier unhook is a choice every later install keeps,
and uninstall.sh neither creates that choice nor forgets one the user made. A wiring that fails
is said out loud. Cursor's adapter is not part
of install.sh until it has been tried on a live Cursor; uninstall.sh still unwires both, since
a dangling entry would run a deleted binary at every tool call.

The install and uninstall snippets are cut out of the real scripts and run with bash against a
sandbox HOME and a made-up PATH: the scripts as a whole talk to launchctl and are never run here.

Run with:  python3 tests/test_install_copilot_20261023.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = open(os.path.join(SRC, "install.sh"), encoding="utf-8").read()
UNINSTALL = open(os.path.join(SRC, "uninstall.sh"), encoding="utf-8").read()
README = open(os.path.join(SRC, "README.md"), encoding="utf-8").read()
HEAVY = "ffmpeg -i a.mov -c:v libx265 b.mp4"

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % (detail,)))
    passed += bool(condition)


def sandbox(with_copilot_dir, with_command, with_session=False):
    home = tempfile.mkdtemp(prefix="tg-install-copilot-")
    base = os.path.join(home, ".coffee-paladin")
    os.makedirs(base)
    adapter = os.path.join(SRC, "integrations", "copilot", "hooks_wire.py")
    if os.path.exists(adapter):
        shutil.copy(adapter, os.path.join(base, "copilot_hooks_wire.py"))   # what the copy loop does
    if with_copilot_dir:
        os.makedirs(os.path.join(home, ".copilot", "ide"))
    if with_session:
        os.makedirs(os.path.join(home, ".copilot", "session-state"))
    fake_bin = os.path.join(home, "fake-bin")
    os.makedirs(fake_bin)
    marker = os.path.join(home, "copilot-was-run")
    if with_command:
        script = os.path.join(fake_bin, "copilot")
        open(script, "w").write("#!/bin/sh\ntouch '%s'\nexit 99\n" % marker)
        os.chmod(script, 0o755)
    env = {"HOME": home, "BASE": base, "PATH": fake_bin + ":/usr/bin:/bin", "LANG": "C"}
    return home, base, env, marker


def run_snippet(snippet, env):
    return subprocess.run(["/bin/bash", "-c", snippet], env=env, capture_output=True, text=True, timeout=60)


print("1. what install.sh copies")
loop = re.search(r"for AGENT_WIRE in ([^;\n]*); do\n", INSTALL)
copied = loop.group(1).split() if loop else []
test("the adapter copy loop includes copilot", "copilot" in copied, copied)
test("...and not cursor (not tried on a live Cursor yet)", "cursor" not in copied, copied)
test("install.sh never runs the Cursor adapter", "cursor_hooks_wire" not in INSTALL)

print("2. install.sh wires Copilot only when the command is on PATH")
block = re.search(r"\n(  if command -v copilot [^\n]*\n.*?\n  fi)\n", INSTALL, re.S)
snippet = block.group(1) if block else ""
test("the Copilot step is found in install.sh", bool(snippet), "no `if command -v copilot` block")
home, base, env, marker = sandbox(with_copilot_dir=True, with_command=False)
r = run_snippet(snippet, env)
test("an IDE-only ~/.copilot, no copilot on PATH: no hook file, nothing said",
     bool(snippet) and not os.path.exists(os.path.join(home, ".copilot", "hooks")) and r.stdout == "",
     (r.stdout, r.stderr[-200:]))
home, base, env, marker = sandbox(with_copilot_dir=True, with_command=True, with_session=True)
r = run_snippet(snippet, env)
own = os.path.join(home, ".copilot", "hooks", "coffee-paladin.json")
try:
    entry = json.load(open(own))["hooks"]["preToolUse"][0]
except (OSError, ValueError, KeyError, IndexError):
    entry = {}
test("copilot on PATH: our hook file is written and the installer says so",
     bool(snippet) and entry.get("bash", "").endswith("coffee-paladin hook-gate || true")
     and "Copilot CLI" in r.stdout, (r.stdout, r.stderr[-200:]))
test("...and copilot itself was never run", not os.path.exists(marker))
home, base, env, marker = sandbox(with_copilot_dir=False, with_command=True)
r = run_snippet(snippet, env)
test("copilot on PATH but no ~/.copilot yet: nothing created, the manual command is printed",
     bool(snippet) and not os.path.exists(os.path.join(home, ".copilot"))
     and "copilot_hooks_wire.py hook" in r.stdout, (r.stdout, r.stderr[-200:]))
home, base, env, marker = sandbox(with_copilot_dir=True, with_command=True)
r = run_snippet(snippet, env)
test("a copilot of another vendor next to an IDE-only ~/.copilot (no CLI session): not wired,"
     " the manual command is printed",
     bool(snippet) and not os.path.exists(os.path.join(home, ".copilot", "hooks"))
     and "copilot_hooks_wire.py hook" in r.stdout and not os.path.exists(marker), (r.stdout, r.stderr[-200:]))
home, base, env, marker = sandbox(with_copilot_dir=False, with_command=True)
elsewhere = os.path.join(home, "copilot-home")
os.makedirs(os.path.join(elsewhere, "command-history-state"))
r = run_snippet(snippet, dict(env, COPILOT_HOME=elsewhere))
test("COPILOT_HOME with a CLI trace: wired there, ~/.copilot not created",
     bool(snippet) and os.path.exists(os.path.join(elsewhere, "hooks", "coffee-paladin.json"))
     and not os.path.exists(os.path.join(home, ".copilot")), (r.stdout, r.stderr[-200:]))

print("2b. a choice made with unhook, and wirings that fail")
home, base, env, marker = sandbox(with_copilot_dir=True, with_command=True, with_session=True)
own = os.path.join(home, ".copilot", "hooks", "coffee-paladin.json")
run_snippet(snippet, env)
subprocess.run(["/usr/bin/python3", os.path.join(base, "copilot_hooks_wire.py"), "unhook"],
               env=env, capture_output=True, text=True, timeout=30)
gone = not os.path.exists(own)
r = run_snippet(snippet, env)
test("after unhook, the next install (a brew upgrade) does not wire it back, and says how to",
     bool(snippet) and gone and not os.path.exists(own) and "left off" in r.stdout
     and "copilot_hooks_wire.py hook" in r.stdout, (gone, r.stdout, r.stderr[-200:]))
home, base, env, marker = sandbox(with_copilot_dir=True, with_command=True, with_session=True)
own = os.path.join(home, ".copilot", "hooks", "coffee-paladin.json")
os.makedirs(os.path.dirname(own))
theirs = '{"version": 1, "hooks": {"sessionStart": [{"type": "command", "bash": "./mine.sh"}]}}'
open(own, "w").write(theirs)
r = run_snippet(snippet, env)
test("a coffee-paladin.json that is not ours: left byte for byte, and the installer says NOT wired",
     bool(snippet) and open(own).read() == theirs and "NOT wired" in r.stdout, (r.stdout, r.stderr[-200:]))
home, base, env, marker = sandbox(with_copilot_dir=True, with_command=True, with_session=True)
open(os.path.join(home, ".copilot", "hooks"), "w").write("a file where the directory should be")
r = run_snippet(snippet, env)
test("a wiring that fails is said out loud, with the command to run by hand",
     bool(snippet) and "NOT wired" in r.stdout and "copilot_hooks_wire.py hook" in r.stdout,
     (r.stdout, r.stderr[-200:]))

print("3. uninstall.sh unwires Copilot and a hand-wired Cursor")


def uninstall_snippet():
    """The adapter loop, with the lines around it that keep the user's Copilot choice."""
    loop = re.search(r"\nfor AGENT_WIRE in [^\n]*; do\n.*?\ndone\n", UNINSTALL, re.S)
    if not loop:
        return ""
    start, end = loop.start() + 1, loop.end()
    head = UNINSTALL.rfind("\nCOPILOT_OFF=", 0, start)
    if head != -1:
        start = head + 1
    tail = UNINSTALL.find('rm -f "$COPILOT_OFF"', end)
    if tail != -1 and UNINSTALL.count("\n", end, tail) == 0:
        end = UNINSTALL.find("\n", tail) + 1
    return UNINSTALL[start:end]


snippet = uninstall_snippet()
home = tempfile.mkdtemp(prefix="tg-uninstall-copilot-")
base = os.path.join(home, ".coffee-paladin")
os.makedirs(base)
os.makedirs(os.path.join(home, ".copilot"))
os.makedirs(os.path.join(home, ".cursor"))
env = {"HOME": home, "PATH": "/usr/bin:/bin", "LANG": "C"}
foreign_shell = {"command": "./scripts/approve-network.sh", "timeout": 30}
cursor_hooks = os.path.join(home, ".cursor", "hooks.json")
json.dump({"version": 1, "hooks": {"beforeShellExecution": [foreign_shell]}}, open(cursor_hooks, "w"))
for host in ("copilot", "cursor"):
    adapter = os.path.join(SRC, "integrations", host, "hooks_wire.py")
    if os.path.exists(adapter):
        shutil.copy(adapter, os.path.join(base, "%s_hooks_wire.py" % host))
        subprocess.run(["/usr/bin/python3", os.path.join(base, "%s_hooks_wire.py" % host), "hook"],
                       env=env, capture_output=True, text=True, timeout=30)
wired_copilot = os.path.exists(os.path.join(home, ".copilot", "hooks", "coffee-paladin.json"))
wired_cursor = len(json.load(open(cursor_hooks))["hooks"]["beforeShellExecution"]) == 2
test("the sandbox is wired in both hosts before uninstalling", wired_copilot and wired_cursor,
     (wired_copilot, wired_cursor))
r = run_snippet(snippet, env)
cursor_after = json.load(open(cursor_hooks))
test("uninstall's loop removes our Copilot hook file",
     bool(snippet) and not os.path.exists(os.path.join(home, ".copilot", "hooks", "coffee-paladin.json")),
     (r.stdout, r.stderr[-200:]))
test("...and our Cursor entry, leaving the user's own",
     bool(snippet) and cursor_after["hooks"]["beforeShellExecution"] == [foreign_shell], cursor_after)
test("...and says so for both", "removed from copilot" in r.stdout and "removed from cursor" in r.stdout,
     r.stdout)
test("...and leaves no 'switched off' choice behind: a reinstall wires Copilot again",
     bool(snippet) and not os.path.exists(os.path.join(base, "copilot_hook_off")),
     os.listdir(base))
open(os.path.join(base, "copilot_hook_off"), "w").close()
r = run_snippet(snippet, env)
test("a choice the user made before uninstalling stays", os.path.exists(os.path.join(base, "copilot_hook_off")),
     (r.stdout, r.stderr[-200:]))

print("4. the README says what install.sh does and no more")
section = README[README.find("**One gate for every agent host.**"):README.find("**Running an agent swarm?")]
section = " ".join(section.split())          # prose is wrapped at any word
test("the hook section names Copilot CLI and its wire command",
     "Copilot CLI" in section and "copilot_hooks_wire.py hook" in section)
cp_at = section.find('/share/coffee-paladin/integrations/cursor/hooks_wire.py" ~/.coffee-paladin/cursor_hooks_wire.py')
wire_at = section.find("cursor_hooks_wire.py hook")
test("Cursor is marked experimental, with the copy step (from the Homebrew share) before its wire command",
     "Cursor" in section and "experimental" in section and cp_at != -1 and wire_at != -1 and cp_at < wire_at,
     (cp_at, wire_at))
test("the README never says install.sh wires no hook", "wires no hook" not in " ".join(README.split()))
test("...and says how to switch the Copilot wiring off for good",
     "copilot_hooks_wire.py unhook switches it off for good" in section.replace("`", ""))
test("the section does not claim a live run", "not yet in a live session" in section
     and "not yet tried on a live Cursor" in section)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
