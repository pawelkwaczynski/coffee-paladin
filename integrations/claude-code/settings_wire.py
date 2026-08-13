#!/usr/bin/env python3
"""Wire or unwire the coffee-paladin statusline in Claude Code settings.

Usage: settings_wire.py wire <script-path> [--replace]
       settings_wire.py unwire

Contract, learned the hard way from field failures: somebody else's statusLine
is NEVER touched without an explicit --replace, every write is atomic and
preceded by a timestamped backup, and unwire removes ONLY an entry that points
at the paladin's own script - a dangling entry would break the user's Claude
Code on every session start, and clobbering a foreign one breaks it now.

Prints one word the caller can branch on: ok / foreign / skip / none.
Respects $HOME, so tests run against a sandbox home.
"""
import fcntl
import json
import os
import re
import shlex
import stat
import sys
import time

SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
LOCK = os.path.join(os.path.expanduser("~"), ".claude", ".coffee-paladin-settings.lock")


def load():
    try:
        data = json.load(open(SETTINGS)) if os.path.exists(SETTINGS) else {}
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def save(settings):
    """Atomic write that respects what is already there.

    settings.json can be a symlink (dotfile repos) - the write must land in the
    link's TARGET, not replace the link with a plain file. The existing mode is
    preserved (a 0600 file must not become 0644), a fresh file starts 0600, and
    backups carry nanosecond stamps so two runs in one second cannot clobber
    each other's evidence.
    """
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
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, real)


def command_target(current):
    """The script a statusLine entry executes, tolerating env-var prefixes."""
    if not isinstance(current, dict):
        return None
    try:
        words = shlex.split(str(current.get("command", "")))
    except ValueError:
        return None
    for word in words:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", word):
            continue          # VAR=value prefix (even VAR=/some/path), not the program
        return os.path.expanduser(word)
    return None


def wire(script, replace):
    if not os.path.isdir(os.path.dirname(SETTINGS)):
        print("skip")          # no ~/.claude = no Claude Code; never create it
        return
    settings = load()
    if settings is None:
        print("skip")          # not a JSON object: never "repair" somebody's file
        return
    # refreshInterval is load-bearing, not decoration: without it Claude Code
    # runs the command only on conversation events, so the red OFF for a dead
    # daemon might never appear on an idle session - the exact failure this
    # line exists to catch.
    entry = {"type": "command",
             "command": script.replace(os.path.expanduser("~"), "~", 1),
             "padding": 0, "refreshInterval": 15}
    current = settings.get("statusLine")
    ours = command_target(current) == os.path.expanduser(script)
    if current is not None and not ours and not replace:
        print("foreign")
        return
    if current == entry:
        print("ok")
        return
    settings["statusLine"] = entry
    save(settings)
    print("ok")


def unwire():
    settings = load()
    if not settings or not isinstance(settings.get("statusLine"), dict):
        print("none")
        return
    target = os.path.join(os.path.expanduser("~"), ".coffee-paladin", "statusline.sh")
    if command_target(settings["statusLine"]) != target:
        print("foreign")
        return
    del settings["statusLine"]
    save(settings)
    print("ok")


HOOK_COMMAND = "~/.local/bin/coffee-paladin hook-gate"
RECORDER_COMMAND = "~/.coffee-paladin/agent_hook.py"
RECORDER_EVENTS = ("SessionStart", "PreToolUse", "PostToolUse",
                   "SubagentStart", "SubagentStop", "Stop", "SessionEnd")


def _is_our_hook(hook):
    if not isinstance(hook, dict):
        return False
    command = str(hook.get("command", ""))
    return ("coffee-paladin hook-gate" in command
            or "/.coffee-paladin/agent_hook.py" in command
            or command.startswith(RECORDER_COMMAND))


def hook_wire():
    """Add the thermal pre-exec gate to hooks.PreToolUse.

    The hooks section is a LIST users curate by hand; the only safe operation
    is appending our one entry and never reordering or rewriting theirs. Ours
    is recognised by its command string, so wiring twice stays idempotent.
    """
    if not os.path.isdir(os.path.dirname(SETTINGS)):
        print("skip")
        return
    settings = load()
    if settings is None:
        print("skip")
        return
    hooks = settings.get("hooks")
    if hooks is None:
        hooks = {}
    if not isinstance(hooks, dict):
        print("foreign")       # a shape we do not understand is not ours to fix
        return
    pre = hooks.get("PreToolUse")
    if pre is None:
        pre = []
    if not isinstance(pre, list):
        print("foreign")
        return
    for group in pre:
        if isinstance(group, dict) and any(_is_our_hook(h) for h in group.get("hooks") or []):
            print("ok")
            return
    pre.append({"matcher": "Bash",
                "hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 10}]})
    hooks["PreToolUse"] = pre
    settings["hooks"] = hooks
    save(settings)
    print("ok")


def record_wire():
    """Register the event recorder under every lifecycle event it needs.

    Same list discipline as the gate: append one entry per event, recognise it
    later by its command string, never touch a foreign entry. Tool events get
    a "*" matcher; lifecycle events take none.
    """
    if not os.path.isdir(os.path.dirname(SETTINGS)):
        print("skip")
        return
    settings = load()
    if settings is None:
        print("skip")
        return
    hooks = settings.get("hooks")
    if hooks is None:
        hooks = {}
    if not isinstance(hooks, dict):
        print("foreign")
        return
    changed = False
    for event in RECORDER_EVENTS:
        groups = hooks.get(event)
        if groups is None:
            groups = []
        if not isinstance(groups, list):
            continue              # a shape we do not understand is not ours to fix
        if any(isinstance(g, dict) and any(_is_our_hook(h) for h in g.get("hooks") or [])
               for g in groups):
            continue
        entry = {"hooks": [{"type": "command", "command": RECORDER_COMMAND, "timeout": 10}]}
        if event in ("PreToolUse", "PostToolUse"):
            entry["matcher"] = "*"
        groups.append(entry)
        hooks[event] = groups
        changed = True
    if changed:
        settings["hooks"] = hooks
        save(settings)
    print("ok")


def hook_unwire():
    """Remove ONLY our entries (gate and recorder) from EVERY event section.

    A dangling entry would run a deleted binary at every tool call, and
    removing a stranger's hook would silently change how their agent behaves -
    both are the Iro class of field failure.
    """
    settings = load()
    if not settings or not isinstance(settings.get("hooks"), dict):
        print("none")
        return
    changed = False
    hooks = settings["hooks"]
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
            kept = [h for h in inner if not _is_our_hook(h)]
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
        settings.pop("hooks", None)
    save(settings)
    print("ok")


def locked(action):
    """Serialise wire/unwire: two installers racing on the same settings.json
    could clobber each other's tmp file or lose a concurrent statusLine edit."""
    if not os.path.isdir(os.path.dirname(LOCK)):
        return action()
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return action()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "wire":
        locked(lambda: wire(sys.argv[2], "--replace" in sys.argv[3:]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "unwire":
        locked(unwire)
    elif len(sys.argv) >= 2 and sys.argv[1] == "hook":
        locked(hook_wire)
    elif len(sys.argv) >= 2 and sys.argv[1] == "record":
        locked(record_wire)
    elif len(sys.argv) >= 2 and sys.argv[1] == "unhook":
        locked(hook_unwire)
    else:
        print(__doc__)
        sys.exit(2)
