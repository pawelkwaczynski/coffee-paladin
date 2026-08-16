#!/usr/bin/env python3
"""Wire or unwire the coffee-paladin thermal gate in Codex CLI.

Usage: hooks_wire.py hook | unhook

Codex merges hooks from ``~/.codex/hooks.json`` (and config.toml, which this
script never touches - TOML round-trips lose comments, JSON does not). The
file is shared with the user's own hooks, so the discipline is the same as
for Claude Code settings: append exactly one entry recognised later by its
command string, never reorder or rewrite foreign ones, write atomically with
a timestamped backup, and unwire removes only what is ours.

Schema verified against Codex CLI 0.146.0 (docs + the binary's embedded JSON
schema): the Claude-style {"hooks": {"PreToolUse": [...]}} envelope, matcher
is a regex over the tool name (shell arrives as "Bash", so ^Bash$), timeout
in seconds. Codex asks the user to TRUST new hooks on first run - the caller
should say so.

Prints one word the caller can branch on: ok / foreign / skip / none.
Respects $HOME, so tests run against a sandbox home.
"""
import fcntl
import json
import os
import stat
import sys
import time

HOOKS = os.path.join(os.path.expanduser("~"), ".codex", "hooks.json")
LOCK = os.path.join(os.path.expanduser("~"), ".codex", ".coffee-paladin-hooks.lock")
GATE_MARK = "coffee-paladin hook-gate"


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


def _is_ours(hook):
    return isinstance(hook, dict) and GATE_MARK in str(hook.get("command", ""))


def hook_wire():
    if not os.path.isdir(os.path.dirname(HOOKS)):
        print("skip")           # no ~/.codex = no Codex CLI; never create it
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
    pre = hooks.get("PreToolUse")
    if pre is None:
        pre = []
    if not isinstance(pre, list):
        print("foreign")
        return
    for group in pre:
        if isinstance(group, dict) and any(_is_ours(h) for h in group.get("hooks") or []):
            print("ok")
            return
    pre.append({"matcher": "^Bash$",
                "hooks": [{"type": "command", "command": gate_command(),
                           "timeout": 10,
                           "statusMessage": "coffee-paladin thermal gate"}]})
    hooks["PreToolUse"] = pre
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
