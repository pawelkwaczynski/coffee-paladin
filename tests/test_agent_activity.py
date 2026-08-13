#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent Activity: the "what did the AI start on this Mac" snapshot.

Contracts: an AI session is recognised by the identity part of its command
line (never by data paths - `ffmpeg claude_brain/a.mov` is NOT an agent); only
the OUTERMOST match is a session root (a node MCP server inside a Claude
session folds under it, it does not become a second root); the tree is capped
in depth and node count so a fork storm cannot balloon the file; the JSON
carries comm names only, no command lines; and the writer is atomic 0600.

Run with:  python3 tests/test_agent_activity.py
Pure synthetic process tables; nothing on the real machine is touched.
"""
import importlib.machinery
import json
import os
import stat
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-activity-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("aa_guard", os.path.join(SRC, "guard.py")).load_module()

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


# Synthetic table: (pid, ppid, cpu, comm) + injectable args reader.
PROCS = [
    (100, 1, 2.0, "claude"),            # session root by comm
    (110, 100, 90.0, "python3"),        # its child burning CPU
    (111, 110, 45.0, "cadical"),        # grandchild
    (112, 100, 1.0, "node"),            # MCP server: args say "claude" -> NOT a second root
    (200, 1, 0.5, "node"),              # standalone agent by args (codex)
    (210, 200, 30.0, "ffmpeg"),
    (300, 1, 80.0, "ffmpeg"),           # heavy but NOT an agent (data path mentions claude)
    (400, 1, 0.0, "Safari"),
]
ARGS = {112: "node mcp-server-claude", 200: "node codex --serve",
        300: ""}  # ffmpeg's identity args carry no marker - data paths were stripped


def fake_args(pid):
    return ARGS.get(pid, "")


print("=== root detection ===")
roots = g._agent_roots(PROCS, args_fn=fake_args)
test("1. claude by comm and codex by args are roots",
     100 in roots and 200 in roots and roots[200] == "codex", str(roots))
test("2. the MCP server inside the session is NOT a second root", 112 not in roots, str(roots))
test("3. ffmpeg with a claude data path is NOT an agent", 300 not in roots, str(roots))

# Field catch from the first live run: the video queue's supervisor was
# classified as a "hermes" session because its script lives under
# ~/HermesWorkspace/. A directory is location, not identity.
path_trap = [(600, 1, 5.0, "python3"), (610, 1, 1.0, "hermes")]
trap_args = {600: "python3 /users/x/hermesworkspace/kompresja/kompresor.sh run"}
r = g._agent_roots(path_trap, args_fn=lambda pid: trap_args.get(pid, ""))
test("3b. a marker inside the script's DIRECTORY does not make an agent",
     600 not in r and 610 in r, str(r))

print("=== the tree ===")
act = g.agent_activity(PROCS, chip_c=71.5, level=1, args_fn=fake_args)
agents = {a["pid"]: a for a in act["agents"]}
test("4. two agents, thermal context attached",
     set(agents) == {100, 200} and act["chip_c"] == 71.5 and act["level"] == 1, str(act)[:200])
claude = agents[100]
test("5. tree CPU sums the whole subtree",
     abs(claude["cpu_tree"] - (2.0 + 90.0 + 45.0 + 1.0)) < 0.1, str(claude["cpu_tree"]))
kid_comms = [k["comm"] for k in claude["children"]]
test("6. children sorted by CPU, python3 first", kid_comms and kid_comms[0] == "python3",
     str(kid_comms))
test("7. grandchild present at depth 2",
     claude["children"][0]["kids"] and claude["children"][0]["kids"][0]["comm"] == "cadical",
     str(claude["children"][:1]))
test("8. no command lines anywhere in the snapshot",
     "mcp-server-claude" not in json.dumps(act) and "codex --serve" not in json.dumps(act))

print("=== caps ===")
deep = [(1000, 1, 1.0, "claude")]
cur = 1000
for i in range(6):
    deep.append((1001 + i, cur, 1.0, "sh"))
    cur = 1001 + i
act = g.agent_activity(deep, args_fn=lambda pid: "")
node, depth = act["agents"][0], 0
walk = node["children"]
while walk:
    depth += 1
    walk = walk[0]["kids"]
test("9. depth capped at %d" % g.ACTIVITY_DEPTH, depth == g.ACTIVITY_DEPTH, "depth=%d" % depth)

wide = [(2000, 1, 1.0, "claude")] + [(3000 + i, 2000, 0.5, "sh") for i in range(500)]
act = g.agent_activity(wide, args_fn=lambda pid: "")
test("10. node budget caps a fork storm",
     len(act["agents"][0]["children"]) <= g.ACTIVITY_MAX_NODES,
     str(len(act["agents"][0]["children"])))

print("=== ppid loop does not hang the root walk ===")
looped = [(500, 501, 1.0, "claude"), (501, 500, 1.0, "sh")]
roots = g._agent_roots(looped, args_fn=lambda pid: "")
test("11. a pid/ppid cycle terminates and still yields the root", 500 in roots, str(roots))

print("=== the writer ===")
g.activity_write(g.agent_activity(PROCS, args_fn=fake_args))
mode = stat.S_IMODE(os.stat(g.ACTIVITY_PATH).st_mode)
data = json.load(open(g.ACTIVITY_PATH))
test("12. atomic write, 0600, valid JSON", mode == 0o600 and len(data["agents"]) == 2,
     oct(mode))

if os.environ.get("TG_LIVE_SMOKE") == "1":
    # Opt-in: assumes a claude session runs on THIS machine. CI and plain
    # terminals have none, so the default battery stays purely synthetic.
    print("=== the real machine smoke test (TG_LIVE_SMOKE=1) ===")
    real = g.agent_activity(g.list_procs())
    test("13. live scan finds at least one agent session",
         any(a["agent"] == "claude" for a in real["agents"]),
         str([a["agent"] for a in real["agents"]]))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
