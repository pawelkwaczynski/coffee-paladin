#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The hook gate against payloads recorded from each host's own documentation (22.10).

Field notes said a Copilot CLI or Cursor hook would get nothing out of the gate: their payloads
do not carry the Claude-style `tool_input.command`, so the gate found "no command" and allowed
everything without a word - a wired gate that is blind and LOOKS wired. There are no Copilot or
Cursor adapters in integrations/, so the gate does not learn their formats here; it has to say
that it could not read a call (stderr plus one [HOOK?] line in guard.log) and then fail open, as
it always has. Formats it does read keep their answers, and Codex never gets an "ask".

Samples, trimmed to the fields the gate looks at plus the ids around them:
  Copilot CLI, camelCase (`preToolUse`), toolArgs is a JSON STRING:
    https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/use-hooks
    (Debugging section: {"timestamp":1704614400000,"cwd":"/tmp","toolName":"bash",
    "toolArgs":"{\"command\":\"ls\"}"})
  Copilot CLI, VS Code compatible (`PreToolUse`), snake_case with a parsed tool_input:
    https://docs.github.com/en/copilot/reference/hooks-configuration
  Cursor `beforeShellExecution` (common fields + command/cwd/sandbox) and `preToolUse` (Shell):
    https://cursor.com/docs/agent/hooks
  Codex PreToolUse input (schema + the request fixture with tool_name "Bash"), and the parser
  that turns permissionDecision "ask" into a failed hook that blocks nothing:
    https://github.com/openai/codex/blob/main/codex-rs/hooks/schema/generated/pre-tool-use.command.input.schema.json
    https://github.com/openai/codex/blob/main/codex-rs/hooks/src/events/pre_tool_use.rs

Run with:  python3 tests/test_hook_hosts_20261022.py
Uses a temporary TG_BASE; nothing on the real machine is touched.
"""
import json
import os
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-hook-hosts-")
json.dump({}, open(os.path.join(BASE, "config.json"), "w"))
LOG = os.path.join(BASE, "guard.log")
ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en")
for k in ("PALADIN_HOOK", "GROK_HOOK_EVENT"):
    ENV.pop(k, None)

HEAVY = "ffmpeg -i a.mov -c:v libx265 b.mp4"

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def gate(payload, env_extra=None):
    e = dict(ENV)
    e.update(env_extra or {})
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, os.path.join(SRC, "guard.py"), "hook-gate"],
                          input=body, env=e, capture_output=True, text=True, timeout=30)


def log_lines():
    try:
        return [l for l in open(LOG, encoding="utf-8") if "[HOOK?]" in l]
    except OSError:
        return []


def unread(name, payload, field, env_extra=None):
    """A payload the gate cannot read: allowed, but said out loud in both places."""
    before = len(log_lines())
    r = gate(payload, env_extra)
    after = log_lines()
    test(name + ": still allowed (the gate fails open by design)", r.returncode == 0, r.returncode)
    test(name + ": stderr says it was NOT checked", "could not read" in r.stderr and field in r.stderr,
         r.stderr[:200])
    test(name + ": one [HOOK?] line in guard.log", len(after) == before + 1 and field in after[-1],
         after[before:])
    test(name + ": no command text leaks into the log", "ffmpeg" not in "".join(after[before:]),
         after[before:])
    return r


print("1. Copilot CLI")
copilot_doc = {"timestamp": 1704614400000, "cwd": "/tmp", "toolName": "bash",
               "toolArgs": "{\"command\":\"ls\"}"}
r = unread("camelCase sample from the docs", copilot_doc, "toolArgs")
test("camelCase: stdout stays empty (no guessed decision schema)", r.stdout.strip() == "", r.stdout[:120])
unread("camelCase with a bare encoder in toolArgs",
       dict(copilot_doc, toolArgs=json.dumps({"command": HEAVY})), "toolArgs")
r = gate({"hook_event_name": "PreToolUse", "session_id": "s-1", "timestamp": "2026-10-22T10:00:00Z",
          "cwd": "/tmp", "tool_name": "Bash", "tool_input": {"command": HEAVY}})
test("VS Code compatible format: read and refused with the safe-run hint (exit 2 = deny there)",
     r.returncode == 2 and "safe-run" in r.stderr, (r.returncode, r.stderr[:120]))

print("2. Cursor")
cursor_common = {"conversation_id": "c-1", "generation_id": "g-1", "hook_event_name": "beforeShellExecution",
                 "cursor_version": "1.0.0", "workspace_roots": ["/project"], "user_email": None,
                 "transcript_path": None}
r = unread("beforeShellExecution sample", dict(cursor_common, command=HEAVY, cwd="/project", sandbox=False),
           "cursor_version")
test("beforeShellExecution: stdout stays empty", r.stdout.strip() == "", r.stdout[:120])
shell = {"tool_name": "Shell", "tool_input": {"command": "npm install", "working_directory": "/project"},
         "tool_use_id": "abc123", "cwd": "/project"}
r = gate(shell)
test("preToolUse Shell sample (npm install) passes quietly", r.returncode == 0 and r.stderr == "",
     (r.returncode, r.stderr[:120]))
r = gate(dict(shell, tool_input={"command": HEAVY, "working_directory": "/project"}))
test("preToolUse Shell with a bare encoder is refused", r.returncode == 2 and "safe-run" in r.stderr,
     (r.returncode, r.stderr[:120]))

print("3. Codex never gets 'ask'")
codex = {"session_id": "s-1", "turn_id": "t-1", "transcript_path": None, "cwd": "/tmp",
         "hook_event_name": "PreToolUse", "model": "m", "permission_mode": "default",
         "tool_name": "Bash", "tool_use_id": "u-1", "tool_input": {"command": HEAVY}}
r = gate(codex)
test("heavy: exit 2 (the one block Codex honours)", r.returncode == 2, r.returncode)
test("heavy: the reason is on stderr (exit 2 with an EMPTY stderr is a failed hook in Codex)",
     r.stderr.strip() != "" and "safe-run -- " in r.stderr, r.stderr[:160])
test("heavy: no 'ask' and no JSON on stdout (Codex runs the command on 'ask')",
     "ask" not in r.stdout and r.stdout.strip() == "", r.stdout[:160])
r = gate(dict(codex, tool_input={"command": "echo hello"}))
test("light (the fixture's own 'echo hello'): exit 0, nothing on stdout or stderr",
     r.returncode == 0 and r.stdout == "" and r.stderr == "", (r.returncode, r.stdout, r.stderr))

print("4. known shapes stay quiet")
before = len(log_lines())
for name, payload in [("non-shell tool", {"tool_name": "Read", "tool_input": {"file_path": "/tmp/ffmpeg"}}),
                      ("light Bash", {"tool_name": "Bash", "tool_input": {"command": "git status"}}),
                      ("non-shell camelCase tool", {"toolName": "read_file", "toolInput": {"path": "x"}}),
                      ("empty command", {"tool_name": "Bash", "tool_input": {"command": ""}})]:
    r = gate(payload)
    test("%s: exit 0, stderr empty" % name, r.returncode == 0 and r.stderr == "", (r.returncode, r.stderr[:120]))
test("...and none of them wrote a [HOOK?] line", len(log_lines()) == before, log_lines()[before:])

print("5. unreadable input of any kind is said, not swallowed")
unread("not JSON", "not json at all", "tool: -")
unread("JSON but not an object", "[1, 2, 3]", "tool: -")
unread("shell tool without tool_input", {"tool_name": "Bash"}, "tool_name")
unread("command of a wrong type", {"tool_name": "Bash", "tool_input": {"command": 42}}, "tool_input")
r = unread("Antigravity shell call without CommandLine", {"toolCall": {"name": "run_command", "args": {}}},
           "toolCall")
try:
    decision = json.loads(r.stdout)
except ValueError:
    decision = {}
test("Antigravity: the fail-open is an explicit stdout allow (its only channel)",
     decision.get("decision") == "allow", r.stdout[:120])
before = len(log_lines())
r = gate(copilot_doc, {"PALADIN_HOOK": "off"})
test("PALADIN_HOOK=off: silent, nothing logged", r.returncode == 0 and r.stderr == "" and
     len(log_lines()) == before, (r.returncode, r.stderr[:80]))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
