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
    else:
        print(__doc__)
        sys.exit(2)
