#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wiring the thermal gate into Cursor (integrations/cursor/hooks_wire.py), 23.10, experimental.

~/.cursor/hooks.json is shared with the user's own hooks, so the contract is the Codex one: no
~/.cursor means skip (never create it); a missing hooks.json is created with version 1 and our
one beforeShellExecution entry; a file that is not a JSON object is never "repaired" (skip, not
a byte changed); a schema we do not know (no version 1, hooks not an object, the event not a
list) is "foreign" and left alone; our entry is appended after the user's, every write leaves a
timestamped backup, wiring is idempotent, unwire removes exactly ours and the events we
emptied, and version stays. 23.10: "ours" is exactly our command under beforeShellExecution; a
stranger's entry that only mentions "coffee-paladin hook-gate", there or under another event, is
theirs. End to end, the command from the file, run through sh -c with a
beforeShellExecution payload, denies a bare encoder with Cursor's JSON and exit 0, and exits 0
with an empty stdout when the binary is gone.

Run with:  python3 tests/test_cursor_wire.py
Everything runs against sandbox HOMEs and a temporary TG_BASE; the real ones are never touched.
"""
import glob
import json
import os
import stat
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIRE = os.path.join(SRC, "integrations", "cursor", "hooks_wire.py")
HEAVY = "ffmpeg -i a.mov -c:v libx265 b.mp4"

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % (detail,)))
    passed += bool(condition)


def env_for(home, **extra):
    env = dict(os.environ, HOME=home)
    for k in ("PALADIN_HOOK", "GROK_HOOK_EVENT", "CURSOR_VERSION"):
        env.pop(k, None)
    env.update(extra)
    return env


def run(home, *args):
    return subprocess.run([sys.executable, WIRE] + list(args), env=env_for(home),
                          capture_output=True, text=True, timeout=30)


def backups(path):
    return glob.glob(path + ".coffee-paladin.*.bak")


if not os.path.exists(WIRE):
    test("the Cursor adapter exists", False, WIRE)
    print("\nRESULT: %d/%d" % (passed, total))
    sys.exit(1)

print("=== no Cursor on this machine ===")
home = tempfile.mkdtemp(prefix="tg-cursorwire-")
r = run(home, "hook")
test("1. no ~/.cursor: skip, and the tree is NOT created",
     r.stdout.strip() == "skip" and not os.path.exists(os.path.join(home, ".cursor")), repr(r.stdout))

print("=== a fresh hooks.json ===")
os.makedirs(os.path.join(home, ".cursor"))
path = os.path.join(home, ".cursor", "hooks.json")
binary = os.path.join(home, ".local", "bin", "coffee-paladin")
ours = {"command": binary + " hook-gate || true", "timeout": 10}
r = run(home, "hook")
data = json.load(open(path))
test("2. created with version 1 and exactly our beforeShellExecution entry",
     r.stdout.strip() == "ok" and data == {"version": 1, "hooks": {"beforeShellExecution": [ours]}},
     repr(data))
test("3. no matcher and no failClosed in our entry", "matcher" not in data["hooks"]["beforeShellExecution"][0]
     and "failClosed" not in data["hooks"]["beforeShellExecution"][0])
test("4. a new file is private (0600)", stat.S_IMODE(os.stat(path).st_mode) == 0o600,
     oct(stat.S_IMODE(os.stat(path).st_mode)))
r = run(home, "unhook")
data = json.load(open(path))
test("5. unhook leaves version and drops the event we emptied",
     r.stdout.strip() == "ok" and data == {"version": 1, "hooks": {}}, repr(data))

print("=== a stranger's hooks.json ===")
home = tempfile.mkdtemp(prefix="tg-cursorwire-")
os.makedirs(os.path.join(home, ".cursor"))
path = os.path.join(home, ".cursor", "hooks.json")
binary = os.path.join(home, ".local", "bin", "coffee-paladin")
ours = {"command": binary + " hook-gate || true", "timeout": 10}
theirs_edit = {"command": "./hooks/format.sh"}
theirs_shell = {"command": "./scripts/approve-network.sh", "timeout": 30, "matcher": "curl|wget|nc "}
foreign = {"version": 1, "hooks": {"afterFileEdit": [theirs_edit], "beforeShellExecution": [theirs_shell]}}
open(path, "w").write(json.dumps(foreign))
os.chmod(path, 0o644)
original = open(path).read()
r = run(home, "hook")
data = json.load(open(path))
test("6. our entry is APPENDED after the stranger's, their afterFileEdit untouched",
     r.stdout.strip() == "ok" and data["hooks"]["beforeShellExecution"] == [theirs_shell, ours]
     and data["hooks"]["afterFileEdit"] == [theirs_edit] and data["version"] == 1, repr(data))
found = backups(path)
test("7. a backup holds the file as it was, byte for byte",
     len(found) == 1 and open(found[0]).read() == original, found)
test("8. the file keeps its mode", stat.S_IMODE(os.stat(path).st_mode) == 0o644,
     oct(stat.S_IMODE(os.stat(path).st_mode)))
before = open(path).read()
r = run(home, "hook")
test("9. wiring twice is idempotent: no rewrite, no new backup",
     r.stdout.strip() == "ok" and open(path).read() == before and len(backups(path)) == 1)

print("=== end to end: the command Cursor would run ===")
base = tempfile.mkdtemp(prefix="tg-cursorwire-base-")
json.dump({}, open(os.path.join(base, "config.json"), "w"))
payload = {"conversation_id": "c-1", "generation_id": "g-1", "hook_event_name": "beforeShellExecution",
           "cursor_version": "3.27.6", "workspace_roots": ["/project"], "user_email": None,
           "transcript_path": None, "command": HEAVY, "cwd": "/project", "sandbox": False}


def hook(payload):
    command = json.load(open(path))["hooks"]["beforeShellExecution"][-1]["command"]
    return subprocess.run(["/bin/sh", "-c", command], input=json.dumps(payload),
                          env=env_for(home, TG_BASE=base, TG_LANG="en"),
                          capture_output=True, text=True, timeout=30)


r = hook(payload)
test("10. without the binary: exit 0 and an empty stdout, the same answer as an allow (whether"
     " Cursor reads it as one is open until a live pilot)", r.returncode == 0 and r.stdout == "",
     (r.returncode, r.stdout[:120]))
os.makedirs(os.path.dirname(binary))
os.symlink(os.path.join(SRC, "guard.py"), binary)
r = hook(payload)
try:
    answer = json.loads(r.stdout)
except ValueError:
    answer = {}
test("11. a bare encoder: exit 0 and Cursor's JSON deny with the safe-run hint for the agent",
     r.returncode == 0 and answer.get("permission") == "deny"
     and "safe-run -- " in answer.get("agent_message", ""), (r.returncode, r.stdout[:200]))
r = hook(dict(payload, command="git status"))
test("12. a light command: exit 0, stdout empty", r.returncode == 0 and r.stdout == "",
     (r.returncode, r.stdout[:120]))

print("=== unwiring ===")
r = run(home, "unhook")
data = json.load(open(path))
test("13. unhook removes exactly ours, the stranger's entries and version survive",
     r.stdout.strip() == "ok" and data == foreign, repr(data))
r = run(home, "unhook")
test("14. nothing of ours left: none", r.stdout.strip() == "none")

print("=== files that are not ours to fix ===")
home = tempfile.mkdtemp(prefix="tg-cursorwire-")
os.makedirs(os.path.join(home, ".cursor"))
path = os.path.join(home, ".cursor", "hooks.json")
cases = [("15. not JSON at all: skip", "{broken", "skip"),
         ("16. a JSON array: skip", "[1, 2]", "skip"),
         ("17. JSON null: skip", "null", "skip"),
         ("18. no version: foreign", json.dumps({"hooks": {"beforeShellExecution": []}}), "foreign"),
         ("19. version 2: foreign", json.dumps({"version": 2, "hooks": {}}), "foreign"),
         ("20. hooks is not an object: foreign", json.dumps({"version": 1, "hooks": []}), "foreign"),
         ("21. beforeShellExecution is not a list: foreign",
          json.dumps({"version": 1, "hooks": {"beforeShellExecution": {"command": "x"}}}), "foreign")]
for name, body, word in cases:
    open(path, "w").write(body)
    r = run(home, "hook")
    test(name + ", not a byte changed, no backup",
         r.stdout.strip() == word and open(path).read() == body and not backups(path),
         (r.stdout, open(path).read()[:80]))

print("=== a home with a space in it ===")
spaced = os.path.join(tempfile.mkdtemp(prefix="tg-cursorwire-"), "Jan Kowalski")
os.makedirs(os.path.join(spaced, ".cursor"))
r = subprocess.run([sys.executable, WIRE, "hook"], env=env_for(spaced), capture_output=True, text=True,
                   timeout=30)
r = subprocess.run([sys.executable, WIRE, "hook"], env=env_for(spaced), capture_output=True, text=True,
                   timeout=30)
data = json.load(open(os.path.join(spaced, ".cursor", "hooks.json")))
test("22. a quoted path is still recognised as ours: one entry after two wirings",
     r.stdout.strip() == "ok" and len(data["hooks"]["beforeShellExecution"]) == 1
     and data["hooks"]["beforeShellExecution"][0]["command"].startswith("'"), repr(data))
r = subprocess.run([sys.executable, WIRE, "unhook"], env=env_for(spaced), capture_output=True, text=True,
                   timeout=30)
data = json.load(open(os.path.join(spaced, ".cursor", "hooks.json")))
test("23. ...and unhook finds it", r.stdout.strip() == "ok" and data["hooks"] == {}, repr(data))

print("=== a stranger's entry that mentions the gate ===")
home = tempfile.mkdtemp(prefix="tg-cursorwire-")
os.makedirs(os.path.join(home, ".cursor"))
path = os.path.join(home, ".cursor", "hooks.json")
ours = {"command": os.path.join(home, ".local", "bin", "coffee-paladin") + " hook-gate || true",
        "timeout": 10}
wrapper = {"command": "./hooks/audit.sh --then coffee-paladin hook-gate", "timeout": 20}
logger = {"command": "echo coffee-paladin hook-gate >> ~/hook.log"}
mentions = {"version": 1, "hooks": {"beforeShellExecution": [wrapper], "afterShellExecution": [logger]}}
open(path, "w").write(json.dumps(mentions))
r = run(home, "hook")
data = json.load(open(path))
test("24. a stranger's wrapper that mentions the gate is not taken for ours: ours is appended",
     r.stdout.strip() == "ok" and data["hooks"]["beforeShellExecution"] == [wrapper, ours], repr(data))
r = run(home, "unhook")
data = json.load(open(path))
test("25. unhook removes ours only: the wrapper and the other event's entry stay",
     r.stdout.strip() == "ok" and data == mentions, repr(data))
r = run(home, "unhook")
test("26. ...and a second unhook finds nothing of ours", r.stdout.strip() == "none"
     and json.load(open(path)) == mentions, r.stdout)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
