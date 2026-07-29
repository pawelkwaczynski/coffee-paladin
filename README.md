# thermal-guard

**A thermal and power safety net for Apple Silicon Macs.** It watches the chip temperature, the
battery, the fans and the power source, and it *freezes* heavy jobs before your laptop cooks
itself — instead of letting them run until the machine shuts down.

No `sudo`. No kernel extensions. No daemons running as root. Everything reads sensors that are
available to a normal user process.

*(Polska wersja poniżej — [przejdź do opisu po polsku](#po-polsku).)*

```
🌡 C67° G64° B33° 🌀3.3k 42W
```

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

### 4. It keeps evidence (the black box)

The daemon writes a heartbeat on every cycle and a marker on clean shutdown. After a restart it
compares those against `kern.boottime`. If the machine went down without warning, it records the
event **together with the last eight measurements taken before the crash**.

`thermal-report` then assembles a single file for a repair shop or warranty claim: hardware and
serial, battery health and cycle count, detected hard shutdowns with the readings that preceded
them, the system's own shutdown-cause entries, every intervention the guard made, and the full
measurement timeline with the peak temperature highlighted.

---

## Where the data comes from

This is the interesting part, because macOS does not hand out chip temperatures to unprivileged
processes.

| Signal | Source | Notes |
|---|---|---|
| **Chip / GPU temperature** | [`macmon`](https://github.com/vladkens/macmon) → **IOReport** | The one route that still works without `sudo`. |
| **Fan RPM, power draw (W)** | same | Also gives per-core frequency and RAM/swap usage. |
| **Thermal pressure** (`nominal`/`fair`/`serious`/`critical`) | `ProcessInfo.thermalState` via a tiny Swift binary | Public API, no privileges needed. |
| **Battery temperature, cycles, cell voltages** | `ioreg -c AppleSmartBattery` | `Temperature` is in hundredths of °C; `MaximumTemperature` is in whole °C — an easy bug to write. |
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

Make sure `~/.local/bin` is on your `PATH`.

---

## Usage

### `heat` — one-shot status

```
🟢 stan termiczny: nominal   chip: 53.5 °C   bateria: 30.6 °C   CPU dostępne: 100%   load: 4.29
   wentylatory: 4500 obr/min, 4831 obr/min
   zasilanie: zasilacz   pobór: 32.6 W
   thermal-guard: działa ✅
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

chip / GPU / battery / fan rpm / power draw / `⚡` when macOS is throttling / `⏸` when something is
paused. `🌀⚠︎0` means the fans are stopped while the chip is hot.

The menu adds a block-character temperature graph, a trend and forecast ("rising 2.1 °C/min —
about 4 minutes to pause"), running `safe-run` jobs, today's intervention count, a manual
**Freeze / Resume** control, and **Export report**.

The bar measures nothing itself — it reads `~/.thermal-guard/status.json`, which the daemon writes
every cycle. It therefore costs no CPU and can never disagree with the guard. Manual commands are
passed back through a file and executed by the daemon, so exactly one process ever decides what
gets paused.

### `thermal-report` — evidence for a repair shop

```bash
thermal-report --dni 14
```

Writes a single text file to your Desktop.

---

## Configuration

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
- Code comments and console output are in Polish; identifiers and this document are in English.

---

## License

MIT — do whatever you like with it. If it saves your machine, that is payment enough.

---

<a name="po-polsku"></a>

# Po polsku

**Bezpiecznik termiczny i zasilania dla Maców na Apple Silicon.** Pilnuje temperatury chipa,
baterii, wentylatorów i źródła zasilania, a gdy robi się gorąco — **zamraża** ciężkie zadania,
zamiast pozwolić im pracować aż komputer zgaśnie.

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

## Instalacja i użycie

```bash
git clone https://github.com/pawelkwaczynski/thermal-guard.git
cd thermal-guard
bash install.sh
```

- `heat` — jednym poleceniem: jak gorąco, co grzeje, czy bezpiecznik żyje
- `safe-run --hours 8 --name render -- <polecenie>` — tak uruchamiaj ciężkie zadania
- `heatbar` — pasek menu z wykresem, prognozą, ręcznym zamrażaniem i eksportem raportu
- `thermal-report --dni 14` — raport dowodowy dla serwisu

Progi w `~/.thermal-guard/config.json`. **Nie ustawiaj progu chipa na 45 °C** — bezczynny M4 Pro
ma 40-55 °C, a Apple Silicon dławi się dopiero koło 100-108 °C. 45 °C to właściwa liczba dla
*baterii* i tam jest używana.

## Licencja

MIT. Rób z tym co chcesz. Jeśli uratuje Ci komputer, to wystarczająca zapłata.
