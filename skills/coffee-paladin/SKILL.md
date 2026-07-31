---
name: coffee-paladin
description: Cooperate with the coffee-paladin thermal guard on this Mac. Use ALWAYS before starting anything heavy (builds, ffmpeg, model inference, large scans, long loops) and whenever a job you started stops making progress. Tells you how to read the machine's thermal state, how to launch heavy work so it is supervised, and what never to do when the guard has paused something.
---

# Working with the paladin on watch

This Mac runs **coffee-paladin** (`thermal-guard`): a daemon that pauses heavy processes
when the chip gets too hot, instead of letting the machine cook itself. It is on your side -
but only if you talk to it. An agent that starts eight parallel jobs without looking at the
temperature is exactly the thing this tool exists to survive.

Is it here at all? `test -f ~/.thermal-guard/status.json` - if that file is missing, this
skill does not apply and you can ignore the rest.

## 1. Look before you start

`~/.thermal-guard/status.json` is refreshed every ~15 s and is meant to be read by programs.
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
frozen), `dry_run` (when `true` the guard only watches and will *not* protect you),
`eta_pause_min` (estimated minutes until the next pause at the current trend), and
`unpausable` - if that key is present, the guard tried to pause something and **failed**;
protection is incomplete and the user needs to know right now.

```bash
python3 -c "import json;d=json.load(open('$HOME/.thermal-guard/status.json'));print(d['level'],d['chip_c'],d.get('paused'))"
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
- **Never edit `~/.thermal-guard/config.json` to raise the thresholds** so your job can keep
  running. Those numbers were measured on real hardware. If they are wrong, say so to the
  user and let them decide.
- **One heavy job at a time**, unless the user asked for more. Half the cores is a sane
  default; all of them is a decision for a human who is watching.

## 4. When the guard pauses something you started

Say it plainly and do not work around it:

> The Mac reached 90 °C, so coffee-paladin paused the encode. It resumes on its own at 82 °C -
> nothing was lost, the process is frozen mid-instruction. Waiting.

Then wait and re-read `status.json`. If a pause lasts beyond `max_pause_minutes` the guard
will terminate the job with `SIGTERM` and you will see it in `~/.thermal-guard/guard.log`.

## 5. You are protected - so is your terminal

Your own process (`claude`, `node`, `codex`, `hermes`, `tmux`, `vim`…) is on the never-touch
list, and any process that holds the foreground of a terminal is skipped as well. That rule
exists because freezing a foreground terminal job leaves it stuck in a way only `fg` can
undo. If you ever see your own session frozen, that is a bug worth reporting.

## 6. Do not create the heat in the first place

Two habits that cost more than any thermal threshold:

- **No background task without a timeout and a cleanup.** A headless browser or an `ffmpeg`
  that nobody reaps keeps a core busy for hours.
- **No recursive search across iCloud-backed folders** (`~/Desktop`, `~/Documents`). It costs
  almost no CPU of its own while forcing `fileproviderd` and `cloudd` to materialise files -
  a fanless Mac reached 90 °C this way on a `grep` that used 13 seconds of CPU in 1 h 42 min.

Full documentation: https://github.com/pawelkwaczynski/coffee-paladin
