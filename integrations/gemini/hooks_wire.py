#!/usr/bin/env python3
"""Wire or unwire the coffee-paladin thermal gate in Gemini CLI.

Usage: hooks_wire.py hook | unhook

Gemini CLI reads hooks from ``~/.gemini/settings.json`` - a file SHARED with
the user's whole Gemini configuration, so the Claude-settings discipline
applies: one appended entry recognised later by its command string, atomic
writes with a timestamped backup, foreign entries untouched, unwire removes
only ours.

Two traps verified against the gemini-cli docs (2026-08): the event is
``BeforeTool`` (not PreToolUse), and ``timeout`` is in MILLISECONDS - a
copy-pasted 10 from the other adapters would give the gate ten milliseconds
to live. The shell tool is ``run_shell_command``; exit 2 blocks with stderr
as the reason, same as Claude Code.

``~/.gemini`` alone does not prove Gemini CLI is installed (Antigravity nests
its own data there): wiring requires the settings file or a ``gemini`` binary
on PATH, otherwise it skips rather than plant configuration for a tool the
user never chose.

Prints one word the caller can branch on: ok / foreign / skip / none.
Respects $HOME, so tests run against a sandbox home.
"""
import fcntl
import json
import os
import shutil
import stat
import sys
import time

SETTINGS = os.path.join(os.path.expanduser("~"), ".gemini", "settings.json")
LOCK = os.path.join(os.path.expanduser("~"), ".gemini", ".coffee-paladin-settings.lock")
GATE_MARK = "coffee-paladin hook-gate"


def gate_command():
    return os.path.join(os.path.expanduser("~"), ".local", "bin",
                        "coffee-paladin") + " hook-gate"


def load():
    try:
        data = json.load(open(SETTINGS)) if os.path.exists(SETTINGS) else {}
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def save(data):
    real = os.path.realpath(SETTINGS)
    mode = 0o600
    if os.path.exists(real):
        mode = stat.S_IMODE(os.stat(real).st_mode)
        backup = SETTINGS + ".coffee-paladin.%d.bak" % time.time_ns()
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(load() or {}, f, indent=2, ensure_ascii=False)
    tmp = "%s.tmp.%d" % (real, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, real)


def _is_ours(hook):
    return isinstance(hook, dict) and GATE_MARK in str(hook.get("command", ""))


def hook_wire():
    if not os.path.isdir(os.path.dirname(SETTINGS)):
        print("skip")
        return
    if not os.path.exists(SETTINGS) and shutil.which("gemini") is None:
        print("skip")           # ~/.gemini can belong to Antigravity alone
        return
    data = load()
    if data is None:
        print("skip")           # not a JSON object: never "repair" somebody's file
        return
    hooks = data.get("hooks")
    if hooks is None:
        hooks = {}
    if not isinstance(hooks, dict):
        print("foreign")        # a shape we do not understand is not ours to fix
        return
    before = hooks.get("BeforeTool")
    if before is None:
        before = []
    if not isinstance(before, list):
        print("foreign")
        return
    for group in before:
        if isinstance(group, dict) and any(_is_ours(h) for h in group.get("hooks") or []):
            print("ok")
            return
    before.append({"matcher": "run_shell_command",
                   "hooks": [{"name": "coffee-paladin-gate", "type": "command",
                              "command": gate_command(), "timeout": 10000}]})
    hooks["BeforeTool"] = before
    data["hooks"] = hooks
    save(data)
    print("ok")


def hook_unwire():
    data = load()
    if not data or not isinstance(data.get("hooks"), dict):
        print("none")
        return
    changed = False
    hooks = data["hooks"]
    for event in list(hooks):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            inner = group.get("hooks") or []
            kept = [h for h in inner if not _is_ours(h)]
            if len(kept) != len(inner):
                changed = True
                if kept:
                    kept_groups.append(dict(group, hooks=kept))
                # a group we emptied entirely was ours; drop it
            else:
                kept_groups.append(group)
        if kept_groups:
            hooks[event] = kept_groups
        elif groups:
            changed = True
            hooks.pop(event, None)
    if not changed:
        print("none")
        return
    if not hooks:
        data.pop("hooks", None)
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
