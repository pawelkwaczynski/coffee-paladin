#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The pre-exec gate for AI coding agents (`coffee-paladin hook-gate`).

Contract under test: exit 2 with a safe-run hint on stderr for a HEAVY bare
command, exit 0 for everything else - already-supervised commands, version
questions, non-shell tools, log files whose NAMES contain a heavy word, and
every malformed input (a broken gate must never hold a coding session
hostage). The gate reads stdin only; it never measures, never signals.

Run with:  python3 tests/test_hook_gate.py
Uses a temporary TG_BASE; nothing on the real machine is touched.
"""
import json
import os
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-hookgate-")
json.dump({}, open(os.path.join(BASE, "config.json"), "w"))
ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en")
ENV.pop("PALADIN_HOOK", None)

passed = 0
total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           "" if condition else "  -> %s" % detail))
    passed += condition


def gate(payload, env_extra=None):
    e = dict(ENV)
    e.update(env_extra or {})
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, os.path.join(SRC, "guard.py"), "hook-gate"],
                         input=body, env=e, capture_output=True, text=True, timeout=30)


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


print("=== blocks ===")
r = gate(bash("ffmpeg -i in.mov -c:v libx265 out.mp4"))
test("1. bare ffmpeg is blocked with the safe-run hint",
     r.returncode == 2 and "safe-run" in r.stderr, "rc=%s %r" % (r.returncode, r.stderr[:120]))
r = gate(bash("cd /tmp && nice /opt/homebrew/bin/ffmpeg -i a.mov b.mp4"))
test("2. path prefix and nice do not hide the tool", r.returncode == 2, r.stderr[:120])
r = gate(bash("ollama run qwen3 'hello'"))
test("3. ollama run is heavy", r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("echo start; cadical proof.cnf"))
test("4. heavy after a separator is caught", r.returncode == 2, "rc=%s" % r.returncode)

print("=== allows ===")
for name, cmd in [
    ("5. already supervised", "safe-run --cores 3 -- ffmpeg -i a.mov b.mp4"),
    ("6. version question", "ffmpeg -version"),
    ("7. a log NAMED after a heavy tool", "cat /tmp/cadical.log"),
    ("8. ollama list is light", "ollama list"),
    ("9. plain light work", "git status && ls -la"),
]:
    r = gate(bash(cmd))
    test(name, r.returncode == 0, "rc=%s %r" % (r.returncode, r.stderr[:100]))

r = gate({"tool_name": "Read", "tool_input": {"file_path": "/tmp/ffmpeg"}})
test("10. non-shell tools pass untouched", r.returncode == 0)
r = gate({"tool_name": "Monitor", "tool_input": {"command": "ffmpeg -i a.mov b.mp4"}})
test("10b. Monitor runs commands too: a bare encoder is refused", r.returncode == 2, r.returncode)
r = gate({"tool_name": "Monitor", "tool_input": {"command": "tail -f enc.log | grep --line-buffered frame"}})
test("10c. Monitor watching a log passes", r.returncode == 0, r.returncode)

print("=== the adversarial round's catches stay caught ===")
r = gate(bash("grep ffmpeg README.md | head -5"))
test("10b. a heavy NAME as an argument to grep is data, not execution",
     r.returncode == 0, "rc=%s %r" % (r.returncode, r.stderr[:100]))
r = gate(bash("echo safe-run; ffmpeg -i a.mov b.mp4"))
test("10c. 'safe-run' in a NEIGHBOURING segment lends no supervision",
     r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("FOO=bar ffmpeg -i a.mov b.mp4"))
test("10d. an env assignment prefix does not hide the tool",
     r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("env LC_ALL=C nice -n 10 ffmpeg -i a.mov b.mp4"))
test("10e. wrapper chains are skipped down to the real argv0",
     r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("git log && x265 --input in.y4m -o out.hevc"))
test("10f. heavy after && is caught", r.returncode == 2, "rc=%s" % r.returncode)
r = gate(bash("ffmpeg -i a.mov b.mp4"), env_extra={"PALADIN_HOOK": "off"})
test("11. PALADIN_HOOK=off disables the gate", r.returncode == 0)

print("=== fail-open on anything unexpected ===")
for name, payload in [
    ("12. garbage stdin", "not json at all"),
    ("13. empty stdin", ""),
    ("14. JSON but not an object", "[1,2,3]"),
    ("15. missing tool_input", '{"tool_name": "Bash"}'),
    ("16. command of a wrong type", '{"tool_name": "Bash", "tool_input": {"command": 42}}'),
]:
    r = gate(payload)
    test(name + " -> allow", r.returncode == 0, "rc=%s" % r.returncode)

print("=== the Grok Build dialect (camelCase + stdout decision) ===")
r = gate({"toolName": "run_terminal_command", "toolInput": {"command": "ffmpeg -i a.mov b.mp4"}})
test("18. camelCase fields are understood (a wired gate must never be blind)",
     r.returncode == 2, "rc=%s" % r.returncode)
r = gate({"toolName": "run_terminal_command", "toolInput": {"command": "git status"}})
test("18b. ...and a light command still passes", r.returncode == 0, "rc=%s" % r.returncode)
r = gate({"toolName": "run_terminal_command",
          "toolInput": {"command": "ffmpeg -i a.mov b.mp4"}},
         env_extra={"GROK_HOOK_EVENT": "pre_tool_use"})
try:
    decision = json.loads(r.stdout)
except ValueError:
    decision = {}
test("19. under Grok's env marker the deny is an explicit stdout decision",
     r.returncode == 2 and decision.get("decision") == "deny"
     and "safe-run" in str(decision.get("reason", "")), repr(r.stdout[:120]))
r = gate(bash("ffmpeg -i a.mov b.mp4"))
test("19b. without the marker stdout stays CLEAN (Claude parses its own schema there)",
     r.returncode == 2 and r.stdout.strip() == "", repr(r.stdout[:120]))
r = gate({"toolName": "read_file", "toolInput": {"command": "ffmpeg fake"}})
test("20. non-shell camelCase tools pass untouched", r.returncode == 0)

print("=== the Antigravity dialect (toolCall + mandatory stdout decision) ===")
r = gate({"toolCall": {"name": "run_command",
                       "args": {"CommandLine": "ffmpeg -i a.mov b.mp4"}}})
try:
    decision = json.loads(r.stdout)
except ValueError:
    decision = {}
test("21. a heavy toolCall is denied via the stdout decision, exit 0 (no exit "
     "contract there - nonzero could read as 'hook crashed', not 'deny')",
     r.returncode == 0 and decision.get("decision") == "deny"
     and "safe-run" in str(decision.get("reason", "")),
     "rc=%s %s" % (r.returncode, repr(r.stdout[:120])))
r = gate({"toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}}})
try:
    decision = json.loads(r.stdout)
except ValueError:
    decision = {}
test("22. a light toolCall gets an EXPLICIT allow (no exit-code contract there)",
     r.returncode == 0 and decision.get("decision") == "allow", repr(r.stdout[:120]))
r = gate({"toolCall": {"name": "view_file", "args": {"CommandLine": "x"}}})
test("23. non-shell toolCall passes silently", r.returncode == 0)
r = gate(bash("git status"))
test("24. outside Antigravity a light command keeps stdout CLEAN",
     r.returncode == 0 and r.stdout.strip() == "", repr(r.stdout[:60]))

print("=== quoted substitutions and informational queries ===")
for name, cmd, blocked in [
    ("single-quoted bash body stays supervised",
     "safe-run -- bash -c 'a; ffmpeg -i x y; echo \"$(ffprobe z)\"'", None),
    ("double-quoted bash body stays supervised",
     'safe-run -- bash -c "ffmpeg -i a b && ffmpeg -i c d"; echo "$(basename x)"', None),
    ("field command with an outer double-quoted bash body",
     'mkdir -p "$D" && safe-run --cpu-limit 50 -- bash -c '
     '"ffmpeg -i a.mp3 x.m4a && ffmpeg -i a.mp3 y.m4a"; '
     'for f in "$D"/*.m4a; do echo "$(basename $f): $(safe-run -- ffprobe $f) s"; done', None),
    ("field command with a single-quoted bash body",
     'safe-run --cpu-limit 50 -- bash -c '
     '\'ffmpeg -i a.mp3 x.m4a; ffmpeg -i a.mp3 y.m4a; '
     'for f in "$D"/*.m4a; do echo "$(basename "$f"): $(ffprobe "$f") s"; done\'', None),
    ("backticks in a single-quoted assignment are text",
     "L='see `ffmpeg -hide_banner -filters` for the list'", None),
    ("double-quoted substitution executes ffmpeg", 'echo "$(ffmpeg -i x y)"', "ffmpeg"),
    ("assignment substitution executes ffmpeg", "x=$(ffmpeg -i a b)", "ffmpeg"),
    ("backtick substitution executes ffmpeg", "echo `ffmpeg -i a b`", "ffmpeg"),
    ("nested substitution executes ffmpeg", 'echo "a $(echo "$(ffmpeg -i a b)")"', "ffmpeg"),
    ("single-quoted substitution is text", "echo 'it is $(ffmpeg -i a b)'", None),
    ("ffmpeg filters is informational", "ffmpeg -hide_banner -filters", None),
    ("ffmpeg encoders is informational", "ffmpeg -v quiet -encoders", None),
    ("ffmpeg help topic is informational", "ffmpeg -h encoder=libx264", None),
    ("ffmpeg input still runs", "ffmpeg -hide_banner -i a.mp4 b.mkv", "ffmpeg"),
]:
    r = gate(bash(cmd))
    if blocked:
        ok = r.returncode == 2 and "'%s'" % blocked in r.stderr
    else:
        ok = r.returncode == 0 and "deny" not in r.stdout
    test(name, ok, "rc=%s %r" % (r.returncode, r.stderr[:160]))

r = gate(bash("cd /x && S=1; ffmpeg -i a b"))
test("hint names the offending segment",
     r.returncode == 2 and "safe-run -- ffmpeg -i a b" in r.stderr
     and "safe-run -- cd" not in r.stderr,
     "rc=%s %r" % (r.returncode, r.stderr[:200]))

print("=== comments, incomplete input and double-dash queries ===")
for name, cmd, blocked in [
    ("apostrophe in a trailing comment", "ffmpeg -i in.mp4 out.mkv  # don't forget", "ffmpeg"),
    ("substitution text in a trailing comment",
     "ffmpeg -i a b | tee log # it's $(fine)", "ffmpeg"),
    ("complete line before an unterminated quote",
     'ffmpeg -i a b\necho "unterminated', "ffmpeg"),
    ("ffmpeg double-dash help", "ffmpeg --help", None),
    ("ffmpeg double-dash version", "ffmpeg --version", None),
    ("ffmpeg double-dash filters", "ffmpeg --hide_banner --filters", None),
    ("ffmpeg help with an input still runs", "ffmpeg --help -i a b", "ffmpeg"),
    ("simple trailing comment", "ffmpeg -i a b # note", "ffmpeg"),
    ("heavy command in a comment is ignored", "echo hi # ffmpeg -i a b", None),
    ("substitution in a comment is ignored", "echo hi # $(ffmpeg -i a b)", None),
    ("hash inside quotes is text", 'echo "# not a comment"; ffmpeg -i a b', "ffmpeg"),
    ("hash inside a word is text", "echo a#b; ffmpeg -i a b", "ffmpeg"),
    ("substitution before its own comment executes",
     'echo "$(ffmpeg -i a b # x)"', "ffmpeg"),
]:
    r = gate(bash(cmd))
    if blocked:
        ok = r.returncode == 2 and "'%s'" % blocked in r.stderr
    else:
        ok = r.returncode == 0 and "deny" not in r.stdout
    test(name, ok, "rc=%s %r" % (r.returncode, r.stderr[:160]))

r = gate(bash("S=1 ffmpeg -i a b"))
test("assignment precedes safe-run in the hint",
     r.returncode == 2 and "Segment: S=1 ffmpeg -i a b" in r.stderr
     and "S=1 safe-run -- ffmpeg -i a b" in r.stderr,
     "rc=%s %r" % (r.returncode, r.stderr[:220]))
r = gate(bash("S='a b' ffmpeg -i a b"))
test("assignment value with spaces stays a shell assignment in the hint",
     r.returncode == 2 and "S='a b' safe-run -- ffmpeg -i a b" in r.stderr,
     "rc=%s %r" % (r.returncode, r.stderr[:220]))

print("=== reserved words, command strings and executor arguments ===")
probe_cases = [
    ("for f in *.mp4; do ffmpeg -i \"$f\" o.mkv; done", "ffmpeg"),
    ("while read f; do ffmpeg -i \"$f\" o.mkv; done < list", "ffmpeg"),
    ("until false; do x265 a; done", "x265"),
    ("if true; then ffmpeg -i a b; fi", "ffmpeg"),
    ("if true; then :; else ffmpeg -i a b; fi", "ffmpeg"),
    ("if ffmpeg -i a b; then echo ok; fi", "ffmpeg"),
    ("! ffmpeg -i a b", "ffmpeg"),
    ("{ ffmpeg -i a b; }", "ffmpeg"),
    ("(ffmpeg -i a b)", "ffmpeg"),
    ("( ffmpeg -i a b )", "ffmpeg"),
    ("f() { ffmpeg -i a b; }; f", "ffmpeg"),
    ("case $x in *.mp4) ffmpeg -i a b;; esac", "ffmpeg"),
    ("bash -c 'ffmpeg -i a b'", "ffmpeg"),
    ('sh -c "ffmpeg -i a b"', "ffmpeg"),
    ("zsh -lc 'cd x && ffmpeg -i a b'", "ffmpeg"),
    ("find . -name '*.mp4' -exec ffmpeg -i {} {}.mkv \\;", "ffmpeg"),
    ("ls *.mp4 | xargs -I {} ffmpeg -i {} {}.mkv", "ffmpeg"),
    ("ls *.mp4 | xargs -n1 -P4 ffmpeg -i", "ffmpeg"),
    ("parallel ffmpeg -i {} {.}.mkv ::: *.mp4", "ffmpeg"),
    ("sudo ffmpeg -i a b", "ffmpeg"),
    ("time ffmpeg -i a b", "ffmpeg"),
    ("time -p ffmpeg -i a b", "ffmpeg"),
    ("watch -n 5 ffmpeg -i a b", "ffmpeg"),
    ("eval ffmpeg -i a b", "ffmpeg"),
    ('eval "ffmpeg -i a b"', "ffmpeg"),
    ("for f in *.mp4; do echo ffmpeg; done", None),
    ("if grep -q ffmpeg log; then echo yes; fi", None),
    ("bash -c 'echo ffmpeg'", None),
    ("safe-run -- bash -c 'for f in *; do ffmpeg -i $f o; done'", None),
    ("for f in *.mp4; do safe-run -- ffmpeg -i \"$f\" o.mkv; done", None),
    ("find . -name '*ffmpeg*' -print", None),
    ("xargs echo ffmpeg < l", None),
    ("echo do ffmpeg", None),
    ("git log --grep 'then ffmpeg'", None),
    ("ls | xargs -I{} safe-run -- ffmpeg -i {} o", None),
]
extra_cases = [
    ("for f in ffmpeg x265; do echo $f; done", None),
    ("bash -c 'safe-run -- ffmpeg -i a b'", None),
    ("bash run_ffmpeg.sh", None),
    ("bash --norc run_ffmpeg.sh", None),
    ('bash -c "echo \\"$(ffmpeg -i a b)\\""', "ffmpeg"),
    ("sudo -u bob ffmpeg -i a b", "ffmpeg"),
    ("find . -exec echo ffmpeg {} \\;", None),
    ("find . -exec safe-run -- ffmpeg -i {} o \\;", None),
    ("find . -name x -exec ls {} \\; -exec ffmpeg -i {} o \\;", "ffmpeg"),
    ("watch 'ffmpeg -i a b'", "ffmpeg"),
    ("then=1; echo $then", None),
]
for cmd, blocked in probe_cases + extra_cases:
    r = gate(bash(cmd))
    ok = r.returncode == (2 if blocked else 0)
    if blocked:
        ok = ok and "'%s'" % blocked in r.stderr
    test("executor syntax: " + cmd, ok, "rc=%s %r" % (r.returncode, r.stderr[:160]))

r = gate(bash('for f in *.mp4; do ffmpeg -i "$f" o.mkv; done'))
test("loop hint names the real command",
     r.returncode == 2 and "safe-run -- ffmpeg" in r.stderr
     and "safe-run -- do" not in r.stderr, repr(r.stderr[:240]))

deep = "ffmpeg -i a b"
for unused in range(4000):
    deep = "eval " + deep
r = gate(bash(deep))
test("deep eval nesting does not crash the gate", r.returncode in (0, 2),
     "rc=%s %r" % (r.returncode, r.stderr[:120]))

print("=== config override ===")
round5 = [
    ("heredoc safe run bash", "safe-run -- bash <<'EOF'\nffmpeg -i in.mov out.mp4\nEOF", 0),
    ("heredoc safe run sh", "safe-run --cpu-limit 50 -- sh <<EOF\nffmpeg -i a b\nEOF", 0),
    ("heredoc override", "PALADIN_HOOK=off bash <<'EOF'\nffmpeg -i a b\nEOF", 0),
    ("heredoc remote bash", "ssh host bash <<'EOF'\ncd /data && ffmpeg -i a.mov b.mp4\nEOF", 0),
    ("heredoc remote sh", "ssh -T user@box sh <<EOF\nffmpeg -i a b\nEOF", 0),
    ("heredoc nested data", "cat > outer.sh <<'OUTER'\nbash <<'EOF'\nffmpeg -i a b\nEOF\nOUTER", 0),
    ("heredoc bare bash", "bash <<'EOF'\nffmpeg -i a b\nEOF", 2),
    ("heredoc caffeinate", "caffeinate -i bash <<'EOF'\nffmpeg -i a b\nEOF", 2),
    ("heredoc pipe bash", "cat <<'EOF' | bash\nffmpeg -i a b\nEOF", 2),
    ("heredoc pipe wrapped shell", "cat <<'EOF' | caffeinate -i bash\nffmpeg -i a b\nEOF", 2),
    ("heredoc pipe supervised shell", "cat <<'EOF' | safe-run -- bash\nffmpeg -i a b\nEOF", 0),
    ("heredoc bash s", "bash -s <<EOF\nffmpeg -i a b\nEOF", 2),
    ("here string bare", "bash <<< 'ffmpeg -i a b'", 2),
    ("case quoted echo xargs", 'echo "edge case in parser"; ls *.mp4 | xargs -I{} ffmpeg -i {} {}.mkv', 2),
    ("case quoted tee", "echo 'test case in progress' | tee /dev/null | ffmpeg -f concat -safe 0 -i - -c copy out.mp4", 2),
    ("case quoted pipe", 'echo "case in point" | ffmpeg -f lavfi -i anullsrc -t 1 o.wav', 2),
    ("case quoted separator", 'echo "; case x in ffmpeg|x265)" | ffmpeg -i a b', 2),
    ("case quoted commit", 'git commit -qm "Fix edge case in hook gate" && ffmpeg -version | head -1', 0),
    ("case after xargs", 'ls *.mov | xargs -I{} ffmpeg -i {} {}.mp4; case $? in 0) echo ok;; esac', 2),
    ("case after newline", 'set -e\nls *.mov | xargs -I{} ffmpeg -i {} {}.mp4', 2),
    ("here string commit text", 'git commit -m "hook: catch bash <<< \'ffmpeg -i a b\'"', 0),
    ("here string echo text", 'echo "hook: catch bash <<< \'ffmpeg -i a b\'"', 0),
    ("here string rg text", 'rg -n "sh <<< \'x265 a\'" tests/', 0),
    ("command ffmpeg value", "command ffmpeg -v error -i a b", 2),
    ("command ffmpeg quiet", "command ffmpeg -hide_banner -v quiet -i a b", 2),
    ("command v", "command -v ffmpeg", 0),
    ("command V", "command -V ffmpeg", 0),
    ("command p v", "command -p -v ffmpeg", 0),
    ("command pv", "command -pv ffmpeg", 0),
    ("dynamic argv0", 'FF=$(command -v ffmpeg); "$FF" -i a b', 0),
    ("python script whisper", "python3 bench.py -m whisper --audio a.wav", 0),
    ("python eval whisper", "python3 asr_eval.py -m whisper --lang pl", 0),
    ("python script cadical", "python3 -u bench.py -m cadical -t 600", 0),
    ("uv python script", "uv run python bench.py -m x265", 0),
    ("python u module", "python3 -u -m mlx_lm.lora --train", 2),
    ("python X module", "python3 -X dev -m mlx_lm lora --train", 2),
    ("python W module", "python3 -W ignore -m mlx_lm.lora", 2),
    ("caffeinate t", "caffeinate -t 3600 ffmpeg -i a b", 2),
    ("caffeinate i t", "caffeinate -i -t 7200 x265 a", 2),
    ("caffeinate w", "caffeinate -w 123 ffmpeg -i a b", 2),
    ("env dash", "env -- ffmpeg -i a b", 2),
    ("env path dash", "/usr/bin/env -- ffmpeg -i a b", 2),
    ("nice dash", "nice -- ffmpeg -i a b", 2),
    ("nice n dash", "nice -n 10 -- ffmpeg -i a b", 2),
    ("nohup dash", "nohup -- ffmpeg -i a b", 2),
    ("caffeinate dash", "caffeinate -i -- ffmpeg -i a b", 2),
    ("timeout dash", "timeout -- 60 ffmpeg -i a b", 2),
    ("timeout kill separated", "timeout --kill-after 5 60 ffmpeg -i a b", 2),
    ("timeout kill equals", "timeout --kill-after=5 60 ffmpeg -i a b", 2),
    ("timeout fraction", "timeout .5 ffmpeg -i a b", 2),
    ("taskpolicy t l", "taskpolicy -t 4 -l 4 ffmpeg -i a b", 2),
    ("taskpolicy m", "taskpolicy -m 4096 ffmpeg -i a b", 2),
    ("taskpolicy b t", "taskpolicy -b -t 5 ffmpeg -i a b", 2),
    ("xargs J", "xargs -J % ffmpeg -i % o.mp4", 2),
    ("xargs R I", "xargs -R 1 -I {} ffmpeg -i {} o.mp4", 2),
    ("parallel joblog", "parallel --joblog j.log ffmpeg -i {} {.}.mkv ::: *.mp4", 2),
    ("parallel I", "parallel -I % ffmpeg -i % %.mkv ::: *.mp4", 2),
    ("pipx spec", "pipx run --spec openai-whisper whisper a.mp3", 2),
    ("bash uo", "bash -uo pipefail -c 'ffmpeg -i a b'", 2),
    ("bash Eeuo", "bash -Eeuo pipefail -c 'ffmpeg -i a b'", 2),
    ("bash xo", "bash -xo pipefail -c 'ffmpeg -i a b'", 2),
    ("escaped slash newline", "echo dir\\\\\nffmpeg -i a b", 2),
    ("escaped path newline", "echo C:\\\\\nffmpeg -i a b", 2),
    ("supervised continuation", "safe-run -- \\\nffmpeg -i a b", 0),
    ("nested heredoc substitution", "cat > info.txt <<EOF\nr: $(cd /tmp && (ffmpeg -i a b))\nEOF", 2),
    ("array substitution", "streams=($(ffmpeg -i in.mov -f null - 2>&1 | grep Stream)); echo ${#streams[@]}", 2),
]
for name, command, expected in round5:
    r = gate(bash(command))
    test("r5 " + name, r.returncode == expected,
         "rc=%s %r" % (r.returncode, r.stderr[:140]))

for name, command, fragment in [
    ("subshell", "(ffmpeg -i a b)", "safe-run -- ffmpeg -i a b"),
    ("exec", "exec ffmpeg -i a b", "exec safe-run -- ffmpeg -i a b"),
    ("escaped assignment", "FOO=a\\ b ffmpeg -i a b", "FOO=a\\ b safe-run -- ffmpeg -i a b"),
    ("substitution assignment", 'OUT=$(date +%s).mp4 ffmpeg -i a.mov "$OUT"',
     'OUT=$(date +%s).mp4 safe-run -- ffmpeg -i a.mov "$OUT"'),
]:
    r = gate(bash(command))
    test("r5 hint " + name, r.returncode == 2 and fragment in r.stderr,
         "rc=%s %r" % (r.returncode, r.stderr[:220]))

round4 = [
    ("lookup", "command -p -v ffmpeg", 0),
    ("redirect query", "ffmpeg -version 2>&1 | head -1", 0),
    ("leading redirect", ">log ffmpeg -i a b", 2),
    ("continuation supervised", "safe-run -- \\\n ffmpeg -i a b", 0),
    ("per command override", "PALADIN_HOOK=off ffmpeg -i a b", 0),
    ("mlx whisper", "mlx_whisper a.wav", 2),
    ("whisper cli", "whisper-cli -f a.wav", 2),
    ("whisperx", "whisperx a.wav", 2),
    ("timeout suffix", "timeout 10m ffmpeg -i a b", 2),
    ("env unset", "env -u DISPLAY ffmpeg -i a b", 2),
    ("python module", "python3 -m mlx_lm lora", 2),
    ("uv run", "uv run ffmpeg -i a b", 2),
    ("shell heredoc", "bash <<'EOF'\nffmpeg -i a b\nEOF", 2),
    ("shell here string", "bash <<< 'ffmpeg -i a b'", 2),
    ("shell -o", "bash -o pipefail -c 'ffmpeg -i a b'", 2),
    ("parallel quoted", "parallel 'ffmpeg -i {} o' ::: *.mp4", 2),
    ("process substitution", "cmp <(ffmpeg -i a b) x", 2),
    ("function keyword", "function enc { ffmpeg -i a b; }", 2),
    ("screen", "screen -dmS enc ffmpeg -i a b", 2),
    ("tmux", "tmux new -d 'ffmpeg -i a b'", 2),
    ("case pattern", 'case "$x" in ffmpeg|x265) echo heavy;; esac', 0),
    ("arithmetic", "echo $((x265 * 2))", 0),
    ("find second exec", "find . -exec ls {} \\; -exec ffmpeg -i a b \\;", 2),
    ("find data", "find . -exec chmod 644 {} \\; -o -name x265 -print", 0),
]
for name, command, expected in round4:
    r = gate(bash(command))
    test("r4 " + name, r.returncode == expected,
         "rc=%s %r" % (r.returncode, r.stderr[:120]))
round4_more = [
    ("command V", "command -V x265", 0),
    ("command v in if", "if ! command -v ffmpeg >/dev/null 2>&1; then echo missing; fi", 0),
    ("type lookup", "type ffmpeg", 0),
    ("which lookup", "which ffmpeg", 0),
    ("hash lookup", "hash ffmpeg", 0),
    ("whence lookup", "whence ffmpeg", 0),
    ("file redirected version", "ffmpeg -version > v.txt", 0),
    ("filters merged stderr", "ffmpeg -hide_banner -filters 2>&1 | grep loud", 0),
    ("if redirected version", "if ffmpeg -version >/dev/null 2>&1; then echo ok; fi", 0),
    ("input redirection", "</dev/null ffmpeg -i a b", 2),
    ("fd redirection", "2>/dev/null ffmpeg -i a b", 2),
    ("both redirection", "&>/dev/null ffmpeg -i a b", 2),
    ("x265 redirected version", "x265 --version 2>&1", 0),
    ("ab-av1 help", "ab-av1 crf-search --help", 0),
    ("continued bare", "ffmpeg -i a b \\\n -c copy o", 2),
    ("override zero", "PALADIN_HOOK=0 ffmpeg -i a b", 0),
    ("override false", "PALADIN_HOOK=FALSE ffmpeg -i a b", 0),
    ("whisper server", "whisper-server a.wav", 0),
    ("whisper stream", "whisper-stream a.wav", 0),
    ("timeout seconds", "timeout 60s ffmpeg -i a b", 2),
    ("timeout hours", "timeout 2h kissat f.cnf", 2),
    ("timeout signal", "timeout -s INT 600 ffmpeg -i a b", 2),
    ("timeout kill", "timeout -k 5 60 ffmpeg -i a b", 2),
    ("gtimeout", "gtimeout 1.5d ffmpeg -i a b", 2),
    ("taskpolicy value", "taskpolicy -c utility ffmpeg -i a b", 2),
    ("env path value", "env -P /opt/homebrew/bin ffmpeg -i a b", 2),
    ("env split", "env -S 'ffmpeg -i a b'", 2),
    ("time output", "/usr/bin/time -o t.txt ffmpeg -i a b", 2),
    ("stdbuf value", "stdbuf -o L ffmpeg -i a b", 2),
    ("gstdbuf attached", "gstdbuf -oL ffmpeg -i a b", 2),
    ("nice signed", "nice -n +10 ffmpeg -i a b", 2),
    ("uvx from", "uvx --from openai-whisper whisper a.wav", 2),
    ("pipx run", "pipx run whisper a.wav", 2),
    ("python dotted module", "python3.9 -m mlx_lm.lora --train", 2),
    ("mlx subcommand", "mlx_lm lora --train", 2),
    ("python code opaque", "python3 -c 'print(1)'", 0),
    ("wrapped shell heredoc", "caffeinate -i bash <<'EOF'\nffmpeg -i a b\nEOF", 2),
    ("sh heredoc", "sh <<EOF\nffmpeg -i a b\nEOF", 2),
    ("cat heredoc data", "cat > run.sh <<'EOF'\nffmpeg -i a b\nEOF", 0),
    ("bash euo", "bash -euo pipefail -c 'ffmpeg -i a b'", 2),
    ("bash extglob", "bash -O extglob -c 'ffmpeg -i a b'", 2),
    ("parallel jobs attached", 'parallel -j4 "ffmpeg -i {} o" ::: *.mp4', 2),
    ("parallel dry run", "parallel --dry-run ffmpeg -i a b ::: *.mp4", 0),
    ("parallel dryrun", "parallel --dryrun ffmpeg -i a b ::: *.mp4", 0),
    ("output process substitution", "tee >(ffmpeg -i a b)", 2),
    ("tmux named session", "tmux new-session -d -s enc 'ffmpeg -i a b'", 2),
    ("zsh noglob", "noglob ffmpeg -i a b", 2),
    ("zsh nocorrect", "nocorrect ffmpeg -i a b", 2),
    ("arithmetic command", "(( x264 > 3 )) && echo y", 0),
    ("unquoted heredoc substitution", "cat <<EOF\n$(date) ffmpeg -i a b\nEOF", 0),
    ("heredoc substitution executes", "cat <<EOF\n$(ffmpeg -i a b)\nEOF", 2),
    ("heredoc backticks execute", "cat <<EOF\n`ffmpeg -i a b`\nEOF", 2),
    ("heredoc escaped substitution", 'cat > v.sh <<EOF\n[ "\\$(ffmpeg -i a b)" = x ]\nEOF', 0),
    ("heredoc escaped backticks", "cat > v.sh <<EOF\n\\`ffmpeg -i a b\\`\nEOF", 0),
    ("heredoc escaped backslash then substitution", "cat <<EOF\n\\\\$(ffmpeg -i a b)\nEOF", 2),
    ("heredoc EOF parenthesis", "echo $(cat <<'EOF'\nffmpeg -i a b\nEOF)", 0),
    ("CRLF heredoc", "cat <<'EOF'\r\nffmpeg -i a b\r\nEOF\r\n", 0),
    ("CRLF commands", "echo hi\r\nffmpeg -i a b", 2),
    ("case array data", 'case "$solver" in\n cadical) cmd=(cadical -q "$cnf") ;;\n kissat) cmd=(kissat -q "$cnf") ;;\nesac\nsafe-run -- "${cmd[@]}"', 0),
]
for name, command, expected in round4_more:
    r = gate(bash(command))
    test("r4 " + name, r.returncode == expected,
         "rc=%s %r" % (r.returncode, r.stderr[:120]))
for name, command, fragment in [
    ("loop hint", 'for f in *.mov; do ffmpeg -i "$f" "${f%.mov}.mp4"; done',
     'safe-run -- ffmpeg -i "$f" "${f%.mov}.mp4"'),
    ("redirection hint", "ffmpeg -i a b 2>&1", "safe-run -- ffmpeg -i a b 2>&1"),
    ("wrapper hint", "timeout 600 ffmpeg -i a b", "safe-run -- timeout 600 ffmpeg -i a b"),
    ("substitution hint", 'ffmpeg -i "$(pick_input)" out.mp4',
     'safe-run -- ffmpeg -i "$(pick_input)" out.mp4'),
    ("quoted assignment hint", "S='a b' ffmpeg -i a b",
     "S='a b' safe-run -- ffmpeg -i a b"),
]:
    r = gate(bash(command))
    test("r4 " + name, r.returncode == 2 and fragment in r.stderr,
         "rc=%s %r" % (r.returncode, r.stderr[:200]))
for value in (5, [3], None):
    json.dump({"hook_heavy_patterns": value}, open(os.path.join(BASE, "config.json"), "w"))
    r = gate(bash("ffmpeg -i a b"))
    test("r4 invalid config %r" % value, r.returncode == 0, "rc=%s" % r.returncode)
json.dump({}, open(os.path.join(BASE, "config.json"), "w"))
import time
for name, command in (
    ("parentheses", "(" * 4000 + "ffmpeg -i a b"),
    ("sudo", "sudo " * 4000 + "ffmpeg -i a b"),
    ("xargs", "xargs " * 4000 + "ffmpeg -i a b"),
    ("bash -c", "bash -c " * 4000 + "ffmpeg -i a b"),
):
    started = time.monotonic()
    r = gate(bash(command))
    elapsed = time.monotonic() - started
    test("r4 bounded " + name, r.returncode in (0, 2) and elapsed < 0.2,
         "rc=%s elapsed=%.3f" % (r.returncode, elapsed))
r = gate(bash('for f in *.mov; do ffmpeg -i "$f" "${f%.mov}.mp4"; done'))
test("r4 loop hint gives whole-command advice",
     r.returncode == 2 and "safe-run -- bash -c '<the whole command>'" in r.stderr
     and "safe-run -- do" not in r.stderr, repr(r.stderr[:350]))
r = gate(bash("PALADIN_HOOK=off ffmpeg -i a b"))
test("r4 override is one command", r.returncode == 0, "rc=%s" % r.returncode)
r = gate(bash("ffmpeg -i a b"))
test("r4 override advice exact syntax",
     "PALADIN_HOOK=off <command>" in r.stderr, repr(r.stderr[:350]))
json.dump({"hook_heavy_patterns": ["sleep"]}, open(os.path.join(BASE, "config.json"), "w"))
r = gate(bash("sleep 999"))
r2 = gate(bash("ffmpeg -i a.mov b.mp4"))
test("17. hook_heavy_patterns replaces the default list",
     r.returncode == 2 and r2.returncode == 0,
     "sleep rc=%s ffmpeg rc=%s" % (r.returncode, r2.returncode))

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
