---
name: coffee-paladin
description: Cooperate with the coffee-paladin thermal guard on this Mac. Use ALWAYS before starting anything heavy (builds, ffmpeg, model inference, large scans, long loops) and whenever a job you started stops making progress. Tells you how to read the machine's thermal state, how to launch heavy work so it is supervised, and what never to do when the guard has paused something.
---

# Working with the paladin on watch

This Mac runs **coffee-paladin**: a daemon that pauses heavy processes
when the chip gets too hot, instead of letting the machine cook itself. It is on your side -
but only if you talk to it. An agent that starts eight parallel jobs without looking at the
temperature is exactly the thing this tool exists to survive.

Is it here at all? `test -f ~/.coffee-paladin/status.json` - if that file is missing, this
skill does not apply and you can ignore the rest.

## 1. Look before you start

`~/.coffee-paladin/status.json` is refreshed every ~15 s and is meant to be read by programs.
Read it; do not parse the pretty output of `heat` (that one is for humans and is translated
into five languages).

The one field that decides everything is `level`:

| `level` | What it means | What you do |
|---|---|---|
| 0 | cool, nothing wrong | start the job |
| 1 | warming up (fair) | start, but do not add a second parallel job |
| 2 | hot / on battery below 10 % | finish what is running, start nothing new |
| 3 | critical - guard is pausing | **start nothing.** Tell the user the Mac is too hot and stop |

Also worth reading: `chip_c`, `fans`, `on_ac`, `paused` (list of process names currently
frozen), `demoted` (process names pushed onto E-cores because the machine was hot - the job
is *running* but possibly an order of magnitude slower; it returns to full speed on its own
once the chip cools, so a "slow" job on this list is not hung and must not be restarted),
`dry_run` (when `true` the guard only watches and will *not* protect you),
`eta_pause_min` (estimated minutes until the next pause at the current trend), and
`unpausable` - if that list is **not empty**, the guard tried to pause something and **failed**;
protection is incomplete and the user needs to know right now.

One scope caveat: `status.json` answers "may I start work now", not "is that process
stopped at this very second". The snapshot lands in the quiet part of the guard's cycle,
so it can show 75 °C and an empty `paused` while the log has pauses every 40 s. For
"is it stopped RIGHT NOW", ask `ps -o stat= -p <pid>` (state `T` = stopped).

**Never judge the machine from a single snapshot.** One read caused two false alarms in
one night (04/05.08.2026): a snapshot caught mid-transition looks like a crisis or like
calm, and `trend_c_min` can even be negative while the chip is climbing. The practice:
take **3 reads, 10 s apart**, and decide from the direction (is `chip_c` rising or
falling across the three?), not from any single value. If two snapshots disagree, the
third one plus the direction is the answer.

If `config_corrections` is **not empty**, the daemon is running on values *different*
from what `config.json` says (a sanity-clamp fixed them in memory). Read that list before
diagnosing anything from the config file - otherwise you are analysing a system that
is not the one actually running.

```bash
python3 -c "import json;d=json.load(open('$HOME/.coffee-paladin/status.json'));print(d['level'],d['chip_c'],d.get('paused'))"
```

**When the read fails, be conservative, not optimistic.** The file is rewritten every cycle,
so it is also a heartbeat:

| What you see | What it means | What you do |
|---|---|---|
| file missing | the guard is not installed here | this skill does not apply; proceed normally |
| unparseable JSON | you caught a write mid-flight | read it again once, ~1 s later |
| `time` older than 60 s | **the daemon is not running** | say so to the user and treat the Mac as unprotected: one job at a time, nothing overnight |
| `dry_run: true` | protection is off, this is watch-only | tell the user before starting anything heavy |

Re-read before each new heavy job, and every few minutes during a long one. Polling faster
than the ~15 s refresh buys you nothing.

**What counts as "heavy"** - the cases that actually matter here: compilation and bundling,
`ffmpeg` and any transcode, local model inference or training, test suites that fan out across
cores, container builds, `find`/`rg`/`grep` over a large tree, and anything you were about to
run more than two of at once.

## 2. Start heavy work through `safe-run`, not directly

```bash
safe-run --name build -- cargo build --release
safe-run --hours 3 --name encode -- ffmpeg -i in.mov out.mp4
```

`safe-run` refuses to start on an already-hot Mac, gives the job its own process group so it
can be paused together with its children, registers it so the guard never has to guess by
name, and holds the sleep lock only while the machine is cool. A job started directly can
still be paused - but the guard has to *recognise* it first, and the pause will be less
precise.

Do not pass `--allow-hot` on your own initiative. That flag exists for a human who has
decided to accept the risk.

## 3. Rules that are not negotiable

- **Never `SIGCONT` a process the guard paused.** If a name appears in `paused`, that is a
  decision, not a glitch. Undoing it puts the machine back on the path to a hard shutdown.
- **Check `paused` before you decide a job "hung".** A frozen job is doing exactly what it
  should and resumes by itself once the chip cools - relaunching it doubles the load that
  caused the pause. If the name is *not* in `paused`, it is a normal hang and you may treat
  it as one.
- **Never edit `~/.coffee-paladin/config.json` to raise the thresholds** so your job can keep
  running. Those numbers were measured on real hardware. If they are wrong, say so to the
  user and let them decide.
- **One heavy job at a time**, unless the user asked for more. Half the cores is a sane
  default; all of them is a decision for a human who is watching.

## 4. When the guard pauses something you started

Say it plainly and do not work around it:

> The Mac reached its pause threshold (85 °C by default), so coffee-paladin paused the encode. It resumes on its own once it cools (76 °C by default) -
> nothing was lost, the process is frozen mid-instruction. Waiting.

Then wait and re-read `status.json`. If a pause lasts beyond `max_pause_minutes` the guard
will terminate the job with `SIGTERM` and you will see it in `~/.coffee-paladin/guard.log`.

## 5. You are protected - so is your terminal

Your own process (`claude`, `codex`, `hermes`, `tmux`, `vim`…) is on the never-touch
list, and any process that holds the foreground of a terminal is skipped as well. That rule
exists because freezing a foreground terminal job leaves it stuck in a way only `fg` can
undo. If you ever see your own session frozen, that is a bug worth reporting.

## 6. Two files that answer "what actually happened"

`status.json` is the present tense. When you need the past - a user asking why a job died
overnight, or evidence for a repair shop - there are two more files, both plain and both
safe to read:

**`~/.coffee-paladin/guard.log`** - one line per action, newest last. Grep it, do not read it
whole:

```bash
grep -E "\\[(PAUSE|RESUME|KILL|DEMOTE|PROMOTE|FANFAIL)\\]" ~/.coffee-paladin/guard.log | tail -20
grep "CONFIG CHANGED" ~/.coffee-paladin/guard.log | tail -5   # who moved the thresholds
```

Lines are `YYYY-MM-DD HH:MM:SS  MESSAGE`. Messages are written in the user's language, so
match on both English and the local word (`PAUSE|PAUZA`) or on the process name.

**`~/.coffee-paladin/events.log`** - the black box: one JSON object per line, only for the
rare and serious (hard shutdown detected after a reboot, fans stopped while hot). Each entry
carries `time`, `type`, `description` and a `context.last_readings` array - the last eight
measurements taken before the machine died. That array is the whole point: it is the evidence
macOS itself does not keep.

```bash
python3 -c "import json;[print(json.loads(l)['time'], json.loads(l)['type']) for l in open('$HOME/.coffee-paladin/events.log')]"
```

An empty `events.log` is good news, not a broken file.

## 7. Building a report for a human

`thermal-report` assembles hardware, battery health, hard shutdowns, interventions and the
measurement timeline into one file. Use it when a human asks for proof, not to answer
questions yourself - for those, read the two files above.

```bash
thermal-report --days 14                 # text file on the Desktop, path printed on stdout
thermal-report --from 2026-07-01 --to 2026-07-31
thermal-report --all --pdf               # everything on record, PDF next to the text file
thermal-report --days 7 --file /tmp/r.txt
```

It prints the path of what it wrote - use that, do not guess the filename. The report is
already branded and dated; do not rewrite it into your own summary when the user asked for
the report itself.

## 8. Do not create the heat in the first place

Two habits that cost more than any thermal threshold:

- **No background task without a timeout and a cleanup.** A headless browser or an `ffmpeg`
  that nobody reaps keeps a core busy for hours.
- **No recursive search across iCloud-backed folders** (`~/Desktop`, `~/Documents`). It costs
  almost no CPU of its own while forcing `fileproviderd` and `cloudd` to materialise files -
  a fanless Mac reached its pause threshold (85 °C by default) this way on a `grep` that used 13 seconds of CPU in 1 h 42 min.

Full documentation: https://github.com/pawelkwaczynski/coffee-paladin
