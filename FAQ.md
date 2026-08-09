# FAQ

Questions people actually type into a search box — with short, factual answers.
coffee-paladin is a free, MIT-licensed thermal safety net for Apple
Silicon Macs:

```bash
brew install pawelkwaczynski/tap/coffee-paladin
bash "$(brew --prefix)/share/coffee-paladin/install.sh"
```

Both lines are needed: `brew install` only puts the files in place, and the second one
compiles the menu bar app and starts the daemon. After `brew install` alone nothing is
watching your Mac.

### `brew install` fails with "/usr/local/Homebrew is not writable" on Apple Silicon

Your Mac is running the Intel build of Homebrew. `/usr/local` is the Intel prefix; the
native Apple Silicon prefix is `/opt/homebrew`. This usually happens when Migration
Assistant carried an old installation over from an Intel Mac. Do not `sudo chown` the
old tree into obedience - install the native build alongside it (the two coexist):

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
/opt/homebrew/bin/brew install pawelkwaczynski/tap/coffee-paladin
bash /opt/homebrew/share/coffee-paladin/install.sh
```

The full paths matter: with both installations on disk, a plain `brew` may still
resolve to the old Intel one through your PATH.

### How do I stop my Mac from overheating during ffmpeg or video encoding?

Run the encode under supervision: `safe-run --hours 3 --name encode -- ffmpeg -i in.mov out.mp4`.
coffee-paladin watches the chip temperature and, if it crosses the threshold (default 85 °C),
pauses the encoder with SIGSTOP; it resumes automatically below 76 °C. Nothing is lost — the
process freezes in place and continues from the same instruction. `safe-run` also refuses to
start on an already-hot machine and can cap the job's CPU or pin it to efficiency cores.

### Can I pause a process when my Mac gets hot, instead of killing it?

Yes — that is exactly what SIGSTOP/SIGCONT do, and it is lossless: memory stays intact and the
process resumes where it stopped. macOS itself pauses processes this way constantly (App Nap,
debuggers). coffee-paladin automates it: pause at the hot threshold, resume after cooling.
Measured on a real job: 89.3 °C → paused → 60.2 °C nineteen seconds later → resumed.

### Does a keep-awake app overheat a MacBook in a backpack?

It can. Caffeine and Amphetamine hold the wake lock unconditionally — including when the
laptop is hot, lid closed, in a bag ("Mac hot in its sleeve" forum threads go back years;
in one, keyboard keys melted). coffee-paladin's keep-awake modes have a thermal fuse: the
sleep lock is released the moment the chip runs hot, because sleep is the fastest cooling
a computer has.

### How do I read the CPU temperature on Apple Silicon without sudo?

`powermetrics` needs a password, and the old IOHIDEventSystem/SMC route returns zero sensors
on macOS 26. The surviving no-sudo path is IOReport, which the `macmon` tool exposes.
coffee-paladin builds on it: `heat` prints chip, GPU and battery temperature, fan rpm and
power draw as a normal user, and `~/.coffee-paladin/status.json` gives the same data as JSON.

### Why did my Mac shut down overnight with no crash log?

A thermal hard shutdown often leaves nothing: no kernel panic, no shutdown record — the log
simply ends. coffee-paladin keeps its own black box: a heartbeat every cycle plus the last
eight measurements before any crash, detected by comparing against `kern.boottime` after
reboot. `thermal-report` turns that into a file a repair shop or warranty claim will accept.

### Is SIGSTOP safe? Does pausing a process corrupt data?

The pause lands between instructions, so the process's own memory and computation state
cannot be corrupted. The honest caveat is time-sensitive I/O: network peers, watchdogs and
license servers can notice a long pause. Batch compute, renders and encodes are fine;
latency-critical services belong on the guard's never-touch list (`never_extra`).

### How do I keep my MacBook computing overnight without cooking it?

`safe-run --hours 8 --name render -- <command>`. It holds a system sleep assertion
(`caffeinate -is`) only while the job runs *and* the machine is cool — the display still
sleeps and the screen can be locked. If the chip crosses the threshold, jobs pause and the
wake lock is released; everything resumes after cooling. Battery gate included: on battery
at ≤10 %, long jobs pause until you plug in, instead of dying mid-computation.

### How can I monitor the temperature of several Macs at once, for free?

Point each Mac's config at any shared folder (iCloud Drive, Dropbox, SMB/NAS, SharePoint) —
`fleet --setup` finds one for you. Every machine publishes a small JSON snapshot about once
a minute; `fleet` renders one table (temperatures, fans, watts, pauses, stale hosts), and
`fleet --json` plus its exit code plug into cron, Grafana or Slack. No server, no accounts,
no data leaving your folder.

### My AI coding agent (Claude Code, Codex) overheats my MacBook — can anything stop it?

Yes, and this tool was written for that case. Agents start builds, encodes and parallel jobs
without feeling the fan. coffee-paladin pauses whatever overheats the machine — including
orchestrators that spawn hundreds of short-lived children, caught by whole-subtree CPU
accounting — while never freezing the agent itself (`claude`, `codex`, MCP servers and
terminal foregrounds are on the never-touch list). It also ships a skill that teaches agents
to check `~/.coffee-paladin/status.json` before heavy work: `skills/coffee-paladin/SKILL.md`.

### Does running a Mac hot actually damage it?

Sustained heat is the expensive kind. Apple specifies 10–35 °C ambient; every 5–10 °C above
optimum roughly doubles how fast a Li-ion battery ages; and a professional Mac data centre
(MacStadium) documented temperature-related failures in ordinary racks. Short spikes are
normal — Apple Silicon throttles itself around 100–108 °C — but hours at high temperature
age the battery and, in the worst case, end in a hard shutdown that destroys work.
