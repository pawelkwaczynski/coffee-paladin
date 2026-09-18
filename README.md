# coffee-paladin v3.3.5

<p align="center">
  <img src="branding/paladin.gif" alt="coffee-paladin - the project mascot" width="260">
</p>
<p align="center"><em>Shield the Process, Sip the Coffee</em></p>

<p align="center">
  <a href="README.pl.md">🇵🇱 <b>Po polsku</b></a> ·
  <a href="#install">Install</a> ·
  <a href="#what-it-actually-does">What it does</a> ·
  <a href="#integrations">Integrations</a> ·
  <a href="#known-limitations">Limitations</a>
</p>

```bash
brew install pawelkwaczynski/tap/coffee-paladin
bash "$(brew --prefix)/share/coffee-paladin/install.sh"
```

The second line matters: `brew install` puts the files in place, the installer starts the guard.

Using a coding agent? Give it the guard in one line:

```
/plugin marketplace add pawelkwaczynski/coffee-paladin
```

**A thermal and power safety net for Apple Silicon Macs - from one laptop to a whole fleet.**
It watches the chip temperature, the battery, the fans and the power source, and it *freezes*
heavy jobs before the machine cooks itself - instead of letting them run until it shuts down.

**What keeps a Mac hot for hours, as the author's own field log shows it** (13 August to
17 September 2026, one machine): the jobs launched most often through `safe-run` were `ffmpeg`
queues, Python jobs, `swiftc` builds and `rclone` transfers; the processes the guard paused most
often were `ollama` and `llama-server`, which hold the GPU at full clock for minutes, then
`ffmpeg` and Python. Coding agents (Claude Code, Codex, Gemini CLI) appear in that log only as
a *source* of such jobs: they start builds, encodes and model runs and do not feel the fan.
Optional hooks and a statusline let the guard talk to them; the daemon itself neither needs nor
knows about any of them (see *Integrations* below).

Also for people who make Macs work for a living in other ways: render farms, post-production
studios, CI pools of Mac minis, ML teams, and anyone leaving a laptop to compute overnight.

No `sudo`. No kernel extensions. No daemons running as root. Everything reads sensors that are
available to a normal user process.

**Requirements: Apple Silicon (M1 or newer) and macOS 14+.** Chip temperature comes from
[`macmon`](https://github.com/vladkens/macmon), an external tool that supports Apple Silicon only; on an older system the app icon shows up
crossed out because macOS blocks apps below their declared minimum version. Intel Macs are
honestly not supported.

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

## What this is not

- **No model, no training, no inference.** The daemon is one Python file on the standard
  library: it reads sensors, compares numbers with thresholds and sends `SIGSTOP` / `SIGCONT`.
  The event log it keeps (`~/.coffee-paladin/history_events.jsonl`) is a plain history of
  what happened; nothing is trained on it. The only forward-looking number the guard
  produces, `eta_pause_min`, is a straight-line extrapolation of the last five minutes of
  chip temperature kept in memory; it never reads the log.
- **No listening port.** `thermal-metrics` writes Prometheus text for the `node_exporter`
  textfile collector; nothing in this project binds a socket.
- **One optional outbound channel in the daemon.** Phone pushes go through ntfy.sh, and only
  if you set `ntfy_topic` in `config.json`. It is empty by default, and then the daemon makes no
  network request at all. (`install.sh` uses Homebrew once, to fetch `macmon`.) The menu bar is
  the one exception: if the external `ccusage` binary is installed, the bar runs it every ten
  minutes for the cost row, and `ccusage` fetches model pricing online unless run with
  `--offline`, which the bar does not pass.
- **Not a sensor of its own.** Chip, GPU, fan and power readings come from
  [`macmon`](https://github.com/vladkens/macmon), an external open-source binary that reads
  Apple's sensor interfaces without `sudo` (SMC for temperatures and fans, IOReport for power);
  the guard parses its output and falls back to battery temperature without it.
- **Not tied to any AI tool.** The agent skill, the hooks, the statusline and the plugin
  manifest are optional integrations. `install.sh` installs the skill and wires the statusline
  only where the matching tool already exists on the machine, and never replaces a statusline
  somebody else configured unless you pass `--replace`. It wires no hook at all: the hook
  adapters are copied into `~/.coffee-paladin/` and each one is switched on by hand (see the hook section below).
  The daemon runs without any of them.

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
Long heat is what ages these machines and their batteries. Apple says ambient above 35 °C
"can permanently damage battery capacity" ([Apple, Maximizing Battery Life](https://www.apple.com/batteries/maximizing-performance/)),
and Battery University's storage table shows a cell kept for a year at full charge retaining
about 80 % of its capacity at 25 °C but 65 % at 40 °C ([BU-808](https://batteryuniversity.com/article/bu-808-how-to-prolong-lithium-based-batteries)).

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

Notification at pause, resume and kill (each with its own system sound, once you flip sounds on in Settings) - and at the **critical** level
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
show you numbers, or drive the fans harder. **None of the popular monitoring ones touches the
workload itself.** The exception is App Tamer, which slows and stops applications by hand or by
CPU rule, and whose 3.0 beta adds profiles switched by CPU temperature; coffee-paladin differs in
what it acts on: whole process trees started by batch jobs, automatically, with a pause budget,
a black box and an admission queue. When the chip hits 90 °C at 3 a.m., a chart of it is not
protection.

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
| What it measures | - | **battery** temperature, 45 °C default (40-55) | **chip** temperature via `macmon` |
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

### Prometheus, Grafana and anything else that scrapes

A rack does not click on a menu bar. `thermal-metrics` prints what the guard knows in the
Prometheus text format, for this machine or for the whole fleet folder in one document:

```
thermal-metrics                 # this Mac, to stdout
thermal-metrics --fleet         # plus every machine in the fleet folder
```

There is no port and no server here. The tool prints and exits, so it wires into the
`node_exporter` textfile collector that a Mac in a rack already runs:

```
*/1 * * * * thermal-metrics --fleet \
    --output /var/lib/node_exporter/textfile/coffee_paladin.prom
```

That is deliberate. The promise of this project is no `sudo`, no kernel extension and no
root daemon, and a listening socket on every machine in a rack is a worse trade than a
one-line cron entry. The write is atomic, so a collector reading mid-write gets the previous
document rather than half of this one.

Two metrics deserve an alert before the temperature does:

| Metric | Why it matters |
|---|---|
| `coffee_paladin_up` | `0` means the guard stopped writing snapshots. Every reading next to it is the last known one, not the current one. |
| `coffee_paladin_dry_run` | `1` means the guard is watching and pausing **nothing**. The machine looks perfectly healthy on every other metric and is not protected. |

Alongside those: chip, GPU and battery temperature, fan rpm, power draw and source, load,
memory, swap, disk, the active thresholds, how many jobs are frozen or demoted right now,
the machine's own thermal percentiles, and counters for pauses, resumes and kills since
install. Machines that stopped reporting stay in the output at `up=0` instead of vanishing:
a host missing from a dashboard reads as "we retired it", a host at zero reads as "go and
look at it".

---

## For CI fleets: self-hosted Mac runners

A Mac mini under a desk running `xcodebuild` all day is the machine this guard was built for,
so we tested the one thing a CI operator will ask first: **what happens to a running job when
the guard pauses its build process?**

We measured it on a live GitHub Actions self-hosted runner (runner v2.336.0, M4 Pro,
2026-08-06), freezing the build process mid-job with the same `SIGSTOP` the guard uses:

| Freeze in the middle of a job | Result |
|---|---|
| 3 minutes | job finished, **conclusion: success** - the log stream shows a 3 m 09 s gap and then picks up mid-line |
| 10 minutes | job finished, **success** - a 10 m 02 s gap, total job time 15 m 15 s |

GitHub Actions has no "no output" watchdog: the connection is kept alive by
`Runner.Listener`, which the guard never touches (it idles far below the CPU threshold,
and runner agents belong on `never_extra` anyway - see below). A pause only stretches the
wall clock, so the one real risk is a tight `timeout-minutes` on the job itself.

What this means in practice:

- **The primary mechanism for CI is the gate, not the pause.** `safe-run` refuses to *start*
  work on a machine that is already hot - put it in front of the job and the queue simply
  waits out the heat instead of failing through it.
- **A mid-job pause is a tested fallback, not a job killer** - at least on GitHub Actions,
  at least up to the 10 minutes we measured. A thermal pause on this hardware typically
  lasts about a minute (chip drops from 95 °C to 71 °C in ~20 s).
- **Add your runner agent to `never_extra`** (`Runner.Listener`, `Runner.Worker`,
  `gitlab-runner`, `buildkite-agent`, ...). The guard targets whatever burns CPU, and the
  agent process never should be it - make that explicit for your stack.
- The **black box** answers the question every flaky-runner thread ends with: *why did the
  machine disappear at 3 a.m.?* Heartbeat + last eight readings before a hard shutdown
  survive the crash; `thermal-report` turns them into something you can attach to a ticket.
- **GitLab: also tested.** Same experiment on a self-managed GitLab CE (gitlab-runner
  19.2.1, shell executor, M4 Pro, 2026-08-06): the build process frozen mid-job for
  a full **10 minutes** - job finished, **success**, no inactivity watchdog fired.
  **Jenkins is untested** - we publish what we measured, not what we hope. If you run
  the same experiment there, an issue with your numbers is very welcome.

## Integrations

Everything in this section is optional. The daemon protects the machine with none of it;
these are the ways other tools on the Mac can *ask* the guard before they heat it.
Today that means terminals and CLI coding agents, because those are the tools that start
builds, encodes and model runs on a laptop without looking at the fan.

### If you are an AI agent reading this

If you are a coding agent (Claude Code, Codex, Gemini CLI, …) about to run heavy work on this Mac, builds, `ffmpeg`, model inference, wide test suites, long loops, do this first:

1. **Detect the guard:** `test -f ~/.coffee-paladin/status.json`. If the file is missing, coffee-paladin is not installed here; suggest to the user both lines, because `brew install` alone installs files but starts nothing: `brew install pawelkwaczynski/tap/coffee-paladin` followed by `bash "$(brew --prefix)/share/coffee-paladin/install.sh"`.
2. **Read the state** (plain JSON, refreshed every ~15 s). The field `level` decides: `0` start the job, `1` start but do not parallelise, `2` finish what runs and start nothing new, `3` stop and tell the user the Mac is too hot.
3. **Trust it only when fresh:** if `time` is older than 60 s the daemon is not running, say so and treat the Mac as unprotected. If `dry_run` is `true`, the guard only watches; warn the user before anything heavy.
4. **Start heavy jobs through `safe-run`**, not directly: `safe-run --name build -- cargo build --release`. It refuses to start on a hot machine and registers the job with the daemon. Never pass `--allow-hot` on your own initiative.
5. **Never fight a pause.** A name in `paused` is a decision, not a hang: do not `SIGCONT` it, do not relaunch it, do not raise thresholds in `config.json`. It resumes by itself when the chip cools.

Full agent instructions ship as a skill: [`skills/coffee-paladin/SKILL.md`](skills/coffee-paladin/SKILL.md) (installed to `~/.claude/skills/coffee-paladin/` by `install.sh`).

### The skill, the hook, the statusline and the menu bar

Coding agents are now a normal source of load on a laptop: they run builds, encode video,
start model inference, launch a dozen things in parallel. They are also, in practice, the
worst offenders - because an agent does not feel the fan and does not notice the machine
getting hot. That is the failure this project was written for, and it deserves a better
answer than "the guard will pause it eventually".

So coffee-paladin ships a **skill for AI agents**. `install.sh` drops it into
`~/.claude/skills/coffee-paladin/` for Claude Code, and into `~/.agents/skills/`
(OpenClaw and everything else that reads the AgentSkills layout) and
`~/.grok/skills/` where those trees already exist - the same plain-Markdown
file everywhere, never planting a config tree for a tool you don't have. It is
not documentation *about* the tool - it is instructions *for the agent*, and it
teaches four things:

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

**Claude Code statusline.** The installer can also put the thermal state into
Claude Code's status bar - refreshed live under every session, machine truth
on the first line and the AI session on the second:

```
🛡  🌡 55°  🌀 2.4k  🧠 50%  💾 94%  ☕
🤖 Fable 5  5h 86% ↺14:30  7d 41% ↺Thu  ctx 62%  my-project
```

The second line carries the model, **your account's rate limits** - the same
5-hour and weekly percentages the `/usage` screen shows, straight from the
session JSON Claude Code hands to statuslines (subscription logins; the fields
appear after the session's first response) - plus context usage and the
directory. Percentages turn yellow at 75 and red at 90. No limits in the JSON
means none are shown: the line never invents a number. The same whitelisted
snapshot lands in `~/.coffee-paladin/claude_usage_cache.json`, where the menu
bar reads it - *Agent activity* shows the limits row while a session is alive
(and drops it five minutes after the last refresh), so the answer to "how much
Claude do I have left" is on the bar, not behind a slash command.

<p align="center">
  <img src="docs/screens/statusline.webp" alt="The statusline under a live Claude Code session, here with Nerd Font icons" width="740">
</p>
<p align="center"><sub>Under a real session: shield, chip 70°, fans, RAM, a red disk at 90%, keep-awake - then model and directory.</sub></p>

The shield turns into an eye in watch-only mode and into a loud red `OFF`
when the daemon's snapshot goes stale - the exact failure where the guard is
unloaded and nobody notices. Elements appear only when they carry an action:
paused jobs, jobs demoted to E-cores (running up to several times slower),
the admission queue, a missing chip sensor, a hard shutdown within the last
24 hours, and at hot levels the name of the process about to be paused. On a
narrow terminal the AI line gives ground first, element by element from the
right, and disappears entirely before a single thermal fact is dropped.

The wiring is deliberately conservative: `install.sh` copies the script and
touches `~/.claude/settings.json` only when no `statusLine` is configured
(with a timestamped backup); an existing statusline of yours is never
overwritten unless you run `bash install.sh --replace`, and `uninstall.sh`
removes only the entry that points at the paladin's own script. This wires the
user-level settings; a project's own `.claude/settings.json` statusline, where
one exists, takes precedence by Claude Code's scope rules. Icons default
to emoji, which every Mac renders; a patched font is opt-in:
`COFFEE_PALADIN_STATUSLINE_ICONS=nerd` (or `ascii` for plain terminals) in
the command line stored in settings.

**One gate for every agent host.** `coffee-paladin hook-gate` implements the
pre-execution hook contract shared - with dialect differences - by Claude
Code, Codex CLI, Gemini CLI, Grok Build and Antigravity. It reads the
tool-call JSON on stdin in whichever spelling the host speaks (snake_case
`tool_input`, Grok's camelCase `toolInput`, Antigravity's
`toolCall.args.CommandLine`) and answers the way that host listens: exit 2 with the reason
on stderr, plus an explicit stdout `{"decision": "deny"}` for the two hosts
that only trust that (Grok is fail-open on anything else; Antigravity has no
exit-code contract at all). It checks process discipline, not temperature: a
heavy tool started bare - `ffmpeg`, an encoder, a SAT solver, `ollama run` -
is refused with the exact `safe-run` line to use instead, in milliseconds and
fail-open on anything unexpected, because a broken gate must never hold a
coding session hostage. `PALADIN_HOOK=off` disables it for one deliberate
command; `hook_heavy_patterns` in config.json replaces the built-in list.

Wiring stays **opt-in per host**, one adapter each, every one with the same
manners as the Claude wiring (own entry appended under a file lock, foreign
entries never touched, timestamped backup before every write, unwire removes
exactly ours):

```bash
python3 ~/.coffee-paladin/settings_wire.py hook          # Claude Code
python3 ~/.coffee-paladin/codex_hooks_wire.py hook       # Codex CLI (trust the hook on first run)
python3 ~/.coffee-paladin/gemini_hooks_wire.py hook      # Gemini CLI
python3 ~/.coffee-paladin/grok_hooks_wire.py hook        # Grok Build
python3 ~/.coffee-paladin/antigravity_hooks_wire.py hook # Antigravity
```

(`unhook` reverses each one; `uninstall.sh` runs them all.) Grok additionally
scans `~/.claude/settings.json` for hooks by default, so a Claude-wired gate
already covers it - the native file only matters when that compatibility is
switched off. Gemini's timeout field is in milliseconds where everyone else
uses seconds; the adapter knows.

**Running an agent swarm? You are already covered.** Multi-agent
orchestrators that spawn their workers as regular CLI sessions -
oh-my-claudecode teams, claude-squad, workmux, dmux panes and friends -
inherit the gate for free: each worker is a `claude` (or codex/gemini/grok)
process, reads the same user-level settings, and hits the same PreToolUse
gate before starting anything heavy. No orchestrator-side configuration,
nothing to install twice. What no orchestrator sees yet is the machine
itself - how hot it runs and how many heavy jobs it can carry - which is
exactly the layer the guard keeps: one `status.json` any scheduler can read
before scaling up.

**Terminals.** The same thermal line works outside agent sessions:
`integrations/terminals/` ships a tmux `status-right` snippet, a WezTerm
`update-status` handler and an iTerm2 status bar component, each a
copy-paste-sized file with install notes inside.

**What today burned.** If the external [`ccusage`](https://github.com/ccusage/ccusage)
is installed, *Agent activity* gains a line with today's usage across every
agent CLI it knows: `322M tokens · ~$312`. Tokens come first on purpose. On a
subscription the dollar figure is not money anyone spent - it is what the same
work would have cost through the API - so it is prefixed with `~` and can be
dropped entirely with `"ccusage_cost": false`. The real budget on a plan is the
5-hour and weekly percentage, which is already on the line above. We call the
binary and cache its answer for 10 minutes rather than vendoring anyone's code
or writing a second token counter; no `ccusage`, no line, and nothing else
changes. `brew install ccusage`.

Expanding that line breaks the day down **per agent** and **per model** - which
CLI and which model actually spent the tokens - and shows the **active
five-hour block** with its rate: `47M tokens · 283k/min · 94 min left`. That
block is counted by ccusage from local logs and is deliberately labelled as
such: it is not your account's official 5-hour limit, which has its own row
straight from Claude Code. And one line no usage dashboard can produce, because
it needs both halves: when the guard's own forecast says the chip will force a
pause before the block ends, it says so.

**Agent activity.** The daemon also writes `~/.coffee-paladin/
agent_activity.json`: which AI sessions run on this Mac and the process tree
each one started, with the thermal context. The menu bar shows it under
*Agent activity*, and a ✨ marker appears on the bar while any session is
alive - the marker's presence is the answer to "is an AI working right now".
Off switch: `"agent_activity": false`.

<p align="center">
  <img src="docs/screens/agent_activity.webp" alt="Agent activity: live process trees of AI sessions, with thermal context" width="640">
</p>
<p align="center"><sub>Agent sessions and what each of them started - straight from the menu bar.</sub></p>

**Also in the repo, so that nobody finds it by accident:**

- `.claude-plugin/plugin.json` is a plugin manifest for Claude Code that ships the agent skill
  (`skills/coffee-paladin/`) as a plugin. It does not install or start the guard; the daemon
  still comes from `install.sh` or Homebrew. It is one more optional way to get the skill, not
  a different product.
- The menu bar has a row *Claude limits: …*. It exists only while the Claude Code statusline
  integration is writing `~/.coffee-paladin/claude_usage_cache.json` (whitelisted fields, no
  session ids or paths); when that file is missing or older than five minutes the function
  returns nothing and the row is not drawn. The bar never queries any account.
- `integrations/` holds hooks for five CLI agents (Claude Code, Codex, Gemini CLI, Grok,
  Antigravity) next to the terminal integrations. A hook makes the agent ask the guard before
  heavy work; without the hook the guard still pauses that work when the chip gets hot.

---

## Where the data comes from

This is the interesting part, because macOS does not hand out chip temperatures to unprivileged
processes.

| Signal | Source | Notes |
|---|---|---|
| **Chip / GPU temperature** | [`macmon`](https://github.com/vladkens/macmon) → **SMC** (IOReport for power) | The one route that still works without `sudo`. |
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
SMC through `macmon` is currently the surviving path.

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
python3 tests/test_paladin.py          # 22 checks: CLI, menu bar, artwork, translations
python3 tests/test_config_odporny.py   # 33 checks: a config must not blind the guard
python3 tests/test_safe_run_hot.py     #  8 checks: safe-run refuses to start when hot
python3 tests/test_metryki.py          # 17 checks: one bad machine must not poison a scrape
python3 tests/test_demote_promote.py   # 20 checks: demotion to E-cores and back
python3 tests/test_b2_node.py          # 17 checks: node is judged by its command line
python3 tests/test_wznowienie.py       # 41 checks: what may resume, and what may be killed
```

**Why that last suite exists (v2.3.2).** For two days the guard paused jobs and resumed none
of them: 15 pauses, zero resumes, four jobs terminated after the pause timeout. Three separate
defects produced one symptom. The resume gate required *every* sensor to fall back, so a
battery sitting at 37 °C - three degrees below its own 40 °C pause threshold, which it had
never crossed - held hostage a job the *chip* had paused, until the 45-minute timeout killed
it. The timeout itself trusted the guard's own bookkeeping instead of the system, so a job
resumed by hand kept ageing towards a SIGTERM it did not deserve. And the CPU limiter's
interlock compared the wrong pid - the group leader instead of the child that was actually
hot - so it woke jobs the guard had just frozen. The lesson is one line: **a safety net must
ask the system, not its own notes**, and an unreadable measurement is "I don't know", never
"nothing is stopped".

**What actually runs, and what it does not.** The suites above are plain Python - no test
framework, no fixtures to install, and they refuse to touch your real black box. On top of
them: **semgrep** over the Python sources (`p/python` + `p/secrets`, 187 rules - currently
0 findings) and **ruff** (`E9,F` - clean). Be sceptical of the last two, though: semgrep's
free rule set is deep for Python and thin for shell and Swift (2 rules), so the menu bar app
is covered by careful review, not by a scanner. There is no fuzzing and no CI here;
this is a tool for one platform, and the interesting failures were found by running it on two
different Macs, not by a matrix.

The review process behind this project is worth describing, because it found bugs no
single reviewer would have caught. Every risky area (signal handling on
process groups, the CPU limiter, sleep-lock management, the crash detector) went through
**several independent review rounds**, with every claim verified by hand against the
actual code before anything
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

If your Mac was set up by Migration Assistant from an Intel one, it may carry the Intel Homebrew
in `/usr/local` as well, and a bare `brew` can still resolve to it - it cannot write there and
does not know this tap. Then use full paths: `/opt/homebrew/bin/brew install ...`. See the FAQ.

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

**A fresh install starts in watch-only mode.** It measures, logs and alerts, but
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

### `heat --profile` - what THIS Mac does, read from its own history

Thresholds ship as one number for every Mac, and no single number fits a fanless Air and a
14-inch Pro at once. This reads the measurements the guard has been writing all along and says
where your machine's own limits are: the temperature it idles at, the plateau it settles on
under sustained load, the temperature that starts the fans, and whether macOS ever had to hold
the CPU back.

```
THERMAL PROFILE OF THIS MAC
   data: 3425 samples on 13 days with measurements (2026-07-29 ... 2026-08-10)
   idle:             42.9 °C   (median of 783 samples, 90% below 52.4 °C)
   under load:       95.7 °C   (plateau of 2413 samples, median 90.5 °C, peak 101.8 °C)
   fans spin up at:  79.5 °C
   throttling:      never seen - macOS did not have to hold the CPU back
```

If the numbers say your thresholds do not fit the machine, it says so and prints the ones that
would. **It never writes anything.** The advice has rails, each from a way this could hurt
someone: the kill threshold is never raised, a suggested pause keeps its distance from it, the
resume threshold never lands inside the band the machine idles in (a job would pause and never
come back), thin data produces no advice at all, and a Mac that has already touched the kill
threshold or that macOS was already throttling is never given a wider margin. Add `--json` for
the same as data.

### `safe-run` - the right way to start a heavy job

```bash
safe-run --hours 8 --name render -- ffmpeg -i input.mov ... output.mp4
```

Refuses to start on an already-hot machine, applies `nice +10` and background QoS (efficiency
cores), puts the job in its own process group, enforces a time budget, and prints a report with
the peak temperature at the end. Jobs started this way are registered with the daemon explicitly,
so they never depend on name matching.

Since v2.4.0:

- `--wait-cool` - on a hot Mac, wait until the chip drops to the guard's *resume* threshold
  and then start, instead of exiting with code 3. A refusal is one line in a long log; an
  overnight queue can lose a job to it without anyone noticing.
- `--grace N` - seconds between `SIGTERM` and `SIGKILL` when the job is being stopped
  (default 30). Give it to solvers and encoders that need a moment to write their state.
- On exit, `safe-run` now checks the job's process group. If the leader died from a signal
  and left children running, they are cleaned up (`SIGCONT` + `SIGTERM`, grace, `SIGKILL`) -
  a leftover child used to survive its supervisor and burn for hours with no time budget.
  After a clean exit, surviving children are only reported, not touched.

Progress heartbeat (optional, advisory): `safe-run` hands every job a file path
in `$PALADIN_PROGRESS` and touches it once at start. A job (or the shell around
it) that touches the file after each finished unit of work - one `touch
"$PALADIN_PROGRESS"` in a loop - gets an honest answer to "is it stalled?".
Declare the expected rhythm with `--progress-interval 300` and the guard will
say so - in `status`, and as a notification - when the job goes 3x quiet. It
never acts on it: monitors used to guess stall thresholds by eye (15, then 5,
then 20 minutes against 21-84 minute encodes) and produced three false alarms
in a day; a declared rhythm replaces the guessing, and no declaration means no
verdict at all.

Admission control (optional, `"admission_control": true` in config.json): jobs declare how
many cores they will chew (`--cores 6`, default: this machine's performance-core count) and
the guard admits or queues them against a thermal core budget - full P-core pool on a cool
chip, half between the resume and pause thresholds, no new admissions on a hot one. Load
from unregistered processes shrinks the budget too. The declaration is enforced through the
CPU duty limiter, so the budget stays truthful. `--queue-priority N` (0 first, 9 last,
default 5) orders the queue; arrival breaks ties and a small job never overtakes the head.
`--after NAME` starts a job only when the safe-run job NAME has finished; a NAME that is
itself still waiting in its own `--after` counts as unfinished, so a chain holds at any
length (3.2.7) - chains without hand-rolled pgrep loops. The queue survives a guard restart, `heat` lists who is waiting,
and `fleet` gains a Q column. The arbiter only delays starts: it never pauses or kills
anything, and on any internal error it admits everyone - thermal safety stays with the
pause logic. Off by default; without the flag every start behaves exactly as before.

### Local LLM inference (Ollama, LM Studio, MLX)

Local models are the fastest way to keep an Apple Silicon chip at 90 C or more for
hours, and no inference runtime ships a temperature limit of its own. Run inference
under supervision and the guard pauses it at the threshold and resumes it after
cooldown - generation continues mid-token, nothing is lost:

```bash
safe-run --name llm -- ollama run qwen3 "..."
safe-run --hours 12 --name finetune -- mlx_lm.lora --train ...
```

A pause typically cools the chip from ~89 to ~60 C in about 20 seconds. With
`admission_control` on, parallel jobs can also declare cores and queue for thermal
headroom instead of piling onto a hot chip at once.

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
hot; RAM is shown as a plain percentage - swap details live in the RAM row of the menu.

Everything on the bar is optional - **Show in the bar** gives you a checkbox per element and the
choice is remembered in `~/.coffee-paladin/heatbar.json`, and three presets sit above the
checkboxes: **Icon only**, **Icon and chip temperature** and **Show all**. A new install
starts with the chip temperature and RAM as the fixed core, plus elements that
appear only while they carry news (spinning fans, a battery from 40 °C up, an
AI-session marker, throttle and pause) with a 60 s hysteresis against flicker. On a Mac with a notch the full readout does not fit, and macOS then draws no status
item at all - no warning, and no way to ask why. If that happens you cannot open the menu either,
so the same three presets work from a terminal:

```bash
coffee-paladin bar icon-only     # nothing but the thermometer, fits anywhere
coffee-paladin bar chip          # the icon and one number
coffee-paladin bar full          # everything
coffee-paladin panel             # open a window without going through the bar
```

<p align="center">
  <img src="docs/screens/bar_icons.webp" alt="The icon-only preset in a real menu bar, with two conditional markers lit" width="150">
</p>
<p align="center"><sub>Icon-only, with two conditional markers lit: 4 AI sessions and the keep-awake cup.</sub></p>

An upgrade keeps the layout you already had.
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

<p align="center">
  <img src="docs/screens/session_stats.webp" alt="Session statistics: pauses, resumes, terminations, across the fleet" width="480">
</p>
<p align="center"><sub>The guard's own scoreboard on one Mac: 2520 jobs frozen, 2347 resumed after cooling, 2 terminated at the kill threshold.</sub></p>

The bar measures nothing itself - it reads `~/.coffee-paladin/status.json`, which the daemon writes
every cycle. It therefore costs no CPU and can never disagree with the guard. Manual commands are
passed back through a file and executed by the daemon, so exactly one process ever decides what
gets paused.

### `thermal-report` - evidence for a repair shop

```bash
thermal-report --days 14          # plain text to your Desktop
thermal-report --days 14 --pdf    # the same, rendered to PDF
```

### `thermal-metrics` - the numbers for a scraper

```bash
thermal-metrics                   # this Mac, Prometheus text format
thermal-metrics --fleet           # every machine in the fleet folder, one document
```

For a rack, a cluster or a rented-out Mac. No port and no server: it prints and exits, so
`--output` feeds the `node_exporter` textfile collector from cron. Details and the two
metrics worth alerting on are under
[Prometheus, Grafana and anything else that scrapes](#prometheus-grafana-and-anything-else-that-scrapes).

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
| `batt_pause_c` / `batt_kill_c` | 40 / 45 | **battery** temperature - lithium cells degrade above ~40 °C |
| `batt_pct_pause` | 10 | pause when on battery at or below this charge |
| `fan_alert_temp_c` | 70 | above this the fans must be spinning |
| `max_pause_minutes` | 45 | a job paused longer than this is **terminated with `SIGTERM`** - for an encoder without checkpoints that means losing all progress, so give long jobs `safe-run --hours N` and headroom here |
| `max_pause_minutes_batt` | 240 | same limit when the *only* reason for the pause is a low battery (waiting for a charger is not a failure) |
| `demote_after_minutes` | 5 | a heavy process grinding longer than this **while the chip is hot** is moved to E-cores; it returns to P-cores on its own once the chip cools to `soc_resume_c` |
| `demote_at_pause` | true | a process the guard freezes for heat is moved to E-cores right there and comes back throttled, held for one `repause_window_s` before promotion may undo it; a bare encoder that reheated the chip 17 s after every resume got 3 % duty under the re-pause backoff alone (3.2.7). Jobs run with `safe-run --normal` keep all cores |
| `demote_above_c` | `soc_resume_c + 4` | demotion only happens at or above this chip temperature - a cool machine never slows anyone down |
| `system_demote_patterns` | Spotlight/photo-analysis daemons | system indexing daemons that stay **untouchable for pause and kill** but may be moved to E-cores when they grind on a warm machine (they otherwise burn 200 %+ CPU with total impunity) |
| `keep_awake_hold_s` | 300 | after the last heavy job ends, keep-awake holds the sleep block this many seconds longer - the gap between two files of a batch queue no longer lets the Mac fall asleep mid-queue; heat still releases the block **immediately** |
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
| `sound` | `false` | system sounds per event (pause / resume / kill); off until you enable them in Settings |
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

This project literally runs on coffee - the release codename is "Cold Brew" and the
keep-awake fuse is my answer to Caffeine. If coffee-paladin saved your Mac (or your render),
buy me a coffee: **https://suppi.pl/panbookovsky**

## License

MIT - do whatever you like with it. If it saves your machine, that is satisfaction enough.

<p align="center">
  <img src="docs/screens/paladin_panel.webp" alt="The paladin panel, pinned under the menu bar" width="260">
</p>
<p align="center"><sub>Click the product name at the top of the menu and the paladin steps out, pinned under the bar.</sub></p>

**Artwork.** The paladin - the mascot you see above, in the welcome window, in the menu header
and in the `heat --paladin` easter egg - is **the author's own design** and is used
as the official mascot of the project. Everything else in `branding/` is derived from those two
source files; details in [`branding/CREDITS.md`](branding/CREDITS.md).

Built by Paweł Kwaczyński / FOCUS FRAME, 2026. A project by the founder of **AIrON**, the
student research club for computer science at AHE in Łódź (SKN Informatyki AHE w Łodzi).

---

<a name="po-polsku"></a>
