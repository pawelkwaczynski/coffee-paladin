#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Claude Code statusline integration: the line itself and the wiring.

Two contracts under test.

The LINE: reads status.json and stdin only, exits 0 and silent when the guard
is absent, shouts red OFF when the snapshot is stale, never shows a shield in
dry-run, survives corrupt JSON and hostile process names, drops the session
tail (model/dir) before ever dropping a thermal fact, and speaks the product's
five languages.

The WIRING: somebody else's statusLine survives wire and unwire BYTE FOR BYTE
(the Iro class of field failure: breaking a stranger's setup on install or
leaving a dangling entry on uninstall), our own entry is added only when the
key is free, and every write leaves a timestamped backup.

Run with:  python3 tests/test_claude_statusline.py
Everything runs against a sandbox HOME; the real one is never touched.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = os.path.join(SRC, "integrations", "claude-code", "statusline.sh")
WIRE = os.path.join(SRC, "integrations", "claude-code", "settings_wire.py")

SANDBOX = tempfile.mkdtemp(prefix="tg-statusline-")
STATUS = os.path.join(SANDBOX, "status.json")

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def run_line(snapshot=None, stdin="", env=None, age=0):
    e = dict(os.environ, COFFEE_PALADIN_STATUS=STATUS, TG_BASE=SANDBOX, TG_LANG="en")
    e.pop("NO_COLOR", None)
    e.update(env or {})
    if snapshot is not None:
        json.dump(snapshot, open(STATUS, "w"))
        past = time.time() - age
        os.utime(STATUS, (past, past))
    return subprocess.run(["bash", LINE], input=stdin, env=e,
                          capture_output=True, text=True, timeout=30)


FRESH = {"level": 0, "chip_c": 55.0, "dry_run": False, "chip_sensor": True,
         "paused": [], "demoted": [], "jobs": [], "fans": [2300, 2400],
         "ram_used_gb": 24.0, "ram_total_gb": 48.0, "disk_used_pct": 50,
         "keep_awake": True}

print("=== the line: states ===")
r = run_line(dict(FRESH))
test("1. fresh level 0: one line, shield, no warnings",
     r.returncode == 0 and r.stdout.count("\n") == 1 and "OFF" not in r.stdout
     and "level" not in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH, level=2, top_proc="ffmpeg", top_cpu=590))
test("2. level 2 names the culprit", "level 2" in r.stdout and "ffmpeg" in r.stdout
     and "590%" in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH), age=120)
test("3. stale snapshot shouts OFF with the age", "OFF" in r.stdout
     and "2 min" in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH, dry_run=True))
test("4. dry_run shows watch, never a shield", "watch-only" in r.stdout, repr(r.stdout))
os.remove(STATUS)
r = run_line(None)
test("5. no status.json: exit 0 and silence", r.returncode == 0 and r.stdout == "",
     repr(r.stdout))
open(STATUS, "w").write("{broken")
r = subprocess.run(["bash", LINE], input="", capture_output=True, text=True,
                   env=dict(os.environ, COFFEE_PALADIN_STATUS=STATUS, TG_BASE=SANDBOX))
test("6. corrupt JSON: exit 0 and silence, no traceback",
     r.returncode == 0 and r.stdout == "" and "Traceback" not in r.stderr, r.stderr[-200:])

print("=== the line: sensors, counters, alarms ===")
r = run_line(dict(FRESH, chip_sensor=False, battery_c=33.4))
test("7. no chip sensor: warning shown, battery stands in",
     "no chip sensor" in r.stdout and "B33°" in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH, paused=["a", "b"], demoted=["x"],
                  jobs=[{"queued": True}, {"queued": False}, {"queued": True}]))
test("8. paused, demoted and queue counters", "2" in r.stdout and "Q 2" in r.stdout,
     repr(r.stdout))
fresh_crash = dict(FRESH, last_hard_shutdown={"time": time.strftime("%Y-%m-%d %H:%M:%S%z")})
r = run_line(fresh_crash)
test("9. fresh hard shutdown alarms", "hard shutdown" in r.stdout, repr(r.stdout))
old_crash = dict(FRESH, last_hard_shutdown={"time": "2026-01-01 10:00:00+0100"})
r = run_line(old_crash)
test("10. an old hard shutdown stays quiet", "hard shutdown" not in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH, last_hard_shutdown={"time": ["junk"]}))
test("11. malformed crash record does not break the line",
     r.returncode == 0 and r.stdout.count("\n") == 1, repr(r.stdout))

print("=== the line: session tail and width ===")
session = json.dumps({"model": {"display_name": "Opus"},
                      "workspace": {"current_dir": "/tmp/projekt"}})
r = run_line(dict(FRESH), stdin=session, env={"COLUMNS": "200"})
test("12. wide terminal: model and dir appear", "Opus" in r.stdout
     and "projekt" in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH, paused=["a"]), stdin=session, env={"COLUMNS": "40"})
test("13. narrow terminal: tail drops first, alarms survive",
     "Opus" not in r.stdout and "⏸" in r.stdout, repr(r.stdout))
hostile = json.dumps({"model": {"display_name": "x\x1b[31mB\x01AD"},
                      "workspace": {"current_dir": "/a/b\nc"}})
r = run_line(dict(FRESH, top_proc="bad\x1b[0mname", level=2), stdin=hostile,
             env={"COLUMNS": "200"})
test("14. ANSI and control bytes are stripped from names",
     "\x01" not in r.stdout and "[31m" not in r.stdout.replace("\x1b[31m", "", 0)
     and "\n" == r.stdout[-1], repr(r.stdout))
r = run_line(dict(FRESH), stdin="not json at all")
test("15. garbage stdin does not break the line", r.returncode == 0
     and r.stdout.count("\n") == 1, repr(r.stdout))

print("=== the line: icons, color, language ===")
r = run_line(dict(FRESH), env={"COFFEE_PALADIN_STATUSLINE_ICONS": "ascii"})
test("16. ascii mode: plain words, zero ANSI", "chip 55" in r.stdout
     and "\x1b" not in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH), env={"NO_COLOR": "1"})
test("17. NO_COLOR strips ANSI but keeps icons", "\x1b" not in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH), env={"TERM": "dumb"})
test("18. TERM=dumb falls back to ascii", "chip 55" in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH, dry_run=True), env={"TG_LANG": "pl"})
test("19. PL words", "obserwacja" in r.stdout, repr(r.stdout))
r = run_line(dict(FRESH), age=120, env={"TG_LANG": "ru"})
test("20. RU stale line", "мин тишины" in r.stdout, repr(r.stdout))

print("=== the wiring: a stranger's Claude Code is sacred ===")
HOME2 = tempfile.mkdtemp(prefix="tg-wirehome-")
WENV = dict(os.environ, HOME=HOME2)
SET = os.path.join(HOME2, ".claude", "settings.json")
SCRIPT = os.path.join(HOME2, ".coffee-paladin", "statusline.sh")


def wire(*args):
    return subprocess.run([sys.executable, WIRE, *args], env=WENV,
                          capture_output=True, text=True).stdout.strip()


test("21. no ~/.claude: wire skips and does not create it",
     wire("wire", SCRIPT) == "skip" and not os.path.isdir(os.path.join(HOME2, ".claude")))
os.makedirs(os.path.dirname(SET))
json.dump({"model": "Fable", "permissions": {"allow": ["Read"]}}, open(SET, "w"))
test("22. settings without statusLine: wired with a backup and a live refresh",
     wire("wire", SCRIPT) == "ok"
     and json.load(open(SET))["statusLine"]["command"].endswith("statusline.sh")
     and json.load(open(SET))["statusLine"]["refreshInterval"] == 15
     and any(".bak" in f for f in os.listdir(os.path.dirname(SET))))
test("23. other keys survive the write",
     json.load(open(SET))["model"] == "Fable"
     and json.load(open(SET))["permissions"] == {"allow": ["Read"]})
test("24. wiring twice is idempotent", wire("wire", SCRIPT) == "ok"
     and open(SET).read().count("statusLine") == 1)
test("25. unwire removes our entry", wire("unwire") == "ok"
     and "statusLine" not in json.load(open(SET)))

foreign = {"statusLine": {"type": "command", "command": "/opt/mine/line.sh"},
           "model": "Fable"}
json.dump(foreign, open(SET, "w"), indent=2)
before = open(SET).read()
test("26. foreign statusLine survives wire byte for byte",
     wire("wire", SCRIPT) == "foreign" and open(SET).read() == before)
test("27. ...and survives unwire byte for byte",
     wire("unwire") == "foreign" and open(SET).read() == before)
test("28. --replace consciously takes over",
     wire("wire", SCRIPT, "--replace") == "ok"
     and json.load(open(SET))["statusLine"]["command"].endswith("statusline.sh"))

nerd = {"statusLine": {"type": "command",
                       "command": "COFFEE_PALADIN_STATUSLINE_ICONS=nerd " + SCRIPT}}
json.dump(nerd, open(SET, "w"))
test("28b. re-wiring OUR env-prefixed entry keeps the prefix (a reinstall must "
     "not reset the user's icon style)",
     wire("wire", SCRIPT) == "ok"
     and json.load(open(SET))["statusLine"]["command"].startswith(
         "COFFEE_PALADIN_STATUSLINE_ICONS=nerd ")
     and json.load(open(SET))["statusLine"]["refreshInterval"] == 15)
test("29. unwire recognises our entry behind an env prefix",
     wire("unwire") == "ok" and "statusLine" not in json.load(open(SET)))
tricky = {"statusLine": {"type": "command",
                         "command": "FOO=/some/path /opt/mine/line.sh"}}
json.dump(tricky, open(SET, "w"))
test("30. env value with a path does not fool the matcher",
     wire("unwire") == "foreign")
open(SET, "w").write("{not json")
test("31. corrupt settings.json: wire refuses to 'repair' it",
     wire("wire", SCRIPT) == "skip" and open(SET).read() == "{not json")

print("=== the wiring: symlinks, permissions, hostile text, huge files ===")
real_file = os.path.join(HOME2, "dotfiles-settings.json")
json.dump({"model": "Fable"}, open(real_file, "w"))
os.chmod(real_file, 0o600)
os.remove(SET)
os.symlink(real_file, SET)
r = wire("wire", SCRIPT)
test("32. symlinked settings: write lands in the target, link survives",
     r == "ok" and os.path.islink(SET)
     and json.load(open(real_file)).get("statusLine", {}).get("command", "").endswith("statusline.sh"))
test("33. 0600 stays 0600 after the write",
     oct(os.stat(real_file).st_mode & 0o777) == "0o600",
     oct(os.stat(real_file).st_mode & 0o777))
os.remove(SET)
json.dump({}, open(SET, "w"))

bidi = json.dumps({"model": {"display_name": "evil‮reversed"},
                   "workspace": {"current_dir": "/tmp/a⁦b\x9bc"}})
r = run_line(dict(FRESH), stdin=bidi, env={"COLUMNS": "200"})
test("34. bidi overrides and C1 controls are stripped",
     "‮" not in r.stdout and "⁦" not in r.stdout
     and "\x9b" not in r.stdout, repr(r.stdout))

open(STATUS, "w").write("x" * (2 * 1024 * 1024))
r = subprocess.run(["bash", LINE], input="", capture_output=True, text=True,
                   env=dict(os.environ, COFFEE_PALADIN_STATUS=STATUS, TG_BASE=SANDBOX))
test("35. an oversized status.json is never parsed: exit 0, silence",
     r.returncode == 0 and r.stdout == "", repr(r.stdout[:80]))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
