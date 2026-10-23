#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The hook gate against payloads recorded from each host's own documentation (22.10, 23.10).

Field notes said a Copilot CLI or Cursor hook would get nothing out of the gate: their payloads
do not carry the Claude-style `tool_input.command`, so the gate found "no command" and allowed
everything without a word - a wired gate that is blind and LOOKS wired. On 22.10 the gate learnt
to say that it could not read a call (stderr plus one [HOOK?] line in guard.log) and then fail
open. On 23.10 it reads both shapes: Copilot's camelCase preToolUse (toolArgs, a JSON string or
an object) and Cursor's payloads (cursor_version; beforeShellExecution has the command at the
top level). The host is told by the payload alone, never by an environment variable, and both
get their own answer on stdout with exit 0: a deny is their JSON, an allow is an empty stdout -
never "allow" and never "ask". A broken payload of theirs is still said out loud. Formats it
read before keep their answers, and Codex never gets an "ask".

Samples, trimmed to the fields the gate looks at plus the ids around them:
  Copilot CLI, camelCase (`preToolUse`), toolArgs is a JSON STRING:
    https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/use-hooks
    (Debugging section: {"timestamp":1704614400000,"cwd":"/tmp","toolName":"bash",
    "toolArgs":"{\"command\":\"ls\"}"})
  Copilot CLI, VS Code compatible (`PreToolUse`), snake_case with a parsed tool_input:
    https://docs.github.com/en/copilot/reference/hooks-configuration
  Cursor `beforeShellExecution` (common fields + command/cwd/sandbox) and `preToolUse` (Shell):
    https://cursor.com/docs/agent/hooks (beforeMCPExecution carries a `command` too: the MCP
    server's launch line, not a shell call)
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


def decision(r):
    """The one JSON object on stdout, or None when stdout is anything else."""
    try:
        answer = json.loads(r.stdout)
    except ValueError:
        return None
    return answer if isinstance(answer, dict) and r.stdout.strip().count("\n") == 0 else None


def quiet(name, payload, env_extra=None):
    """A call the gate read and let through: exit 0, nothing on stdout or stderr, nothing logged."""
    before = len(log_lines())
    r = gate(payload, env_extra)
    test(name + ": exit 0, stdout and stderr empty, no [HOOK?] line",
         r.returncode == 0 and r.stdout == "" and r.stderr == "" and len(log_lines()) == before,
         (r.returncode, r.stdout[:120], r.stderr[:120], log_lines()[before:]))
    return r


print("1. Copilot CLI")
copilot_doc = {"timestamp": 1704614400000, "cwd": "/tmp", "toolName": "bash",
               "toolArgs": "{\"command\":\"ls\"}"}
quiet("camelCase sample from the docs (ls)", copilot_doc)
for label, args in [("toolArgs as a JSON string", json.dumps({"command": HEAVY})),
                    ("toolArgs as an object", {"command": HEAVY})]:
    r = gate(dict(copilot_doc, sessionId="s-1", toolArgs=args))
    answer = decision(r)
    test("camelCase, %s, bare encoder: exit 0 (any other exit is a crash there)" % label,
         r.returncode == 0, r.returncode)
    test("camelCase, %s: one JSON object, permissionDecision deny with the safe-run hint" % label,
         answer is not None and set(answer) == {"permissionDecision", "permissionDecisionReason"}
         and answer["permissionDecision"] == "deny"
         and "safe-run -- " in answer["permissionDecisionReason"], r.stdout[:200])
    test("camelCase, %s: never 'allow' or 'ask' on stdout" % label,
         '"allow"' not in r.stdout and '"ask"' not in r.stdout, r.stdout[:200])
    test("camelCase, %s: the reason is on stderr as well" % label, "safe-run -- " in r.stderr,
         r.stderr[:160])
r = unread("camelCase with toolArgs that is not JSON", dict(copilot_doc, toolArgs="{zepsuty"), "toolArgs")
test("broken toolArgs: stdout stays empty (Copilot's default, not an allow)", r.stdout == "", r.stdout[:120])
quiet("camelCase non-shell tool (view) on a path with ffmpeg in it",
      dict(copilot_doc, toolName="view", toolArgs=json.dumps({"path": "/tmp/ffmpeg -i a.mov"})))
r = gate(dict(copilot_doc, toolArgs=json.dumps({"command": HEAVY})), {"TG_LANG": "pl"})
answer = decision(r)
test("camelCase in Polish: still one valid JSON object with a deny",
     answer is not None and answer.get("permissionDecision") == "deny", r.stdout[:200])
r = gate({"hook_event_name": "PreToolUse", "session_id": "s-1", "timestamp": "2026-10-22T10:00:00Z",
          "cwd": "/tmp", "tool_name": "Bash", "tool_input": {"command": HEAVY}})
test("VS Code compatible format: read and refused with the safe-run hint (exit 2 = deny there)",
     r.returncode == 2 and "safe-run" in r.stderr, (r.returncode, r.stderr[:120]))
test("VS Code compatible format: stdout stays empty", r.stdout == "", r.stdout[:120])

print("2. Cursor")
cursor_common = {"conversation_id": "c-1", "generation_id": "g-1", "hook_event_name": "beforeShellExecution",
                 "cursor_version": "3.27.6", "workspace_roots": ["/project"], "user_email": None,
                 "transcript_path": None}
before_shell = dict(cursor_common, command="npm install", cwd="/project", sandbox=False)
quiet("beforeShellExecution sample (npm install)", before_shell)
r = gate(dict(before_shell, command=HEAVY))
answer = decision(r)
test("beforeShellExecution with a bare encoder: exit 0", r.returncode == 0, r.returncode)
test("beforeShellExecution: permission deny, exactly permission/user_message/agent_message",
     answer is not None and set(answer) == {"permission", "user_message", "agent_message"}
     and answer["permission"] == "deny", r.stdout[:200])
test("beforeShellExecution: the agent gets the safe-run hint, the user one non-empty line",
     answer is not None and "safe-run -- " in answer["agent_message"]
     and answer["user_message"].strip() != "" and "\n" not in answer["user_message"], r.stdout[:200])
shell = {"tool_name": "Shell", "tool_input": {"command": "npm install", "working_directory": "/project"},
         "tool_use_id": "abc123", "cwd": "/project"}
pre_tool = dict(cursor_common, hook_event_name="preToolUse", **shell)
quiet("preToolUse Shell with the common fields (npm install)", pre_tool)
r = gate(dict(pre_tool, tool_input={"command": HEAVY, "working_directory": "/project"}))
answer = decision(r)
test("preToolUse Shell with the common fields and a bare encoder: exit 0 and a JSON deny",
     r.returncode == 0 and answer is not None and answer.get("permission") == "deny",
     (r.returncode, r.stdout[:200]))
r = gate(shell)
test("preToolUse Shell sample trimmed to its own fields (npm install) passes quietly",
     r.returncode == 0 and r.stderr == "", (r.returncode, r.stderr[:120]))
r = gate(dict(shell, tool_input={"command": HEAVY, "working_directory": "/project"}))
test("...the trimmed sample with a bare encoder keeps the exit-2 answer",
     r.returncode == 2 and "safe-run" in r.stderr and r.stdout == "", (r.returncode, r.stderr[:120]))
quiet("beforeMCPExecution whose launch command is an encoder (not a shell call)",
      dict(cursor_common, hook_event_name="beforeMCPExecution", tool_name="transcode",
           tool_input="{}", mcp_server_name="media", command=HEAVY))
# 23.10: an MCP tool may carry a shell tool's name; its params are a JSON string and it is
# still not a shell call, so the generic path (unread, or a deny) must not catch it.
for label, params in [("as a JSON string, per the docs", json.dumps({"command": HEAVY})),
                      ("as an object", {"command": HEAVY})]:
    quiet("beforeMCPExecution of an MCP tool named 'shell', params %s" % label,
          dict(cursor_common, hook_event_name="beforeMCPExecution", tool_name="shell",
               tool_input=params, mcp_server_name="tools", command="npx some-mcp-server"))
r = unread("beforeShellExecution without a command", dict(cursor_common, cwd="/project"), "cursor_version")
test("beforeShellExecution without a command: stdout stays empty", r.stdout == "", r.stdout[:120])
for label, payload in [("Claude Code", {"session_id": "s-1", "hook_event_name": "PreToolUse",
                                        "tool_name": "Bash", "tool_input": {"command": HEAVY}}),
                       ("Codex", {"session_id": "s-1", "turn_id": "t-1", "hook_event_name": "PreToolUse",
                                  "tool_name": "Bash", "tool_use_id": "u-1",
                                  "tool_input": {"command": HEAVY}})]:
    r = gate(payload, {"CURSOR_VERSION": "3.27.6", "CURSOR_PROJECT_DIR": "/project"})
    test("%s started from Cursor's terminal (CURSOR_VERSION set): still exit 2, stdout empty" % label,
         r.returncode == 2 and r.stdout == "" and "safe-run -- " in r.stderr,
         (r.returncode, r.stdout[:120]))

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
