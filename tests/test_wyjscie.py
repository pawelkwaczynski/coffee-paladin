#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The way out and the way in: uninstall from the menu, and a window without the bar.

Both exist because of one report: a status item that macOS silently declines to
draw leaves a running program with no way in, and the person who cannot get it
working then has no way out either.

  A. `coffee-paladin panel` - the bar-independent entry point,
  B. the uninstaller is where the app can reach it,
  C. the menu offers uninstall, above quit, and asks twice before deleting data,
  D. the uninstaller survives being told to kill its own parent.

Run with:  python3 tests/test_wyjscie.py
Does not touch the real ~/.coffee-paladin.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
ok = fail = 0


def check(name, condition, detail=""):
    global ok, fail
    if condition:
        ok += 1
        print("  [PASS] %s" % name)
    else:
        fail += 1
        print("  [FAIL] %s %s" % (name, detail))


def guard(*args):
    env = dict(os.environ, TG_BASE=BASE, TG_LANG="en")
    return subprocess.run([sys.executable, os.path.join(SRC, "guard.py")] + list(args),
                          capture_output=True, text=True, env=env, timeout=60)


print("=" * 78)
print("A. A WINDOW WITHOUT THE MENU BAR")
print("=" * 78)

# Only the bar can open windows. Whether it is running decides EVERYTHING here,
# so the test runs both cases instead of grepping for the code that checks it.
signal_file = os.path.join(BASE, "show_window")
bar_is_running = subprocess.run(
    ["launchctl", "list"], capture_output=True, text=True).stdout
bar_is_running = any(l.split()[2:3] == ["pl.pawel.coffee-paladin-bar"] and not l.startswith("-")
                     for l in bar_is_running.splitlines() if len(l.split()) >= 3)

r = guard("panel")
if bar_is_running:
    check("1. with the bar running, `panel` succeeds", r.returncode == 0, r.stderr.strip())
    check("2. and leaves exactly the signal the bar watches for",
          os.path.exists(signal_file)
          and io.open(signal_file, encoding="utf-8").read().strip() == "panel")
    check("3. and says so instead of exiting silently", "panel" in r.stdout.lower(), r.stdout)
    os.remove(signal_file)
else:
    check("1. with the bar stopped, `panel` FAILS instead of promising a window",
          r.returncode != 0, "code %d" % r.returncode)
    check("2. and leaves no signal behind to fire at the next login",
          not os.path.exists(signal_file))
    check("3. and says how to start the bar",
          "kickstart" in r.stderr, r.stderr.strip())

r = guard("--nonsense")
check("4. an unknown argument still fails and prints the usage line",
      r.returncode == 2 and "panel" in r.stderr, r.stderr.strip())

# The signal must never be written by a command line the tool rejects.
r = guard("panel", "--nonsense")
check("4b. `panel` mixed with nonsense is rejected and writes nothing",
      r.returncode == 2 and not os.path.exists(signal_file), r.stderr.strip())

bar_source = io.open(os.path.join(SRC, "heatbar.swift"), encoding="utf-8").read()
check("5. the bar actually handles that signal",
      'case "panel": PaladinPanel.shared.toggle()' in bar_source)
# The panel must not depend on the very thing that is missing.
check("6. the panel places itself even when the status button has no window",
      "Bar.shared?.item.button" in bar_source and "NSScreen" in bar_source)

heat_source = io.open(os.path.join(SRC, "heat"), encoding="utf-8").read()
check("7. `heat` tells a person about it when the bar is running",
      "coffee-paladin panel" in heat_source and "def bar_running" in heat_source)

print("=" * 78)
print("B. THE UNINSTALLER IS WHERE THE APP LOOKS")
print("=" * 78)

installer = io.open(os.path.join(SRC, "install.sh"), encoding="utf-8").read()
check("8. install.sh copies uninstall.sh into the data directory",
      'cp "$SRC/uninstall.sh" "$BASE/uninstall.sh"' in installer)
check("9. and makes it executable", 'chmod 755 "$BASE/uninstall.sh"' in installer)
check("10. the app looks for it exactly there",
      'base + "/uninstall.sh"' in bar_source)
check("11. a missing script is reported, not silently ignored",
      "uninstall.sh not found" in bar_source)

print("=" * 78)
print("C. THE MENU OFFERS THE WAY OUT, AND ASKS TWICE")
print("=" * 78)

uninstall_at = bar_source.find('T("Uninstall coffee-paladin…")')
quit_at = bar_source.find('T("Quit coffee-paladin (protection stops)"),\n                                action:')
check("12. uninstall sits ABOVE quit in the menu",
      0 < uninstall_at < quit_at, "uninstall %d, quit %d" % (uninstall_at, quit_at))
check("13. deleting the data is a checkbox, not a button next to 'Uninstall'",
      'checkboxWithTitle: T("Delete the history and the black box too")' in bar_source)
check("14. and it triggers a SECOND question before anything is deleted",
      "if purge && !confirmPurge() { return }" in bar_source)
check("15. neither window uninstalls on Enter",
      bar_source.count('[T("Uninstall"), T("Cancel")], defaultIndex: 1') == 1
      and bar_source.count('[T("Delete everything"), T("Cancel")], defaultIndex: 1') == 1)
for key in ("Uninstall coffee-paladin…", "Uninstall", "Delete everything",
            "Delete the black box as well?"):
    for lang in ("PL", "RU", "ZH", "ES"):
        block = bar_source.split("let %s: [String: String] = [" % lang)[1].split("\n]\n")[0]
        check("16. %r is translated into %s" % (key[:28], lang), '"%s":' % key in block)

print("=" * 78)
print("D. THE UNINSTALLER OUTLIVES ITS PARENT")
print("=" * 78)

# The script's first act is to boot out the job that started it, and launchd
# takes the whole job down. Without a session of its own the uninstaller dies
# halfway through, leaving a Mac with no daemon and half the files in place.
check("17. the app starts it in a session of its own", "os.setsid()" in bar_source)

# Prove the mechanism instead of trusting it: a parent that kills its own
# process group must not take the grandchild with it.
proof = os.path.join(BASE, "survived")
script = os.path.join(BASE, "slow.sh")
io.open(script, "w", encoding="utf-8").write("#!/bin/bash\nsleep 2\ntouch %s\n" % proof)
os.chmod(script, 0o755)
launcher = ("import os, signal, subprocess, sys, time\n"
            "os.setsid()\n"
            "subprocess.Popen(['/bin/bash', %r])\n" % script)
parent = subprocess.Popen([sys.executable, "-c",
                           "import os, subprocess, sys, time\n"
                           "os.setpgrp()\n"
                           "subprocess.Popen([sys.executable, '-c', %r])\n"
                           "time.sleep(0.3)\n"
                           "os.killpg(os.getpgid(0), 9)\n" % launcher])
parent.wait()
deadline = __import__("time").time() + 8
while not os.path.exists(proof) and __import__("time").time() < deadline:
    __import__("time").sleep(0.2)
check("18. a grandchild in its own session survives the parent's group being killed",
      os.path.exists(proof))

print("=" * 78)
print("F. ONE COMMAND FOR A BAR THAT DOES NOT FIT")
print("=" * 78)

# The menu has the same three presets, but a person who cannot see the icon
# cannot open the menu either. This has to work from a terminal, in one line.
layout = os.path.join(BASE, "heatbar.json")
r = guard("bar", "icon-only")
saved = json.load(io.open(layout, encoding="utf-8"))["show"] if os.path.exists(layout) else {}
check("25. `bar icon-only` leaves nothing on the bar but the icon",
      r.returncode == 0 and saved and not any(saved.values()), "%s %s" % (r.stderr.strip(), saved))
bar_source_now = io.open(os.path.join(SRC, "heatbar.swift"), encoding="utf-8").read()
check("26. and it writes every key the bar knows, so nothing falls back to a default",
      set(saved) == {c.strip() for c in bar_source_now.split("case chip,")[1]
                     .split("\n")[0].split(",")} | {"chip"},
      sorted(saved))

r = guard("bar", "full")
saved = json.load(io.open(layout, encoding="utf-8"))["show"]
check("27. `bar full` puts everything back", r.returncode == 0 and all(saved.values()))

r = guard("bar", "chip")
saved = json.load(io.open(layout, encoding="utf-8"))["show"]
check("28. `bar chip` is the middle ground: the icon and one number",
      saved["chip"] and not any(v for k, v in saved.items() if k != "chip"))

for bad in ([], ["icon-only", "full"], ["nonsense"]):
    r = guard("bar", *bad)
    check("29. `bar %s` is refused instead of guessing" % (" ".join(bad) or "(nothing)"),
          r.returncode == 2, r.stderr.strip())
for bad in (["chip"], ["--once", "bar", "chip"], ["bar", "chip", "panel"]):
    r = guard(*bad)
    check("29b. `%s` is refused: the preset is not a command of its own" % " ".join(bad),
          r.returncode == 2, r.stderr.strip())

# THE regression that matters: the rescue commands ran into the daemon's own
# exclusivity lock, so they failed on every Mac where the daemon was working -
# that is, on every Mac where somebody would need them. A fresh TG_BASE hid it.
lock_file = os.path.join(BASE, "guard.lock")
import fcntl
held = open(lock_file, "w")
fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
for command in (["bar", "chip"], ["panel"], ["status"], ["--version"]):
    r = guard(*command)
    check("29c. `%s` still answers while the daemon holds the lock" % " ".join(command),
          "already running" not in (r.stdout + r.stderr), (r.stdout + r.stderr).strip()[:80])
held.close()
# The check above must FAIL on the old code, so prove the lock was really held:
# otherwise the assertion passes for the wrong reason.
held2 = open(lock_file, "w")
fcntl.flock(held2.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
probe = subprocess.run(
    [sys.executable, "-c",
     "import fcntl, sys\n"
     "fh = open(sys.argv[1], 'w')\n"
     "try:\n"
     "    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
     "except OSError:\n"
     "    sys.exit(7)\n", lock_file], capture_output=True, timeout=30)
check("29d. and that lock was genuinely held, so the check above means something",
      probe.returncode == 7, "probe exit %d" % probe.returncode)
held2.close()

check("30. the installer says the command at the moment it matters",
      "coffee-paladin bar icon-only" in installer)

print("=" * 78)
print("E. THE UNINSTALLER'S OWN PROMISES")
print("=" * 78)

uninstaller = io.open(os.path.join(SRC, "uninstall.sh"), encoding="utf-8").read()
# The guard freezes whole process groups. Resuming the leader alone would leave
# its children stopped with nothing left on the Mac that knows they exist.
check("19. it resumes the process GROUP, not only the leader",
      "os.killpg(int(pgid), signal.SIGCONT)" in uninstaller)
# Stopping the display before the thing that pauses processes leaves a Mac that
# is still being managed by something invisible.
daemon_at = uninstaller.find("for A in pl.pawel.coffee-paladin pl.pawel.coffee-paladin-bar")
check("20. the daemon is stopped before the menu bar", daemon_at > 0)
check("21. a bootout that failed is reported, not swallowed",
      "STILL_RUNNING" in uninstaller and "still loaded:" in uninstaller)
check("22. the installed copy of the script removes itself, and not while bash reads it",
      "sleep 2; rm -f \"$SELF\"" in uninstaller)

# Test the resume logic by running the script's OWN python block, never the
# script itself. uninstall.sh talks to launchctl and to absolute paths like
# /Applications, and neither of those cares about a fake HOME: running it here
# once uninstalled the live protection on the machine running the tests.
# The heredoc marker is followed by the rest of the shell line ("2>/dev/null
# || true"), so the python starts on the NEXT line.
resume_block = uninstaller.split("<<'PY'", 1)[1].split("\n", 1)[1].split("\nPY", 1)[0]
fake = tempfile.mkdtemp()
state_file = os.path.join(fake, "state.json")
victim = subprocess.Popen(["/bin/sleep", "30"])
os.kill(victim.pid, __import__("signal").SIGSTOP)
io.open(state_file, "w", encoding="utf-8").write(
    '{"paused": {"%d": {"comm": "sleep", "pgid": %d}}}' % (victim.pid, os.getpgid(victim.pid)))
run = subprocess.run([sys.executable, "-", state_file], input=resume_block,
                     capture_output=True, text=True, timeout=60)
state = subprocess.run(["ps", "-o", "stat=", "-p", str(victim.pid)],
                       capture_output=True, text=True).stdout.strip()
check("23. the resume step really wakes a stopped process up",
      not state.startswith("T"), "ps stat %r, output %r %r" % (state, run.stdout, run.stderr))
victim.kill()
victim.wait()

# A state file from a crashed daemon, a truncated one, or one naming processes
# that are long gone must not stop the uninstall.
for broken in ('{"paused": {"999999": {"comm": "ghost", "pgid": 999999}}}',
               '{"paused": {"nonsense": null}}', "not json at all", ""):
    io.open(state_file, "w", encoding="utf-8").write(broken)
    run = subprocess.run([sys.executable, "-", state_file], input=resume_block,
                         capture_output=True, text=True, timeout=60)
    check("24. a broken state file does not stop the uninstall: %r" % broken[:28],
          run.returncode == 0, run.stderr.strip())
shutil.rmtree(fake, ignore_errors=True)

print("=" * 78)
print("  RESULT: %d/%d" % (ok, ok + fail))
shutil.rmtree(BASE, ignore_errors=True)
sys.exit(1 if fail else 0)
