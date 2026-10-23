# Event streams, version 1

This document specifies the two event files coffee-paladin writes. It is derived from the
code of release 3.3.5 (`guard.py`, `safe-run`), not from intentions: every event type and
field below has a call site that writes it. `tests/test_spec_20261022.py` fails when the code
writes an event type or field that this document does not list, so the two cannot drift
apart silently.

Measurements (`status.json`, `history.csv`, `thermal-metrics`) are specified separately in
[metrics-v1.md](metrics-v1.md).

| File | Written by | What it holds |
|---|---|---|
| `history_events.jsonl` | the daemon and `safe-run` | what was done to processes: pause, resume, terminate, demote, job start and end |
| `events.log` | the daemon | the black box: hard shutdowns and cooling alarms, the evidence a repair-shop report is built from |

Both live in the data directory, `~/.coffee-paladin/` (or `$TG_BASE` when that variable is
set, which is how the tests run in isolation). `guard.log` is a log for humans, translated
into the user's language, and is not covered here.

## Compatibility

- Within version 1, event types and fields are only **added**. A reader must ignore event
  types and fields it does not know.
- Removing or renaming an event type or a field, or changing its type, unit or meaning,
  bumps the version: it gets a new document (`events-v2.md`) and a line in the release notes.
- Records carry no version field. A reader that follows the first rule keeps working across
  every version 1 release.

## Conventions shared by both files

- **Format:** JSON Lines. UTF-8, one JSON object per line, non-ASCII characters written as
  they are (not `\u` escaped).
- **Broken lines:** a line can be cut short when the machine loses power in the middle of a
  write. Readers skip a line that does not parse and carry on.
- **`time`:** local time with its UTC offset, `%Y-%m-%d %H:%M:%S%z`, for example
  `2026-10-22 12:53:07+0200` (24 characters). The first 19 characters are the format used
  before 2.1.8, so a parser that reads `line[:19]` still works.
- **`epoch`:** seconds since the Unix epoch, a JSON number with a fractional part. Use it for
  ordering and arithmetic; `time` is for people.
- **Writes are best effort.** A write that fails (disk full, permissions) is dropped and the
  guard keeps protecting the machine. A missing line is possible; a line that lies is not.

## 1. history_events.jsonl

Two writers append to the same file: the daemon (`source` = `guard`) and every `safe-run`
wrapper (`source` = `safe-run`). Their lines interleave; order by `epoch`.

**Privacy by design:** no command lines, no paths, no environment. A process is identified by
its name and pid only, because a full command line can hold client names and tokens.

**Absent, never null:** an optional field without a value is left out of the line. It is
never written as `null`.

**Rotation:** before each append the writer checks the size. Above 5 MiB (5,242,880 bytes)
the file becomes `history_events.jsonl.1`, the previous `.1` becomes `.2`, and so on up to
`.5`; the old `.5` is deleted. `.1` is the newest generation. The full history, oldest first,
is `.5`, `.4`, `.3`, `.2`, `.1`, then the current file. Both writers use this same scheme.

### Common fields

Every line carries these four fields.

| Field | Type | Meaning |
|---|---|---|
| `time` | string | when the line was written, see Conventions |
| `epoch` | number | when the line was written, seconds, one decimal |
| `type` | string | the event type, one of the headings below |
| `source` | string | `guard` (the daemon) or `safe-run` (the wrapper) |

The event-specific fields use these meanings everywhere:

- `name`: a process name exactly as `ps -c` reports it (the executable name, never a path).
  For `safe-run` events it is the job name instead, see `job_start`.
- `pid`, `pgid`: integers. `pgid` is the process group the guard signals together with the
  process; it is absent when the guard did not know it.
- `reason_code`: why the guard paused. `termika` means heat (chip or battery temperature,
  macOS thermal state, CPU throttling); `bateria` means a low battery on battery power. These
  are stable identifiers, not translated text.
- `pause_s`: how long the pause lasted when the line was written, whole seconds.

### `pause_start`

Source `guard`. Written right after the guard stopped a process with `SIGSTOP` and the signal
succeeded. Not written in watch-only mode (`dry_run`) and not when the signal failed (a
process the guard is not allowed to stop is listed in `unpausable` in `status.json` instead).

| Field | Type | Meaning |
|---|---|---|
| `name` | string | the paused process |
| `pid` | integer | its pid |
| `pgid` | integer | its process group; absent when unknown |
| `reason_code` | string | `termika` or `bateria` |
| `cpu_pct` | integer | CPU use when the guard decided, percent of one core; includes the process's children when `count_children` is on (the default), so it can exceed 100 |
| `manual` | boolean | `true` when a human froze it from the menu bar; absent for the guard's own decisions |

### `pause_end`

Source `guard`. Written after the guard sent `SIGCONT` and checked that the process left the
stopped state. Every resume path writes it: after cooling, a manual resume from the menu bar,
at daemon start (restoring a pause left by a previous run) and at daemon shutdown.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | the resumed process |
| `pid` | integer | its pid |
| `pgid` | integer | present only when the paused process itself had already exited and the guard resumed what was left of its process group; `pid` is then the dead leader's pid |
| `pause_s` | integer | how long it was paused |

### `pause_entry_dropped`

Source `guard`. The guard forgot a pause entry without sending any signal.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | the process the entry was about |
| `pid` | integer | the pid in the entry |
| `reason` | string | `process_gone`: the process no longer exists, nothing left to resume. `pid_reused`: the pid now belongs to a different process, so signalling it would hit the wrong program |
| `pause_s` | integer | how long the entry existed; present for `process_gone`, absent for `pid_reused` |

### `terminate`

Source `guard`. Written when the guard ended a paused process: `SIGCONT` followed by
`SIGTERM`, at the critical level or when a pause outlasted its limit. Manual freezes are never
terminated, so they never produce this event.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | the terminated process |
| `pid` | integer | its pid |
| `pgid` | integer | its process group; absent when unknown |
| `reason_code` | string | the `reason_code` of the pause that preceded it; absent for pauses recorded by versions that did not store one |
| `pause_s` | integer | how long it had been paused |

### `demote_start`

Source `guard`. Written when the guard moved a process to background QoS (efficiency cores)
with `taskpolicy -b`, either after it stayed heavy on a hot chip or together with a pause.
The process keeps running, possibly an order of magnitude slower.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | the demoted process |
| `pid` | integer | its pid |
| `pgid` | integer | its process group; absent when unknown |
| `chip_c` | number | chip temperature at that moment, °C; absent when there was no chip reading |
| `cpu_pct` | integer | CPU use when the guard decided, percent of one core |

### `demote_end`

Source `guard`. Written when the guard returned a demoted process to normal scheduling
because the chip cooled down.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | the process |
| `pid` | integer | its pid |
| `chip_c` | number | chip temperature at that moment, °C; absent when there was no chip reading |

### `job_start`

Source `safe-run`. Written once the wrapper has started the job in its own process group and
tried to register it with the daemon.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | the job name: `--name`, or the command's file name when no name was given; reduced to its last path component, control characters removed, at most 64 characters, `?` when nothing is left |
| `pid` | integer | the job's pid |
| `pgid` | integer | the job's process group; equal to `pid`, because the job leads its own group |
| `cores` | integer | cores the job declared with `--cores`, or the default declaration when admission control is on; absent when nothing was declared |
| `cpu_limit_pct` | number | the CPU duty-cycle cap applied to the job, percent, between 10 and 100 |
| `protected` | boolean | `true` when the command is a protected app (calls, recording, passwords): it runs on all cores with `cpu_limit_pct` 100, and its `cores` still count in the admission queue and budget but are not enforced as a limit; absent for every other job |

### `job_end`

Source `safe-run`. Written when the job has exited or was ended by the wrapper. A wrapper
that is itself killed can leave a `job_start` without a matching `job_end`.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | same as in `job_start` |
| `pid` | integer | the job's pid |
| `pgid` | integer | the job's process group |
| `exit_code` | integer | the wrapper's own exit code: the job's exit status, `124` when the time budget (`--hours`) ended it, `128 + N` when it died from signal N |
| `killed_by_time` | boolean | `true` when the time budget ended the job; absent otherwise |
| `duration_s` | integer | wall-clock run time in seconds |

## 2. events.log

Written only by the daemon, only for rare and serious events. The file is **append-only and
never rotated**: it holds a handful of lines per year on a healthy machine, and it is
evidence. An empty or missing file means nothing serious was recorded.

Unlike `history_events.jsonl`, the timestamps here describe the **event**, which can be long
before the line was written: a hard shutdown is detected only when the daemon starts again
after the reboot.

### Common fields

| Field | Type | Meaning |
|---|---|---|
| `time` | string | when the event happened, see Conventions |
| `epoch` | number | when the event happened, seconds, three decimals |
| `detected_at` | string | when the line was written, same format as `time` |
| `type` | string | the event type, one of the headings below |
| `description` | string | one sentence for humans, in the user's language at the time of writing; do not parse it |
| `synthetic` | boolean | `true` for entries written by tests or a harness; absent for real events. Evidence readers (`thermal-report`) skip synthetic entries |
| `context` | object | event-specific data, listed per type below; absent when the event has none |

### `HARD_SHUTDOWN`

Written at daemon start when the previous session ended without a clean shutdown: the last
heartbeat is older than the current boot and no clean-stop marker was written between that
heartbeat and the boot. `time`
and `epoch` are the last heartbeat, the last moment the machine was seen alive. The same
shutdown (the same `epoch` within 90 seconds) is written once, however many times the daemon
restarts afterwards.

| Field | Type | Meaning |
|---|---|---|
| `context.last_readings` | array | up to 8 objects, the last `history.csv` rows before the shutdown, keyed by the `history.csv` header; every value is a string, exactly as in the file (see metrics-v1.md) |
| `context.confidence` | string | `high`, or `low` when the last heartbeat is more than 12 hours before the boot (the guard may have been stopped long before the machine went down) or more than 30 days before it (a wrong clock or restored data) |
| `context.confidence_reason` | string | why the confidence is low, for humans, translated; empty when `high` |
| `context.gap_to_boot_s` | number | seconds between the last heartbeat and the boot, one decimal |

### `COOLING_ALARM`

Written when the chip is at or above `fan_alert_temp_c` (default 70 °C) while every fan
reports 0 rpm, for at least `fan_alert_polls` consecutive readings (default 3) and at least
`fan_alert_seconds` of wall time (default 300 s). At most one line per 10 minutes.

| Field | Type | Meaning |
|---|---|---|
| `context.chip_c` | number | chip temperature, °C, one decimal |
| `context.fans` | array | rpm of every fan, integers |
| `context.held_s` | integer | how long the hot-and-stopped condition had lasted, seconds |
| `context.polls` | integer | consecutive readings that showed it |
