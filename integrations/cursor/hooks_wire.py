#!/usr/bin/env python3
"""Wire or unwire the coffee-paladin thermal gate in Cursor (experimental).

Usage: hooks_wire.py hook | unhook

Cursor reads user hooks from ``~/.cursor/hooks.json``, a file SHARED with the
user's own hooks, so the discipline is the Codex adapter's: append exactly one
entry recognised later by its command string, never reorder or rewrite foreign
ones, write atomically with a timestamped backup, unwire removes only ours.

Registered shape (read 23.10 from cursor.com/docs/hooks): ``{"version": 1,
"hooks": {"beforeShellExecution": [{"command": ..., "timeout": 10}]}}`` with
the timeout in seconds. The gate recognises Cursor's payload by its
cursor_version field and answers a deny with Cursor's own JSON and exit 0. No
matcher (for this event it filters the command text, which is the gate's job)
and no failClosed: a broken gate must let work through.

23.10: an entry is ours only when it sits under beforeShellExecution and its
command is exactly the one this script writes. A stranger's script that merely
mentions "coffee-paladin hook-gate" is theirs and is never removed.

Not tried against a live Cursor yet, which is why install.sh does not run it:
the docs leave open whether an empty stdout at exit 0 - the gate's way of
saying "allowed" - counts as no output or as invalid JSON, which Cursor treats
as a block for permission hooks. The command ends in ``|| true`` like the
Copilot one, and here that is a trade, not a guarantee: it stops a stray exit
2 from reading as a deny, but Cursor already lets other non-zero exits through,
and ``|| true`` turns a missing binary's 127 into exit 0 with an empty stdout -
the same open question as an allow. Pilot on a live Cursor before calling it
wired: a light command (echo) runs, a bare encoder is refused with the hint,
and with the binary renamed away echo still runs.

Prints one word the caller can branch on: ok / foreign / skip / none.
Respects $HOME, so tests run against a sandbox home.
"""
import fcntl
import json
import os
import shlex
import stat
import sys
import time

CURSOR_DIR = os.path.join(os.path.expanduser("~"), ".cursor")
HOOKS = os.path.join(CURSOR_DIR, "hooks.json")
LOCK = os.path.join(CURSOR_DIR, ".coffee-paladin-hooks.lock")
EVENT = "beforeShellExecution"
MISSING = object()
BROKEN = object()


def gate_command():
    binary = os.path.join(os.path.expanduser("~"), ".local", "bin", "coffee-paladin")
    return shlex.quote(binary) + " hook-gate || true"


def load():
    if not os.path.exists(HOOKS):
        return MISSING
    try:
        return json.load(open(HOOKS))
    except ValueError:
        return BROKEN


def save(data):
    real = os.path.realpath(HOOKS)
    mode = 0o600
    if os.path.exists(real):
        mode = stat.S_IMODE(os.stat(real).st_mode)
        backup = HOOKS + ".coffee-paladin.%d.bak" % time.time_ns()
        with open(real, "rb") as src:
            body = src.read()
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(body)
    tmp = "%s.tmp.%d" % (real, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, real)


def _is_ours(hook):
    return isinstance(hook, dict) and hook.get("command") == gate_command()


def hook_wire():
    if not os.path.isdir(CURSOR_DIR):
        print("skip")           # no ~/.cursor = no Cursor; never create it
        return
    data = load()
    entry = {"command": gate_command(), "timeout": 10}
    if data is MISSING:
        save({"version": 1, "hooks": {EVENT: [entry]}})
        print("ok")
        return
    if not isinstance(data, dict):
        print("skip")           # not a JSON object: never "repair" somebody's file
        return
    hooks = data.get("hooks")
    if hooks is None:
        hooks = {}
    if data.get("version") != 1 or not isinstance(hooks, dict):
        print("foreign")        # a schema we do not know is not ours to rewrite
        return
    event = hooks.get(EVENT)
    if event is None:
        event = []
    if not isinstance(event, list):
        print("foreign")
        return
    if any(_is_ours(h) for h in event):
        print("ok")
        return
    event.append(entry)
    hooks[EVENT] = event
    data["hooks"] = hooks
    save(data)
    print("ok")


def hook_unwire():
    data = load()
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
        print("none")
        return
    hooks = data["hooks"]
    entries = hooks.get(EVENT)
    if not isinstance(entries, list):
        print("none")
        return
    kept = [h for h in entries if not _is_ours(h)]
    if len(kept) == len(entries):
        print("none")
        return
    if kept:
        hooks[EVENT] = kept
    else:
        del hooks[EVENT]        # an event we emptied held only ours
    save(data)
    print("ok")


def locked(action):
    """Serialise hook/unhook: two racing writers on a shared config could
    clobber each other's tmp file or drop a concurrent edit (same contract as
    the Claude adapter's lock)."""
    if not os.path.isdir(CURSOR_DIR):
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
