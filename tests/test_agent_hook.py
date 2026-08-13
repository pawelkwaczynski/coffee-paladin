#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Claude Code event recorder (agent_hook.py) and its wiring.

Contracts: every event lands as one whitelisted JSONL line (never full paths,
command lines, or tool payloads), the thermal context rides along, exit code
is always 0 (a recorder must never block a session), old daily files are
pruned after SessionEnd, the Obsidian page appears ONLY when a vault path is
configured, and the `record`/`unhook` wiring appends and removes our entries
across ALL event sections while foreign hooks survive intact.

Run with:  python3 tests/test_agent_hook.py
Runs against sandbox TG_BASE and HOME; the real ones are never touched.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(SRC, "integrations", "claude-code", "agent_hook.py")
WIRE = os.path.join(SRC, "integrations", "claude-code", "settings_wire.py")

BASE = tempfile.mkdtemp(prefix="tg-agenthook-")
EV = os.path.join(BASE, "agent_events")
ENV = dict(os.environ, TG_BASE=BASE)

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def fire(payload):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, HOOK], input=body, env=ENV,
                          capture_output=True, text=True, timeout=30)


def events():
    day = os.path.join(EV, time.strftime("%Y-%m-%d") + ".jsonl")
    if not os.path.exists(day):
        return []
    return [json.loads(line) for line in open(day) if line.strip()]


json.dump({"level": 1, "chip_c": 88.5}, open(os.path.join(BASE, "status.json"), "w"))

print("=== recording ===")
r = fire({"hook_event_name": "PreToolUse", "session_id": "abc-123",
          "tool_name": "Bash", "tool_use_id": "t1",
          "tool_input": {"command": "ffmpeg -i /Users/x/client-secret/a.mov out.mp4"},
          "cwd": "/Users/x/projects/tajny-klient"})
e = events()[-1]
test("1. one whitelisted line per event, exit 0",
     r.returncode == 0 and e["hook_event_name"] == "PreToolUse"
     and e["tool_name"] == "Bash" and e["session_id"] == "abc-123", str(e))
test("2. project is a basename, the command line is NOT recorded",
     e.get("project") == "tajny-klient" and "client-secret" not in json.dumps(e)
     and "ffmpeg" not in json.dumps(e), str(e))
test("3. thermal context rides along",
     e.get("thermal", {}).get("chip_c") == 88.5 and e["thermal"]["level"] == 1, str(e))

r = fire("garbage not json")
test("4. garbage stdin: exit 0, nothing recorded", r.returncode == 0 and len(events()) == 1)

print("=== SessionEnd: prune and the optional vault page ===")
old = os.path.join(EV, "2026-01-01.jsonl")
open(old, "w").write("{}\n")
past = time.time() - 30 * 86400
os.utime(old, (past, past))
json.dump({}, open(os.path.join(BASE, "config.json"), "w"))
fire({"hook_event_name": "SessionEnd", "session_id": "abc-123", "reason": "clear"})
test("5. old daily files are pruned", not os.path.exists(old))
test("6. no vault configured = no page anywhere",
     not any("Coffee Paladin" in r for r, d, f in os.walk(BASE)))

vault = tempfile.mkdtemp(prefix="tg-vault-")
json.dump({"agent_obsidian_vault_path": vault}, open(os.path.join(BASE, "config.json"), "w"))
fire({"hook_event_name": "SessionEnd", "session_id": "abc-123", "reason": "logout"})
pages_dir = os.path.join(vault, "Coffee Paladin", "Agent Activity")
pages = os.listdir(pages_dir) if os.path.isdir(pages_dir) else []
test("7. with a vault set, one page per session end", len(pages) == 1, str(pages))
if pages:
    body = open(os.path.join(pages_dir, pages[0])).read()
    test("8. the page counts tools and carries no payloads",
         "Bash" in body and "tajny-klient" in body and "client-secret" not in body, body[:300])
else:
    test("8. the page counts tools and carries no payloads", False, "no page")
r = fire({"hook_event_name": "SessionEnd", "session_id": "abc-123", "reason": "x"})
json.dump({"agent_obsidian_vault_path": "/dev/null/impossible"}, open(os.path.join(BASE, "config.json"), "w"))
r = fire({"hook_event_name": "SessionEnd", "session_id": "abc-123", "reason": "x"})
test("9. an unwritable vault never breaks the hook", r.returncode == 0, r.stderr[:120])

print("=== wiring across event sections ===")
HOME2 = tempfile.mkdtemp(prefix="tg-recwire-")
WENV = dict(os.environ, HOME=HOME2)
SET = os.path.join(HOME2, ".claude", "settings.json")
os.makedirs(os.path.dirname(SET))
FOREIGN = {"hooks": {"PostToolUse": [{"matcher": "Bash",
                                     "hooks": [{"type": "command", "command": "/opt/mine/audit.sh"}]}]}}
json.dump(FOREIGN, open(SET, "w"), indent=2)


def wire(*args):
    return subprocess.run([sys.executable, WIRE, *args], env=WENV,
                          capture_output=True, text=True).stdout.strip()


test("10. record registers under every lifecycle event", wire("record") == "ok"
     and all(any(any("agent_hook" in str(h.get("command", "")) for h in g.get("hooks", []))
                 for g in json.load(open(SET))["hooks"].get(ev, []))
             for ev in ("SessionStart", "PreToolUse", "PostToolUse", "SessionEnd")),
     json.dumps(json.load(open(SET)))[:300])
after = json.load(open(SET))
test("11. the foreign PostToolUse entry survives",
     FOREIGN["hooks"]["PostToolUse"][0] in after["hooks"]["PostToolUse"])
test("12. record twice is idempotent", wire("record") == "ok"
     and sum("agent_hook" in json.dumps(g) for g in json.load(open(SET))["hooks"]["PreToolUse"]) == 1)
test("13. tool events get a matcher, lifecycle events none",
     "matcher" in after["hooks"]["PreToolUse"][-1]
     and "matcher" not in after["hooks"]["SessionEnd"][-1])
test("14. unhook clears recorder AND gate entries everywhere, foreign stays",
     wire("hook") == "ok" and wire("unhook") == "ok"
     and json.load(open(SET))["hooks"] == FOREIGN["hooks"], json.dumps(json.load(open(SET))))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
