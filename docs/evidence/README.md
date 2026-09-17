# Field evidence

What the guard recorded on the author's own machine (one MacBook Pro with an M4 Pro,
48 GB) between 2026-08-13 and 2026-09-17. This is not a
benchmark and nobody curated it: it is the event log the daemon writes for
itself, passed through a filter and published as is, gaps included.

## Files

- `export_events.py` - the filter. It copies only the fields on its positive
  list, drops every free-text field, and keeps a process name only when it is a
  well-known binary (`ffmpeg`, `ollama`, `llama-server`, `swiftc`, ...). Every
  other job name becomes `job-001`, `job-002`, ... in order of first appearance.
  `python3 export_events.py --self-test` feeds it a record full of things that
  must not leave the machine and checks that none of them survive.
- `history_events_filtered.jsonl.gz` - the export itself, 7,619 events. Run the
  script against your own `~/.coffee-paladin/history_events.jsonl` to get the same
  shape for your machine.

Why a script and not the raw file: job names are chosen by the user, and on a
working machine they spell out clients, experiments and schedules. A reviewer who
runs the script on their own log gets better evidence than any log we could paste.

## What the export says

Counts are what the log contains, nothing is interpolated.

| Event | Count | Meaning |
|---|---|---|
| `job_start` / `job_end` | 698 / 689 | jobs launched through `safe-run`; 662.9 h of supervised wall time in total, 20 jobs stopped by their own `--hours` limit |
| `pause_start` / `pause_end` | 2,163 / 1,885 | a process subtree frozen with `SIGSTOP` and resumed with `SIGCONT`; 1,950 pauses for chip temperature, 213 for battery |
| `demote_start` / `demote_end` | 1,088 / 997 | a process moved to efficiency cores instead of being frozen (GUI apps and system services) |
| `terminate` | 53 | a paused process that never came back, so its pause entry was closed by the guard |
| `pause_entry_dropped` | 46 | a paused process that vanished while frozen (`process_gone`) |

- Median pause: 80 s. Nine in ten pauses end within 493 s. The longest is 14,361 s
  (a job frozen on a battery-only night and resumed the next morning).
- Median chip temperature at the moment a demotion starts: 92.5 °C; nine in ten
  demotions start below 99.7 °C; the highest recorded is 102.5 °C.
- The most paused processes are `ollama` and `llama-server` (613 each), then
  `ffmpeg` (360) and `Python` (261). The most launched jobs through `safe-run` are
  `ffmpeg` (63), `python3` (26), `swiftc` (18) and `rclone` (15); the rest are
  anonymised.

## The gaps, because they are the point

`pause_start` and `pause_end` do not balance: 278 pauses have no recorded end.
`terminate` and `pause_entry_dropped` explain 99 of them. The rest cluster on days
when the daemon itself was restarted or the machine went down while jobs were
frozen (for example 2026-08-26: 8 starts, 0 ends; 2026-09-04: 69 starts, 0 ends;
2026-09-13: 24 starts, 0 ends). On those days the guard's own end-of-pause line
never got written, which is exactly the situation the separate black box exists for.

One entry from that black box, verbatim in meaning: on **2026-09-08 at 11:53:05** the
daemon's last heartbeat was written and at 11:53:22 the system booted again, with no
clean-stop marker in between. The guard recorded it as `HARD_SHUTDOWN` with the last
eight readings attached. Those readings do not show a hot chip: 78.8 °C at 11:45:51,
thermal state "fair", level 1, a Python process at 99 % CPU. The guard did not
prevent that shutdown and its log does not explain it; the working hypothesis is
memory pressure, which the guard does not watch. We
publish it because a safety net that only reports its successes is not evidence.

## What this is not

Not a controlled experiment, not a comparison with anything, not a claim about
hardware lifetime. It shows that the mechanism runs for weeks on a real machine,
what it pauses, for how long, and where its own bookkeeping breaks.
