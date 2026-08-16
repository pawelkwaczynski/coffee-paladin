#!/usr/bin/env python3
"""Wire or unwire the coffee-paladin thermal gate in Grok Build.

Usage: hooks_wire.py hook | unhook

Grok discovers hooks from every ``~/.grok/hooks/*.json`` file and merges them,
so unlike Claude Code there is no shared settings file to edit: the paladin
OWNS one file (coffee-paladin.json) and never reads or touches any other.
Wiring writes that file, unwiring removes it - a stranger's hooks cannot be
harmed because they live in files we never open.

Registered shape (verified against Grok's bundled user guide, 10-hooks.md):
the Claude-style {"hooks": {"PreToolUse": [...]}} envelope, matcher "Bash"
(Grok aliases it to run_terminal_command), command hooks with a timeout.
The command path is expanded at wire time: the docs promise ${VAR} expansion,
not tilde expansion, and a hook that silently never runs is the worst outcome.

Prints one word the caller can branch on: ok / skip / none.
Respects $HOME, so tests run against a sandbox home.
"""
import json
import os
import sys

HOOK_DIR = os.path.join(os.path.expanduser("~"), ".grok", "hooks")
HOOK_FILE = os.path.join(HOOK_DIR, "coffee-paladin.json")


def gate_command():
    return os.path.join(os.path.expanduser("~"), ".local", "bin",
                        "coffee-paladin") + " hook-gate"


def hook_wire():
    if not os.path.isdir(os.path.dirname(HOOK_DIR)):
        print("skip")           # no ~/.grok = no Grok Build; never create it
        return
    entry = {"hooks": {"PreToolUse": [
        {"matcher": "Bash",
         "hooks": [{"type": "command", "command": gate_command(), "timeout": 10}]}]}}
    try:
        if os.path.exists(HOOK_FILE) and json.load(open(HOOK_FILE)) == entry:
            print("ok")
            return
    except ValueError:
        pass                    # our own file gone bad: rewrite it below
    os.makedirs(HOOK_DIR, exist_ok=True)
    tmp = "%s.tmp.%d" % (HOOK_FILE, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(entry, f, indent=2)
        f.write("\n")
    os.replace(tmp, HOOK_FILE)
    print("ok")


def hook_unwire():
    if not os.path.exists(HOOK_FILE):
        print("none")
        return
    os.remove(HOOK_FILE)
    print("ok")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "hook":
        hook_wire()
    elif len(sys.argv) >= 2 and sys.argv[1] == "unhook":
        hook_unwire()
    else:
        print(__doc__)
        sys.exit(2)
