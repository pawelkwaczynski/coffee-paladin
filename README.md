# coffee-paladin v2.2.6

<p align="center">
  <img src="branding/paladin.gif" alt="coffee-paladin - the project mascot" width="260">
</p>
<p align="center"><em>Shield the Process, Sip the Coffee</em></p>

**A thermal and power safety net for Apple Silicon Macs - from one laptop to a whole fleet.**
It watches the chip temperature, the battery, the fans and the power source, and it *freezes*
heavy jobs before the machine cooks itself - instead of letting them run until it shuts down.
Built for people who make Macs work for a living: render farms, post-production studios,
CI pools of Mac minis, ML teams, and anyone leaving a laptop to compute overnight.

No `sudo`. No kernel extensions. No daemons running as root. Everything reads sensors that are
available to a normal user process.

*(Polska wersja poniżej - [przejdź do opisu po polsku](#po-polsku).)*

**Other languages:** [中文](README.zh.md) · [Русский](README.ru.md) · [Español](README.es.md) - short versions; this file is the complete one.

```
C67°  G64°  B33°  ·  3.3k rpm  ·  42W  ·  RAM 62%  ·  disk 46%
```

chip · GPU · battery · fan rpm · power draw · RAM used · disk used - and you choose which of
those appear, with checkboxes under **Show in the bar**. The menu bar, the notifications and all
CLI tools speak **five languages** - English (default), Polish, Russian, Chinese and Spanish -
switched from the menu bar (*Settings > Language*), with `TG_LANG` or `"lang"` in the config.

<p align="center">
  <img src="docs/screens/menu_en.webp" alt="coffee-paladin menu bar" width="360">
</p>

<p align="center">
  <img src="docs/screens/languages.webp" alt="The same menu in English, Polish, Russian, Chinese and Spanish" width="820">
</p>
<p align="center"><sub>The same menu in five languages - one click in <em>Settings &gt; Language</em>.</sub></p>

---

## Why the name, and why the coffee

<p align="center">
  <img src="branding/paladin.png" alt="coffee-paladin" width="260">
</p>

The coffee is not decoration. This tool stands on `caffeinate` - a real utility built into
macOS since 2012, living at `/usr/bin/caffeinate`, doing exactly what the name suggests:
**it stops the machine from falling asleep**. Apple made the joke first, naming it after
caffeine, and the whole category followed - Caffeine with its coffee-cup icon, then
Amphetamine, where the metaphor escalated a notch.

Our knight holds that cup for one reason: **he drinks from it too**. Start a job with
`safe-run` and a `caffeinate` assertion goes up underneath, keeping the Mac awake through
your render.

The difference is what he does with the cup when things get hot: **he puts it down**.
Everything else in this category holds the Mac awake unconditionally - including when it
is lying hot in a backpack. This one releases the lock the moment the chip crosses the
threshold, because sleep is the fastest cooling a computer has.

Hence a paladin, not just a knight. A paladin stands watch by choice and holds a principle
above an order. The order says "do not let it sleep."
The principle says "but do not let it cook."

**Shield the Process, Sip the Coffee.**

---

## Why this exists

A MacBook Pro M4 Pro was working overnight - video rendering and other heavy workloads, the
kind of thing these machines are bought for. In the morning: a burning smell from under the
chassis and a hard shutdown. Worse, when the logs were examined afterwards, there was
**nothing to examine**: no kernel panic, no thermal shutdown record, and the system log simply
ended at the moment the machine died. There was no way to reconstruct what the temperature
had been.

And losing a Mac hurts more in 2026 than it ever did. When we called leasing operators in
Poland this July, the quoted wait for new MacBooks was 15+ weeks with clients queued since
April; even aging M1 machines were selling out, and list prices had gone up. Wherever you
are, the direction is the same: nobody can afford to lose the machine they have.

This project is the answer to all of it: *stop it before it cooks*, and *keep the evidence
when something goes wrong anyway*.

---

## Why this matters more in 2026 than ever

Excess heat always broke computers. What changed in 2026 is that failures got expensive
like never before.

Overheating is not a theory. MacStadium, a professional data centre full of Macs, wrote
on its own blog [back in 2020](https://macstadium.com/blog/digging-deeper-into-2018-mac-minis-at-macstadium)
that a Mac mini at 100% CPU starts throttling after about an hour, and that ordinary rack
mounts gave them cases of temperature-related failures. They solved it with custom sleds
and cold-air aisles. Your Mac on a desk has none of those things. Apple itself
[once apologised for throttling](https://techcrunch.com/2018/07/24/apple-apologizes-issues-update-for-macbook-pro-thermal-throttling/)
(clock dropping under heat). After their 2018 fix the same MacBooks ran up to 70 percent
faster - and the 13-inch up to twice as fast(!). That is the cost of bad thermal management, priced by Apple itself. Ok, that
is big companies - but what if you are a student who closes the lid out of habit, with
a process still running, and slides the laptop into a backpack? Apple specifies an
[operating range of 10-35 °C ambient](https://support.apple.com/en-us/102336), and
"Mac hot in its sleeve because some app kept it awake" threads go back years. In
[one of them](https://forums.macrumors.com/threads/2017-running-very-hot-in-my-bag.2216012/)
the user's keyboard keys even melted...

Replacing a "cooked" Mac got expensive and painfully slow. On June 25, 2026 Apple
[raised prices](https://9to5mac.com/2026/06/25/apple-price-increases-mac-ipad-more/):
the Mac Studio M3 Ultra went from $3,999 to $5,299 in one day. Tim Cook said he had never
seen a component get this expensive this fast, and back in April he already admitted
Studio and mini [need "several months"](https://www.macrumors.com/2026/04/30/mac-studio-mac-mini-constrained-months/)
to catch up with demand driven by AI. Consumer DRAM rose
[80-90% in a single quarter](https://spectrum.ieee.org/dram-shortage). The surge started
cooling in July, but forecasts put normalisation somewhere in 2027-2028. Deliveries?
Base configurations take weeks, a Mac Studio
[10-14 weeks](https://appleinsider.com/articles/26/07/22/upgraded-mac-mini-mac-studio-and-oled-imac-are-all-in-the-pipeline),
and high-RAM options take months or show up as "Currently Unavailable". Apple pulled the
512 GB option in March and [cut 128 GB in May](https://www.tomshardware.com/desktops/apple-quietly-axes-128gb-mac-studio-amid-supply-constraints-and-local-ai-frenzy-highest-memory-capacity-reduced-to-96gb-two-months-after-discontinuation-of-512gb-model).
In spring the wait [reached 4-5 months](https://www.macrumors.com/2026/04/06/mac-mini-and-mac-studio-long-shipping-delays/).

I also checked this on my own skin. On July 30 I wrote to three Polish Apple resellers
about leasing a single Mac Studio. One replied that "due to the global availability
problem we are not taking orders for this product category". Another, an authorised
Apple partner, quoted a price 23% above the pre-hike list and reserved the right to
change the price after the order is placed, or to cancel it altogether. The third never
answered.

And the AI boom, hyped everywhere, works these machines harder than anything ever
before. A Mac with big unified memory (shared between CPU and GPU) is the cheapest way
to run large models locally: 512 GB in a Mac cost $9,499, while one 80 GB H100 goes for
about $30,000. So Macs everywhere now grind LLMs and renders for hours, chip saturated.
Long heat is exactly what kills these units, laptops and batteries, because every
5-10 °C above optimum roughly doubles how fast a Li-ion cell ages.

The conclusion is simple. The Mac you have cannot be re-bought quickly or at the price
from the start of the year. That is why coffee-paladin guards it FOR FREE, in code you
can read before you trust it, and takes care of your processes.

---

## What it actually does

### 1. It pauses instead of killing

When the chip gets too hot, heavy processes receive `SIGSTOP`. That is **not** destructive: the
process freezes exactly where it is, its memory is untouched, and when things cool down it gets
`SIGCONT` and continues from where it stopped. Memory and computation state survive intact -
the stop lands between instructions, so the pause itself cannot corrupt the process's data.
And it is nothing exotic: macOS pauses processes this way all day on its own (App Nap does it
to background apps, every debugger does it on attach), so there is no wear on the hardware
either - a paused process simply is not scheduled. The honest caveat is time-sensitive I/O:
network peers, watchdogs and license servers can notice the pause (see Known limitations).
The alternative is worse anyway: unmanaged heat means macOS throttles everything, and in the
extreme the machine hard-shuts - which is what actually destroys work.

Measured on a real job: chip at 89.3 °C → paused → **60.2 °C nineteen seconds later** → resumed.
The computation never noticed.

Termination (`SIGTERM`, gently, so jobs can checkpoint) only happens after several consecutive
critical readings - in practice pausing cools the chip long before that.

### 2. It finds the *real* culprit, not just the obvious one

This is the part most naive implementations get wrong, and it took two failures to discover.

**Failure one - the name list.** A guard that only manages processes matching a list of known
names (`ffmpeg`, `python`, `ollama`…) is blind to your own compiled binaries. A custom solver
named `b3core` pushed the machine to 90 °C while the guard happily reported everything as
managed. Name lists are *always* incomplete.

**Failure two - the invisible orchestrator.** A Python script was spawning hundreds of `cadical`
SAT-solver instances, each living about one second. Every child was too short-lived to ever cross
a CPU threshold, and the parent itself used almost no CPU. Individually: nothing to see.
Together: eight cores at 100 %.

So coffee-paladin:

- computes **CPU usage across the entire process subtree**, so an orchestrator that spawns
  short-lived children is correctly identified (that Python process showed up as **595 %**) and
  frozen *at the source*, which stops new children from being spawned;
- treats **any** of your processes above 50 % CPU that has lived longer than 2 minutes as a
  manageable heavy job, regardless of its name;
- protects a hard "never touch" list: the system, WindowServer, Finder, your terminal, SSH, and
  Apple background daemons that either refuse `SIGSTOP` or misbehave when frozen.

<p align="center">
  <img src="docs/screens/load_info.webp" alt="Load info: what is heating the Mac and what is eating RAM" width="420">
</p>
<p align="center"><sub><em>Load info</em>: the actual culprits, the thresholds in force, and today's pause count.</sub></p>

### 3. It watches power, not just heat

- **Battery gate** - if you are on battery and drop to 10 %, long jobs are paused and only resume
  once you plug in. A 30-day computation should not die halfway through a block because the
  laptop ran flat. Waiting for a charger is not a failure, so this pause is allowed to last for
  hours; a *thermal* pause is not.
- **Fan alarm** - if the chip is above 70 °C and both fans report 0 rpm, you get a notification
  and a log entry. A seized fan is a common cause of exactly the burning smell described above.

### 4. Keep-awake modes - an add-on to the fuse, not the point of the tool

`safe-run` holds a sleep block (`caffeinate`) for exactly as long as the job runs, and the daemon
can do the same automatically for any heavy job it sees (*Keep the Mac awake while heavy jobs
run* in Settings - off by default). The menu bar also offers the full Amphetamine-style set of
**manual modes**: a timer (15 min to 12 h), *indefinitely*, *while an app is running* (pick from
the list of running apps) and *while downloading* (network activity, with a 2-minute grace gap
between files). The difference from Caffeine/Amphetamine is the **fuse**: every one of these
modes holds the wake lock **only while the machine is cool**. The moment the guard pauses jobs
for heat, the lock is released - sleep is the fastest cooler there is - and an unconditional
keep-awake in a backpack is precisely how MacBooks get cooked. When the job ends (or the timer
runs out), the Mac goes back to sleeping normally. A cup icon on the bar shows when the lock is
held.

<p align="center">
  <img src="docs/screens/keep_awake.webp" alt="Keep-awake modes with a thermal fuse" width="420">
</p>
<p align="center"><sub>Every mode here is released the moment the Mac runs hot.</sub></p>

**I used Amphetamine for years.** Great app, rich triggers - and that is exactly the trap:
it will faithfully hold your Mac awake while the machine is hot, in a bag, on a pillow, wherever.
I uninstalled it the day I understood that my keep-awake tool had no idea what temperature my
Mac was. A wake lock without a thermal fuse is a promise to keep heating.

> **The whole difference in one line:** every app in this category can hold a Mac awake.
> Only this one **puts the cup down when it gets hot** - the others will faithfully keep a
> Mac awake while it cooks in a backpack. That is not a variant of the same feature;
> it is the opposite philosophy, and everything else here is built on top of it.

| | Caffeine | Amphetamine | coffee-paladin |
|---|---|---|---|
| Keeps the system computing | via display | yes | yes |
| Lets the display sleep and lock | no | depends on setup | **always** |
| Releases the lock when the Mac runs hot | no | no | **yes - thermal fuse** |
| Sees temperature at all | no | no | **yes (chip, battery, fans)** |
| Timer / while-app-runs / while-downloading | timer | yes | yes |
| Pauses jobs that overheat the Mac | no | no | **yes** |
| Records a black box before a hard shutdown (warranty evidence) | no | no | **yes** |
| Open source | no | no | **MIT** |

**The screen sleeps. The math doesn't.** This is the second difference from the Caffeine
family: classic keep-awake apps hold the *display* assertion (`caffeinate -d`) - the screen
burns watts all night just to prove the machine is awake. coffee-paladin holds only the
*system* assertion (`caffeinate -is`): lock the screen (Ctrl+Cmd+Q), let the display sleep on
its own schedule - the jobs keep computing in the dark, and the display (often the single
biggest power draw during light work) costs you nothing. One caveat: keep the lid open -
closing it forces sleep regardless of assertions (clamshell mode with an external display and
power being the exception). And the thermal fuse stays supreme: if the machine runs hot, the
lock is released and the Mac may fully sleep; a `safe-run` job resumes when you wake it.

### 4b. It controls how hard heavy jobs are allowed to push

Two knobs in Settings, both consumed by `safe-run` as defaults: **which cores** heavy jobs run on
(*efficiency cores only* - cool and quiet, or *all cores* - fast, with the guard still watching
the temperature) and a **CPU limit** (50-100 %, default 95). Below 100 % the whole process group
gets cpulimit-style micro-pauses (SIGSTOP for ~100 ms in every 2 s window), so the cap works for
any program - including ones that ignore thread-count options. Per-run overrides: `--normal`
(all cores), `--efficiency`, `--cpu-limit 80`.

### 4c. It adapts itself to the Mac it lands on

<p align="center">
  <img src="docs/screens/about_my_mac.webp" alt="About my Mac: what the guard measured on this machine" width="330">
</p>
<p align="center"><sub>What the guard knows about the machine it is protecting - and the thresholds it chose for it.</sub></p>

On first start the daemon detects the hardware - chip, performance/efficiency core split, RAM,
fan count, battery health - writes it to `hardware.json` (shown in **About my Mac** in the menu
bar) and calibrates the defaults: a fanless Mac (Air) gets lower chip thresholds (78/70/88) and
its always-false fan alarm disabled. Calibration runs once per machine and **never overrides
thresholds you set yourself**.

### 5. It escalates so you cannot miss it

Notification with a distinct sound at pause, resume and kill - and at the **critical** level
additionally a **system alert on top of everything** (`critical_banner`, its own 3-minute gap,
self-dismissing). A notification is easy to miss under Focus or a full-screen app; the critical
banner is not. And when you are not at the machine at all: set a secret topic under **Settings >
Phone push (ntfy.sh)**, install the free [ntfy](https://ntfy.sh) app and subscribe to the same
topic - pauses, kills, cooling failures and hard-shutdown reports arrive on your phone. No
account, no server of ours; leave the field empty and nothing is ever sent.

This works from anywhere - it is internet push, not local networking. The Mac and the phone
do NOT need to share a WiFi network (and Bluetooth plays no part): the daemon posts over
HTTPS to ntfy.sh, and the phone receives it through normal system push wherever it has any
connection - LTE on a train, hotel WiFi, another country. Leave the Mac rendering at the
office, get the 90 °C pause on your phone at home, seconds later. Two honest edge cases:
if the MAC loses internet, pushes stop (protection itself keeps working locally - sounds
and the critical banner are a separate layer); if the PHONE is briefly offline, ntfy.sh
buffers messages (about 12 h) and delivers when it is back.

**The topic name is the whole secret.** Public ntfy.sh topics have no other access control:
anyone who knows (or guesses) the name can read your alerts *and* send fake ones. Do not use
a guessable name like `mac-guard` - the settings dialog **suggests a random, unguessable name**
(e.g. `mac-guard-x7kq93w2`) whenever the field is empty; take it, or bring your own long random
one. The messages themselves contain process names and temperatures, nothing more.

### 6. It keeps evidence (the black box)

<p align="center">
  <img src="docs/screens/guard_log.webp" alt="guard.log with a real cooling-failure alert" width="620">
</p>
<p align="center"><sub>A real entry from this log: <code>!!! COOLING FAILURE? chip 75.0 C and both fans at 0 rpm</code>.</sub></p>

<p align="center">
  <img src="docs/screens/export_report.webp" alt="Export a report for a repair shop: PDF or plain text" width="420">
</p>
<p align="center"><sub>One click turns the black box into something a repair shop will accept.</sub></p>

The daemon writes a heartbeat on every cycle and a marker on clean shutdown. After a restart it
compares those against `kern.boottime`. If the machine went down without warning, it records the
event **together with the last eight measurements taken before the crash**.

`thermal-report` then assembles a single file for a repair shop or warranty claim: hardware and
serial, battery health and cycle count, detected hard shutdowns with the readings that preceded
them, the system's own shutdown-cause entries, every intervention the guard made, and the full
measurement timeline with the peak temperature highlighted.

---

## What the usual tools don't do

There are excellent Mac monitoring tools - Stats, iStat Menus, TG Pro, Macs Fan Control. They
show you numbers, or drive the fans harder. **None of the popular ones touches the workload itself.** When the chip
hits 90 °C at 3 a.m., a chart of it is not protection.

coffee-paladin occupies a different category:

| | Monitoring apps | Fan controllers | **coffee-paladin** |
|---|---|---|---|
| Shows temperatures | yes | yes | yes |
| Drives fans | - | yes | no (macOS does) |
| **Pauses the workload itself, losslessly** | - | - | **yes - SIGSTOP/SIGCONT** |
| Sees orchestrators spawning 1-second children | - | - | **yes - subtree CPU accounting** |
| Keeps pre-crash readings for a warranty claim | - | - | **yes - black box + report** |
| Protects long jobs from draining the battery | - | - | **yes - battery gate** |
| Keeps the Mac awake for a job **only while it is cool** | - | - | **yes - keep-awake with a thermal fuse** |
| Whole-fleet view with zero infrastructure | - | - | **yes - a shared folder** |
| Needs sudo / kexts / accounts | varies | often | **no** |

The freeze is the heart of it: a paused process loses *nothing* - memory intact, resumes from
the same instruction. Measured live: 89.3 °C → 60.2 °C in 19 seconds, computation unharmed.

### Compared with keep-awake apps

Keep-awake apps solve a real problem, and coffee-paladin is not a replacement for them. But if
you use one while the machine is under load, it is worth knowing what happens to the heat.

| | Amphetamine | Wide Awake | **coffee-paladin** |
|---|---|---|---|
| Price | free (App Store) | Pro feature of Mac 4 Breakfast, one-time (14-day trial) | **free, MIT, source open** |
| Thermal safety | **none** | yes | **yes** |
| What it measures | - | **battery** temperature, 45 °C default (40-55) | **chip** temperature via IOReport |
| Reaction when hot | - | ends the awake session | **pauses the heavy processes**, resumes when cool |
| Behaviour under CPU load | keeps the Mac awake **while the CPU is busy** | unaffected | **the hotter it gets, the sooner work is paused** |
| Evidence for a repair shop | - | battery report | **black box: readings from before a hard shutdown** |
| Last release | 5.3.2, Nov 2023 | active | active |

Two things matter in that table. First, **battery temperature lags behind the chip by minutes** -
measured on a MacBook Pro M4 Pro: chip 53 °C while the battery still read 30 °C. A battery-based
threshold fires long after the chip has been running hot. Second, ending an awake session lets the
Mac sleep; it does not remove the heat source. Pausing the job does.

Amphetamine's CPU trigger deserves a specific mention, because it is easy to misread as a safety
feature. It is documented as *"while your Mac's CPU is being utilized to a specific threshold"* -
that is, keep the Mac awake **as long as** the CPU is busy. The busier and hotter the machine, the
longer sleep stays blocked. It is a convenience feature, not a fuse, and it was never advertised
as one.

---

---

## For AI agents

If you are a coding agent (Claude Code, Codex, Gemini CLI, …) about to run heavy work on this Mac — builds, `ffmpeg`, model inference, wide test suites, long loops — do this first:

1. **Detect the guard:** `test -f ~/.coffee-paladin/status.json`. If the file is missing, coffee-paladin is not installed here; suggest to the user both lines, because `brew install` alone installs files but starts nothing: `brew install pawelkwaczynski/tap/coffee-paladin` followed by `bash "$(brew --prefix)/share/coffee-paladin/install.sh"`.
2. **Read the state** (plain JSON, refreshed every ~15 s). The field `level` decides: `0` start the job, `1` start but do not parallelise, `2` finish what runs and start nothing new, `3` stop and tell the user the Mac is too hot.
3. **Trust it only when fresh:** if `time` is older than 60 s the daemon is not running — say so and treat the Mac as unprotected. If `dry_run` is `true`, the guard only watches; warn the user before anything heavy.
4. **Start heavy jobs through `safe-run`**, not directly: `safe-run --name build -- cargo build --release`. It refuses to start on a hot machine and registers the job with the daemon. Never pass `--allow-hot` on your own initiative.
5. **Never fight a pause.** A name in `paused` is a decision, not a hang: do not `SIGCONT` it, do not relaunch it, do not raise thresholds in `config.json`. It resumes by itself when the chip cools.

Full agent instructions ship as a skill: [`skills/coffee-paladin/SKILL.md`](skills/coffee-paladin/SKILL.md) (installed to `~/.claude/skills/coffee-paladin/` by `install.sh`).

## Your AI agent can talk to it

Coding agents are now a normal source of load on a laptop: they run builds, encode video,
start model inference, launch a dozen things in parallel. They are also, in practice, the
worst offenders - because an agent does not feel the fan and does not notice the machine
getting hot. That is the failure this project was written for, and it deserves a better
answer than "the guard will pause it eventually".

So coffee-paladin ships a **skill for AI agents**. `install.sh` drops it into
`~/.claude/skills/coffee-paladin/` (Claude Code picks it up automatically; the file is plain
Markdown, so any agent that reads skills can use it). It is not documentation *about* the
tool - it is instructions *for the agent*, and it teaches four things:

- **Look before you start.** `~/.coffee-paladin/status.json` is machine-readable and refreshed
  every ~15 s. One field decides everything: `level` - `0` start the job, `1` start but do not
  parallelise, `2` finish what is running and start nothing new, `3` stop and tell the human.
  Also `dry_run` (protection may be off!) and `unpausable` (protection is incomplete right now).
- **Start heavy work through `safe-run`.** Own process group, registered with the daemon,
  refuses to start on an already-hot Mac. And `--allow-hot` is a human's decision, not the
  agent's.
- **Never fight the pause.** No `SIGCONT` on a process the guard froze. No relaunching a job
  that "hung" before checking `paused`. No editing thresholds in `config.json` to push a job
  through. These are the three things an agent does when it mistakes protection for a bug.
- **Do not create the heat in the first place.** No background task without a timeout and a
  cleanup; no recursive search across iCloud-backed folders. That second rule came from a real
  incident: a `grep` that used 13 seconds of CPU in 1 h 42 min held a fanless Mac at 90 °C,
  because it kept `fileproviderd` and `cloudd` busy materialising files from the cloud. The
  CPU column showed almost nothing. Nobody guesses that one; it has to be written down.

The skill also treats `status.json` as a **heartbeat**: if its timestamp is older than 60 s
the daemon is not running, and the agent is told to say so and behave as if the Mac were
unprotected. An agent that reads a stale file and reports "level 0, all good" is worse than
one that never looked.

The agent itself is protected in return: `claude`, `codex`, `hermes`, `tmux`, `vim` and
anything holding a terminal's foreground are on the never-touch list by name, and `node`
processes are recognised by their **command line** - one running an agent, an MCP server or
a language server is untouchable, while a plain `node build.js` stays pausable, which is
exactly what a thermal guard is for. A guard that freezes the session driving it is not a guard.

```bash
cat ~/.claude/skills/coffee-paladin/SKILL.md    # what your agent was told
```


## Fleets: every Mac in one table

<p align="center">
  <img src="docs/screens/fleet.webp" alt="Apple fleet: two Macs, one of them stale" width="620">
</p>
<p align="center"><sub>Two machines, one reporting and one silent for 9 hours - machine names redacted here.</sub></p>

Companies increasingly run local AI on Macs: a Mac mini or Studio with plenty of RAM, models
on-prem, data that never leaves the building. Those machines grind 24/7 - just like render
farms, post-production studios and CI pools. With 15+ week queues for new Macs and rising
prices, losing one is not a minor incident, it is real downtime - every machine saved is
real money.

The fleet is deliberately simple: **the "server" is a folder your company already has**
(iCloud, Dropbox, SharePoint, SMB/NAS). No accounts, no SaaS panel, no data leaving your
folder - which makes compliance conversations short: IT sees plain JSON files in a place it
already controls. `fleet --json` plus the exit code plug into alerts, cron, Grafana or Slack,
and the guard on every machine keeps pausing overheating jobs and recording its black box
on its own.

```
FLEET: 14 machines, folder /Volumes/Studio/FleetTG

HOST         CHIP  FAN   POWER  RAM  DISK  STATE  TODAY  SEEN        ISSUES
render-01    91C   6.1k  72W    81%  88%   HOT    31p    now         throttled to 70%
render-02    64C   3.0k  55W    77%  61%   calm   2p     now
edit-suite   47C   1.2k  18W    52%  95%   calm   0p     now         disk 95% full
mini-ci-7    -     -     -      -    -     ?      -      3 h ago     STALE - not reporting
...
```

Each agent publishes a snapshot (`<hostname>.json`, about once a minute) into a **shared
folder**, and `fleet` reads the folder. That is the whole architecture. No server, no accounts,
no inbound network, nothing phoning home - the data is plain JSON you can open and read.

### Setup, step by step

**1. Pick the shared folder.** Any folder that all machines can write to:

| You have | Folder to use | Notes |
|---|---|---|
| iCloud (same Apple ID on your Macs) | `~/Library/Mobile Documents/com~apple~CloudDocs/FleetTG` | Right for one person with 2-5 machines. This is the closest thing to "link my Apple ID" - Apple offers no fleet API, but iCloud Drive syncs a folder just fine. |
| Dropbox / Google Drive | `~/Dropbox/FleetTG` | Share the folder with each machine's account. Good for small teams. |
| Microsoft 365 | a synced SharePoint library folder | The corporate route; IT already manages access. |
| A NAS / file server | `/Volumes/<share>/FleetTG` | The render-farm route - fastest updates (no cloud sync delay). Make sure the share mounts at login. |

**2. On every machine**, after installing coffee-paladin, point the agent at the folder - one key
in the config:

```bash
python3 - <<'EOF'
import json, os
p = os.path.expanduser("~/.coffee-paladin/config.json")
c = json.load(open(p)) if os.path.exists(p) else {}
c["fleet_dir"] = "~/Library/Mobile Documents/com~apple~CloudDocs/FleetTG"   # your folder here
json.dump(c, open(p, "w"), indent=2)
EOF
```

Or let the tool find your synced folders and do it for you:

```bash
fleet --setup      # detects iCloud Drive / Dropbox / Google Drive / OneDrive / mounted volumes,
                   # you pick a number, it writes the config
```

No restart needed - the daemon re-reads its config every cycle and starts publishing within a
minute.

**What "the same folder" actually requires.** Nothing Apple-specific. Any folder each Mac can
reach under a path of its own - and the path may differ per machine, because every Mac stores
its own `fleet_dir`.

| Folder | What it takes |
|---|---|
| iCloud Drive | the same Apple ID signed in on every Mac, or a folder shared with the other Apple ID |
| Google Drive / OneDrive / Dropbox | the same account signed in on every Mac, or a folder shared with the other account. Paths contain the account name, so they differ per machine - that is fine |
| SMB / NAS / external volume | mount it on every Mac |

**Sync is not instant, and that is visible.** With on-demand storage (iCloud *Optimize Mac
Storage*, Drive streaming) another Mac's snapshot can arrive minutes late, or sit there as a
placeholder that has not been downloaded yet. Until it lands, that machine is simply missing
from the table on this Mac, or listed as not reporting - the data is not lost, it just has not
arrived. Each Mac always sees itself immediately, because it writes its own file locally.

**3. On whichever machine you sit at**, look at the fleet:

```bash
fleet              # one table, flags what needs attention, exit code 2 if anything does
fleet --watch      # refreshes every 30 s
fleet --json       # machine-readable, for dashboards and automation
```

A host that has not reported for 5 minutes is flagged `STALE` - crashed, asleep, or its sync
broke; either way you want to know. `fleet --json` plus the exit code make it trivial to wire
into Slack alerts, Grafana, or a cron job that emails you.

### What is in the published snapshot

Hostname (or your custom label), model, serial number, temperatures, fan rpm, power draw,
RAM/disk usage, power source, guard level and reason, paused-job names, today's intervention
counts, and the last detected hard shutdown. To be clear about privacy: the snapshot never
leaves **your own shared folder** - there is no server and nothing phones home - and if the
serial number or the top-process name is too much for your environment, strip them: the whole
file is built in one function (`fleet_write`).

---

## Where the data comes from

This is the interesting part, because macOS does not hand out chip temperatures to unprivileged
processes.

| Signal | Source | Notes |
|---|---|---|
| **Chip / GPU temperature** | [`macmon`](https://github.com/vladkens/macmon) → **IOReport** | The one route that still works without `sudo`. |
| **Fan RPM, power draw (W)** | same | Also gives per-core frequency and RAM/swap usage. |
| **Thermal pressure** (`nominal`/`fair`/`serious`/`critical`) | `ProcessInfo.thermalState` via a tiny Swift binary | Public API, no privileges needed. |
| **Battery temperature, cycles, cell voltages** | `ioreg -c AppleSmartBattery` | Units vary by model - see the gotcha below. |
| **CPU throttling** | `pmset -g therm` → `CPU_Speed_Limit` | 100 = not throttled. Note this is available *speed*, not free capacity: a machine can be busy at 100% speed limit - which is why the menu shows this row only when actual throttling is happening. |
| **Power source, battery %** | `pmset -g batt` | |
| **Processes** | `ps` | Own CPU plus subtree rollup. |

### Three thermometers, one machine

It is one piece of silicon, but different regions, separate sensors and different jobs:

1. **Chip (CPU) vs GPU.** On an M4 Pro the processor cores and the graphics cores sit
   next to each other on the same die, but they heat up separately, depending on what
   you do: compilation, Python and scripts heat the CPU part; video, games and AI
   models on the GPU heat the graphics part. The difference can be a dozen degrees,
   which is why we show both. (The Neural Engine is on that die too, but Apple exposes
   no public sensor for it - when it grinds, its heat shows up indirectly in the CPU
   reading anyway.)
2. **The paladin watches the hotter one.** For the pause decision the guard takes
   max(CPU, GPU) - "the hottest point of the die" (`soc_temp_c` in `guard.py`) - so it
   does not matter which half of the chip is cooking, the protection works the same.
3. **The battery is a different league entirely.** A separate physical component that
   heats slowly (from charging and from case heat), but with much lower limits:
   lithium-ion degrades above ~40 °C. That is why its pause threshold is 40 °C while
   the chip is allowed to run to 90 °C.

In short: chip and GPU are two thermometers in one piece of silicon (different jobs,
different temperatures), and the battery is a third thermometer in a more fragile place.

### Two dead ends, documented so you don't repeat them

**`powermetrics` requires a password.** It is the obvious tool and it is unusable for an
unattended agent.

**Reading SMC sensors through `IOHIDEventSystem` no longer works.** This was for years *the*
way to read Apple Silicon temperatures without root: match HID services on usage page `0xff00`,
usage `0x0005`, and pull `kIOHIDEventTypeTemperature`. On **macOS 26 it returns zero sensors** for
an unentitled process - Apple closed it. A complete, working-by-the-old-rules implementation is
kept in [`experiments/soctemp.swift`](experiments/soctemp.swift) as a reference and a warning.
IOReport is currently the surviving path.

**The battery temperature unit is not fixed.** Different battery controllers report different
scales: hundredths of a degree on one Mac (`3081` = 30.81 °C), tenths on another (`444` = 44.4 °C),
and some fields whole degrees (`41` = 41 °C). A hardcoded divisor is wrong somewhere - it produced
a reading of *444 °C* on one machine and *0.4 °C* on another. coffee-paladin scales the raw value
into the range a lithium cell can physically be in instead of assuming a unit.

**Why battery temperature alone is not enough.** It lags the chip by minutes and reads far lower.
A measurement taken while writing this README: **chip 53.5 °C, battery 30.6 °C.** A guard using
only battery temperature reacts long after the damage window has opened.

---

## Tests

The hard-crash detector - the code that writes warranty evidence - ships with its own test
matrix: 16 cases covering clean/dirty shutdowns, backup artifacts, garbage content and
timezone changes (a pulse written in Warsaw must still prove a crash after booting in New
York). It runs in one command against an isolated HOME and never touches your real black box:

```bash
T=$(mktemp -d) && python3 tests/test_wykryj_twardy_pad.py "$T"; rm -rf "$T"
python3 tests/test_paladin.py          # 21 checks: CLI, menu bar, artwork, translations
python3 tests/test_config_odporny.py   # 24 checks: a config must not blind the guard
python3 tests/test_safe_run_hot.py     #  8 checks: safe-run refuses to start when hot
python3 tests/test_demote_promote.py   # 20 checks: demotion to E-cores and back
python3 tests/test_b2_node.py          # 17 checks: node is judged by its command line
```

**What actually runs, and what it does not.** The suites above are plain Python - no test
framework, no fixtures to install, and they refuse to touch your real black box. On top of
them: **semgrep** over the Python sources (`p/python` + `p/secrets`, 187 rules - currently
0 findings) and **ruff** (`E9,F` - clean). Be sceptical of the last two, though: semgrep's
free rule set is deep for Python and thin for shell and Swift (2 rules), so the menu bar app
is covered by human and model review, not by a scanner. There is no fuzzing and no CI here;
this is a tool for one platform, and the interesting failures were found by running it on two
different Macs, not by a matrix.

This project was **tested and refined with the help of AI - four heads at once** ;) and the
process is worth describing, because it found bugs no single reviewer would have caught. Every risky area (signal handling on
process groups, the CPU limiter, sleep-lock management, the crash detector) was reviewed
by **four different AI models independently** - Claude (Anthropic), Codex/GPT-5.5 (OpenAI)
and two local ones, Devstral 24B on MLX and qwen3:4b on Ollama - across six
review rounds, with every claim verified by hand against the actual code before anything
was changed. On top of that, **a second Mac audited the first one's install**: a fanless
8 GB machine exercised code paths a well-cooled 14-core machine never would. The
cross-machine audits caught, among ~40 fixes in one day: a UI checkbox that reported
protection as armed while the daemon only observed, an installer that declared success
while the menu bar never started, and a timezone bug that could silence a genuine crash
in the evidence file (a pulse written in Warsaw, read after "flying" to New York, parsed
as the future). Agreement between reviewers proves little; the divergence is the signal.

---

## Install

Requires macOS on Apple Silicon, Xcode command line tools (`xcode-select --install`) for `swiftc`,
and [Homebrew](https://brew.sh) so the installer can fetch `macmon`.

**Homebrew (recommended):**

```bash
brew install pawelkwaczynski/tap/coffee-paladin
bash "$(brew --prefix)/share/coffee-paladin/install.sh"
```

**From source:**

```bash
git clone https://github.com/pawelkwaczynski/coffee-paladin.git
cd coffee-paladin
bash install.sh
```

Both give you the same version. The installer compiles the two Swift helpers, installs the scripts
into `~/.local/bin`, writes a default config into `~/.coffee-paladin/config.json` (it will **not**
overwrite an existing one), and loads two LaunchAgents - the daemon and, separately, the menu bar
app, so you can disable the latter without touching the safety net.

The menu bar app is installed as **`coffee-paladin.app` in your Applications folder** - with an
icon, a version Finder can read, and a signature on the whole bundle. It still sets `LSUIElement`,
so it stays out of the Dock and out of Cmd+Tab. Nothing is downloaded pre-built: the app is
compiled on your machine from the sources you just fetched, so Gatekeeper has nothing to quarantine
and you never see the "unidentified developer" warning.

**A fresh install starts in watch-only mode.** It measures, logs and alerts - with sound - but
pauses nothing, until you enable protection yourself: one click in the menu bar (*Enable
protection*) or `"dry_run": false` in the config. A tool that touches your processes should earn
that right by first showing you what it *would* have done. The menu bar shows an eye icon while
in watch-only mode, so you cannot forget which mode you are in.

To remove everything: `bash uninstall.sh` (keeps the measurement history and black box -
you may still need them for a warranty claim; `--purge` removes those too).

Make sure `~/.local/bin` is on your `PATH`.

---

## Usage

### `heat` - one-shot status

```
[OK] thermal state: nominal   chip: 53.5 °C   battery: 30.6 °C   CPU available: 100%   load: 4.29
   fans: 4500 rpm, 4831 rpm
   power: AC adapter   draw: 32.6 W
   coffee-paladin: running ✅
```

Plus what is currently burning CPU, the 24-hour peak, and the guard's recent interventions.

### `safe-run` - the right way to start a heavy job

```bash
safe-run --hours 8 --name render -- ffmpeg -i input.mov ... output.mp4
```

Refuses to start on an already-hot machine, applies `nice +10` and background QoS (efficiency
cores), puts the job in its own process group, enforces a time budget, and prints a report with
the peak temperature at the end. Jobs started this way are registered with the daemon explicitly,
so they never depend on name matching.

### `heatbar` - menu bar

<p align="center">
  <img src="docs/screens/show_in_bar.webp" alt="Choose what appears in the menu bar" width="420">
</p>
<p align="center"><sub>You choose what the bar shows - seven readings, all optional.</sub></p>

<p align="center">
  <img src="docs/screens/settings.webp" alt="Settings: thresholds, battery gate, CPU limit" width="440">
</p>
<p align="center"><sub>Thresholds, the battery gate and the CPU ceiling - with the reasoning printed under each slider.</sub></p>

```
C67°  G64°  B33°  ·  3.3k rpm  ·  42W  ·  throttled  ·  paused
```

chip / GPU / battery / fan rpm / power draw / RAM used / disk used, plus a throttling marker when macOS is
limiting the CPU and a pause marker when something is frozen. a fan reading of 0 with a warning mark means the fans are stopped while the chip is
hot; a RAM warning means memory is 62 % used **and** the machine has started swapping.

Everything on the bar is optional - **Show in the bar** gives you a checkbox per element and the
choice is remembered in `~/.coffee-paladin/heatbar.json`. RAM and disk are off by default.
The language switch (EN · PL · RU · 中文 · ES) sits as a row of buttons right on the main menu,
**About my Mac** shows the detected hardware, and **Start at login** toggles autostart of both
agents (on by default).

**Apple fleet** in the menu shows every Mac publishing to your shared fleet folder - chip
temperature, fans, watts, RAM, state, paused jobs and last-seen age per host - each under its
own custom name (*Settings > Name this Mac in the fleet*; with five identical MacBooks the
hostname tells you nothing), with the model shown inline and the serial number in the tooltip,
and a
`STALE - not reporting` marker after 5 minutes of silence. It reads the same files as the
`fleet` CLI, refreshed by a background cache every ~30 s, so opening the menu never blocks on
iCloud/SMB. "Live" here means the agent's ~1-minute publishing rhythm plus your folder's sync
delay - perfect for a glance, not for second-by-second monitoring (that is what a future HTTP
collector would be for).

**Branding:** the menu header and footer render `~/.coffee-paladin/logo.png` (black-on-transparent,
theme-aware template) and `logo_footer.png` (+ optional `logo_footer_dark.png` for dark mode;
a click opens `footer_logo_url` from the config). The installer copies the logos shipped in
`branding/` - swap those files for your own to rebrand your install.

The menu adds a block-character temperature graph, a trend and forecast ("rising 2.1 °C/min -
about 4 minutes to pause"), **what is heating the machine right now** (top 3 by CPU - the best
per-process proxy for heat there is) and **what is eating the RAM** (top 3 by resident memory),
running `safe-run` jobs, today's intervention count, a manual **Freeze / Resume** control, and
**Export report**.

The bar measures nothing itself - it reads `~/.coffee-paladin/status.json`, which the daemon writes
every cycle. It therefore costs no CPU and can never disagree with the guard. Manual commands are
passed back through a file and executed by the daemon, so exactly one process ever decides what
gets paused.

### `thermal-report` - evidence for a repair shop

```bash
thermal-report --days 14          # plain text to your Desktop
thermal-report --days 14 --pdf    # the same, rendered to PDF
```

---

## Configuration

Most of it is adjustable from the menu bar: **Settings** holds a slider for the chip pause
threshold with a live warning under it, a slider for the battery gate, and switches for
notifications, language, and a **watch-only (dry run)** mode that logs what it *would* do without
touching a single process - the honest way to build trust in a tool that can freeze your work.

The daemon re-reads its config on every cycle, so changes take effect immediately, with no restart.

### Do different chips need different thresholds?

Between M-series generations, not really: they all throttle themselves somewhere around
100-108 °C and Tjmax is about 110 °C, so the shipped 85/76/90 is sane from M1 to M4 and there is
no reason to expect M5 or M6 to leave that range.

**Cooling is what differs.** A fanless Mac (Air, 12-inch) dumps heat into the chassis and gets hot
sooner, so a lower threshold - around 75-78 °C - is kinder to it. coffee-paladin detects the
absence of fans and simply skips the fan alarm there, but the temperature threshold is yours to
set. That is exactly what the slider is for.

`~/.coffee-paladin/config.json`. The defaults:

| Setting | Default | Meaning |
|---|---|---|
| `soc_pause_c` | 85 | freeze heavy jobs at this chip temperature |
| `soc_resume_c` | 76 | resume below this (hysteresis) |
| `soc_kill_c` | 90 | terminate, but only after `kill_after_polls` consecutive readings |
| `batt_pause_c` / `batt_kill_c` | 40 / 45 | **battery** temperature - lithium cells degrade above ~45 °C |
| `batt_pct_pause` | 10 | pause when on battery at or below this charge |
| `fan_alert_temp_c` | 70 | above this the fans must be spinning |
| `max_pause_minutes` | 45 | a job paused longer than this is **terminated with `SIGTERM`** - for an encoder without checkpoints that means losing all progress, so give long jobs `safe-run --hours N` and headroom here |
| `max_pause_minutes_batt` | 240 | same limit when the *only* reason for the pause is a low battery (waiting for a charger is not a failure) |
| `demote_after_minutes` | 5 | a heavy process grinding longer than this **while the chip is hot** is moved to E-cores; it returns to P-cores on its own once the chip cools to `soc_resume_c` |
| `demote_above_c` | `soc_resume_c + 4` | demotion only happens at or above this chip temperature - a cool machine never slows anyone down |
| `unknown_cpu_percent` | 50 | catch-all threshold for unrecognised processes |
| `never_patterns` | see `guard.py` | never touched, overrides everything |
| `never_extra` | `[]` | your own additions to the never-touch list (tools you do not want frozen) |
| `never_arg_patterns` | guard's own tooling | matched against the **full command line**, useful when a job runs under an interpreter |
| `lang` | `en` | `en`, `pl`, `ru`, `zh` or `es` |
| `dry_run` | **`true`** | watch-only: log and alert, never signal (disable to arm the guard) |
| `critical_banner` | `true` | modal system alert at the critical level (own 180 s gap, self-dismissing) |
| `keep_awake_auto` | `false` | hold a sleep block while a heavy job runs **and** the machine is cool |
| `job_cores_mode` | `"efficiency"` | default cores for `safe-run` jobs: `"efficiency"` or `"all"` |
| `job_cpu_percent` | `95` | duty-cycle CPU cap for `safe-run` jobs (50-100) |
| `ntfy_topic` | `""` | secret ntfy.sh topic for phone push (empty = off) |
| `download_kbps` | `500` | network-activity threshold for the *while downloading* keep-awake mode |
| `calibrated_for` | set by the daemon | hardware tag; delete it to re-run auto-calibration |
| `sound` | `true` | distinct system sound per event (pause / resume / kill) |
| `fleet_dir` | `""` | shared folder for fleet snapshots (see the fleet section) |

### A note on numbers, because this trips people up

**Do not set `soc_pause_c` to 45.** Chips are not batteries. An idle M4 Pro sits at 40-55 °C, and
ordinary work pushes it past 60 without anything being wrong. Apple Silicon throttles itself
somewhere around 100-108 °C and Tjmax is about 110 °C. A 45 °C threshold means permanent pause and
a useless safety net. 45 °C is the correct number for the *battery*, and that is where it is used.

The shipped defaults are deliberately more conservative than Apple's own throttling point.

---

## Known limitations

- **Time-sensitive I/O can notice a pause.** A frozen process stops answering the network:
  long pauses can trip remote timeouts, heartbeats/watchdogs and license-server check-ins.
  Batch compute, renders and downloads by the guard's own hand are fine; latency-critical
  services belong in `never_extra`.
- **It will freeze GUI applications too.** If Blender or a video export pushes the chip to 85 °C,
  that window freezes until things cool down. Nothing is lost, but it looks like a hang. Add such
  apps to `never_patterns` if you would rather they were left alone.
- **Chip temperature depends on `macmon`.** Without it the daemon still runs, but falls back to
  battery temperature and thermal pressure only, and loses fan monitoring.
- **Apple Silicon only.**
- The LaunchAgent labels are `pl.pawel.coffee-paladin` and `pl.pawel.coffee-paladin-bar`. Rename them in the
  plists if you prefer something neutral.
- Messages are English by default; `"lang"` in `config.json` (or `TG_LANG`) switches every tool,
  the notifications and the menu bar to Polish, Russian, Chinese or Spanish. Adding a language
  means adding one dictionary per file.
- Some inline code comments are still in Polish.

---

## Honest authorship note

**Author: Paweł Kwaczyński (FOCUS FRAME).** The requirements, the decisions, the verification
and the risk in this project are one person's - the models below wrote code against that.

I work in Python. The Swift menu bar app exists only because I build Swift in a pair with
AI - and this project takes that seriously: four different models reviewed each other's work
across six rounds, and a second Mac audited the first one's install. Here it was the human
who decided, verified and took the risks; the AI wrote the Swift - human-in-the-loop. Which
is why I see no reason to hide it.

Named, because vague credit is not credit. The Swift - the menu bar, the welcome window, the
paladin panel - was written by **Claude (Anthropic)** inside Claude Code, against my
requirements and my review. **Codex (OpenAI, GPT-5.5)** was the adversarial reviewer: it read
the same code independently and its job was to find what the author missed. Two **local models**
ran alongside - **Devstral 24B** on MLX and **qwen3:4b** on Ollama - because a reviewer that
never leaves the laptop can be asked anything, as often as you like. The paladin artwork was
generated with **ChatGPT (OpenAI)**. Nothing here shipped because a model approved it; every
claim was checked against the running code first.

## Buy me a double espresso ☕︎

This project literally runs on coffee - the release codename is "Ristretto" and the
keep-awake fuse is my answer to Caffeine. If coffee-paladin saved your Mac (or your render),
buy me a coffee: **https://suppi.pl/panbookovsky**

## License

MIT - do whatever you like with it. If it saves your machine, that is satisfaction enough.

<p align="center">
  <img src="docs/screens/paladin_panel.webp" alt="The paladin panel, pinned under the menu bar" width="260">
</p>
<p align="center"><sub>Click the product name at the top of the menu and the paladin steps out, pinned under the bar.</sub></p>

**Artwork.** The paladin - the mascot you see above, in the welcome window, in the menu header
and in the `heat --paladin` easter egg - was **generated with ChatGPT (OpenAI)** and is used
as the official mascot of the project. Everything else in `branding/` is derived from those two
source files; details in [`branding/CREDITS.md`](branding/CREDITS.md).

Built by Paweł Kwaczyński / FOCUS FRAME, 2026. Developed also as a project of **AIrON** -
the student research club for computer science at AHE in Łódź (SKN Informatyki AHE w Łodzi).

---

<a name="po-polsku"></a>

# Po polsku

**Inne języki:** [中文](README.zh.md) · [Русский](README.ru.md) · [Español](README.es.md) — wersje skrócone.

**Bezpiecznik termiczny i zasilania dla Maców na Apple Silicon - od jednego laptopa po całą
flotę.** Pilnuje temperatury chipa, baterii, wentylatorów i zasilania, a gdy robi się gorąco -
**wstrzymuje** ciężkie zadania, zamiast pozwolić im pracować aż komputer zgaśnie. Pisany z myślą
o ludziach, u których Maki pracują na chleb: farmy renderujące, studia postprodukcji, pule
Mac mini pod CI, zespoły ML - i każdy, kto zostawia laptop z obliczeniami na noc.

Bez `sudo`, bez rozszerzeń jądra, bez niczego działającego jako root.

## Skąd ta nazwa i skąd ta kawa

<p align="center">
  <img src="branding/paladin.png" alt="coffee-paladin" width="260">
</p>

Kawa nie jest ozdobnikiem. Ten program stoi na `caffeinate` - prawdziwym narzędziu
wbudowanym w macOS od 2012 roku, które leży w `/usr/bin/caffeinate` i robi dokładnie to,
co sugeruje nazwa: **nie pozwala komputerowi zasnąć**. Apple zażartowało, nazywając je
po kofeinie, i cała kategoria poszła za tym żartem - najpierw Caffeine z ikoną filiżanki,
potem Amphetamine, gdzie metafora poszła o stopień dalej.

Nasz rycerz trzyma tę filiżankę z jednego powodu: **też pije z tego kubka**. Gdy odpalasz
`safe-run`, pod spodem startuje `caffeinate` i pilnuje, żeby Mac nie usnął w połowie
Twojego renderu.

Różnica jest w tym, co ten rycerz robi z kubkiem, gdy zrobi się gorąco: **odstawia go**.
Cała reszta tej kategorii trzyma Maca w czuwaniu bezwarunkowo - także wtedy, gdy leży
rozgrzany w plecaku. Nasz puszcza blokadę snu w chwili, gdy chip przekracza próg, bo sen
jest najszybszym chłodzeniem, jakie ma komputer.

Stąd paladyn, a nie zwykły rycerz. Paladyn to ten, który stoi na warcie dobrowolnie
i ma zasadę ważniejszą od rozkazu. Rozkaz brzmi „nie pozwól mu zasnąć".
Zasada brzmi „ale nie pozwól mu się ugotować".

**Shield the Process, Sip the Coffee.**

## Skąd się wziął

MacBook Pro M4 Pro pracował nocą - render wideo i inne ciężkie obciążenia, czyli dokładnie to,
do czego takie maszyny się kupuje. Rano: zapach spalenizny spod obudowy i twarde wyłączenie.
Gorzej - gdy potem sięgnięto do logów, **nie było czego czytać**: żadnej paniki jądra, żadnego
zapisu o przegrzaniu, a dziennik systemowy po prostu urywał się w chwili zgaśnięcia. Nie dało
się odtworzyć, jaka była temperatura.

A utrata Maca boli w 2026 bardziej niż kiedykolwiek. Gdy w lipcu dzwoniliśmy po operatorach
leasingu, kolejka na nowe MacBooki wynosiła 15+ tygodni (klienci czekający od kwietnia),
z rynku znikały nawet leciwe M1, a cenniki poszły w górę. Nikt nie może sobie pozwolić
na utratę maszyny, którą ma.

Ten projekt odpowiada na oba problemy: *zatrzymać, zanim się ugotuje*, i *zachować dowody, gdy coś
jednak pójdzie źle*.

## Dlaczego to jest cenne właśnie teraz (2026)

Zbyt duża temperatura zawsze psuła komputery. W 2026 zmieniło się co innego: awarie stały
się drogie jak nigdy.

Przegrzania to nie teoria. MacStadium, czyli zawodowa serwerownia pełna Maców, napisało
na własnym blogu [w 2020 roku](https://macstadium.com/blog/digging-deeper-into-2018-mac-minis-at-macstadium),
że Mac mini na 100% CPU zaczyna zwalniać po około godzinie, a w zwykłych szafach
rackowych mieli przypadki awarii związanych z temperaturą. Poradzili sobie, bo zbudowali
własne uchwyty i korytarze zimnego powietrza. Twój Mac na biurku nie ma żadnej z tych
rzeczy. Samo Apple [przepraszało kiedyś za throttling](https://techcrunch.com/2018/07/24/apple-apologizes-issues-update-for-macbook-pro-thermal-throttling/)
(dławienie zegarów przy przegrzaniu). Po ich poprawce z 2018 roku te same MacBooki
były do 70 procent szybsze, a 13-calowy nawet dwukrotnie(!). Tyle kosztuje złe zarządzanie ciepłem, policzyło to
samo Apple. Ok, mówimy o wielkich firmach, a co jeśli jesteś studentem i z przyzwyczajenia
zamykasz laptop z otwartym procesem ładując go do plecaka? Apple podaje
[przedział zakresu pracy na 10-35 °C otoczenia](https://support.apple.com/en-us/102336),
a wątki „Mac gorący w etui, bo jakaś apka nie dała mu zasnąć" ciągną się na forach od lat.
W [jednym z nich](https://forums.macrumors.com/threads/2017-running-very-hot-in-my-bag.2216012/)
użytkownikowi stopiły się nawet klawisze...

Wymiana „ugotowanego" Maca zrobiła się droga i boleśnie wolna. 25 czerwca 2026 Apple
[podniosło ceny](https://9to5mac.com/2026/06/25/apple-price-increases-mac-ipad-more/):
Mac Studio M3 Ultra z 3999 na 5299 dolarów, w jeden dzień. Tim Cook mówił, że nigdy nie
widział, żeby komponent zdrożał tak szybko, a już w kwietniu przyznał, że Studio i mini
[potrzebują „kilku miesięcy"](https://www.macrumors.com/2026/04/30/mac-studio-mac-mini-constrained-months/),
żeby dogonić popyt napędzany przez AI. Pamięci DRAM podrożały
[80-90% w jeden kwartał](https://spectrum.ieee.org/dram-shortage). W lipcu wzrosty
zaczęły hamować, ale prognozy mówią o normalizacji dopiero w latach 2027-2028. Dostawy?
Bazowe konfiguracje to tygodnie, Mac Studio
[10-14 tygodni](https://appleinsider.com/articles/26/07/22/upgraded-mac-mini-mac-studio-and-oled-imac-are-all-in-the-pipeline),
a wysokie opcje RAM to miesiące albo status „Currently Unavailable". Opcję 512 GB Apple
wycięło w marcu, [128 GB w maju](https://www.tomshardware.com/desktops/apple-quietly-axes-128gb-mac-studio-amid-supply-constraints-and-local-ai-frenzy-highest-memory-capacity-reduced-to-96gb-two-months-after-discontinuation-of-512gb-model).
Wiosną czekało się [nawet 4-5 miesięcy](https://www.macrumors.com/2026/04/06/mac-mini-and-mac-studio-long-shipping-delays/).

Sprawdziłem to także na sobie. 30 lipca napisałem do trzech polskich dostawców Apple
o leasing jednego Mac Studio. Jeden odpisał, że „ze względu na globalny problem
z dostępnością nie przyjmuje zamówień na tę kategorię produktów". Drugi, autoryzowany
partner Apple, podał cenę o 23% wyższą niż cennik sprzed podwyżki i zastrzegł, że terminu
nie zna, cenę może zmienić już po złożeniu zamówienia, a samo zamówienie może anulować.
Trzeci nie odpisał wcale.

A hype'owany wszędzie boom na AI katuje te maszyny jak nic nigdy wcześniej. Mac z dużą
pamięcią unified (wspólną dla procesora i grafiki) to najtańszy sposób na duże modele
lokalnie. 512 GB w Macu kosztowało 9499 dolarów. Jedna karta H100 z 80 GB chodzi po
około 30 tysięcy. Więc Maki na całym świecie mielą teraz LLM-y i rendery godzinami,
pod korek. Długie grzanie to dokładnie to, co zabija te jednostki, laptopy i baterie,
bo każde 5-10 °C ponad optimum to mniej więcej dwa razy szybsze starzenie ogniwa.

Wniosek jest prosty. Działającego Maca nie odkupisz dziś ani szybko, ani w cenie
z początku roku. Dlatego coffee-paladin pilnuje go ZA DARMO, w kodzie, który możesz
przeczytać, zanim mu zaufasz i opiekuje się twoimi procesami.

## Co robi

<p align="center">
  <img src="docs/screens/menu_pl.webp" alt="coffee-paladin - pasek menu po polsku" width="360">
</p>
<p align="center">
  <img src="docs/screens/languages.webp" alt="To samo menu w pieciu jezykach" width="820">
</p>
<p align="center"><sub>To samo menu w pięciu językach - jeden klik w <em>Ustawienia &gt; Język</em>.</sub></p>

**Zamraża, nie zabija.** Przy przegrzaniu ciężkie procesy dostają `SIGSTOP` - proces zamiera
w miejscu, pamięć zostaje nietknięta, a po ostygnięciu `SIGCONT` i liczy dalej od miejsca,
w którym stanął. Zatrzymanie następuje między instrukcjami, więc sama pauza nie może uszkodzić
danych procesu. I nie ma w tym nic egzotycznego: macOS sam pauzuje tak procesy na okrągło
(App Nap robi to aplikacjom w tle, każdy debugger przy podpięciu), sprzęt też nic nie traci -
wstrzymany proces po prostu nie dostaje czasu procesora. Uczciwe zastrzeżenie: pauzę mogą
zauważyć rzeczy wrażliwe na czas - druga strona połączenia sieciowego, watchdogi, serwery
licencji (patrz ograniczenia). Alternatywa i tak jest gorsza: niepilnowane ciepło znaczy, że
macOS dławi wszystko zegarami, a w skrajności komputer gaśnie twardo - i to DOPIERO niszczy
pracę. Zmierzone na żywym zadaniu: chip 89,3 °C → pauza → **60,2 °C po dziewiętnastu
sekundach** → wznowienie. Obliczenia niczego nie zauważyły. Ubicie (łagodnym `SIGTERM`, żeby
zadanie zdążyło zapisać checkpoint) następuje dopiero po kilku krytycznych odczytach z rzędu.

**Znajduje prawdziwego sprawcę.** Lista znanych nazw procesów zawsze będzie dziurawa - własna
binarka `b3core` rozgrzała maszynę do 90 °C, bo do niczego nie pasowała. Jeszcze gorszy przypadek:
skrypt Pythona rozsiewał setki instancji solvera `cadical` żyjących po sekundę - dziecko było za
krótkie, by przekroczyć próg, a rodzic sam nie zużywał prawie nic. Dlatego guard liczy **CPU
całego poddrzewa procesów** (ten Python pokazał **595 %**) i zamraża źródło, oraz traktuje jako
ciężkie **każde** zadanie powyżej 50 % CPU żyjące dłużej niż 2 minuty, niezależnie od nazwy.

**Pilnuje zasilania.** Na baterii poniżej 10 % pauzuje długie obliczenia i wznawia je dopiero po
podpięciu zasilacza - czekanie na kabel nie jest awarią, więc taka pauza może trwać godzinami.
Osobno ostrzega, gdy chip przekracza 70 °C, a wentylatory stoją.

**Trzyma Maca w czuwaniu - ale z bezpiecznikiem.** `safe-run` blokuje sen dokładnie na czas
zadania (`caffeinate`), a demon umie robić to sam dla każdego ciężkiego zadania (opcja w
Ustawieniach, domyślnie wyłączona). Z paska menu dostępne są też tryby ręczne jak w Amphetamine:
timer (15 min - 12 h), bezterminowo, „dopóki działa aplikacja" (wybór z listy uruchomionych)
i „dopóki trwa pobieranie" (aktywność sieci). Różnica względem Caffeine/Amphetamine: każdy z tych
trybów trzyma blokadę czuwania **tylko póki maszyna jest chłodna** - przy przegrzaniu guard ją
zwalnia, bo sen chłodzi najszybciej. Bezwarunkowy keep-awake w plecaku to klasyczna droga do
ugotowania laptopa. Kubek na pasku pokazuje, kiedy blokada jest trzymana.

**Sam latami używałem Amphetamine.** Świetna appka, bogate wyzwalacze - i właśnie w tym
pułapka: wiernie trzyma czuwanie także wtedy, gdy Mac jest gorący, w torbie, na kołdrze,
gdziekolwiek. Odinstalowałem ją w dniu, w którym zrozumiałem, że moje narzędzie keep-awake
nie ma pojęcia, jaką temperaturę ma mój Mac. Blokada snu bez bezpiecznika termicznego to
obietnica dalszego grzania.

> **Cała różnica w jednym zdaniu:** każda aplikacja tej kategorii umie trzymać Maca
> w czuwaniu. Tylko ta **odstawia kubek, gdy robi się gorąco** - pozostałe wiernie
> podtrzymają czuwanie także wtedy, gdy Mac gotuje się w plecaku. To nie jest wariant
> tej samej funkcji, to odwrotna filozofia - i cała reszta narzędzia stoi na niej.

| | Caffeine | Amphetamine | coffee-paladin |
|---|---|---|---|
| Trzyma obliczenia | przez ekran | tak | tak |
| Pozwala ekranowi zgasnąć i się zablokować | nie | zależnie od konfiguracji | **zawsze** |
| Zwalnia blokadę, gdy Mac jest gorący | nie | nie | **tak - bezpiecznik termiczny** |
| W ogóle widzi temperaturę | nie | nie | **tak (chip, bateria, wentylatory)** |
| Timer / dopóki działa apka / dopóki pobiera | timer | tak | tak |
| Pauzuje zadania, które przegrzewają Maca | nie | nie | **tak** |
| Zapisuje czarną skrzynkę przed twardym wyłączeniem (dowód w przypadku awarii) | nie | nie | **tak** |
| Open source | nie | nie | **MIT** |

**Ekran śpi. Obliczenia nie.** Druga różnica względem rodziny Caffeine: klasyczne aplikacje
trzymają asercję *wyświetlacza* (`caffeinate -d`) - ekran pali waty całą noc tylko po to, żeby
udowodnić, że Mac czuwa. coffee-paladin trzyma wyłącznie asercję *systemu* (`caffeinate -is`):
zablokuj ekran (Ctrl+Cmd+Q), pozwól mu zgasnąć - zadania liczą dalej po ciemku, a wyświetlacz
(przy lekkiej pracy często największy pojedynczy odbiornik energii) nie kosztuje nic. Jeden
haczyk: klapa musi zostać otwarta - zamknięcie pokrywy wymusza sen mimo asercji (wyjątek:
tryb clamshell z zewnętrznym monitorem i zasilaczem). Bezpiecznik termiczny pozostaje nadrzędny.

**Steruje mocą ciężkich zadań i dopasowuje się do maszyny.** W Ustawieniach wybierasz, na jakich
rdzeniach chodzą zadania z `safe-run` (tylko energooszczędne E albo wszystkie - temperatury i tak
pilnuje guard) i limit CPU 50-100 % (mikropauzy całej grupy procesów, działa z każdym programem).
Przy pierwszym starcie demon sam wykrywa sprzęt (chip, podział rdzeni P/E, RAM, wentylatory,
zdrowie baterii - zakładka **O moim Macu**) i kalibruje progi: Mac bez wentylatorów dostaje
niższe (78/70/88) i wyłączony alarm wentylatorów. Ręcznie ustawionych progów kalibracja nigdy
nie nadpisuje. Push na telefon: **Ustawienia > Push na telefon (ntfy.sh)** + darmowa aplikacja
ntfy z tym samym tematem. **Nazwa tematu to jedyny sekret** - kto ją zna, czyta Twoje
alerty i może wysyłać fałszywe; dialog podpowiada losową, niezgadywalną nazwę. Działa
z dowolnego miejsca na świecie - to push internetowy, nie łączność lokalna: Mac i telefon
NIE muszą być w tej samej sieci WiFi (Bluetooth nie bierze w tym udziału) - demon wysyła
przez HTTPS do ntfy.sh, a telefon odbiera systemowym pushem gdziekolwiek ma internet (LTE
w pociągu, hotelowe WiFi, inny kraj). Zostawiasz Maca z renderem w biurze, pauzę przy 90 °C
dostajesz na telefon w domu parę sekund później. Dwa uczciwe przypadki brzegowe: gdy MAC
straci internet, pushe nie wychodzą (sama ochrona działa dalej lokalnie - dźwięki i baner
to osobna warstwa); gdy TELEFON jest chwilowo offline, ntfy.sh buforuje wiadomości (~12 h)
i dowozi po powrocie zasięgu. Przełącznik **Uruchamiaj przy starcie komputera** (domyślnie włączony)
i wybór języka guzikami wprost na głównej karcie menu.

**Alarmuje tak, że nie da się przeoczyć.** Powiadomienie z osobnym dźwiękiem przy pauzie,
wznowieniu i ubiciu - a przy poziomie **krytycznym** dodatkowo **modalny alert systemowy na
wierzchu wszystkiego** (`critical_banner`, własny odstęp 3 min, sam znika). Powiadomienie łatwo
zginie pod Skupieniem albo aplikacją na pełnym ekranie; ten baner nie zginie.

**Zbiera dowody.** Tyka puls przy każdym przebiegu, a po restarcie porównuje go z czasem startu
systemu. Jeśli Mac zgasł bez uprzedzenia, zapisuje to zdarzenie razem z ośmioma ostatnimi
pomiarami sprzed padu. `thermal-report` składa z tego jeden plik dla serwisu: sprzęt, stan
baterii, wykryte twarde pady z odczytami, interwencje bezpiecznika i pełną oś czasu pomiarów.


<p align="center">
  <img src="docs/screens/guard_log.webp" alt="guard.log z alarmem awarii chlodzenia" width="620">
</p>
<p align="center"><sub>Prawdziwy wpis z tego dziennika: <code>!!! AWARIA CHŁODZENIA? chip 75.0 C, a oba wentylatory 0 obr/min</code>.</sub></p>
<p align="center">
  <img src="docs/screens/export_report_pl.webp" alt="Raport dla serwisu: PDF albo tekst" width="420">
</p>
<p align="center"><sub>Jeden klik zamienia czarną skrzynkę w dokument, który serwis przyjmie.</sub></p>
## Skąd biorą się dane

### Trzy termometry, jedna maszyna

To jeden kawałek krzemu, ale różne rejony, osobne czujniki i różne zadania:

1. **Chip (CPU) vs GPU.** Na M4 Pro rdzenie procesora i rdzenie graficzne leżą obok
   siebie na tym samym krzemie, ale grzeją się osobno, zależnie od tego, co robisz:
   kompilacja, Python i skrypty grzeją część CPU, a wideo, gry i modele AI na GPU
   część graficzną. Różnica potrafi być kilkanaście stopni, dlatego pokazujemy obie.
   (Neural Engine też tam siedzi, ale Apple nie daje do niego publicznego czujnika.
   Gdy mieli, jego ciepło i tak widać pośrednio w odczycie CPU.)
2. **Paladyn i tak patrzy na gorętszą.** Do decyzji o pauzie bierze max(CPU, GPU),
   czyli „najgorętszy punkt układu" (`soc_temp_c` w `guard.py`). Obojętne, która
   połowa chipa się gotuje, ochrona działa tak samo.
3. **Bateria to zupełnie inna liga.** Osobny fizyczny podzespół, który grzeje się
   wolno (od ładowania i ciepła obudowy), ale ma dużo niższe granice: lit-jon
   degraduje się już powyżej ~40 °C. Dlatego jej próg pauzy to 40 °C, gdy chip może
   spokojnie chodzić do 90 °C.

Krótko: chip i GPU to dwa termometry w jednym kawałku krzemu (różne zadania, różne
temperatury), a bateria to trzeci termometr w delikatniejszym miejscu.


macOS nie udostępnia temperatury chipa zwykłemu procesowi. Działające źródła:

- **temperatura chipa i GPU, obroty wentylatorów, pobór mocy** - [`macmon`](https://github.com/vladkens/macmon) przez **IOReport**, jedyna droga bez `sudo`,
- **stan termiczny systemu** - `ProcessInfo.thermalState` przez malutką binarkę Swift,
- **bateria** - `ioreg -c AppleSmartBattery` (uwaga: jednostki różnią się między modelami -
  raz setne stopnia, raz dziesiąte, raz całe; skalujemy do zakresu fizycznie możliwego
  dla ogniwa, zamiast zakładać jednostkę),
- **dławienie CPU** - `pmset -g therm`, **zasilanie** - `pmset -g batt`, **procesy** - `ps`.

Dwie ślepe uliczki, spisane, żeby nikt nie powtarzał: **`powermetrics` żąda hasła**, a odczyt
sensorów przez **`IOHIDEventSystem`** (przez lata standardowy sposób) **na macOS 26 zwraca zero
sensorów** dla procesu bez uprawnień - Apple to zamknęło. Kompletna implementacja tej metody leży
w [`experiments/soctemp.swift`](experiments/soctemp.swift) jako materiał poglądowy.

Sama bateria nie wystarcza: pomiar z czasu pisania tego pliku to **chip 53,5 °C przy baterii
30,6 °C**. Bateria reaguje z kilkuminutowym opóźnieniem, czyli długo po otwarciu okna na szkodę.

## Czym to się różni od Stats / iStat / TG Pro

Tamte narzędzia **pokazują** liczby albo podkręcają wentylatory. Żadne nie dotyka samej pracy.
Gdy chip dobija do 90 °C o trzeciej w nocy, wykres tego faktu nie jest żadną ochroną.

| | Monitoring (Stats, iStat) | Sterowniki wentylatorów (TG Pro, MFC) | **coffee-paladin** |
|---|---|---|---|
| Pokazuje temperatury | tak | tak | tak |
| Steruje wentylatorami | - | tak | nie (robi to macOS) |
| **Wstrzymuje samą pracę, bezstratnie** | - | - | **tak - SIGSTOP/SIGCONT, zmierzone 89,3 → 60,2 °C w 19 s** |
| Widzi orkiestratory rozsiewające sekundowe procesy | - | - | **tak - CPU całego drzewa procesów** |
| Trzyma pomiary sprzed padu na wypadek awarii | - | - | **tak - czarna skrzynka + raport** |
| Chroni długie obliczenia przed rozładowaniem | - | - | **tak - bramka baterii** |
| Keep-awake trzymany **tylko gdy chłodno** | - | - | **tak - bezpiecznik termiczny** |
| Cała flota w jednej tabeli, bez serwera | - | - | **tak - wspólny folder** |
| Wymaga sudo / kextów / kont | różnie | często | **nie** |

## A czym różni się od apek keep-awake (Amphetamine, Wide Awake)

Apki keep-awake rozwiązują realny problem i coffee-paladin ich nie zastępuje. Ale jeśli
używasz takiej apki, gdy maszyna pracuje pod obciążeniem, warto wiedzieć, co dzieje się
wtedy z ciepłem.

| | Amphetamine | Wide Awake | **coffee-paladin** |
|---|---|---|---|
| Cena | darmowa (App Store) | funkcja Pro pakietu Mac 4 Breakfast, płatność jednorazowa (14 dni triala) | **darmowy, MIT, otwarty kod** |
| Bezpiecznik termiczny | **brak** | jest | **jest** |
| Co mierzy | - | temperaturę **baterii**, domyślnie 45 °C (zakres 40-55) | temperaturę **chipa** przez IOReport |
| Reakcja na gorąco | - | kończy sesję czuwania | **wstrzymuje ciężkie procesy**, wznawia po ostygnięciu |
| Zachowanie przy obciążeniu CPU | trzyma czuwanie, **dopóki CPU jest obciążony** | bez związku | **im goręcej, tym szybciej praca zostaje wstrzymana** |
| Dowody do serwisu | - | raport baterii | **czarna skrzynka: pomiary sprzed twardego wyłączenia** |
| Ostatnie wydanie | 5.3.2, listopad 2023 | aktywne | aktywne |

W tej tabeli liczą się dwie rzeczy. Po pierwsze, **temperatura baterii zostaje kilka minut
w tyle za chipem** - zmierzone na MacBooku Pro M4 Pro: chip 53 °C, gdy bateria pokazywała
jeszcze 30 °C. Próg oparty na baterii odpala się długo po tym, jak chip zdążył pracować
gorąco. Po drugie, zakończenie sesji czuwania pozwala Makowi zasnąć, ale nie usuwa źródła
ciepła. Wstrzymanie zadania - usuwa.

Osobno o wyzwalaczu CPU w Amphetamine, bo łatwo wziąć go za funkcję ochronną. W opisie
brzmi: *„while your Mac's CPU is being utilized to a specific threshold"* - czyli trzymaj
Maca w czuwaniu **tak długo, jak** CPU jest obciążony. Im ciężej i goręcej pracuje maszyna,
tym dłużej blokowane jest uśpienie. To funkcja wygody, nie bezpiecznik, i nigdy nie była
reklamowana jako bezpiecznik.

---

## Twój agent AI umie z nim rozmawiać

Agenty kodujące to dziś zwyczajne źródło obciążenia laptopa: budują, kodują wideo, odpalają
modele, puszczają kilkanaście rzeczy naraz. I w praktyce są najgorszym sprawcą — bo agent nie
słyszy wentylatora i nie zauważa, że maszyna się grzeje. To jest dokładnie ta awaria, przez
którą ten projekt powstał, i zasługuje na lepszą odpowiedź niż „guard w końcu to wstrzyma".

Dlatego coffee-paladin dowozi **skill dla agentów AI**. `install.sh` wykłada go do
`~/.claude/skills/coffee-paladin/` (Claude Code podnosi go sam; to zwykły Markdown, więc
poradzi sobie każdy agent, który czyta skille). To nie jest dokumentacja *o* narzędziu — to
instrukcja *dla agenta*, i uczy czterech rzeczy:

- **Popatrz, zanim odpalisz.** `~/.coffee-paladin/status.json` jest do czytania przez program
  i odświeża się co ~15 s. Jedno pole rozstrzyga wszystko: `level` — `0` startuj, `1` startuj,
  ale nie zrównoleglaj, `2` dokończ to, co biegnie, i nie zaczynaj nic nowego, `3` stop i
  powiedz człowiekowi. Do tego `dry_run` (ochrona może być wyłączona!) i `unpausable`
  (ochrona jest w tej chwili niepełna).
- **Ciężkie zadania przez `safe-run`.** Własna grupa procesów, rejestracja u demona, odmowa
  startu na już gorącym Macu. A `--allow-hot` to decyzja człowieka, nie agenta.
- **Nie walcz z pauzą.** Żadnego `SIGCONT` na procesie, który guard zamroził. Żadnego
  restartu zadania, które „zawisło", zanim sprawdzisz `paused`. Żadnego podnoszenia progów
  w `config.json`, żeby przepchnąć swoje. To są trzy rzeczy, które agent robi, gdy bierze
  ochronę za usterkę.
- **Nie wytwarzaj ciepła bez potrzeby.** Żadnego zadania w tle bez limitu czasu i sprzątania,
  żadnego rekurencyjnego przeszukiwania katalogów w iCloudzie. Ta druga zasada wzięła się
  z prawdziwego incydentu: `grep`, który zużył 13 sekund procesora w 1 h 42 min, trzymał
  bezwentylatorowego Maca na 90 °C — bo kazał demonom `fileproviderd` i `cloudd` ściągać pliki
  z chmury. W kolumnie CPU nie było prawie nic. Tego nikt nie zgadnie; to trzeba mieć zapisane.

Skill traktuje też `status.json` jak **puls**: jeśli znacznik czasu jest starszy niż 60 s,
demon nie działa — a agent ma to powiedzieć i zachowywać się tak, jakby Mac był bez ochrony.
Agent, który czyta nieaktualny plik i melduje „poziom 0, wszystko gra", jest gorszy niż taki,
który w ogóle nie zajrzał.

W zamian sam agent jest chroniony: `claude`, `codex`, `hermes`, `tmux`, `vim` i cokolwiek
trzyma pierwszy plan terminala są na liście nietykalnych po nazwie, a procesy `node`
rozpoznajemy po **linii poleceń** - ten z agentem, serwerem MCP czy language serverem jest
nietykalny, ale zwykły `node build.js` pozostaje pauzowalny, czyli dokładnie tak, jak ma
działać bezpiecznik termiczny. Guard, który zamraża sesję sterującą nim samym, nie jest guardem.

```bash
cat ~/.claude/skills/coffee-paladin/SKILL.md    # co dostał Twój agent
```


## Flota: wszystkie Maki w jednej tabeli

<p align="center">
  <img src="docs/screens/fleet_pl.webp" alt="Flota Apple: dwa Maki, jeden milczy" width="620">
</p>
<p align="center"><sub>Dwie maszyny: jedna raportuje, druga milczy od 9 godzin. Nazwy maszyn zamazane.</sub></p>

Firmy coraz częściej stawiają lokalne AI na Makach: Mac mini albo Mac Studio z dużym RAM-em,
modele on-prem, dane bez wysyłania do chmury. Te maszyny mielą 24/7 - tak samo jak farmy
renderujące, studia postprodukcji i pule CI. Przy kolejkach na nowe Maki rzędu 15+ tygodni
i podwyżkach cen utrata jednej sztuki to nie drobna awaria, tylko realny przestój - każda
uratowana maszyna to konkretny pieniądz.

Flota w coffee-paladin jest prosta: każdy Mac publikuje co około minutę migawkę JSON do
wspólnego folderu, a `fleet` i pasek menu składają z tych plików jedną tabelę: temperatura,
wentylatory, waty, RAM, stan, wstrzymane zadania i ostatni raport. Maszyny mają własne nazwy,
model i numer seryjny; po 5 minutach ciszy dostają znacznik `NIE RAPORTUJE`. **„Serwerem" jest
folder, który firma już ma** - iCloud, Dropbox, SharePoint albo SMB/NAS.

Nie ma serwera, kont, panelu SaaS ani danych wychodzących poza folder firmy. To ułatwia
compliance: IT widzi zwykłe pliki JSON w miejscu, którym samo zarządza. `fleet --json` plus
kod wyjścia wpinają się w alerty, cron, Grafanę albo Slacka, a guard na każdej maszynie sam
pauzuje przegrzane zadania i zbiera czarną skrzynkę na wypadek awarii.

Konkretnie daje to: wgląd w całą flotę bez wdrażania infrastruktury, dłuższe życie sprzętu
pracującego pod pełnym obciążeniem, szybkie wykrycie maszyn, które przestały raportować,
i dowody dla serwisu po twardym padzie.

Świeża instalacja startuje w **trybie obserwacji**: mierzy, loguje i alarmuje (też dźwiękiem),
ale niczego nie wstrzymuje, dopóki nie włączysz ochrony - jednym kliknięciem w menu paska.
Na pasku widać wtedy ikonę oka. Odinstalowanie: `bash uninstall.sh`.

Konfiguracja floty: `fleet --setup` (wykrywa foldery synchronizowane i zapisuje wybór) albo
ręcznie - jeden klucz na każdej maszynie: `"fleet_dir": "<ścieżka folderu>"` w
`~/.coffee-paladin/config.json` - bez restartu, agent zacznie publikować w ciągu minuty. Potem
na swojej maszynie: `fleet` (tabela + problemy), `fleet --watch` (odświeżanie), `fleet --json`
(pod automaty i dashboardy). Host bez raportu od 5 minut dostaje flagę `NIE RAPORTUJE`.

Co znaczy "ten sam folder": nic apple'owego. Wystarczy folder, do którego każdy Mac ma dostęp
pod jakąkolwiek swoją ścieżką - ścieżki mogą się różnić, bo każda maszyna trzyma własny
`fleet_dir`. iCloud Drive wymaga tego samego Apple ID na wszystkich Makach (albo folderu
udostępnionego drugiemu Apple ID). Google Drive, OneDrive i Dropbox - tego samego konta
zalogowanego wszędzie albo folderu udostępnionego drugiemu kontu; ich ścieżki zawierają nazwę
konta, więc na każdej maszynie wyglądają inaczej i tak ma być. Dysk sieciowy SMB/NAS - po prostu
podmontowany na każdym Macu.

Synchronizacja nie jest natychmiastowa i to widać. Przy pobieraniu na żądanie (iCloud
*Optymalizuj miejsce*, streaming w Drive) migawka drugiego Maca potrafi dojść z kilkuminutowym
opóźnieniem albo leżeć jako niepobrany placeholder. Do tego czasu tamta maszyna po prostu nie
ma jej w tabeli na tym Macu albo widnieje jako nieraportująca - dane nie zginęły, jeszcze nie
dojechały. Siebie każdy Mac widzi od razu, bo swój plik zapisuje lokalnie.

## Testy

Detektor twardego padu (kod piszący dowody gwarancyjne) ma własną matrycę 16 przypadków -
łącznie ze zmianami stref czasowych i artefaktami z backupów. Jedno polecenie, izolowany HOME,
prawdziwa czarna skrzynka nietknięta:
`T=$(mktemp -d) && python3 tests/test_wykryj_twardy_pad.py "$T"; rm -rf "$T"`
`python3 tests/test_paladin.py` - 21 sprawdzeń: CLI, pasek menu, grafika, tłumaczenia.
`python3 tests/test_config_odporny.py` - 24 sprawdzenia: config nie może oślepić strażnika.
`python3 tests/test_safe_run_hot.py` - 8 sprawdzeń: safe-run odmawia startu na gorącej maszynie.
`python3 tests/test_demote_promote.py` - 20 sprawdzeń: degradacja na E-cores i powrót.
`python3 tests/test_b2_node.py` - 17 sprawdzeń: node oceniany po linii poleceń, nie po nazwie.

**Co naprawdę się kręci, a co nie.** Powyższe zestawy to czysty Python - żadnego frameworka,
nic do doinstalowania, i z założenia nie dotykają Twojej prawdziwej czarnej skrzynki. Do tego
**semgrep** na źródłach Pythona (`p/python` + `p/secrets`, 187 reguł - na dziś 0 znalezisk)
i **ruff** (`E9,F` - czysto). Do tych dwóch podchodź jednak sceptycznie: darmowy zestaw reguł
semgrepa jest głęboki dla Pythona, a cienki dla basha i Swifta (2 reguły), więc aplikację
paska pilnuje recenzja - ludzka i modelowa - a nie skaner. Nie ma tu fuzzingu ani CI; to
narzędzie na jedną platformę, a ciekawe błędy znalazło uruchamianie go na dwóch różnych
Makach, nie macierz konfiguracji.

Ten projekt był **testowany i udoskonalany z pomocą AI - czterech głów naraz** ;) a proces
warto opisać, bo wyłapał błędy, których żaden pojedynczy recenzent by nie znalazł. Każdy ryzykowny obszar (sygnały na grupach
procesów, limiter CPU, blokady snu, detektor padu) recenzowały **cztery różne modele AI
niezależnie** - Claude (Anthropic), Codex/GPT-5.5 (OpenAI) oraz dwa modele lokalne:
Devstral 24B na MLX i qwen3:4b na Ollamie - w sześciu rundach, a każde twierdzenie było
weryfikowane ręcznie w kodzie, zanim cokolwiek zmieniono. Do tego **drugi Mac audytował
instalację pierwszego**: bezwentylatorowa maszyna z 8 GB przeszła ścieżki kodu, których
dobrze chłodzona 14-rdzeniówka nigdy by nie dotknęła. Audyty krzyżowe złapały - wśród
~40 poprawek jednego dnia - m.in.: checkbox, który pokazywał ochronę jako włączoną, gdy
demon tylko obserwował; instalator raportujący sukces, gdy pasek menu nigdy nie wstał;
i błąd strefy czasowej, który potrafił wyciszyć prawdziwy pad w pliku dowodowym (puls
zapisany w Warszawie, odczytany po „przelocie" do Nowego Jorku, parsował się jako
przyszłość). Zgoda recenzentów niewiele dowodzi - sygnałem jest rozbieżność.

## Instalacja i użycie

**Czego potrzebujesz:** Maca na Apple Silicon, narzędzi wiersza poleceń Xcode (dla `swiftc`)
i [Homebrew](https://brew.sh) (instalator pobiera przez niego `macmon`).

```bash
xcode-select --install                                    # bez tego NIE BĘDZIE paska menu
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Bez `swiftc` tracisz **naraz** pasek menu i czujnik temperatury chipa - zostaje sam bezpiecznik
bateryjny, czyli połowa produktu. Bez Homebrew nie ma `macmon`, więc guard nie widzi ani chipa,
ani obrotów wentylatorów. Instalator sprawdza obie rzeczy na starcie i mówi, czego brakuje;
`xcode-select --install` potrafi uruchomić sam, Homebrew zostawia Tobie - jego instalator prosi
o hasło administratora i nie powinien iść przez cudzy skrypt.

**Przez Homebrew (najprościej):**

```bash
brew install pawelkwaczynski/tap/coffee-paladin
bash "$(brew --prefix)/share/coffee-paladin/install.sh"
```

**Ze źródeł:**

```bash
git clone https://github.com/pawelkwaczynski/coffee-paladin.git
cd coffee-paladin
bash install.sh
```

Obie drogi dają tę samą wersję. Pasek menu instaluje się jako **`coffee-paladin.app`
w Aplikacjach** - z ikoną, wersją widoczną w Finderze i podpisem na całym pakiecie. Nadal ma
ustawione `LSUIElement`, więc nie zaśmieca Docka ani Cmd+Tab. Nic nie jest pobierane w postaci
gotowej binarki: aplikacja kompiluje się na Twoim Macu ze źródeł, więc Gatekeeper nie ma czego
poddawać kwarantannie i nie zobaczysz ostrzeżenia o „niezidentyfikowanym deweloperze".

**Świeża instalacja startuje w trybie obserwacji**: mierzy, zapisuje i alarmuje, ale niczego
nie wstrzymuje, dopóki sam nie włączysz ochrony - jednym kliknięciem w pasku menu albo przez
`"dry_run": false` w konfiguracji.

- `heat` - jednym poleceniem: jak gorąco, co grzeje, czy bezpiecznik żyje
- `safe-run --hours 8 --name render -- <polecenie>` - tak uruchamiaj ciężkie zadania
- `heatbar` - pasek menu: chip, GPU, bateria, obroty, waty, RAM i dysk (wybierasz checkboxami
  w „Pokaż na pasku"), wykres, prognoza, listy „co grzeje" (top 3 po CPU - najlepsze dostępne
  przybliżenie ciepła per proces) i „co zjada RAM" (top 3 po pamięci), ręczne zamrażanie,
  eksport raportu oraz **Flota Apple** - wszystkie Twoje Maki z parametrami, własnymi nazwami
  (Ustawienia > „Nazwij tego Maca we flocie" - przy pięciu identycznych MacBookach nazwa
  systemowa nic nie mówi), modelem w wierszu i numerem seryjnym w podpowiedzi, ze znacznikiem
  „NIE RAPORTUJE" (cache w tle, otwarcie menu nigdy nie czeka na iCloud/SMB)
- `thermal-report --days 14` - raport dowodowy dla serwisu

Progi w `~/.coffee-paladin/config.json`. **Nie ustawiaj progu chipa na 45 °C** - bezczynny M4 Pro
ma 40-55 °C, a Apple Silicon dławi się dopiero koło 100-108 °C. 45 °C to właściwa liczba dla
*baterii* i tam jest używana.

Język: domyślnie angielski. Pasek menu, powiadomienia i wszystkie narzędzia CLI mówią w **pięciu
językach** (angielski, polski, rosyjski, chiński, hiszpański) - przełączasz w menu paska
(*Ustawienia > Język*) albo przez `"lang"` w `~/.coffee-paladin/config.json` / `TG_LANG`.

## Uczciwa notka o autorstwie

**Autor: Paweł Kwaczyński (FOCUS FRAME).** Wymagania, decyzje, weryfikacja i ryzyko w tym
projekcie należą do jednej osoby - modele niżej pisały kod pod to.

Pracuję w Pythonie. Aplikacja paska w Swift istnieje tylko dlatego, że Swift buduję w parze
z AI - i ten projekt traktuje to poważnie: cztery różne modele recenzowały nawzajem swoją
pracę w sześciu rundach, a drugi Mac audytował instalację pierwszego. Tutaj to człowiek
decydował, weryfikował i brał ryzyko; AI napisało Swifta - metoda human-in-the-loop. Dlatego
nie widzę powodu, żeby to ukrywać.

Z nazwiska, bo ogólnikowe podziękowanie to żadne podziękowanie. Swifta - pasek menu, okno
powitalne, panel paladyna - napisał **Claude (Anthropic)** w Claude Code, pod moje wymagania
i moją recenzję. **Codex (OpenAI, GPT-5.5)** był recenzentem przeciwnym: czytał ten sam kod
niezależnie, a jego zadaniem było znaleźć to, co autorowi umknęło. Obok szły dwa **modele
lokalne** - **Devstral 24B** na MLX i **qwen3:4b** na Ollamie - bo recenzenta, który nigdy nie
wychodzi z laptopa, można pytać o wszystko i dowolnie często. Grafikę paladyna wygenerował
**ChatGPT (OpenAI)**. Nic tu nie weszło dlatego, że model to zaakceptował; każda teza była
najpierw sprawdzana w działającym kodzie.

## Postaw mi podwójne espresso ☕︎

Ten projekt dosłownie opiera się na kawie - kodowa nazwa wydania to „Ristretto",
a bezpiecznik keep-awake to moja odpowiedź na Caffeine. Jeśli coffee-paladin uratował Ci Maca
(albo render), postaw mi kawę: **https://suppi.pl/panbookovsky**

## Licencja

MIT. Rób z tym co chcesz. Jeśli uratuje Ci komputer, to wystarczająca satysfakcja.

<p align="center">
  <img src="docs/screens/paladin_panel.webp" alt="Panel paladyna przypiety pod paskiem" width="260">
</p>
<p align="center"><sub>Kliknij nazwę na górze menu, a paladyn wychodzi — przypięty pod paskiem.</sub></p>

**Grafika.** Paladyn — maskotka z nagłówka, z okna powitalnego, z menu i z easter eggów
`heat --paladin` — został **wygenerowany w ChatGPT (OpenAI)** i jest używany jako oficjalna
maskotka projektu. Reszta plików w `branding/` to pochodne tych dwóch źródeł; szczegóły
w [`branding/CREDITS.md`](branding/CREDITS.md).

Autor: Paweł Kwaczyński / FOCUS FRAME, 2026. Projekt rozwijany także w ramach koła naukowego
**AIrON** (SKN Informatyki AHE w Łodzi).
