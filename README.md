# thermal-guard v1.7.5

**A thermal and power safety net for Apple Silicon Macs — from one laptop to a whole fleet.**
It watches the chip temperature, the battery, the fans and the power source, and it *freezes*
heavy jobs before the machine cooks itself — instead of letting them run until it shuts down.
Built for people who make Macs work for a living: render farms, post-production studios,
CI pools of Mac minis, ML teams, and anyone leaving a laptop to compute overnight.

No `sudo`. No kernel extensions. No daemons running as root. Everything reads sensors that are
available to a normal user process.

*(Polska wersja poniżej — [przejdź do opisu po polsku](#po-polsku).)*

```
🌡 C67° G64° B33° 🌀3.3k 42W 🧠62% 💾46%
```

chip · GPU · battery · fan rpm · power draw · RAM used · disk used — and you choose which of
those appear, with checkboxes under **Show in the bar**. The menu bar, the notifications and all
CLI tools speak **five languages** — English (default), Polish, Russian, Chinese and Spanish —
switched from the menu bar (*Settings > Language*), with `TG_LANG` or `"lang"` in the config.

---

## Why this exists

A MacBook Pro M4 Pro was left running an overnight batch of computational experiments: 11 jobs,
3 in parallel, one of them with 4 extra workers. Twelve and a half hours at full load on every
core. One job ground away for 6 h 42 min and produced nothing. The orchestrator had an
auto-restart, so any job killed by the machine came straight back for more.

Nothing in that pipeline read a single temperature.

The result was a burning smell from under the chassis and a hard shutdown. Worse, when the logs
were examined afterwards, there was **nothing to examine**: no kernel panic, no thermal shutdown
record, and the system log simply ended at the moment the machine died. There was no way to
reconstruct what the temperature had been.

This project is the answer to both problems: *stop it before it cooks*, and *keep the evidence
when something goes wrong anyway*.

---

## What it actually does

### 1. It pauses instead of killing

When the chip gets too hot, heavy processes receive `SIGSTOP`. That is **not** destructive: the
process freezes exactly where it is, its memory is untouched, and when things cool down it gets
`SIGCONT` and continues **from the same instruction**. Nothing is lost.

Measured on a real job: chip at 89.3 °C → paused → **60.2 °C nineteen seconds later** → resumed.
The computation never noticed.

Termination (`SIGTERM`, gently, so jobs can checkpoint) only happens after several consecutive
critical readings — in practice pausing cools the chip long before that.

### 2. It finds the *real* culprit, not just the obvious one

This is the part most naive implementations get wrong, and it took two failures to discover.

**Failure one — the name list.** A guard that only manages processes matching a list of known
names (`ffmpeg`, `python`, `ollama`…) is blind to your own compiled binaries. A custom solver
named `b3core` pushed the machine to 90 °C while the guard happily reported everything as
managed. Name lists are *always* incomplete.

**Failure two — the invisible orchestrator.** A Python script was spawning hundreds of `cadical`
SAT-solver instances, each living about one second. Every child was too short-lived to ever cross
a CPU threshold, and the parent itself used almost no CPU. Individually: nothing to see.
Together: eight cores at 100 %.

So thermal-guard:

- computes **CPU usage across the entire process subtree**, so an orchestrator that spawns
  short-lived children is correctly identified (that Python process showed up as **595 %**) and
  frozen *at the source*, which stops new children from being spawned;
- treats **any** of your processes above 50 % CPU that has lived longer than 2 minutes as a
  manageable heavy job, regardless of its name;
- protects a hard "never touch" list: the system, WindowServer, Finder, your terminal, SSH, and
  Apple background daemons that either refuse `SIGSTOP` or misbehave when frozen.

### 3. It watches power, not just heat

- **Battery gate** — if you are on battery and drop to 10 %, long jobs are paused and only resume
  once you plug in. A 30-day computation should not die halfway through a block because the
  laptop ran flat. Waiting for a charger is not a failure, so this pause is allowed to last for
  hours; a *thermal* pause is not.
- **Fan alarm** — if the chip is above 70 °C and both fans report 0 rpm, you get a notification
  and a log entry. A seized fan is a common cause of exactly the burning smell described above.

### 4. It keeps the Mac awake — with a fuse

`safe-run` holds a sleep block (`caffeinate`) for exactly as long as the job runs, and the daemon
can do the same automatically for any heavy job it sees (*Keep the Mac awake while heavy jobs
run* in Settings — off by default). The menu bar also offers the full Amphetamine-style set of
**manual modes**: a timer (15 min to 12 h), *indefinitely*, *while an app is running* (pick from
the list of running apps) and *while downloading* (network activity, with a 2-minute grace gap
between files). The difference from Caffeine/Amphetamine is the **fuse**: every one of these
modes holds the wake lock **only while the machine is cool**. The moment the guard pauses jobs
for heat, the lock is released — sleep is the fastest cooler there is — and an unconditional
keep-awake in a backpack is precisely how MacBooks get cooked. When the job ends (or the timer
runs out), the Mac goes back to sleeping normally. A cup icon on the bar shows when the lock is
held.

**The screen sleeps. The math doesn't.** This is the second difference from the Caffeine
family: classic keep-awake apps hold the *display* assertion (`caffeinate -d`) — the screen
burns watts all night just to prove the machine is awake. thermal-guard holds only the
*system* assertion (`caffeinate -is`): lock the screen (Ctrl+Cmd+Q), let the display sleep on
its own schedule — the jobs keep computing in the dark, and the display (often the single
biggest power draw during light work) costs you nothing. One caveat: keep the lid open —
closing it forces sleep regardless of assertions (clamshell mode with an external display and
power being the exception). And the thermal fuse stays supreme: if the machine runs hot, the
lock is released and the Mac may fully sleep; a `safe-run` job resumes when you wake it.

### 4b. It controls how hard heavy jobs are allowed to push

Two knobs in Settings, both consumed by `safe-run` as defaults: **which cores** heavy jobs run on
(*efficiency cores only* — cool and quiet, or *all cores* — fast, with the guard still watching
the temperature) and a **CPU limit** (50–100 %, default 95). Below 100 % the whole process group
gets cpulimit-style micro-pauses (SIGSTOP for ~100 ms in every 2 s window), so the cap works for
any program — including ones that ignore thread-count options. Per-run overrides: `--normal`
(all cores), `--efficiency`, `--cpu-limit 80`.

### 4c. It adapts itself to the Mac it lands on

On first start the daemon detects the hardware — chip, performance/efficiency core split, RAM,
fan count, battery health — writes it to `hardware.json` (shown in **About my Mac** in the menu
bar) and calibrates the defaults: a fanless Mac (Air) gets lower chip thresholds (78/70/88) and
its always-false fan alarm disabled. Calibration runs once per machine and **never overrides
thresholds you set yourself**.

### 5. It escalates so you cannot miss it

Notification with a distinct sound at pause, resume and kill — and at the **critical** level
additionally a **system alert on top of everything** (`critical_banner`, its own 3-minute gap,
self-dismissing). A notification is easy to miss under Focus or a full-screen app; the critical
banner is not. And when you are not at the machine at all: set a secret topic under **Settings >
Phone push (ntfy.sh)**, install the free [ntfy](https://ntfy.sh) app and subscribe to the same
topic — pauses, kills, cooling failures and hard-shutdown reports arrive on your phone. No
account, no server of ours; leave the field empty and nothing is ever sent.

**The topic name is the whole secret.** Public ntfy.sh topics have no other access control:
anyone who knows (or guesses) the name can read your alerts *and* send fake ones. Do not use
a guessable name like `mac-guard` — the settings dialog **suggests a random, unguessable name**
(e.g. `mac-guard-x7kq93w2`) whenever the field is empty; take it, or bring your own long random
one. The messages themselves contain process names and temperatures, nothing more.

### 6. It keeps evidence (the black box)

The daemon writes a heartbeat on every cycle and a marker on clean shutdown. After a restart it
compares those against `kern.boottime`. If the machine went down without warning, it records the
event **together with the last eight measurements taken before the crash**.

`thermal-report` then assembles a single file for a repair shop or warranty claim: hardware and
serial, battery health and cycle count, detected hard shutdowns with the readings that preceded
them, the system's own shutdown-cause entries, every intervention the guard made, and the full
measurement timeline with the peak temperature highlighted.

---

## What nothing else does

There are excellent Mac monitoring tools — Stats, iStat Menus, TG Pro, Macs Fan Control. They
show you numbers, or drive the fans harder. **None of them touches the workload.** When the chip
hits 90 °C at 3 a.m., a chart of it is not protection.

thermal-guard occupies a different category:

| | Monitoring apps | Fan controllers | **thermal-guard** |
|---|---|---|---|
| Shows temperatures | yes | yes | yes |
| Drives fans | – | yes | no (macOS does) |
| **Pauses the workload itself, losslessly** | – | – | **yes — SIGSTOP/SIGCONT** |
| Sees orchestrators spawning 1-second children | – | – | **yes — subtree CPU accounting** |
| Keeps pre-crash readings for a warranty claim | – | – | **yes — black box + report** |
| Protects long jobs from draining the battery | – | – | **yes — battery gate** |
| Keeps the Mac awake for a job **only while it is cool** | – | – | **yes — keep-awake with a thermal fuse** |
| Whole-fleet view with zero infrastructure | – | – | **yes — a shared folder** |
| Needs sudo / kexts / accounts | varies | often | **no** |

The freeze is the heart of it: a paused process loses *nothing* — memory intact, resumes from
the same instruction. Measured live: 89.3 °C → 60.2 °C in 19 seconds, computation unharmed.

---

## Fleets: every Mac in one table

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
no inbound network, nothing phoning home — the data is plain JSON you can open and read.

### Setup, step by step

**1. Pick the shared folder.** Any folder that all machines can write to:

| You have | Folder to use | Notes |
|---|---|---|
| iCloud (same Apple ID on your Macs) | `~/Library/Mobile Documents/com~apple~CloudDocs/FleetTG` | Right for one person with 2–5 machines. This is the closest thing to "link my Apple ID" — Apple offers no fleet API, but iCloud Drive syncs a folder just fine. |
| Dropbox / Google Drive | `~/Dropbox/FleetTG` | Share the folder with each machine's account. Good for small teams. |
| Microsoft 365 | a synced SharePoint library folder | The corporate route; IT already manages access. |
| A NAS / file server | `/Volumes/<share>/FleetTG` | The render-farm route — fastest updates (no cloud sync delay). Make sure the share mounts at login. |

**2. On every machine**, after installing thermal-guard, point the agent at the folder — one key
in the config:

```bash
python3 - <<'EOF'
import json, os
p = os.path.expanduser("~/.thermal-guard/config.json")
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

No restart needed — the daemon re-reads its config every cycle and starts publishing within a
minute.

**3. On whichever machine you sit at**, look at the fleet:

```bash
fleet              # one table, flags what needs attention, exit code 2 if anything does
fleet --watch      # refreshes every 30 s
fleet --json       # machine-readable, for dashboards and automation
```

A host that has not reported for 5 minutes is flagged `STALE` — crashed, asleep, or its sync
broke; either way you want to know. `fleet --json` plus the exit code make it trivial to wire
into Slack alerts, Grafana, or a cron job that emails you.

### What is in the published snapshot

Hostname, temperatures, fan rpm, power draw, RAM/disk usage, power source, guard level and
reason, paused-job names, today's intervention counts, and the last detected hard shutdown.
No file paths, no serial numbers. If publishing the name of the top CPU process is too much for
your environment, you can strip it — the file is built in one function (`fleet_write`).

---

## Where the data comes from

This is the interesting part, because macOS does not hand out chip temperatures to unprivileged
processes.

| Signal | Source | Notes |
|---|---|---|
| **Chip / GPU temperature** | [`macmon`](https://github.com/vladkens/macmon) → **IOReport** | The one route that still works without `sudo`. |
| **Fan RPM, power draw (W)** | same | Also gives per-core frequency and RAM/swap usage. |
| **Thermal pressure** (`nominal`/`fair`/`serious`/`critical`) | `ProcessInfo.thermalState` via a tiny Swift binary | Public API, no privileges needed. |
| **Battery temperature, cycles, cell voltages** | `ioreg -c AppleSmartBattery` | Units vary by model — see the gotcha below. |
| **CPU throttling** | `pmset -g therm` → `CPU_Speed_Limit` | 100 = not throttled. |
| **Power source, battery %** | `pmset -g batt` | |
| **Processes** | `ps` | Own CPU plus subtree rollup. |

### Two dead ends, documented so you don't repeat them

**`powermetrics` requires a password.** It is the obvious tool and it is unusable for an
unattended agent.

**Reading SMC sensors through `IOHIDEventSystem` no longer works.** This was for years *the*
way to read Apple Silicon temperatures without root: match HID services on usage page `0xff00`,
usage `0x0005`, and pull `kIOHIDEventTypeTemperature`. On **macOS 26 it returns zero sensors** for
an unentitled process — Apple closed it. A complete, working-by-the-old-rules implementation is
kept in [`experiments/soctemp.swift`](experiments/soctemp.swift) as a reference and a warning.
IOReport is currently the surviving path.

**The battery temperature unit is not fixed.** Different battery controllers report different
scales: hundredths of a degree on one Mac (`3081` = 30.81 °C), tenths on another (`444` = 44.4 °C),
and some fields whole degrees (`41` = 41 °C). A hardcoded divisor is wrong somewhere — it produced
a reading of *444 °C* on one machine and *0.4 °C* on another. thermal-guard scales the raw value
into the range a lithium cell can physically be in instead of assuming a unit.

**Why battery temperature alone is not enough.** It lags the chip by minutes and reads far lower.
A measurement taken while writing this README: **chip 53.5 °C, battery 30.6 °C.** A guard using
only battery temperature reacts long after the damage window has opened.

---

## Install

Requires macOS on Apple Silicon, Xcode command line tools (`xcode-select --install`) for `swiftc`,
and [Homebrew](https://brew.sh) so the installer can fetch `macmon`.

```bash
git clone https://github.com/pawelkwaczynski/thermal-guard.git
cd thermal-guard
bash install.sh
```

The installer compiles the two Swift helpers, installs the scripts into `~/.local/bin`, writes a
default config into `~/.thermal-guard/config.json` (it will **not** overwrite an existing one),
and loads two LaunchAgents — the daemon and, separately, the menu bar app, so you can disable the
latter without touching the safety net.

**A fresh install starts in watch-only mode.** It measures, logs and alerts — with sound — but
pauses nothing, until you enable protection yourself: one click in the menu bar (*Enable
protection*) or `"dry_run": false` in the config. A tool that touches your processes should earn
that right by first showing you what it *would* have done. The menu bar shows an eye icon while
in watch-only mode, so you cannot forget which mode you are in.

To remove everything: `bash uninstall.sh` (keeps the measurement history and black box —
you may still need them for a warranty claim; `--purge` removes those too).

Make sure `~/.local/bin` is on your `PATH`.

---

## Usage

### `heat` — one-shot status

```
🟢 thermal state: nominal   chip: 53.5 °C   battery: 30.6 °C   CPU available: 100%   load: 4.29
   fans: 4500 rpm, 4831 rpm
   power: AC adapter   draw: 32.6 W
   thermal-guard: running ✅
```

Plus what is currently burning CPU, the 24-hour peak, and the guard's recent interventions.

### `safe-run` — the right way to start a heavy job

```bash
safe-run --hours 8 --name render -- ffmpeg -i input.mov ... output.mp4
```

Refuses to start on an already-hot machine, applies `nice +10` and background QoS (efficiency
cores), puts the job in its own process group, enforces a time budget, and prints a report with
the peak temperature at the end. Jobs started this way are registered with the daemon explicitly,
so they never depend on name matching.

### `heatbar` — menu bar

```
🌡 C67° G64° B33° 🌀3.3k 42W ⚡ ⏸
```

chip / GPU / battery / fan rpm / power draw / RAM used / disk used, plus `⚡` when macOS is
throttling and `⏸` when something is paused. `🌀⚠︎0` means the fans are stopped while the chip is
hot; `🧠62%⚠︎` means RAM is 62 % used **and** the machine has started swapping.

Everything on the bar is optional — **Show in the bar** gives you a checkbox per element and the
choice is remembered in `~/.thermal-guard/heatbar.json`. RAM and disk are off by default.
The language switch (EN · PL · RU · 中文 · ES) sits as a row of buttons right on the main menu,
**About my Mac** shows the detected hardware, and **Start at login** toggles autostart of both
agents (on by default).

**Apple fleet** in the menu shows every Mac publishing to your shared fleet folder — chip
temperature, fans, watts, RAM, state, paused jobs and last-seen age per host — each under its
own custom name (*Settings > Name this Mac in the fleet*; with five identical MacBooks the
hostname tells you nothing), with the model shown inline and the serial number in the tooltip,
and a
`STALE - not reporting` marker after 5 minutes of silence. It reads the same files as the
`fleet` CLI, refreshed by a background cache every ~30 s, so opening the menu never blocks on
iCloud/SMB. "Live" here means the agent's ~1-minute publishing rhythm plus your folder's sync
delay — perfect for a glance, not for second-by-second monitoring (that is what a future HTTP
collector would be for).

**Branding:** the menu header and footer render `~/.thermal-guard/logo.png` (black-on-transparent,
theme-aware template) and `logo_footer.png` (+ optional `logo_footer_dark.png` for dark mode;
a click opens `footer_logo_url` from the config). The installer copies the logos shipped in
`branding/` — swap those files for your own to rebrand your install.

The menu adds a block-character temperature graph, a trend and forecast ("rising 2.1 °C/min —
about 4 minutes to pause"), **what is heating the machine right now** (top 3 by CPU — the best
per-process proxy for heat there is) and **what is eating the RAM** (top 3 by resident memory),
running `safe-run` jobs, today's intervention count, a manual **Freeze / Resume** control, and
**Export report**.

The bar measures nothing itself — it reads `~/.thermal-guard/status.json`, which the daemon writes
every cycle. It therefore costs no CPU and can never disagree with the guard. Manual commands are
passed back through a file and executed by the daemon, so exactly one process ever decides what
gets paused.

### `thermal-report` — evidence for a repair shop

```bash
thermal-report --days 14          # plain text to your Desktop
thermal-report --days 14 --pdf    # the same, rendered to PDF
```

---

## Configuration

Most of it is adjustable from the menu bar: **Settings** holds a slider for the chip pause
threshold with a live warning under it, a slider for the battery gate, and switches for
notifications, language, and a **watch-only (dry run)** mode that logs what it *would* do without
touching a single process — the honest way to build trust in a tool that can freeze your work.

The daemon re-reads its config on every cycle, so changes take effect immediately, with no restart.

### Do different chips need different thresholds?

Between M-series generations, not really: they all throttle themselves somewhere around
100-108 °C and Tjmax is about 110 °C, so the shipped 85/76/90 is sane from M1 to M4 and there is
no reason to expect M5 or M6 to leave that range.

**Cooling is what differs.** A fanless Mac (Air, 12-inch) dumps heat into the chassis and gets hot
sooner, so a lower threshold — around 75-78 °C — is kinder to it. thermal-guard detects the
absence of fans and simply skips the fan alarm there, but the temperature threshold is yours to
set. That is exactly what the slider is for.

`~/.thermal-guard/config.json`. The defaults:

| Setting | Default | Meaning |
|---|---|---|
| `soc_pause_c` | 85 | freeze heavy jobs at this chip temperature |
| `soc_resume_c` | 76 | resume below this (hysteresis) |
| `soc_kill_c` | 90 | terminate, but only after `kill_after_polls` consecutive readings |
| `batt_pause_c` / `batt_kill_c` | 40 / 45 | **battery** temperature — lithium cells degrade above ~45 °C |
| `batt_pct_pause` | 10 | pause when on battery at or below this charge |
| `fan_alert_temp_c` | 70 | above this the fans must be spinning |
| `unknown_cpu_percent` | 50 | catch-all threshold for unrecognised processes |
| `never_patterns` | see `guard.py` | never touched, overrides everything |
| `never_extra` | `[]` | your own additions to the never-touch list (tools you do not want frozen) |
| `never_arg_patterns` | guard's own tooling | matched against the **full command line**, useful when a job runs under an interpreter |
| `lang` | `en` | `en`, `pl`, `ru`, `zh` or `es` |
| `dry_run` | **`true`** | watch-only: log and alert, never signal (disable to arm the guard) |
| `critical_banner` | `true` | modal system alert at the critical level (own 180 s gap, self-dismissing) |
| `keep_awake_auto` | `false` | hold a sleep block while a heavy job runs **and** the machine is cool |
| `job_cores_mode` | `"efficiency"` | default cores for `safe-run` jobs: `"efficiency"` or `"all"` |
| `job_cpu_percent` | `95` | duty-cycle CPU cap for `safe-run` jobs (50–100) |
| `ntfy_topic` | `""` | secret ntfy.sh topic for phone push (empty = off) |
| `download_kbps` | `500` | network-activity threshold for the *while downloading* keep-awake mode |
| `calibrated_for` | set by the daemon | hardware tag; delete it to re-run auto-calibration |
| `sound` | `true` | distinct system sound per event (pause / resume / kill) |
| `fleet_dir` | `""` | shared folder for fleet snapshots (see the fleet section) |

### A note on numbers, because this trips people up

**Do not set `soc_pause_c` to 45.** Chips are not batteries. An idle M4 Pro sits at 40–55 °C, and
ordinary work pushes it past 60 without anything being wrong. Apple Silicon throttles itself
somewhere around 100–108 °C and Tjmax is about 110 °C. A 45 °C threshold means permanent pause and
a useless safety net. 45 °C is the correct number for the *battery*, and that is where it is used.

The shipped defaults are deliberately more conservative than Apple's own throttling point.

---

## Known limitations

- **It will freeze GUI applications too.** If Blender or a video export pushes the chip to 85 °C,
  that window freezes until things cool down. Nothing is lost, but it looks like a hang. Add such
  apps to `never_patterns` if you would rather they were left alone.
- **Chip temperature depends on `macmon`.** Without it the daemon still runs, but falls back to
  battery temperature and thermal pressure only, and loses fan monitoring.
- **Apple Silicon only.**
- The LaunchAgent labels are `pl.pawel.thermal-guard` and `pl.pawel.heatbar`. Rename them in the
  plists if you prefer something neutral.
- Messages are English by default; `"lang"` in `config.json` (or `TG_LANG`) switches every tool,
  the notifications and the menu bar to Polish, Russian, Chinese or Spanish. Adding a language
  means adding one dictionary per file.
- Some inline code comments are still in Polish.

---

## License

MIT — do whatever you like with it. If it saves your machine, that is payment enough.

Built by Paweł Kwaczyński / FOCUS FRAME, 2026. Developed also as a project of **AIrON** —
the student research club for computer science at AHE in Łódź (SKN Informatyki AHE w Łodzi).

---

<a name="po-polsku"></a>

# Po polsku

**Bezpiecznik termiczny i zasilania dla Maców na Apple Silicon — od jednego laptopa po całą
flotę.** Pilnuje temperatury chipa, baterii, wentylatorów i zasilania, a gdy robi się gorąco —
**wstrzymuje** ciężkie zadania, zamiast pozwolić im pracować aż komputer zgaśnie. Pisany z myślą
o ludziach, u których Maki pracują na chleb: farmy renderujące, studia postprodukcji, pule
Mac mini pod CI, zespoły ML — i każdy, kto zostawia laptop z obliczeniami na noc.

Bez `sudo`, bez rozszerzeń jądra, bez niczego działającego jako root.

## Skąd się wziął

MacBook Pro M4 Pro dostał na noc kolejkę eksperymentów obliczeniowych: 11 zadań, 3 równolegle,
jedno z czterema dodatkowymi wątkami roboczymi. Dwanaście i pół godziny pełnego obciążenia
wszystkich rdzeni. Jedno zadanie mieliło 6 h 42 min bez żadnego wyniku. Orkiestrator miał
auto-restart, więc zadanie ubite przez komputer wracało do walki.

W całym tym kodzie nie było ani jednego odczytu temperatury.

Skończyło się zapachem spalenizny spod obudowy i twardym wyłączeniem. Gorzej — gdy potem sięgnięto
do logów, **nie było czego czytać**: żadnej paniki jądra, żadnego zapisu o przegrzaniu, a dziennik
systemowy po prostu urywał się w chwili zgaśnięcia. Nie dało się odtworzyć, jaka była temperatura.

Ten projekt odpowiada na oba problemy: *zatrzymać, zanim się ugotuje*, i *zachować dowody, gdy coś
jednak pójdzie źle*.

## Co robi

**Zamraża, nie zabija.** Przy przegrzaniu ciężkie procesy dostają `SIGSTOP` — proces zamiera
w miejscu, pamięć zostaje nietknięta, a po ostygnięciu `SIGCONT` i liczy dalej od tej samej
instrukcji. Zmierzone na żywym zadaniu: chip 89,3 °C → pauza → **60,2 °C po dziewiętnastu
sekundach** → wznowienie. Obliczenia niczego nie zauważyły. Ubicie (łagodnym `SIGTERM`, żeby
zadanie zdążyło zapisać checkpoint) następuje dopiero po kilku krytycznych odczytach z rzędu.

**Znajduje prawdziwego sprawcę.** Lista znanych nazw procesów zawsze będzie dziurawa — własna
binarka `b3core` rozgrzała maszynę do 90 °C, bo do niczego nie pasowała. Jeszcze gorszy przypadek:
skrypt Pythona rozsiewał setki instancji solvera `cadical` żyjących po sekundę — dziecko było za
krótkie, by przekroczyć próg, a rodzic sam nie zużywał prawie nic. Dlatego guard liczy **CPU
całego poddrzewa procesów** (ten Python pokazał **595 %**) i zamraża źródło, oraz traktuje jako
ciężkie **każde** zadanie powyżej 50 % CPU żyjące dłużej niż 2 minuty, niezależnie od nazwy.

**Pilnuje zasilania.** Na baterii poniżej 10 % pauzuje długie obliczenia i wznawia je dopiero po
podpięciu zasilacza — czekanie na kabel nie jest awarią, więc taka pauza może trwać godzinami.
Osobno ostrzega, gdy chip przekracza 70 °C, a wentylatory stoją.

**Trzyma Maca w czuwaniu — ale z bezpiecznikiem.** `safe-run` blokuje sen dokładnie na czas
zadania (`caffeinate`), a demon umie robić to sam dla każdego ciężkiego zadania (opcja w
Ustawieniach, domyślnie wyłączona). Z paska menu dostępne są też tryby ręczne jak w Amphetamine:
timer (15 min – 12 h), bezterminowo, „dopóki działa aplikacja" (wybór z listy uruchomionych)
i „dopóki trwa pobieranie" (aktywność sieci). Różnica względem Caffeine/Amphetamine: każdy z tych
trybów trzyma blokadę czuwania **tylko póki maszyna jest chłodna** — przy przegrzaniu guard ją
zwalnia, bo sen chłodzi najszybciej. Bezwarunkowy keep-awake w plecaku to klasyczna droga do
ugotowania laptopa. Kubek na pasku pokazuje, kiedy blokada jest trzymana.

**Ekran śpi. Obliczenia nie.** Druga różnica względem rodziny Caffeine: klasyczne aplikacje
trzymają asercję *wyświetlacza* (`caffeinate -d`) — ekran pali waty całą noc tylko po to, żeby
udowodnić, że Mac czuwa. thermal-guard trzyma wyłącznie asercję *systemu* (`caffeinate -is`):
zablokuj ekran (Ctrl+Cmd+Q), pozwól mu zgasnąć — zadania liczą dalej po ciemku, a wyświetlacz
(przy lekkiej pracy często największy pojedynczy odbiornik energii) nie kosztuje nic. Jeden
haczyk: klapa musi zostać otwarta — zamknięcie pokrywy wymusza sen mimo asercji (wyjątek:
tryb clamshell z zewnętrznym monitorem i zasilaczem). Bezpiecznik termiczny pozostaje nadrzędny.

**Steruje mocą ciężkich zadań i dopasowuje się do maszyny.** W Ustawieniach wybierasz, na jakich
rdzeniach chodzą zadania z `safe-run` (tylko energooszczędne E albo wszystkie — temperatury i tak
pilnuje guard) i limit CPU 50–100 % (mikropauzy całej grupy procesów, działa z każdym programem).
Przy pierwszym starcie demon sam wykrywa sprzęt (chip, podział rdzeni P/E, RAM, wentylatory,
zdrowie baterii — zakładka **O moim Macu**) i kalibruje progi: Mac bez wentylatorów dostaje
niższe (78/70/88) i wyłączony alarm wentylatorów. Ręcznie ustawionych progów kalibracja nigdy
nie nadpisuje. Push na telefon: **Ustawienia > Push na telefon (ntfy.sh)** + darmowa aplikacja
ntfy z tym samym tematem. Przełącznik **Uruchamiaj przy starcie komputera** (domyślnie włączony)
i wybór języka guzikami wprost na głównej karcie menu.

**Alarmuje tak, że nie da się przeoczyć.** Powiadomienie z osobnym dźwiękiem przy pauzie,
wznowieniu i ubiciu — a przy poziomie **krytycznym** dodatkowo **modalny alert systemowy na
wierzchu wszystkiego** (`critical_banner`, własny odstęp 3 min, sam znika). Powiadomienie łatwo
zginie pod Skupieniem albo aplikacją na pełnym ekranie; ten baner nie zginie.

**Zbiera dowody.** Tyka puls przy każdym przebiegu, a po restarcie porównuje go z czasem startu
systemu. Jeśli Mac zgasł bez uprzedzenia, zapisuje to zdarzenie razem z ośmioma ostatnimi
pomiarami sprzed padu. `thermal-report` składa z tego jeden plik dla serwisu: sprzęt, stan
baterii, wykryte twarde pady z odczytami, interwencje bezpiecznika i pełną oś czasu pomiarów.

## Skąd biorą się dane

macOS nie udostępnia temperatury chipa zwykłemu procesowi. Działające źródła:

- **temperatura chipa i GPU, obroty wentylatorów, pobór mocy** — [`macmon`](https://github.com/vladkens/macmon) przez **IOReport**, jedyna droga bez `sudo`,
- **stan termiczny systemu** — `ProcessInfo.thermalState` przez malutką binarkę Swift,
- **bateria** — `ioreg -c AppleSmartBattery` (uwaga: `Temperature` w setnych °C, ale
  `MaximumTemperature` w całych — łatwo o błąd),
- **dławienie CPU** — `pmset -g therm`, **zasilanie** — `pmset -g batt`, **procesy** — `ps`.

Dwie ślepe uliczki, spisane, żeby nikt nie powtarzał: **`powermetrics` żąda hasła**, a odczyt
sensorów przez **`IOHIDEventSystem`** (przez lata standardowy sposób) **na macOS 26 zwraca zero
sensorów** dla procesu bez uprawnień — Apple to zamknęło. Kompletna implementacja tej metody leży
w [`experiments/soctemp.swift`](experiments/soctemp.swift) jako materiał poglądowy.

Sama bateria nie wystarcza: pomiar z czasu pisania tego pliku to **chip 53,5 °C przy baterii
30,6 °C**. Bateria reaguje z kilkuminutowym opóźnieniem, czyli długo po otwarciu okna na szkodę.

## Czym to się różni od Stats / iStat / TG Pro

Tamte narzędzia **pokazują** liczby albo podkręcają wentylatory. Żadne nie dotyka samej pracy.
thermal-guard jako jedyny: **wstrzymuje obciążenie bezstratnie** (SIGSTOP — proces wraca do tej
samej instrukcji; zmierzone 89,3 → 60,2 °C w 19 s bez utraty obliczeń), **widzi orkiestratory**
rozsiewające sekundowe procesy (liczy CPU całego drzewa), **zbiera dowody** sprzed twardego padu
do reklamacji, **pilnuje baterii** przy wielodniowych obliczeniach i **składa całą flotę w jedną
tabelę** bez żadnego serwera.

## Flota: wszystkie Maki w jednej tabeli

Każdy agent publikuje migawkę do **wspólnego folderu** (`<host>.json`, co ~1 min), a polecenie
`fleet` czyta ten folder. Folderem może być: **iCloud Drive** (to samo Apple ID na Twoich Makach —
najbliższy odpowiednik „spięcia jednym Apple ID", bo Apple nie daje API do flot), **Dropbox /
Google Drive** (folder udostępniony zespołowi), **SharePoint** (droga korporacyjna) albo **dysk
sieciowy NAS/SMB** (droga farmy renderującej — najszybsza, bez opóźnień chmury).

Świeża instalacja startuje w **trybie obserwacji**: mierzy, loguje i alarmuje (też dźwiękiem),
ale niczego nie wstrzymuje, dopóki nie włączysz ochrony — jednym kliknięciem w menu paska.
Na pasku widać wtedy ikonę oka. Odinstalowanie: `bash uninstall.sh`.

Konfiguracja floty: `fleet --setup` (wykrywa foldery synchronizowane i zapisuje wybór) albo
ręcznie — jeden klucz na każdej maszynie: `"fleet_dir": "<ścieżka folderu>"` w
`~/.thermal-guard/config.json` — bez restartu, agent zacznie publikować w ciągu minuty. Potem
na swojej maszynie: `fleet` (tabela + problemy), `fleet --watch` (odświeżanie), `fleet --json`
(pod automaty i dashboardy). Host bez raportu od 5 minut dostaje flagę `NIE RAPORTUJE`.

## Instalacja i użycie

```bash
git clone https://github.com/pawelkwaczynski/thermal-guard.git
cd thermal-guard
bash install.sh
```

- `heat` — jednym poleceniem: jak gorąco, co grzeje, czy bezpiecznik żyje
- `safe-run --hours 8 --name render -- <polecenie>` — tak uruchamiaj ciężkie zadania
- `heatbar` — pasek menu: chip, GPU, bateria, obroty, waty, RAM i dysk (wybierasz checkboxami
  w „Pokaż na pasku"), wykres, prognoza, listy „co grzeje" (top 3 po CPU — najlepsze dostępne
  przybliżenie ciepła per proces) i „co zjada RAM" (top 3 po pamięci), ręczne zamrażanie,
  eksport raportu oraz **Flota Apple** — wszystkie Twoje Maki z parametrami, własnymi nazwami
  (Ustawienia > „Nazwij tego Maca we flocie" — przy pięciu identycznych MacBookach nazwa
  systemowa nic nie mówi), modelem w wierszu i numerem seryjnym w podpowiedzi, ze znacznikiem
  „NIE RAPORTUJE" (cache w tle, otwarcie menu nigdy nie czeka na iCloud/SMB)
- `thermal-report --dni 14` — raport dowodowy dla serwisu

Progi w `~/.thermal-guard/config.json`. **Nie ustawiaj progu chipa na 45 °C** — bezczynny M4 Pro
ma 40-55 °C, a Apple Silicon dławi się dopiero koło 100-108 °C. 45 °C to właściwa liczba dla
*baterii* i tam jest używana.

Język: domyślnie angielski. Pasek menu, powiadomienia i wszystkie narzędzia CLI mówią w **pięciu
językach** (angielski, polski, rosyjski, chiński, hiszpański) — przełączasz w menu paska
(*Ustawienia > Język*) albo przez `"lang"` w `~/.thermal-guard/config.json` / `TG_LANG`.

## Licencja

MIT. Rób z tym co chcesz. Jeśli uratuje Ci komputer, to wystarczająca zapłata.

Autor: Paweł Kwaczyński / FOCUS FRAME, 2026. Projekt rozwijany także w ramach koła naukowego
**AIrON** (SKN Informatyki AHE w Łodzi).
