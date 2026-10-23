#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wiring the thermal gate into GitHub Copilot CLI (integrations/copilot/hooks_wire.py), 23.10.

Contract under test: the paladin owns exactly ONE file in the Copilot hooks directory
($COPILOT_HOME/hooks, by default ~/.copilot/hooks) and never touches anything else there;
no Copilot home means skip (never create a config tree the user does not have); the file has
the documented shape (version 1, camelCase preToolUse, matcher bash, timeoutSec in seconds);
wiring is idempotent; unwiring removes only our file. 23.10: a coffee-paladin.json holding
anything but exactly what the adapter writes (another shape, hand edits, not JSON at all) is
"foreign": wiring never replaces it and unwiring never removes it. unhook records the choice in
~/.coffee-paladin/copilot_hook_off for install.sh, hook by hand takes it back, and a file system
that says no ends in one word ("error", exit 1), not a traceback. End to end, the command written into
the file, run the way Copilot runs it (sh -c, payload on stdin), answers a bare encoder with
Copilot's JSON deny and exit 0, and exits 0 with an empty stdout when the binary is gone:
Copilot denies every tool call on a crashed preToolUse hook, so a missing gate must not crash.

Run with:  python3 tests/test_copilot_wire.py
Everything runs against a sandbox HOME and a temporary TG_BASE; the real ones are never touched.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIRE = os.path.join(SRC, "integrations", "copilot", "hooks_wire.py")
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
    for k in ("COPILOT_HOME", "PALADIN_HOOK", "GROK_HOOK_EVENT"):
        env.pop(k, None)
    env.update(extra)
    return env


def run(home, *args, **extra):
    return subprocess.run([sys.executable, WIRE] + list(args), env=env_for(home, **extra),
                          capture_output=True, text=True, timeout=30)


if not os.path.exists(WIRE):
    test("the Copilot adapter exists", False, WIRE)
    print("\nRESULT: %d/%d" % (passed, total))
    sys.exit(1)

print("=== no Copilot on this machine ===")
home = tempfile.mkdtemp(prefix="tg-copilotwire-")
r = run(home, "hook")
test("1. no ~/.copilot: skip, and the tree is NOT created",
     r.stdout.strip() == "skip" and not os.path.exists(os.path.join(home, ".copilot")), repr(r.stdout))
missing = os.path.join(home, "no-such-copilot-home")
r = run(home, "hook", COPILOT_HOME=missing)
test("2. COPILOT_HOME pointing nowhere: skip, nothing created",
     r.stdout.strip() == "skip" and not os.path.exists(missing), repr(r.stdout))

print("=== wiring ===")
os.makedirs(os.path.join(home, ".copilot", "hooks"))
foreign = os.path.join(home, ".copilot", "hooks", "other.json")
foreign_body = '{"version": 1, "hooks": {"sessionStart": [{"type": "command", "bash": "echo hi"}]}}'
open(foreign, "w").write(foreign_body)
r = run(home, "hook")
own = os.path.join(home, ".copilot", "hooks", "coffee-paladin.json")
data = json.load(open(own))
binary = os.path.join(home, ".local", "bin", "coffee-paladin")
expected = {"version": 1, "hooks": {"preToolUse": [
    {"type": "command", "matcher": "bash", "bash": binary + " hook-gate || true", "timeoutSec": 10}]}}
test("3. wire writes our file with exactly the documented shape",
     r.stdout.strip() == "ok" and data == expected, repr(data))
test("4. the file is private (0600)", stat.S_IMODE(os.stat(own).st_mode) == 0o600,
     oct(stat.S_IMODE(os.stat(own).st_mode)))
test("5. the command path is absolute and ends in || true (Copilot fails closed on a crash)",
     data["hooks"]["preToolUse"][0]["bash"].startswith("/")
     and data["hooks"]["preToolUse"][0]["bash"].endswith(" || true"), repr(data))
test("6. nothing in it says allow or ask", '"allow"' not in open(own).read()
     and '"ask"' not in open(own).read())
before = open(own).read()
r = run(home, "hook")
test("7. wiring twice is idempotent", r.stdout.strip() == "ok" and open(own).read() == before)
test("8. a stranger's hook file is untouched byte for byte", open(foreign).read() == foreign_body)
leftovers = [n for n in os.listdir(os.path.dirname(own)) if n not in ("coffee-paladin.json", "other.json")]
test("9. no temporary files left behind", not leftovers, leftovers)

print("=== a coffee-paladin.json we did not write ===")
stale = json.dumps({"version": 1, "hooks": {"preToolUse": [
    {"type": "command", "matcher": "bash", "bash": "/Users/someone-else/.local/bin/coffee-paladin hook-gate",
     "timeoutSec": 10}], "sessionStart": [{"type": "command", "bash": "./my-own-start.sh"}]}})
for label, body in [("another shape, a hook of the user's inside", stale), ("not JSON at all", "{broken")]:
    open(own, "w").write(body)
    r = run(home, "hook")
    test("10. %s: wire says foreign and leaves every byte" % label,
         r.stdout.strip() == "foreign" and open(own).read() == body, (r.stdout, open(own).read()[:60]))
    r = run(home, "unhook")
    test("11. %s: unhook says foreign and does not delete it" % label,
         r.stdout.strip() == "foreign" and os.path.exists(own) and open(own).read() == body,
         (r.stdout, os.path.exists(own)))
if os.path.exists(own):
    os.remove(own)
r = run(home, "hook")
test("12. once that file is gone, wiring writes ours again", r.stdout.strip() == "ok"
     and json.load(open(own)) == expected, repr(r.stdout))

print("=== the choice made with unhook ===")
paladin = os.path.join(home, ".coffee-paladin")
os.makedirs(paladin)
marker = os.path.join(paladin, "copilot_hook_off")
r = run(home, "unhook")
test("13. unhook removes our file and records the choice for install.sh",
     r.stdout.strip() == "ok" and not os.path.exists(own) and os.path.exists(marker), repr(r.stdout))
r = run(home, "hook")
test("14. hook by hand wires again and takes the choice back",
     r.stdout.strip() == "ok" and os.path.exists(own) and not os.path.exists(marker), repr(r.stdout))

print("=== a file system that says no ===")
home3 = tempfile.mkdtemp(prefix="tg-copilotwire-err-")
os.makedirs(os.path.join(home3, ".copilot"))
open(os.path.join(home3, ".copilot", "hooks"), "w").write("not a directory")
r = run(home3, "hook")
test("15. hooks is a file: one word 'error', exit 1, no traceback",
     r.stdout.strip() == "error" and r.returncode == 1 and "Traceback" not in r.stderr,
     (r.stdout, r.returncode, r.stderr[-160:]))
os.remove(os.path.join(home3, ".copilot", "hooks"))
r = run(home3, "hook")
locked_own = os.path.join(home3, ".copilot", "hooks", "coffee-paladin.json")
os.chmod(locked_own, 0)
r = run(home3, "unhook")
if os.path.exists(locked_own):
    os.chmod(locked_own, 0o600)
test("16. our file unreadable: unhook says 'error', exit 1, no traceback, the file stays",
     r.stdout.strip() == "error" and r.returncode == 1 and "Traceback" not in r.stderr
     and os.path.exists(locked_own), (r.stdout, r.returncode, r.stderr[-160:]))

print("=== COPILOT_HOME is respected ===")
home2 = tempfile.mkdtemp(prefix="tg-copilotwire-home2-")
ch = os.path.join(home2, "elsewhere")
os.makedirs(ch)
r = run(home2, "hook", COPILOT_HOME=ch)
test("17. wired into $COPILOT_HOME/hooks, ~/.copilot not created",
     r.stdout.strip() == "ok" and os.path.exists(os.path.join(ch, "hooks", "coffee-paladin.json"))
     and not os.path.exists(os.path.join(home2, ".copilot")), repr(r.stdout))
r = run(home2, "unhook", COPILOT_HOME=ch)
test("18. unhook under COPILOT_HOME removes it there",
     r.stdout.strip() == "ok" and not os.path.exists(os.path.join(ch, "hooks", "coffee-paladin.json")))

print("=== end to end: the command Copilot would run ===")
base = tempfile.mkdtemp(prefix="tg-copilotwire-base-")
json.dump({}, open(os.path.join(base, "config.json"), "w"))
run_env = env_for(home, TG_BASE=base, TG_LANG="en")


def hook(payload):
    command = json.load(open(own))["hooks"]["preToolUse"][0]["bash"]
    return subprocess.run(["/bin/sh", "-c", command], input=json.dumps(payload), env=run_env,
                          capture_output=True, text=True, timeout=30)


payload = {"sessionId": "s-1", "timestamp": 1704614400000, "cwd": "/tmp", "toolName": "bash",
           "toolArgs": json.dumps({"command": HEAVY})}
r = hook(payload)
test("19. without the binary: exit 0 and an empty stdout (Copilot's default, not a crash)",
     r.returncode == 0 and r.stdout == "", (r.returncode, r.stdout[:120]))
os.makedirs(os.path.dirname(binary))
os.symlink(os.path.join(SRC, "guard.py"), binary)
r = hook(payload)
try:
    answer = json.loads(r.stdout)
except ValueError:
    answer = {}
test("20. a bare encoder: exit 0 and one JSON deny with the safe-run hint",
     r.returncode == 0 and answer.get("permissionDecision") == "deny"
     and "safe-run -- " in answer.get("permissionDecisionReason", ""), (r.returncode, r.stdout[:200]))
r = hook(dict(payload, toolArgs=json.dumps({"command": "git status"})))
test("21. a light command: exit 0, stdout empty", r.returncode == 0 and r.stdout == "",
     (r.returncode, r.stdout[:120]))

print("=== a home with a space in it ===")
spaced = os.path.join(tempfile.mkdtemp(prefix="tg-copilotwire-"), "Jan Kowalski")
os.makedirs(os.path.join(spaced, ".copilot"))
os.makedirs(os.path.join(spaced, ".local", "bin"))
os.symlink(os.path.join(SRC, "guard.py"), os.path.join(spaced, ".local", "bin", "coffee-paladin"))
r = run(spaced, "hook")
command = json.load(open(os.path.join(spaced, ".copilot", "hooks", "coffee-paladin.json")))[
    "hooks"]["preToolUse"][0]["bash"]
r = subprocess.run(["/bin/sh", "-c", command], input=json.dumps(payload),
                   env=env_for(spaced, TG_BASE=base, TG_LANG="en"),
                   capture_output=True, text=True, timeout=30)
test("22. the path is quoted: the gate still answers with a deny",
     r.returncode == 0 and '"deny"' in r.stdout, (r.returncode, r.stdout[:120], r.stderr[:160]))

print("=== unwiring ===")
r = run(home, "unhook")
test("23. unhook removes only our file",
     r.stdout.strip() == "ok" and not os.path.exists(own) and open(foreign).read() == foreign_body)
r = run(home, "unhook")
test("24. unhook with nothing of ours: none", r.stdout.strip() == "none")

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
