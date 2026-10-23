#!/usr/bin/env python3
"""Wire or unwire the coffee-paladin thermal gate in GitHub Copilot CLI.

Usage: hooks_wire.py hook | unhook

Copilot CLI loads every ``*.json`` file in its user hooks directory
(``$COPILOT_HOME/hooks``, by default ``~/.copilot/hooks``) and adds them up,
so, as with Grok, the paladin OWNS one file (coffee-paladin.json) and never
opens any other. Wiring writes that file, unwiring removes it.

23.10: owning a file name is not owning whatever sits under it. A file of
that name is ours only while it holds exactly what this script writes;
anything else - another shape, hand edits, a file that does not parse - is
reported as "foreign" and neither replaced nor removed. So no write ever
replaces an existing file and no backup is needed: the file is created only
where none exists, without clobbering one that appears in the meantime.

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

23.10: install.sh wires Copilot CLI on its own, so ``unhook`` leaves a note
(``~/.coffee-paladin/copilot_hook_off``) that later installs respect; ``hook``
run by hand takes it away again.

Copilot reads hook files at startup: a running session needs a restart.

Prints one word the caller can branch on: ok / foreign / skip / none, or
error (exit 1) when the file system said no.
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


def off_marker():
    return os.path.join(os.path.expanduser("~"), ".coffee-paladin", "copilot_hook_off")


def gate_command():
    binary = os.path.join(os.path.expanduser("~"), ".local", "bin", "coffee-paladin")
    return shlex.quote(binary) + " hook-gate || true"


def entry():
    return {"version": 1, "hooks": {"preToolUse": [
        {"type": "command", "matcher": "bash", "bash": gate_command(), "timeoutSec": 10}]}}


def is_ours(path):
    """True only for the exact content this script writes. A file that does
    not parse is not ours to repair; an unreadable one raises OSError."""
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f) == entry()
        except (ValueError, RecursionError):
            return False


def hook_wire():
    if not os.path.isdir(copilot_dir()):
        print("skip")           # no Copilot home = no Copilot CLI; never create it
        return
    path = hook_file()
    if not os.path.lexists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.tmp.%d" % (path, os.getpid())
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(entry(), f, indent=2)
                f.write("\n")
            try:
                os.link(tmp, path)      # atomic and, unlike rename, never replaces a file
            except FileExistsError:
                pass                    # somebody got there first: judged below like any file
        finally:
            os.remove(tmp)
    if not is_ours(path):
        print("foreign")        # a coffee-paladin.json we did not write stays as it is
        return
    try:
        os.remove(off_marker())  # wiring by hand takes back an earlier unhook
    except FileNotFoundError:
        pass
    print("ok")


def hook_unwire():
    # The choice is recorded first, so a foreign file in the way does not lose it.
    if os.path.isdir(os.path.dirname(off_marker())):
        open(off_marker(), "a").close()
    path = hook_file()
    if not os.path.lexists(path):
        print("none")
        return
    if not is_ours(path):
        print("foreign")
        return
    os.remove(path)
    print("ok")


if __name__ == "__main__":
    action = {"hook": hook_wire, "unhook": hook_unwire}.get(sys.argv[1] if len(sys.argv) >= 2 else "")
    if action is None:
        print(__doc__)
        sys.exit(2)
    try:
        action()
    except OSError as e:
        # 23.10: one word for install.sh to branch on, the reason on stderr, no traceback.
        print("error")
        sys.stderr.write("copilot hooks_wire: %s\n" % e)
        sys.exit(1)
