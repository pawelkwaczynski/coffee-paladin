# AGENTS.md

Instructions for coding agents working in this repository (coffee-paladin; the Homebrew formula is still named `thermal-guard`).

## What this is

A thermal safety net for Apple Silicon Macs: a Python daemon (`guard.py`) that pauses heavy
processes with SIGSTOP before the chip overheats, a Swift menu bar app (`heatbar.swift`),
and CLI tools (`heat`, `safe-run`, `thermal-report`, `fleet`). Userspace only: no sudo, no
kernel extensions, no root daemons — keep it that way in every change.

## Layout

- `guard.py` — the daemon; the only process that ever signals other processes
- `heat`, `safe-run`, `thermal-report`, `fleet` — Python CLIs (no file extension, executable)
- `heatbar.swift`, `thermalstate.swift` — Swift; compiled by `install.sh` with `swiftc`, no Xcode project
- `install.sh` / `uninstall.sh` — install to `~/.local/bin`, LaunchAgents `pl.pawel.coffee-paladin*`
- `skills/coffee-paladin/SKILL.md` — runtime instructions for AI agents on machines where the guard is installed (different audience than this file)
- `tests/` — plain Python, no framework
- `experiments/` — dead code kept deliberately as documentation; do not "clean it up"

## Hard rules

- **No new runtime dependencies.** Python stdlib only; the single external binary is `macmon` (installed via Homebrew). No pip packages, no Swift packages.
- **Never weaken the never-touch list** in `guard.py` (`never_patterns`, terminal-foreground and agent/MCP detection). Freezing the user's terminal or their AI agent is the worst failure mode this project has.
- **`dry_run` defaults to `true`** for fresh installs. Do not change that: the tool must earn the right to touch processes.
- **Every user-facing string is translated five ways** (EN/PL/RU/ZH/ES) — one dictionary per file. Adding a string means adding all five entries; adding a feature to the menu bar means updating the translations test.
- **Signals only from the daemon.** The menu bar and CLIs communicate through files in `~/.coffee-paladin/` (`status.json`, command files); they must never signal processes directly.
- Some inline comments and log markers are in Polish (e.g. `PAUZA`, `WZNOW`). Grep for both languages; do not mass-translate them — external log parsers match on them.

## Testing your changes

```bash
T=$(mktemp -d) && python3 tests/test_wykryj_twardy_pad.py "$T"; rm -rf "$T"   # crash detector, isolated HOME
python3 tests/test_paladin.py                                                  # CLI, menu bar, artwork, translations
ruff check --select E9,F .                                                     # must stay clean
```

Tests never touch the real `~/.coffee-paladin/` — keep that property in any test you add.
Swift has no automated tests; compile-check with `swiftc -parse heatbar.swift` and describe
manual verification in your report.

## Working on a Mac that runs the guard

If `~/.coffee-paladin/status.json` exists on your machine, the guard is live. Read
`skills/coffee-paladin/SKILL.md` and follow it: check `level` before heavy work, launch long
jobs through `safe-run`, and never `SIGCONT` a paused process or edit thresholds to push a
job through. Be careful when testing signal-handling changes: you are modifying the tool
that supervises you.
