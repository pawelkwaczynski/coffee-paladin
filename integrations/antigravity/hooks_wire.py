#!/usr/bin/env python3
"""Wire or unwire the coffee-paladin thermal gate in Antigravity.

Usage: hooks_wire.py hook | unhook

Antigravity reads ``~/.gemini/config/hooks.json`` and its schema differs from
every other host: the top level maps HOOK NAMES to event configurations (one
extra nesting level), the shell tool is ``run_command``, and blocking happens
ONLY through a stdout ``{"decision": "deny"}`` - there is no exit-code
contract at all (the gate emits the decision when it recognises the toolCall
payload shape). Verified against antigravity.google/docs/hooks, 2026-08.

Owning a NAMED key makes the merge simple and safe: wiring adds or refreshes
exactly the "coffee-paladin-gate" key, unwiring deletes exactly that key, and
every other name in the file belongs to the user (the /hooks TUI writes this
same file - hence the timestamped backup before every write).

Prints one word the caller can branch on: ok / skip / none.
Respects $HOME, so tests run against a sandbox home.
"""
import fcntl
import json
import os
import stat
import sys
import time

HOOKS = os.path.join(os.path.expanduser("~"), ".gemini", "config", "hooks.json")
LOCK = os.path.join(os.path.expanduser("~"), ".gemini", "config", ".coffee-paladin-hooks.lock")
OUR_KEY = "coffee-paladin-gate"


def gate_command():
    return os.path.join(os.path.expanduser("~"), ".local", "bin",
                        "coffee-paladin") + " hook-gate"


def load():
    try:
        data = json.load(open(HOOKS)) if os.path.exists(HOOKS) else {}
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def save(data):
    real = os.path.realpath(HOOKS)
    mode = 0o600
    if os.path.exists(real):
        mode = stat.S_IMODE(os.stat(real).st_mode)
        backup = HOOKS + ".coffee-paladin.%d.bak" % time.time_ns()
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(load() or {}, f, indent=2, ensure_ascii=False)
    tmp = "%s.tmp.%d" % (real, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, real)


def hook_wire():
    if not os.path.isdir(os.path.dirname(HOOKS)):
        print("skip")           # no ~/.gemini/config = no Antigravity; never create it
        return
    data = load()
    if data is None:
        print("skip")           # not a JSON object: never "repair" somebody's file
        return
    entry = {"PreToolUse": [
        {"matcher": "run_command",
         "hooks": [{"type": "command", "command": gate_command(), "timeout": 10}]}]}
    if data.get(OUR_KEY) == entry:
        print("ok")
        return
    data[OUR_KEY] = entry
    save(data)
    print("ok")


def hook_unwire():
    data = load()
    if not data or OUR_KEY not in data:
        print("none")
        return
    del data[OUR_KEY]
    save(data)
    print("ok")


def locked(action):
    """Serialise hook/unhook: two racing writers on a shared config could
    clobber each other's tmp file or drop a concurrent edit (same contract as
    the Claude adapter's lock)."""
    if not os.path.isdir(os.path.dirname(LOCK)):
        return action()
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return action()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "hook":
        locked(hook_wire)
    elif len(sys.argv) >= 2 and sys.argv[1] == "unhook":
        locked(hook_unwire)
    else:
        print(__doc__)
        sys.exit(2)
