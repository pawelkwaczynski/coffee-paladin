# Measurements, version 1

This document specifies what coffee-paladin measures and where it puts the numbers: the live
snapshot `status.json`, the measurement history `history.csv`, the Prometheus output of
`thermal-metrics`, and the per-machine snapshot in a shared fleet folder. It is derived from
the code of release 3.3.5 (`guard.py`, `thermal-metrics`). `tests/test_spec_20261022.py`
fails when the code writes a field, a column or a metric name that this document does not
list, and when this document lists one the code no longer writes.

Events (pauses, resumes, hard shutdowns) are specified in [events-v1.md](events-v1.md).

## Compatibility

- Within version 1, fields and metrics are only **added**. Readers must ignore fields they do
  not know.
- Removing or renaming a field, a column or a metric, or changing its type, unit or meaning,
  bumps the version: a new document (`metrics-v2.md`) and a line in the release notes.
- `history.csv` is the strict case, because it is positional: see its section.

## Conventions

- **Data directory:** `~/.coffee-paladin/`, or `$TG_BASE` when that variable is set.
- **Temperatures** are degrees Celsius. **Memory and disk** sizes in `status.json` are GiB
  (1024³ bytes) even where the field name says `gb`.
- **The chip temperature** (`chip_c`) is the hotter of the CPU and GPU averages that `macmon`
  reads from the SMC without root. It is the number the guard's thresholds act on.
- **null means "not measured"**, never zero. A Mac without a battery has `battery_c` null; a
  Mac where macOS reports no CPU speed limit has `cpu_limit` null. A reader must not turn
  null into 0 or 100: a missing reading is not proof that everything is fine.
- **`time`:** local time with its UTC offset, `%Y-%m-%d %H:%M:%S%z`, for example
  `2026-10-22 12:53:07+0200`.

## 1. status.json

The live snapshot. The daemon replaces it every cycle (`poll_seconds`, default 15 s) by
writing a temporary file and renaming it over the old one, so a reader never sees half a
file. It doubles as a heartbeat: when `time` is more than 60 seconds old, the daemon is not
running and every value in the file is a fossil. Fields marked "every ~1 min" are refreshed
every fourth cycle and repeated in between.

| Field | Type | Meaning |
|---|---|---|
| `time` | string | when the snapshot was written |
| `guard_version` | string | the version of the daemon that wrote the snapshot; absent in snapshots written by releases up to and including 3.3.5 |
| `level` | integer | the guard's verdict: `0` cool, `1` warm, `2` hot (the guard pauses heavy jobs), `3` critical (the guard terminates paused jobs once the level holds) |
| `reason` | string | why the level is what it is, for humans, translated, comma-separated; empty when calm. Do not parse it |
| `thermal_state` | string | macOS thermal state: `nominal`, `fair`, `serious`, `critical`, or `unknown` when the helper did not answer |
| `thermal_pressure` | object or null | the five-level Darwin thermal pressure notification, read without root; null when macOS gave no answer |
| `thermal_pressure.level` | integer | `0` nominal, `1` moderate, `2` heavy, `3` trapping, `4` sleeping |
| `thermal_pressure.name` | string | the same level as a word: `nominal`, `moderate`, `heavy`, `trapping`, `sleeping` |
| `chip_c` | number or null | chip temperature, °C, one decimal; null when there is no chip reading |
| `chip_stale` | boolean | `true` when `chip_c` is the last good reading reused for up to 120 s because the sensor did not answer this cycle |
| `chip_sensor` | boolean | `false` when `macmon` gave no reading this cycle and no recent one could be reused; protection then rests on the battery sensor and macOS thermal state |
| `gpu_c` | number or null | GPU temperature, °C |
| `battery_c` | number or null | battery pack temperature, °C; null on a Mac without a battery |
| `battery_pct` | integer or null | battery charge, percent; null on a Mac without a battery |
| `on_ac` | boolean | `true` on the power adapter |
| `fans` | array | rpm of every fan, integers; empty on a fanless Mac or without a reading |
| `watts` | number or null | power reported by `macmon` (`all_power`: CPU, GPU and neural engine), watts; null without `macmon` |
| `cpu_limit` | integer or null | `CPU_Speed_Limit` from `pmset -g therm`, percent, `100` = not throttled; null when macOS reports none, which is common on Apple Silicon |
| `load1` | number | one-minute load average |
| `ram_used_gb` | number or null | memory in use, GiB; null without `macmon` |
| `ram_total_gb` | number or null | memory installed, GiB; null without `macmon` |
| `swap_used_gb` | number or null | swap in use, GiB; null without `macmon` |
| `disk_used_gb` | integer or null | used space on the data volume, GiB, refreshed about every 5 minutes |
| `disk_total_gb` | integer or null | size of the data volume, GiB |
| `disk_used_pct` | integer or null | used space, percent |
| `thresholds` | object | chip temperatures the daemon enforces right now, after its sanity checks; read these, not `config.json` |
| `thresholds.pause` | number | pause at or above, °C |
| `thresholds.resume` | number | resume at or below, °C |
| `thresholds.kill` | number | terminate paused jobs at or above, °C |
| `trend_c_min` | number or null | how fast the chip temperature changes, °C per minute, over the last few minutes; null before three readings exist and without a chip reading |
| `eta_pause_min` | number or null | minutes until the pause threshold at the current trend; null unless the chip is rising faster than 0.5 °C per minute and is still below the threshold |
| `dry_run` | boolean | `true` in watch-only mode: the guard pauses nothing, however hot the machine gets |
| `manual_pause` | boolean | `true` while a human freeze from the menu bar is in effect |
| `paused` | array | names of the processes in the guard's pause list, strings: the ones paused right now, and any whose termination is under way, which may be running; `paused_details.terminating` tells them apart |
| `paused_details` | array | one object per paused process |
| `paused_details.name` | string | process name |
| `paused_details.pid` | integer | its pid |
| `paused_details.since` | number | when the pause started, Unix epoch seconds |
| `paused_details.reason` | string | `termika` (heat) or `bateria` (low battery); see events-v1.md |
| `paused_details.manual` | boolean | `true` for a human freeze |
| `paused_details.age_s` | integer | how long it has been paused, seconds |
| `paused_details.terminating` | boolean | `true` when the guard has already sent `SIGCONT` and `SIGTERM` and still owes the `SIGKILL`, because the process listing after the grace period failed; such a process may be running, and the guard sends the `SIGKILL` on its next cycle with a readable listing. Absent for an ordinary pause |
| `demoted` | array | names of the processes moved to efficiency cores right now; they run, slower |
| `unpausable` | array | names the guard tried to pause and could not. Not empty means protection is incomplete right now |
| `heavy_count` | integer | heavy processes the guard could act on, children not counted twice |
| `top_proc` | string or null | the heaviest of them; null when there is none |
| `top_cpu` | integer or null | its CPU use, percent of one core |
| `freeze_candidates` | array | exactly the processes a manual freeze would stop: objects with `pid`, `name`, `cpu` (percent of one core) |
| `gui_hot` | array | heavy desktop apps the guard deliberately does not freeze: objects with `name`, `cpu`, `protected` (boolean, `true` for protected apps such as calls, recordings and password managers, which are not slowed either) |
| `system_hot` | array | heavy macOS services the guard leaves alone: objects with `name`, `cpu` |
| `top_cpu_list` | array | up to three busiest processes on the machine: objects with `name` (at most 24 characters) and `cpu`; every ~1 min |
| `top_ram_list` | array | up to three processes with the most resident memory above 100 MiB: objects with `name` and `gb` (GiB); every ~1 min |
| `jobs` | array | jobs started through `safe-run` that are still alive; every ~1 min |
| `jobs.name` | string | job name |
| `jobs.pid` | integer | the job's pid |
| `jobs.started` | number or null | start time, Unix epoch seconds |
| `jobs.queued` | boolean | `true` while the job waits for admission |
| `jobs.cpu_limit_pct` | number or null | the job's CPU duty-cycle cap, percent |
| `jobs.cpu_limited` | boolean | `true` when that cap is below 100; such a job blinks between running and stopped on purpose, which is not a guard pause |
| `jobs.progress_age_s` | integer or null | seconds since the job last touched its progress file; null when it has none |
| `jobs.progress_interval_s` | number or null | the progress interval the job declared |
| `jobs.progress_stalled` | boolean | `true` when the job has been silent for more than three declared intervals; advisory only, the guard never acts on it |
| `jobs.minutes` | integer | run time so far, minutes |
| `keep_awake` | boolean | `true` while the guard holds the Mac awake |
| `awake_mode` | string or null | manual keep-awake mode set from the menu bar: `timer`, `forever`, `app` or `download`; null when none |
| `awake_until` | number or null | end of a `timer` keep-awake, Unix epoch seconds |
| `awake_app` | string or null | the app an `app` keep-awake waits for |
| `stats` | object | today's interventions (local date): `pauses`, `resumes`, `kills`, integers; `kills` counts terminations started (`SIGTERM` sent), once per job; every ~1 min |
| `stats_total` | object | interventions since the counters were last reset by hand: `since` (Unix epoch seconds) and the integer counters `pauses`, `resumes`, `kills`, `awake_released_hot`; a counter appears after its first event. `kills` counts terminations started (`SIGTERM` sent), once per job, whether or not a `SIGKILL` followed. Manual freezes are not counted |
| `stats_session` | object | the same counters since the daemon started |
| `chip_profile` | object or null | what temperatures this Mac reaches, from its own `history.csv`, recomputed at most hourly; null with fewer than 200 chip readings |
| `chip_profile.samples` | integer | readings the profile is built from |
| `chip_profile.max` | number | highest chip reading, °C |
| `chip_profile.p50` | number | median chip reading, °C |
| `chip_profile.p90` | number | 90th percentile, °C |
| `chip_profile.p99` | number | 99th percentile, °C |
| `chip_profile.above` | object | for every whole degree from 80 to 110 (keys are strings, `"80"` … `"110"`), the percentage of readings at or above it |
| `last_hard_shutdown` | object or null | the hard shutdown the daemon detected when it started: `time`, `description`, `readings`, `confidence`, with the same meaning as the `HARD_SHUTDOWN` event in events-v1.md; null when it has not detected one |
| `config_corrections` | array | strings, one per value the daemon corrected in memory because `config.json` held something unsafe or malformed; each names the config key first. Not empty means `config.json` is not what is running |
| `admission` | object | present only when `admission_control` is on |
| `admission.enabled` | boolean | always `true` when the object is present |
| `admission.budget_cores` | integer | cores the arbiter may hand out now: all performance cores when cool or without a chip reading, half between the resume and pause thresholds, none at or above pause or at level 2 and above; `-1` together with `error` |
| `admission.used_cores` | integer | cores declared by running registered jobs |
| `admission.foreign_load` | integer | load from unregistered work, subtracted from the budget |
| `admission.admitted` | array | pids of waiting wrappers that may start now |
| `admission.queued` | array | waiting wrappers in admission order: objects with `pid`, `name`, `cores`, `priority`, `since` |
| `admission.error` | boolean | `true` when the arbiter failed; every waiting wrapper is admitted then. Absent otherwise |
| `queued_count` | integer | number of waiting wrappers; present only together with `admission` |

## 2. history.csv

The measurement history, the evidence a report is built from. One header line, then one row
about every 5 minutes (every `300 / poll_seconds` cycles), and one row every cycle while the
level is 2 or higher. Comma-separated, no quoting: a comma inside a process name is replaced
by a space before writing.

**An empty cell means "not measured".** A chip reading that was reused from memory
(`chip_stale` in `status.json`) is not written here: those cells stay empty.

The columns, in this exact order:

| Column | Type | Meaning |
|---|---|---|
| `time` | string | when the row was written |
| `thermal_state` | string | as `thermal_state` in `status.json` |
| `chip_C` | number | chip temperature, °C, one decimal |
| `gpu_C` | number | GPU temperature, °C, one decimal |
| `battery_C` | number | battery temperature, °C, one decimal |
| `fan_rpm` | integer | the fastest fan, rpm |
| `watts` | number | as `watts` in `status.json`, one decimal |
| `battery_pct` | integer | battery charge, percent |
| `on_ac` | integer | `1` on the power adapter, `0` on battery |
| `cpu_limit` | integer | as `cpu_limit` in `status.json`; empty when macOS reports none |
| `load1` | number | one-minute load average, two decimals |
| `level` | integer | the guard's level, 0 to 3 |
| `top_proc` | string | the heaviest process the guard could act on |
| `top_cpu` | integer | its CPU use, percent of one core |

**Rotation:** like the event stream: above 5 MiB the file moves to `history.csv.1`, older
generations shift up to `.5`, the oldest is deleted. The full history, oldest first, is `.5`
to `.1`, then the current file.

**Header changes:** the daemon writes the header only into a new file. When it finds a file
whose header differs from its own, it renames that file to `history_old.csv` (replacing an
earlier one) and starts a new file. Adding a column is therefore an addition for the format,
but the current file starts over: readers that want the past read `history_old.csv` too.

## 3. thermal-metrics

`thermal-metrics` prints the snapshot in the Prometheus text exposition format: one
`# HELP` and one `# TYPE` line per metric name, then the samples. It opens no port; it prints
or writes a file atomically for a textfile collector, and exits.

**Rules that apply to every metric:**

- Every sample has the label `host`: the `fleet_label` from `config.json`, else the Mac's
  ComputerName, else its host name. With `--fleet` or `--dir`, every machine in the fleet
  folder adds its own samples under its own `host`.
- A field that is null, missing, NaN or infinite produces **no sample**, never a zero.
  Booleans become `1` and `0`.
- When the snapshot is 900 seconds old or older, only `up`, `snapshot_unreadable` and
  `snapshot_age_seconds` are printed for that host: a fossil temperature must not draw a calm
  line on a dashboard.
- When a snapshot cannot be read at all, only `up` = 0 and `snapshot_unreadable` = 1 are
  printed for that host.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `coffee_paladin_up` | gauge | host | `1` when the snapshot is younger than 300 seconds; `0` means the guard stopped writing and every other value is the last known one |
| `coffee_paladin_snapshot_unreadable` | gauge | host | `1` when the snapshot exists but cannot be read (truncated, evicted by iCloud, wrong shape) |
| `coffee_paladin_snapshot_age_seconds` | gauge | host | seconds since the snapshot was written |
| `coffee_paladin_chip_celsius` | gauge | host | `chip_c` |
| `coffee_paladin_gpu_celsius` | gauge | host | `gpu_c` |
| `coffee_paladin_battery_celsius` | gauge | host | `battery_c` |
| `coffee_paladin_battery_percent` | gauge | host | `battery_pct` |
| `coffee_paladin_chip_sensor` | gauge | host | `chip_sensor` |
| `coffee_paladin_chip_stale` | gauge | host | `chip_stale` |
| `coffee_paladin_fan_rpm` | gauge | host, fan | one sample per fan, `fan` = `0`, `1`, … |
| `coffee_paladin_power_watts` | gauge | host | `watts` |
| `coffee_paladin_on_ac` | gauge | host | `on_ac` |
| `coffee_paladin_load1` | gauge | host | `load1` |
| `coffee_paladin_cpu_limit_percent` | gauge | host | `cpu_limit`, the macOS CPU speed limit; absent when macOS reports none |
| `coffee_paladin_level` | gauge | host | `level` |
| `coffee_paladin_memory_used_bytes` | gauge | host | `ram_used_gb` × 1024³ |
| `coffee_paladin_memory_total_bytes` | gauge | host | `ram_total_gb` × 1024³ |
| `coffee_paladin_swap_used_bytes` | gauge | host | `swap_used_gb` × 1024³ |
| `coffee_paladin_disk_used_bytes` | gauge | host | `disk_used_gb` × 1024³ (whole GiB, so an approximation) |
| `coffee_paladin_disk_total_bytes` | gauge | host | `disk_total_gb` × 1024³ |
| `coffee_paladin_threshold_celsius` | gauge | host, threshold | `thresholds`, one sample each for `threshold` = `pause`, `resume`, `kill` |
| `coffee_paladin_paused_jobs` | gauge | host | number of entries in `paused` |
| `coffee_paladin_demoted_jobs` | gauge | host | number of entries in `demoted` |
| `coffee_paladin_freeze_candidates` | gauge | host | number of entries in `freeze_candidates` |
| `coffee_paladin_unpausable_jobs` | gauge | host | number of entries in `unpausable` |
| `coffee_paladin_heavy_jobs` | gauge | host | `heavy_count` |
| `coffee_paladin_keep_awake` | gauge | host | `keep_awake` |
| `coffee_paladin_manual_pause` | gauge | host | `manual_pause` |
| `coffee_paladin_dry_run` | gauge | host | `dry_run`; `1` means the machine is watched, not protected |
| `coffee_paladin_pauses_total` | counter | host | `stats_total.pauses` |
| `coffee_paladin_resumes_total` | counter | host | `stats_total.resumes` |
| `coffee_paladin_kills_total` | counter | host | `stats_total.kills`: terminations started, once per job |
| `coffee_paladin_awake_released_hot_total` | counter | host | `stats_total.awake_released_hot` |
| `coffee_paladin_chip_profile_samples` | gauge | host | `chip_profile.samples` |
| `coffee_paladin_chip_p50_celsius` | gauge | host | `chip_profile.p50` |
| `coffee_paladin_chip_p90_celsius` | gauge | host | `chip_profile.p90` |
| `coffee_paladin_chip_p99_celsius` | gauge | host | `chip_profile.p99` |
| `coffee_paladin_chip_max_celsius` | gauge | host | `chip_profile.max` |
| `coffee_paladin_build_info` | gauge | host, version | always `1`; `version` is the snapshot's `guard_version`. Printed for the local machine and for every machine in the fleet folder; no sample for a snapshot without `guard_version`, which is a local `status.json` written by a release up to and including 3.3.5 (fleet snapshots always carried it) |

The counters count since the last manual reset, not since boot; a reset shows up as a drop,
which Prometheus `rate()` treats as a counter reset.

### Added in this version

Listed here before a release ships them. Releases up to and including 3.3.5 do not print
these metrics.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `coffee_paladin_thermal_pressure_level` | gauge | host | `thermal_pressure.level`, `0` to `4`; absent when `thermal_pressure` is null |

## 4. Fleet snapshot

When `fleet_dir` is set in `config.json`, the daemon also writes `<fleet_dir>/<name>.json`
about once a minute, where `<name>` is the Mac's ComputerName (or its host name) with
characters other than letters, digits, space, `.`, `_` and `-` replaced by `_`. It holds the
same object as `status.json` plus the fields below. Other machines,
`fleet` and `thermal-metrics --fleet` read it. The file is world-readable (mode 0644) because
it is meant to be shared, and it carries the **serial number**: point `fleet_dir` only at a
folder you would show your hardware inventory to.

| Field | Type | Meaning |
|---|---|---|
| `host` | string | the machine's name in the fleet: `fleet_label` when it is set, else the same name as in the file name |
| `model` | string or null | model name and chip, from `hardware.json`; null when that file cannot be read |
| `serial` | string or null | serial number, from `hardware.json`; null when that file cannot be read |
| `guard_version` | string | the daemon's version |
| `epoch` | number | when the snapshot was written, Unix epoch seconds. Readers use it instead of the file time, which iCloud can leave unchanged on a fresh file |
| `swallowed_errors` | object | location name to count of errors the daemon caught and survived; present only when there were any |
