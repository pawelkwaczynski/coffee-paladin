#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The pre-exec gate for AI coding agents (`coffee-paladin hook-gate`).

Contract under test: exit 2 with a safe-run hint on stderr for a HEAVY bare
command, exit 0 for everything else - already-supervised commands, version
questions, non-shell tools, log files whose NAMES contain a heavy word, and
every malformed input (a broken gate must never hold a coding session
hostage). The gate reads stdin only; it never measures, never signals.

Run with:  python3 tests/test_hook_gate.py
Uses a temporary TG_BASE; nothing on the real machine is touched.
"""
import json
import os
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-hookgate-")
json.dump({}, open(os.path.join(BASE, "config.json"), "w"))
ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en")
ENV.pop("PALADIN_HOOK", None)

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def gate(payload, env_extra=None):
    e = dict(ENV)
    e.update(env_extra or {})
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, os.path.join(SRC, "guard.py"), "hook-gate"],
                         input=body, env=e, capture_output=True, text=True, timeout=30)


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


print("=== blocks ===")
r = gate(bash("ffmpeg -i in.mov -c:v libx265 out.mp4"))
test("1. bare ffmpeg is blocked with the safe-run hint",
     r.returncode == 2 and "safe-run" in r.stderr, "rc=%s %r" % (r.returncode, r.stderr[:120]))
r = gate(bash("cd /tmp && nice /opt/homebrew/bin/ffmpeg -i a.mov b.mp4"))
test("2. path prefix and nice do not hide the tool", r.returncode == 2, r.stderr[:120])
r = gate(bash("ollama run qwen3 'hello'"))
test("3. ollama run is heavy", r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("echo start; cadical proof.cnf"))
test("4. heavy after a separator is caught", r.returncode == 2, "rc=%s" % r.returncode)

print("=== allows ===")
for name, cmd in [
    ("5. already supervised", "safe-run --cores 3 -- ffmpeg -i a.mov b.mp4"),
    ("6. version question", "ffmpeg -version"),
    ("7. a log NAMED after a heavy tool", "cat /tmp/cadical.log"),
    ("8. ollama list is light", "ollama list"),
    ("9. plain light work", "git status && ls -la"),
]:
    r = gate(bash(cmd))
    test(name, r.returncode == 0, "rc=%s %r" % (r.returncode, r.stderr[:100]))

r = gate({"tool_name": "Read", "tool_input": {"file_path": "/tmp/ffmpeg"}})
test("10. non-shell tools pass untouched", r.returncode == 0)

print("=== the adversarial round's catches stay caught ===")
r = gate(bash("grep ffmpeg README.md | head -5"))
test("10b. a heavy NAME as an argument to grep is data, not execution",
     r.returncode == 0, "rc=%s %r" % (r.returncode, r.stderr[:100]))
r = gate(bash("echo safe-run; ffmpeg -i a.mov b.mp4"))
test("10c. 'safe-run' in a NEIGHBOURING segment lends no supervision",
     r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("FOO=bar ffmpeg -i a.mov b.mp4"))
test("10d. an env assignment prefix does not hide the tool",
     r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("env LC_ALL=C nice -n 10 ffmpeg -i a.mov b.mp4"))
test("10e. wrapper chains are skipped down to the real argv0",
     r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("git log && x265 --input in.y4m -o out.hevc"))
test("10f. heavy after && is caught", r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("ffmpeg -i a.mov b.mp4"), env_extra={"PALADIN_HOOK": "off"})
test("11. PALADIN_HOOK=off disables the gate", r.returncode == 0)

print("=== fail-open on anything unexpected ===")
for name, payload in [
    ("12. garbage stdin", "not json at all"),
    ("13. empty stdin", ""),
    ("14. JSON but not an object", "[1,2,3]"),
    ("15. missing tool_input", '{"tool_name": "Bash"}'),
    ("16. command of a wrong type", '{"tool_name": "Bash", "tool_input": {"command": 42}}'),
]:
    r = gate(payload)
    test(name + " -> allow", r.returncode == 0, "rc=%s" % r.returncode)

print("=== the Grok Build dialect (camelCase + stdout decision) ===")
r = gate({"toolName": "run_terminal_command", "toolInput": {"command": "ffmpeg -i a.mov b.mp4"}})
test("18. camelCase fields are understood (a wired gate must never be blind)",
     r.returncode == 2, "rc=%s" % r.returncode)
r = gate({"toolName": "run_terminal_command", "toolInput": {"command": "git status"}})
test("18b. ...and a light command still passes", r.returncode == 0, "rc=%s" % r.returncode)
r = gate({"toolName": "run_terminal_command",
          "toolInput": {"command": "ffmpeg -i a.mov b.mp4"}},
         env_extra={"GROK_HOOK_EVENT": "pre_tool_use"})
try:
    decision = json.loads(r.stdout)
except ValueError:
    decision = {}
test("19. under Grok's env marker the deny is an explicit stdout decision",
     r.returncode == 2 and decision.get("decision") == "deny"
     and "safe-run" in str(decision.get("reason", "")), repr(r.stdout[:120]))
r = gate(bash("ffmpeg -i a.mov b.mp4"))
test("19b. without the marker stdout stays CLEAN (Claude parses its own schema there)",
     r.returncode == 2 and r.stdout.strip() == "", repr(r.stdout[:120]))
r = gate({"toolName": "read_file", "toolInput": {"command": "ffmpeg fake"}})
test("20. non-shell camelCase tools pass untouched", r.returncode == 0)

print("=== the Antigravity dialect (toolCall + mandatory stdout decision) ===")
r = gate({"toolCall": {"name": "run_command",
                       "args": {"CommandLine": "ffmpeg -i a.mov b.mp4"}}})
try:
    decision = json.loads(r.stdout)
except ValueError:
    decision = {}
test("21. a heavy toolCall is denied via the stdout decision, exit 0 (no exit "
     "contract there - nonzero could read as 'hook crashed', not 'deny')",
     r.returncode == 0 and decision.get("decision") == "deny"
     and "safe-run" in str(decision.get("reason", "")),
     "rc=%s %s" % (r.returncode, repr(r.stdout[:120])))
r = gate({"toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}}})
try:
    decision = json.loads(r.stdout)
except ValueError:
    decision = {}
test("22. a light toolCall gets an EXPLICIT allow (no exit-code contract there)",
     r.returncode == 0 and decision.get("decision") == "allow", repr(r.stdout[:120]))
r = gate({"toolCall": {"name": "view_file", "args": {"CommandLine": "x"}}})
test("23. non-shell toolCall passes silently", r.returncode == 0)
r = gate(bash("git status"))
test("24. outside Antigravity a light command keeps stdout CLEAN",
     r.returncode == 0 and r.stdout.strip() == "", repr(r.stdout[:60]))

print("=== quoted substitutions and informational queries ===")
for name, cmd, blocked in [
    ("single-quoted bash body stays supervised",
     "safe-run -- bash -c 'a; ffmpeg -i x y; echo \"$(ffprobe z)\"'", None),
    ("double-quoted bash body stays supervised",
     'safe-run -- bash -c "ffmpeg -i a b && ffmpeg -i c d"; echo "$(basename x)"', None),
    ("field command with an outer double-quoted bash body",
     'mkdir -p "$D" && safe-run --cpu-limit 50 -- bash -c '
     '"ffmpeg -i a.mp3 x.m4a && ffmpeg -i a.mp3 y.m4a"; '
     'for f in "$D"/*.m4a; do echo "$(basename $f): $(safe-run -- ffprobe $f) s"; done', None),
    ("field command with a single-quoted bash body",
     'safe-run --cpu-limit 50 -- bash -c '
     '\'ffmpeg -i a.mp3 x.m4a; ffmpeg -i a.mp3 y.m4a; '
     'for f in "$D"/*.m4a; do echo "$(basename "$f"): $(ffprobe "$f") s"; done\'', None),
    ("backticks in a single-quoted assignment are text",
     "L='see `ffmpeg -hide_banner -filters` for the list'", None),
    ("double-quoted substitution executes ffmpeg", 'echo "$(ffmpeg -i x y)"', "ffmpeg"),
    ("assignment substitution executes ffmpeg", "x=$(ffmpeg -i a b)", "ffmpeg"),
    ("backtick substitution executes ffmpeg", "echo `ffmpeg -i a b`", "ffmpeg"),
    ("nested substitution executes ffmpeg", 'echo "a $(echo "$(ffmpeg -i a b)")"', "ffmpeg"),
    ("single-quoted substitution is text", "echo 'it is $(ffmpeg -i a b)'", None),
    ("ffmpeg filters is informational", "ffmpeg -hide_banner -filters", None),
    ("ffmpeg encoders is informational", "ffmpeg -v quiet -encoders", None),
    ("ffmpeg help topic is informational", "ffmpeg -h encoder=libx264", None),
    ("ffmpeg input still runs", "ffmpeg -hide_banner -i a.mp4 b.mkv", "ffmpeg"),
]:
    r = gate(bash(cmd))
    if blocked:
        ok = r.returncode == 2 and "'%s'" % blocked in r.stderr
    else:
        ok = r.returncode == 0 and "deny" not in r.stdout
    test(name, ok, "rc=%s %r" % (r.returncode, r.stderr[:160]))

r = gate(bash("cd /x && S=1; ffmpeg -i a b"))
test("hint names the offending segment",
     r.returncode == 2 and "safe-run -- ffmpeg -i a b" in r.stderr
     and "safe-run -- cd" not in r.stderr,
     "rc=%s %r" % (r.returncode, r.stderr[:200]))

print("=== comments, incomplete input and double-dash queries ===")
for name, cmd, blocked in [
    ("apostrophe in a trailing comment", "ffmpeg -i in.mp4 out.mkv  # don't forget", "ffmpeg"),
    ("substitution text in a trailing comment",
     "ffmpeg -i a b | tee log # it's $(fine)", "ffmpeg"),
    ("complete line before an unterminated quote",
     'ffmpeg -i a b\necho "unterminated', "ffmpeg"),
    ("ffmpeg double-dash help", "ffmpeg --help", None),
    ("ffmpeg double-dash version", "ffmpeg --version", None),
    ("ffmpeg double-dash filters", "ffmpeg --hide_banner --filters", None),
    ("ffmpeg help with an input still runs", "ffmpeg --help -i a b", "ffmpeg"),
    ("simple trailing comment", "ffmpeg -i a b # note", "ffmpeg"),
    ("heavy command in a comment is ignored", "echo hi # ffmpeg -i a b", None),
    ("substitution in a comment is ignored", "echo hi # $(ffmpeg -i a b)", None),
    ("hash inside quotes is text", 'echo "# not a comment"; ffmpeg -i a b', "ffmpeg"),
    ("hash inside a word is text", "echo a#b; ffmpeg -i a b", "ffmpeg"),
    ("substitution before its own comment executes",
     'echo "$(ffmpeg -i a b # x)"', "ffmpeg"),
]:
    r = gate(bash(cmd))
    if blocked:
        ok = r.returncode == 2 and "'%s'" % blocked in r.stderr
    else:
        ok = r.returncode == 0 and "deny" not in r.stdout
    test(name, ok, "rc=%s %r" % (r.returncode, r.stderr[:160]))

r = gate(bash("S=1 ffmpeg -i a b"))
test("assignment precedes safe-run in the hint",
     r.returncode == 2 and "Segment: S=1 ffmpeg -i a b" in r.stderr
     and "S=1 safe-run -- ffmpeg -i a b" in r.stderr,
     "rc=%s %r" % (r.returncode, r.stderr[:220]))
r = gate(bash("S='a b' ffmpeg -i a b"))
test("assignment value with spaces stays a shell assignment in the hint",
     r.returncode == 2 and "S='a b' safe-run -- ffmpeg -i a b" in r.stderr,
     "rc=%s %r" % (r.returncode, r.stderr[:220]))

print("=== config override ===")
json.dump({"hook_heavy_patterns": ["sleep"]}, open(os.path.join(BASE, "config.json"), "w"))
r = gate(bash("sleep 999"))
r2 = gate(bash("ffmpeg -i a.mov b.mp4"))
test("17. hook_heavy_patterns replaces the default list",
     r.returncode == 2 and r2.returncode == 0,
     "sleep rc=%s ffmpeg rc=%s" % (r.returncode, r2.returncode))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
