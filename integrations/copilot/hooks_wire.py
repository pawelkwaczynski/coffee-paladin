#!/usr/bin/env python3
"""Wire or unwire the coffee-paladin thermal gate in GitHub Copilot CLI.

Usage: hooks_wire.py hook | unhook

Copilot CLI loads every ``*.json`` file in its user hooks directory
(``$COPILOT_HOME/hooks``, by default ``~/.copilot/hooks``) and adds them up,
so, as with Grok, the paladin OWNS one file (coffee-paladin.json) and never
opens any other. Wiring writes that file, unwiring removes it.

Registered shape (verified 23.10 against docs.github.com, hooks reference):
``{"version": 1, "hooks": {"preToolUse": [...]}}``, a ``bash`` command with
``timeoutSec`` in seconds, ``matcher`` a regex anchored over the tool name.
The camelCase event name matters: it selects the payload with toolName and
toolArgs, which the gate recognises and answers with Copilot's own JSON on
stdout and exit 0. Copilot fails CLOSED on a crashed preToolUse hook - any
non-zero exit, including a missing binary's 127, denies the tool call - so
the command ends in ``|| true``: a broken or uninstalled gate lets work
through instead of stopping every shell command. Exit 2 is never used here;
``|| true`` would turn it into an allow anyway, so the deny lives on stdout.

Copilot reads hook files at startup: a running session needs a restart.

Prints one word the caller can branch on: ok / skip / none.
Respects $HOME and $COPILOT_HOME, so tests run against a sandbox home.
"""
import json
import os
import shlex
import sys


def copilot_dir():
    return os.environ.get("COPILOT_HOME") or os.path.join(os.path.expanduser("~"), ".copilot")


def hook_file():
    return os.path.join(copilot_dir(), "hooks", "coffee-paladin.json")


def gate_command():
    binary = os.path.join(os.path.expanduser("~"), ".local", "bin", "coffee-paladin")
    return shlex.quote(binary) + " hook-gate || true"


def entry():
    return {"version": 1, "hooks": {"preToolUse": [
        {"type": "command", "matcher": "bash", "bash": gate_command(), "timeoutSec": 10}]}}


def hook_wire():
    if not os.path.isdir(copilot_dir()):
        print("skip")           # no Copilot home = no Copilot CLI; never create it
        return
    path = hook_file()
    wanted = entry()
    try:
        if os.path.exists(path) and json.load(open(path)) == wanted:
            print("ok")
            return
    except ValueError:
        pass                    # our own file gone bad: rewrite it below
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(wanted, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    print("ok")


def hook_unwire():
    path = hook_file()
    if not os.path.exists(path):
        print("none")
        return
    os.remove(path)
    print("ok")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "hook":
        hook_wire()
    elif len(sys.argv) >= 2 and sys.argv[1] == "unhook":
        hook_unwire()
    else:
        print(__doc__)
        sys.exit(2)
