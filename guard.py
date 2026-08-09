#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coffee-paladin - watches temperature and load on a Mac, without sudo.

Every N seconds it reads:
  * macOS thermal pressure (thermalstate: nominal/fair/serious/critical)
  * chip and GPU temperature, fan rpm and power draw (macmon -> IOReport)
  * battery temperature (ioreg AppleSmartBattery)
  * CPU throttling (pmset -g therm -> CPU_Speed_Limit)
  * load average and processes, with CPU rolled up across each process subtree (ps)

When it gets hot: SIGSTOP on heavy jobs. When it cools down: SIGCONT. In a critical state:
SIGCONT + SIGTERM so jobs can checkpoint, then SIGKILL after a grace period. The system,
Finder and interactive shells are never touched.

Measurement history: ~/.coffee-paladin/history.csv   (evidence for "what happened at 3 a.m.")
Events:              ~/.coffee-paladin/events.log    (hard shutdowns, cooling alarms)
Log:                 ~/.coffee-paladin/guard.log
State (pauses):      ~/.coffee-paladin/state.json    (restored on start -> nothing stays frozen)
Snapshot for the menu bar: ~/.coffee-paladin/status.json

Usage:
  guard.py            # the loop (this is how the LaunchAgent starts it)
  guard.py --once     # a single pass, prints the reading (for testing)

Language of messages: TG_LANG=en|pl, or "lang" in config.json. Default: en.
"""

import datetime
import json
import os
import re
import errno
import signal
import subprocess
import sys
import time

GUARD_VERSION = "2.5.0"   # bump together with heatbar VERSION, thermal-report VERSION, README

HOME = os.path.expanduser("~")
BASE = os.environ.get("TG_BASE") or os.path.join(HOME, ".coffee-paladin")
BASE = os.path.expanduser(BASE)   # TG_BASE supports isolated tests.
CFG_PATH = os.path.join(BASE, "config.json")
STATE_PATH = os.path.join(BASE, "state.json")
LOG_PATH = os.path.join(BASE, "guard.log")
HIST_PATH = os.path.join(BASE, "history.csv")
STATUS_PATH = os.path.join(BASE, "status.json")   # snapshot for the menu bar
HEARTBEAT_PATH = os.path.join(BASE, "heartbeat")  # live pulse; a hard shutdown leaves the last one
CLEAN_STOP_PATH = os.path.join(BASE, "clean_stop")
EVENTS_PATH = os.path.join(BASE, "events.log")    # black box: crashes, alarms
COMMAND_PATH = os.path.join(BASE, "command")      # menu bar commands
AWAKE_PATH = os.path.join(BASE, "awake.json")     # manual menu-bar keep-awake timer/app/download
HW_PATH = os.path.join(BASE, "hardware.json")     # detected hardware for About my Mac and calibration
MANAGED_DIR = os.path.join(BASE, "managed")   # <pid>.json files from safe-run
MAX_LOG_BYTES = 5 * 1024 * 1024
MAX_LOG_GENERATIONS = 5        # number of rotated generations kept, see rotate()

# "unknown" is not "slightly warm". It means thermalstate did not answer.
# Mapping it to 1 left Macs without a battery and without macmon, such as mini or Studio,
# stuck at level 1 forever. They never reached 2, so nothing was paused, while the menu bar
# and fleet view showed a healthy, mildly warm machine.
LEVELS = {"nominal": 0, "fair": 1, "serious": 2, "critical": 3, "unknown": 0}

DEFAULTS = {
    "poll_seconds": 15,
    # Battery temperature in C. The battery is the best no-sudo chassis sensor.
    "batt_pause_c": 40.0,       # >= this: pause heavy jobs
    "batt_resume_c": 36.0,      # <= this: resume, with hysteresis
    "batt_kill_c": 45.0,        # >= this: terminate after the grace period
    "pause_on_thermal_state": "serious",   # serious | critical
    "speed_limit_pause": 60,    # CPU_Speed_Limit below this percent means heavy throttling
    # Chip temperature (SoC) reacts within seconds; the battery reacts after minutes.
    # Read through `macmon` (IOReport, no sudo). Without macmon, these thresholds are ignored.
    # These thresholds are intentionally sharper than macOS factory throttling (~100-108 C).
    # A pause cools the chip within seconds (measured: 89 -> 60 C in 19 s), so termination
    # rarely happens in practice, and SIGSTOP does not damage the job. Do not set this to
    # 45 C: an idle M-series chip sits at 40-55 C, so that would mean a permanent pause.
    "soc_pause_c": 85.0,        # >= this: pause
    "soc_resume_c": 76.0,       # <= this: resume
    "soc_kill_c": 90.0,         # >= this: terminate, but only after kill_after_polls in a row
    # Battery gate: keep long jobs from draining the laptop to zero and dying mid-block.
    # Resume only after AC is connected.
    "batt_pct_pause": 10,       # <= this percent on battery power: pause
    "batt_pct_resume": 25,      # resume on AC or when charged above this
    # Fan control: a hot chip with stopped fans means a cooling failure.
    # Warn loudly but do not pause. A false alarm must not kill computation.
    # Emergency catch-all: the names below will always miss something (b3core, cadical...).
    # Treat any owned process above this CPU and older than this many seconds as a heavy job,
    # even when its name is unknown. never_patterns still protects it.
    # Do not pause a process that owns its terminal keyboard. That risks the SIGTTIN trap.
    "skip_foreground_tty": True,
    "manage_unknown_heavy": True,
    "unknown_cpu_percent": 50.0,
    "unknown_min_seconds": 120,
    # Waiting for AC is not a failure. A battery pause may last much longer.
    "max_pause_minutes_batt": 240,
    "fan_check": True,
    "fan_alert_temp_c": 70.0,   # above this chip temperature, fans MUST spin
    "cpu_min_percent": 20.0,    # only processes above this usage can be touched
    "max_pause_minutes": 45,    # longer than this paused: gentle termination with checkpoint time
    "fan_alert_polls": 3,       # this many consecutive "hot + 0 rpm" readings triggers alarm
    "kill_after_polls": 4,      # this many consecutive critical readings triggers SIGTERM
    # Chip thresholds have hysteresis (pause 95 / resume 87), but the second trigger,
    # system `thermalState`, is binary and has no hysteresis.
    # Measured effect, 02.08 10:46-10:48: six pause/resume pairs in 15-second cycles at
    # chip 84-85 C, ten degrees below the pause threshold. The job bounced while nothing
    # cooled. Once stopped, a process stays stopped for at least this long so the pause
    # can have an effect.
    "min_pause_seconds": 60,
    # A pause caused only by system thermal state, without crossing the chip threshold,
    # requires confirmation in the next cycle. A single `thermalState` jump to "serious"
    # can last for one reading.
    "state_confirm_polls": 2,
    "demote_after_minutes": 5,  # hot chip plus a process grinding longer than this -> E-cores
    "demote_cpu_percent": 60.0,
    # Demote only when chip >= this threshold (None = soc_resume_c + 4). Return to
    # P-cores when chip <= soc_resume_c, using a threshold pair like pause/resume.
    "demote_above_c": None,
    # System indexing daemons are untouchable for PAUSE and TERMINATE; the never list
    # remains sacred. They may be pushed to E-cores while busy on a warm machine.
    # Reason: corespotlightd held 215% CPU all night as "untouchable" (165 entries,
    # 04/05.08). By default this covers only per-user daemons; taskpolicy would reject
    # processes owned by another user anyway.
    "system_demote_patterns": ["corespotlightd", "spotlightknowledged",
                               "photoanalysisd", "mediaanalysisd"],
    "notify": True,
    "notify_min_gap_s": 300,
    # Critical-level banner: a normal notification is easy to miss (Focus, fullscreen app).
    # A modal system alert always breaks through. Use a separate gap because this is the
    # highest-severity alarm and must not spam.
    "critical_banner": True,
    "critical_banner_gap_s": 180,
    # Phone push (ntfy.sh, free, no account): set a private secret topic, install the ntfy
    # app, and subscribe to the same topic. Pauses, terminations, cooling failures, and hard
    # shutdowns arrive as push notifications. Empty means disabled.
    "ntfy_topic": "",
    # Heavy jobs (safe-run): which cores and CPU limit to use.
    # "efficiency" = E-cores only (cooler, slower), "all" = every core (faster, warmer;
    # the guard still watches temperature). The percent limit uses micro-pauses for the
    # whole process group, like cpulimit. 95 is almost full speed with some room for UI.
    "job_cores_mode": "all",   # default to all cores; temperature stays under guard control
    "job_cpu_percent": 95,
    # Network activity threshold for "keep awake while downloading" in KB/s.
    "download_kbps": 500,
    # System sounds for events. afplay works even when Focus silences notifications.
    # Different events have different sounds so they can be recognized without looking:
    # pause=low, resume=glass, terminate/crash=serious.
    "sound": False,   # default silent; users can enable it in Settings
    # Do not sleep while computing, like Caffeine/Amphetamine with a fuse. Hold wake only
    # while a heavy job is actually running and the machine is cool. On pause or heat,
    # release the assertion because sleep cools fastest. After the job ends, the Mac sleeps
    # normally. Unconditional Amphetamine is the classic way to cook a laptop in a bag, so
    # this is disabled by default and enabled deliberately in Settings.
    "keep_awake_auto": False,
    "keep_awake_display": False,   # -d: keep the display awake too, for presentations; warmer
    # Decay: after the last heavy job exits, keep the wake assertion for this many seconds.
    # Without it, the gap between queued files released sleep, so an aggressively sleeping
    # Mac could sleep in the middle of a queue. The switch counter reached 45-59 entries per
    # day. Heat has priority: at level >=2 the assertion drops immediately, with no decay.
    "keep_awake_hold_s": 300,
    # Admission control: safe-run jobs declare cores (--cores) and the guard admits or
    # queues them against a thermal core budget. Off by default: without the flag every
    # start behaves exactly as before. The arbiter only DELAYS starts; it never pauses or
    # kills anything - that stays with the thermal core of the guard.
    "admission_control": False,
    # Watch-only by default. A fresh install measures, logs, and alerts, but does not pause
    # anyone's processes. Protection is enabled deliberately, either from the menu bar or
    # with "dry_run": false. A tool that touches other people's work on first launch loses
    # trust on its first false alarm; one that first shows what it would do can earn it.
    "dry_run": True,
    # Custom name for this Mac in fleet tables and menu. Empty means system name.
    # With 5 machines, "MacBook Pro (3)" says nothing; "render-01" or "Neo" says enough.
    "fleet_label": "",
    # Fleet: shared-folder path (iCloud/Dropbox/SMB/SharePoint). When set, guard publishes
    # a <hostname>.json snapshot there, and `fleet` builds a table from those files.
    # This is deliberately a folder, not a server: every company already has a shared drive.
    "fleet_dir": "",
    # What may be paused, matched by process name case-insensitively.
    "managed_patterns": [
        "ffmpeg", "ffprobe", "handbrake", "x265", "x264", "compressor",
        "python", "python3", "uv", "julia", "z3", "geng", "nauty", "lean", "lake",
        "ollama", "llama", "mlx", "whisper", "node", "java", "rustc", "cargo",
        "blender", "rclone", "7z", "zstd", "xz", "tar", "bsdtar", "make", "cc1plus", "clang",
    ],
    # User patterns appended to never_patterns. Add tools you do not want frozen, such as
    # long-running CLIs, local daemons, or editors.
    "never_extra": [],
    # Same idea, but matched against the full command line instead of process name.
    # Useful when a heavy job runs through an interpreter (python, node) and the process
    # name says nothing. This protects AI-agent and editor backends, such as node with
    # claude/mcp/language-server in argv, not every node process. Plain `node build.js`
    # must remain pausable; that is exactly the case this tool exists for.
    "never_arg_patterns": ["coffee-paladin", "guard.py", "safe-run",
                           "claude", "codex", "cursor", "mcp", "language-server", ".vscode"],
    # What must never be touched. This overrides everything above.
    "never_patterns": [
        "kernel_task", "windowserver", "launchd", "loginwindow", "logd", "opendirectoryd",
        "backupd", "mds", "mdworker", "spotlight", "fileproviderd", "cloudd", "bird",
        "finder", "dock", "terminal", "ghostty", "iterm", "zsh", "bash", "sshd", "ssh",
        "guard.py", "coffee-paladin", "safe-run", "code helper", "electron",
        # System daemons can burn a core for a long time, but they reject SIGSTOP or break
        # after freezing. Trying them only pollutes the log and blocks real targets.
        "duetexpertd", "suggestd", "photoanalysisd", "mediaanalysisd", "coreaudiod",
        "bluetoothd", "powerd", "syspolicyd", "xprotect", "trustd", "nsurlsessiond",
        # Interactive tools and their backends: SIGSTOP on a terminal session detaches its
        # terminal, and SIGCONT resumes it in the background -> SIGTTIN -> the process hangs
        # forever even though the log says "RESUMED". Freezing such a session kills it.
        # By name, include only things that are never compute jobs. node/npm/npx/bun/deno
        # are deliberately absent: a heavy Node build must be pausable. Agent backends are
        # protected by never_arg_patterns (command line) plus skip_foreground_tty (keyboard).
        "claude", "codex", "cursor",
        "hermes", "hermes-secret", "mcp", "caffeinate", "tmux", "screen", "vim", "nvim",
    ],
}


# ---------------------------------------------------------------- tools

# Config keys whose changes MUST leave a log trail. In one overnight run, thresholds changed
# twice and it was impossible to tell who changed them or when.
LOGGED_KEYS = (
    "soc_pause_c", "soc_resume_c", "soc_kill_c",
    "batt_pause_c", "batt_resume_c", "batt_kill_c",
    "demote_after_minutes", "demote_above_c", "demote_cpu_percent",
    "max_pause_minutes", "max_pause_minutes_batt", "cpu_min_percent",
    "job_cores_mode", "job_cpu_percent", "dry_run", "lang",
    "keep_awake_hold_s", "system_demote_patterns", "admission_control",
)


def logged_keys_snapshot(cfg):
    return {k: cfg.get(k) for k in LOGGED_KEYS}


def log_config_changes(previous, cfg):
    """Log each observed config-key change and return the new snapshot."""
    current = logged_keys_snapshot(cfg)
    if previous is not None:
        for k in LOGGED_KEYS:
            if previous.get(k) != current.get(k):
                log("CONFIG CHANGED %s: %r -> %r" % (k, previous.get(k), current.get(k)))
    return current


class config_lock:
    """Lock config read-modify-write operations with flock.

    The lock uses a separate .lock file, not config.json. Config writes are atomic
    os.replace operations, so locking its descriptor would point at the old inode.
    The Swift menu bar takes the same lock before writing.
    """

    def __enter__(self):
        import fcntl
        self._f = open(os.path.join(BASE, "config.lock"), "w")
        fcntl.flock(self._f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        import fcntl
        try:
            fcntl.flock(self._f, fcntl.LOCK_UN)
        finally:
            self._f.close()
        return False


def now():
    return time.time()


def ts(t=None):
    """Return an evidence timestamp with a timezone offset.

    Up to 2.1.7 this was bare `%Y-%m-%d %H:%M:%S`, a local time without saying
    which local time. events.log filters by absolute `epoch`, while history and
    guard.log filter by timestamp text, so the same data directory could produce
    two contradictory reports across time zones.

    The format is 24 characters, and the first 19 match the old timestamp exactly.
    Existing parsers that use `line[:19]` keep working; new ones can use `line[:24]`
    and compute absolute time.
    """
    return time.strftime("%Y-%m-%d %H:%M:%S%z", time.localtime(t if t else now()))


def abs_epoch(s):
    """Parse an absolute epoch from a `ts()` timestamp.

    Accepts timestamps with offsets and legacy pre-2.1.8 timestamps without offsets.
    Offset timestamps produce the same epoch in every timezone. Legacy no-offset
    timestamps are interpreted as local time, preserving the old behavior and the
    exact ambiguity the offset was added to remove. Returns 0.0 for junk and never
    raises.
    """
    # Evidence-file parsing must never raise: one junk row must not break the whole
    # document. A narrower except once lost tolerance for non-strings; fuzzing caught
    # AttributeError for input 123 and TypeError for b"...".
    if not isinstance(s, str):
        return 0.0
    s = s.strip()
    if len(s) < 19:
        return 0.0
    try:
        if len(s) >= 24 and s[19] in "+-":
            return datetime.datetime.strptime(s[:24], "%Y-%m-%d %H:%M:%S%z").timestamp()
        return time.mktime(time.strptime(s[:19], "%Y-%m-%d %H:%M:%S"))
    except Exception:      # noqa: BLE001 - contract: never raises
        return 0.0


def ensure_dirs():
    """Create owner-only data directories.

    On a multi-account Mac, 0755 meant any local user could read `config.json`,
    including `ntfy_topic`, which is the only secret protecting notification
    channels. Anyone who knows it can read alerts and send fake ones. `managed/`
    also contains full job command lines.
    """
    for d in (BASE, MANAGED_DIR):
        if not os.path.isdir(d):
            try:
                os.makedirs(d, 0o700)
            except OSError as e:
                # Without this, the daemon crashed with a traceback in the first line of
                # main(), and launchd restarted it every 30 s forever. The traceback went
                # to stderr.log, a file in the directory that could not be written, so the
                # user saw no diagnostics at all.
                print("coffee-paladin: nie moge utworzyc %s (%s)" % (d, e), file=sys.stderr)
    # Existing installs: tighten permissions at every start. Cheap and idempotent.
    for path, permissions in ((BASE, 0o700), (MANAGED_DIR, 0o700), (CFG_PATH, 0o600)):
        try:
            if os.path.exists(path) and (os.stat(path).st_mode & 0o077):
                os.chmod(path, permissions)
        except OSError:
            pass


# Names this tool can call itself. They must always be on the never-touch list, even if the
# config was saved before a rename. Otherwise a second instance, or an instance from another
# directory, sees the daemon as an ordinary CPU-hungry "Python" process and pauses it.
OWN_NAMES = ("coffee-paladin", "guard.py", "safe-run")

# Config keys that had the wrong type and were replaced with defaults, for logging.
_zle_typy = []
_ostatnio_odrzucone = {"v": None}


def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH) as f:
            user = json.load(f)
        if isinstance(user, dict):
            cfg.update(user)
    except Exception:
        pass
    # Config values take the DEFAULT type, not the type the human wrote.
    # Without this, one typo ("cpu_min_percent": "dwadziescia") crashes the loop
    # every cycle: status.json stops being written, nothing is paused, and `heat`
    # still reports that the daemon is running. The guard is alive but blind.
    for key, default in DEFAULTS.items():
        value = cfg.get(key)
        if isinstance(default, bool):
            if not isinstance(value, bool):
                cfg[key] = default
                _zle_typy.append(key)
        elif isinstance(default, (int, float)):
            # bool is a Python int subclass, so `poll_seconds: true` would pass as
            # 1 second, making a hot-chip daemon poll 15x more often.
            if isinstance(value, bool):
                cfg[key] = default
                _zle_typy.append(key)
            else:
                try:
                    # Catch OverflowError because 1e400 and 400-digit ints crashed the
                    # whole function. load_cfg runs in main() without a wrapper, so the
                    # daemon never started. NaN and infinity made every comparison false,
                    # so threshold "nan" turned pick_targets into a trap for every process
                    # above zero percent CPU, without one log line.
                    converted = type(default)(value)
                    if isinstance(converted, float) and (converted != converted or converted in (float("inf"), float("-inf"))):
                        raise ValueError("NaN albo nieskonczonosc")
                    cfg[key] = converted
                except (TypeError, ValueError, OverflowError):
                    cfg[key] = default
                    _zle_typy.append(key)
        elif isinstance(default, list) and not isinstance(value, list):
            cfg[key] = list(default)
            _zle_typy.append(key)
        elif isinstance(default, str) and not isinstance(value, str):
            cfg[key] = default
            _zle_typy.append(key)

    # Thresholds MUST increase: resume < pause < terminate. Without that, one typo turns
    # the guard into a churner (resume >= pause: pause and resume every cycle) or a job
    # killer (kill <= pause: SIGTERM at a completely healthy 82 C).
    threshold_pairs = (("soc_resume_c", "soc_pause_c"), ("soc_pause_c", "soc_kill_c"),
                   ("batt_resume_c", "batt_pause_c"), ("batt_pause_c", "batt_kill_c"))
    # Correction MUST repeat: lowering soc_pause_c in the second pair can break the
    # relation fixed in the first. Three passes are enough for four pairs.
    for _ in range(3):
        changed_any = False
        for lower, upper in threshold_pairs:
            try:
                n, w = float(cfg[lower]), float(cfg[upper])
            except (KeyError, TypeError, ValueError):
                continue
            if n >= w:
                cfg[lower] = w - 2.0
                _zle_typy.append("%s (>= %s, obnizone do %.1f)" % (lower, upper, cfg[lower]))
                changed_any = True
        if not changed_any:
            break
    # After correction, a threshold can land outside physical sense, for example
    # soc_kill_c: 0 intended to "disable termination" can drag pause to -2 C. Then the
    # whole threshold family returns to defaults: known 85/76/90 beats custom nonsense.
    for family, bounds in ((("soc_resume_c", "soc_pause_c", "soc_kill_c"), (40.0, 110.0)),
                            (("batt_resume_c", "batt_pause_c", "batt_kill_c"), (20.0, 60.0))):
        if any(k in cfg and not (bounds[0] <= float(cfg[k]) <= bounds[1]) for k in family
               if isinstance(cfg.get(k), (int, float))):
            for k in family:
                if k in DEFAULTS:
                    cfg[k] = DEFAULTS[k]
            _zle_typy.append("progi %s poza zakresem %.0f-%.0f - przywrocone domyslne"
                             % (family[0].split("_")[0], bounds[0], bounds[1]))

    # Temperature thresholds had ranges, but counters and intervals had none. Those can do
    # the most damage because they do not look dangerous:
    #   poll_seconds: 0        -> loop with no sleep, one core pegged on the Mac this
    #                             program is supposed to protect from heat
    #   max_pause_minutes: -1  -> every pause immediately exceeds the limit, so a freshly
    #                             stopped job gets SIGTERM in the same second
    #   kill_after_polls: 0    -> terminate on the first critical reading, with no grace
    # Instead of rejecting the whole config, clamp one value to a sane bound and log it.
    for key, lower_bound, upper_bound in (("poll_seconds", 1, 300),
                                ("min_pause_seconds", 0, 3600),
                                ("fan_alert_polls", 1, 100),
                                ("state_confirm_polls", 1, 100),
                                ("max_pause_minutes", 1, 10080),
                                ("max_pause_minutes_batt", 1, 10080),
                                ("kill_after_polls", 1, 100),
                                ("job_cpu_percent", 5, 100),
                                ("batt_pct_pause", 0, 100),
                                ("batt_pct_resume", 0, 100),
                                ("keep_awake_hold_s", 0, 86400)):
        v = cfg.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if v < lower_bound or v > upper_bound:
                cfg[key] = type(DEFAULTS[key])(min(max(v, lower_bound), upper_bound)) \
                             if key in DEFAULTS else min(max(v, lower_bound), upper_bound)
                _zle_typy.append("%s = %s poza zakresem %s-%s - przyciete do %s"
                                 % (key, v, lower_bound, upper_bound, cfg[key]))

    # A minimum pause longer than the pause limit is a killing machine: resume can never
    # happen, and every pause ends in SIGTERM. Clamp it and say so.
    _limit_s = cfg.get("max_pause_minutes", 45) * 60
    if isinstance(cfg.get("min_pause_seconds"), (int, float)) and cfg["min_pause_seconds"] >= _limit_s:
        cfg["min_pause_seconds"] = max(0, int(_limit_s / 3))
        _zle_typy.append("min_pause_seconds >= max_pause_minutes - przyciete do %d s"
                         % cfg["min_pause_seconds"])

    # Never-touch lists are extended with our own names, never overwritten by them.
    # Users may add their patterns, but cannot accidentally expose the daemon. Empty
    # strings are dropped: "" matches EVERY process name, so one empty list item blinds
    # the guard without signaling it. The rejected-values list is logged and cleared on
    # every load. It used to grow forever (load_cfg runs every loop cycle, ~5760 entries
    # per day), while the user got no signal that their threshold was silently changed.
    if _zle_typy:
        rejected = sorted(set(_zle_typy))
        del _zle_typy[:]
        if rejected != _ostatnio_odrzucone["v"]:
            _ostatnio_odrzucone["v"] = rejected
            log("CONFIG: odrzucone albo poprawione wartosci: %s" % ", ".join(rejected))
            # The clamp fixes values IN MEMORY while the file stays as it was. That is a
            # trap: a second session, human or AI agent, reads config.json and sees
            # something different from what the daemon enforces. A queue session set
            # soc_pause_c=100 while guard ran on clamped 98 and the file still said 100.
            # We deliberately do not overwrite the file behind the human's back. Instead,
            # say exactly what to fix.
            notify(cfg, "coffee-paladin: config corrected in memory",
                   "config.json still holds the old values. Fix: %s" % "; ".join(rejected),
                   key="cfgclamp")
    else:
        # Corrections disappeared because the file was fixed; status must not warn forever.
        _ostatnio_odrzucone["v"] = []
    for key in ("never_patterns", "never_arg_patterns", "never_extra",
                  "managed_patterns", "system_demote_patterns"):
        items = [w for w in (cfg.get(key) or []) if isinstance(w, str) and w.strip()]
        if key in ("never_patterns", "never_arg_patterns"):
            for name in OWN_NAMES:
                if name not in items:
                    items.append(name)
        cfg[key] = items
    return cfg


# ---------------------------------------------------------------- language

SUPPORTED_LANGS = ("en", "pl", "ru", "zh", "es")


def _lang():
    """Return the message language from TG_LANG, then config.json, defaulting to English."""
    v = (os.environ.get("TG_LANG") or "").lower()[:2]
    if v in SUPPORTED_LANGS:
        return v
    try:
        with open(CFG_PATH) as f:
            v = (json.load(f).get("lang") or "").lower()[:2]
        if v in SUPPORTED_LANGS:
            return v
    except Exception:
        pass
    return "en"


LANG = _lang()

# Translation catalog. Keys are the English originals from code, so a missing entry simply
# displays English instead of becoming an error.
PL = {
    "PAUSED %s (pid %d, %.0f%% CPU) - %s": "PAUZA  %s (pid %d, %.0f%% CPU) - %s",
    "[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s": "[DRY-RUN] pauza %s (pid %d, %.0f%% CPU) - %s",
    "FAILED to pause %s (pid %d) - not permitted to send the signal": "NIE UDALO SIE wstrzymac %s (pid %d) - brak uprawnien do sygnalu",
    "RESUMED %s (pid %d) - %s": "WZNOWIONE %s (pid %d) - %s",
    "dropping stale pause entry: %s (pid %s) is running again "
    "- resumed outside the guard":
        "kasuje nieaktualny wpis pauzy: %s (pid %s) znowu pracuje "
        "- wznowiony poza bezpiecznikiem",
    "[DRY-RUN] would terminate %s (pid %d) - %s": "[DRY-RUN] ubicie %s (pid %d) - %s",
    "TERMINATED (SIGTERM) %s (pid %d) - %s": "STOP (SIGTERM) %s (pid %d) - %s",
    "SIGKILL %s (pid %d)": "SIGKILL %s (pid %d)",
    "[DRY-RUN] would demote %s (pid %d)": "[DRY-RUN] demote %s (pid %d)",
    "DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)":
        "DEMOTE %s (pid %d) -> tlo/E-cores (goraco i mieli >%d min)",
    "PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)":
        "PROMOTE %s (pid %d) -> z powrotem na rdzenie P (maszyna ostygla)",
    "Thermal guard: hot": "Thermal guard: goraco",
    "unknown argument: %s": "nieznany argument: %s",
    "usage: coffee-paladin [--once | status | --version]   (no arguments = run the daemon)":
        "uzycie: coffee-paladin [--once | status | --version]   (bez argumentow = uruchom demona)",
    "Thermal guard: job slowed down": "Thermal guard: zadanie zwolnione",
    "%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools":
        "%s zepchniete na rdzenie E (nawet kilka razy wolniej) - wroci na pelna predkosc, gdy maszyna ostygnie",
    "Thermal guard: full speed again": "Thermal guard: znow pelna predkosc",
    "%s is back on P-cores": "%s wrocil na rdzenie P",
    "Thermal guard (watch-only): hot": "Thermal guard (obserwacja): goraco",
    "Would pause %s - %s. Protection is off.":
        "Wstrzymalbym %s - %s. Ochrona jest wylaczona.",
    "Paused: %s (%s)": "Wstrzymano: %s (%s)",
    "Thermal guard: cooled down": "Thermal guard: ochlodzone",
    "Resumed paused jobs (%s)": "Wznowiono wstrzymane zadania (%s)",
    "Thermal guard: STOPPED": "Thermal guard: ZATRZYMANE",
    "Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.":
        "Ubito zadania (%s). Wznow z checkpointu, gdy Mac ostygnie.",
    "!!! HARD SHUTDOWN DETECTED - ": "!!! WYKRYTO TWARDY PAD - ",
    "Mac shut down without warning": "Mac zgasl bez ostrzezenia",
    "Evidence from the moment of the crash was saved - menu bar > Export report":
        "Zapisalem dowody z chwili padu - menu paska > Eksportuj raport",
    "manual freeze: there was nothing to freeze": "reczne zamrozenie: nie bylo czego zamrozic",
    "Nothing to freeze": "Nie ma czego zamrozic",
    "No heavy job meets the conditions": "Zadne ciezkie zadanie nie spelnia warunkow",
    "COOLING FAILURE? chip %.1f C while both fans report 0 rpm":
        "AWARIA CHLODZENIA? chip %.1f C, a oba wentylatory 0 obr/min",
    "Fans stopped while the chip is hot": "Wentylatory stoja przy goracym chipie",
    "PAUSE >%d min - terminating job %s (pid %s)": "PAUZA >%d min - koncze zadanie %s (pid %s)",
    "paused for longer than %d min": "pauza dluzsza niz %d min",
    "LOOP ERROR: %r": "BLAD petli: %r",
    "MANUAL FREEZE (from the menu bar)": "ZAMROZENIE RECZNE (z paska menu)",
    "manual resume (from the menu bar)": "wznowienie reczne (z paska menu)",
    "conditions are back to normal": "warunki wrocily do normy",
    "guard startup - nothing is left frozen": "start guarda - nic nie zostaje zamrozone",
    "guard is shutting down": "guard konczy prace",
    "CRITICAL: ": "KRYTYCZNIE: ",
    "chip %.1f C": "chip %.1f C",
    "battery %.1f C": "bateria %.1f C",
    "thermal state=%s": "stan termiczny=%s",
    "thermal state=critical": "stan termiczny=critical",
    "thermal state=fair": "stan termiczny=fair",
    "CPU throttled to %d%%": "CPU dlawione do %d%%",
    "battery %d%% on battery power": "bateria %d%% bez zasilacza",
    "nothing to freeze": "nie ma czego zamrazac",
    "Mac went down without a clean shutdown. Guard's last heartbeat: %s, system booted: %s.":
        "Mac zgasl bez czystego zamkniecia. Ostatni puls guarda: %s, system wstal: %s.",
    "yes": "tak",
    "NO (macmon missing - running on battery temperature only)":
        "NIE (brak macmon - lecimy na samej baterii)",
    "coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s)"
    " | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery":
        "coffee-paladin start | chip: pauza>=%.0fC wznow<=%.0fC ubicie>=%.0fC (czujnik: %s)"
        " | bateria: pauza>=%.0fC ubicie>=%.0fC | stan>=%s | bramka baterii: <=%d%% bez zasilacza",
    "state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)":
        "stan=%s chip=%s bateria=%s wentylatory=%s zasilanie=%s CPU_limit=%d%% load1=%.2f poziom=%d (%s)",
    "  candidate: %-20s pid=%-7d %.0f%% CPU": "  kandydat: %-20s pid=%-7d %.0f%% CPU",
    "AC": "AC",
    "battery %s%%": "bateria %s%%",
    "calm": "spokoj",
    "gone before pause: %s (pid %d)": "zniknal przed pauza: %s (pid %d)",
    "FAILED to pause %s (pid %d) - errno %d, giving up on this pid":
        "NIE UDALO SIE wstrzymac %s (pid %d) - errno %d, rezygnuje z tego pid",
    "STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, type 'fg' in its window":
        "NADAL WSTRZYMANY po SIGCONT: %s (pid %d) - zadanie pierwszoplanowe terminala, wpisz 'fg' w jego oknie",
    "Thermal guard: job needs your hand": "Thermal guard: zadanie wymaga Twojej reki",
    "%s cannot resume by itself - switch to its terminal and type 'fg'.":
        "%s nie wznowi sie samo - przejdz do jego terminala i wpisz 'fg'.",
    "Thermal guard: PROTECTION INCOMPLETE": "Thermal guard: OCHRONA NIEPELNA",
    "No chip temperature sensor (macmon missing). Only battery temperature is watched, and it reacts minutes late. Fix: brew install macmon": "Brak czujnika temperatury chipa (nie ma macmona). Pilnowana jest tylko bateria, a ona reaguje z kilkuminutowym opoznieniem. Naprawa: brew install macmon",
    "Could not pause: %s (%s). The Mac stays hot - intervene manually.":
        "Nie udalo sie wstrzymac: %s (%s). Mac zostaje goracy - zareaguj recznie.",
    "Thermal guard: CRITICAL overheating": "Thermal guard: KRYTYCZNE przegrzanie",
    "The Mac is critically hot (%s). Heavy jobs are being stopped.":
        "Mac jest krytycznie gorący (%s). Ciężkie zadania są zatrzymywane.",
    "The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.":
        "Mac jest krytycznie gorący (%s). Tryb obserwacji - nic nie jest zatrzymywane.",
    "coffee-paladin: watch-only mode": "coffee-paladin: tryb obserwacji",
    "Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click).":
        "Tylko mierzę i alarmuję - nic nie jest wstrzymywane. Włącz ochronę w menu paska (jeden klik).",
    "another coffee-paladin daemon is already running - this one exits": "inny demon coffee-paladin juz dziala - ten sie wylacza",
    "CONFIDENCE: LOW - %s.":
        "WIARYGODNOSC: NISKA - %s.",
    "the last heartbeat is %d days before boot - the clock was most likely wrong (dead RTC, NTP jump) or the data came from a backup":
        "ostatni puls jest %d dni przed startem systemu - zegar byl najpewniej zly (rozladowany RTC, skok NTP) albo dane pochodza z kopii zapasowej",
    "%.1f h passed between the last heartbeat and boot - the guard may have been killed long before the Mac actually went down":
        "miedzy ostatnim pulsem a startem systemu uplynelo %.1f h - bezpiecznik mogl zostac ubity dlugo przed tym, jak Mac naprawde zgasl",
}

# Notifications and alerts for the remaining menu-bar languages (ru/zh/es). Translate what
# the human sees, such as notifications, banners, and reasons. Technical logs stay in
# English/Polish.
RU = {
    "Thermal guard: hot": "Thermal guard: горячо",
    "Thermal guard: job slowed down": "Thermal guard: задача замедлена",
    "%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools":
        "%s переведён на E-ядра (в несколько раз медленнее) - вернётся на полную скорость, когда машина остынет",
    "Thermal guard: full speed again": "Thermal guard: снова полная скорость",
    "%s is back on P-cores": "%s снова на P-ядрах",
    "Thermal guard (watch-only): hot": "Thermal guard (наблюдение): горячо",
    "Would pause %s - %s. Protection is off.":
        "Приостановил бы %s - %s. Защита выключена.",
    "Paused: %s (%s)": "Приостановлено: %s (%s)",
    "Thermal guard: cooled down": "Thermal guard: остыло",
    "Resumed paused jobs (%s)": "Возобновлены приостановленные задачи (%s)",
    "Thermal guard: STOPPED": "Thermal guard: ОСТАНОВЛЕНО",
    "Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.":
        "Задачи завершены (%s). Возобновите с контрольной точки, когда Mac остынет.",
    "Mac shut down without warning": "Mac выключился без предупреждения",
    "Evidence from the moment of the crash was saved - menu bar > Export report":
        "Данные с момента сбоя сохранены - строка меню > Экспорт отчёта",
    "Nothing to freeze": "Нечего приостанавливать",
    "No heavy job meets the conditions": "Ни одна тяжёлая задача не подходит под условия",
    "Fans stopped while the chip is hot": "Вентиляторы стоят при горячем чипе",
    "COOLING FAILURE? chip %.1f C while both fans report 0 rpm":
        "ОТКАЗ ОХЛАЖДЕНИЯ? чип %.1f C, а оба вентилятора 0 об/мин",
    "chip %.1f C": "чип %.1f C",
    "battery %.1f C": "батарея %.1f C",
    "thermal state=%s": "термосостояние=%s",
    "thermal state=critical": "термосостояние=critical",
    "thermal state=fair": "термосостояние=fair",
    "CPU throttled to %d%%": "CPU ограничен до %d%%",
    "battery %d%% on battery power": "батарея %d%% без адаптера",
    "CRITICAL: ": "КРИТИЧНО: ",
    "MANUAL FREEZE (from the menu bar)": "РУЧНАЯ ПАУЗА (из строки меню)",
    "manual resume (from the menu bar)": "ручное возобновление (из строки меню)",
    "conditions are back to normal": "условия вернулись в норму",
    "paused for longer than %d min": "в паузе дольше %d мин",
    "Thermal guard: CRITICAL overheating": "Thermal guard: КРИТИЧЕСКИЙ перегрев",
    "The Mac is critically hot (%s). Heavy jobs are being stopped.":
        "Mac критически горячий (%s). Тяжёлые задачи останавливаются.",
    "The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.":
        "Mac критически горячий (%s). Режим наблюдения - ничего не останавливается.",
    "coffee-paladin: watch-only mode": "coffee-paladin: режим наблюдения",
    "Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click).":
        "Только измеряю и предупреждаю - ничего не приостанавливается. Включите защиту в меню (один клик).",
    "another coffee-paladin daemon is already running - this one exits": "другой демон coffee-paladin уже работает - этот завершается",
    "PAUSED %s (pid %d, %.0f%% CPU) - %s": "ПАУЗА  %s (pid %d, %.0f%% CPU) - %s",
    "[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s": "[НАБЛЮДЕНИЕ] поставил бы на паузу %s (pid %d, %.0f%% CPU) - %s",
    "FAILED to pause %s (pid %d) - not permitted to send the signal": "НЕ УДАЛОСЬ поставить на паузу %s (pid %d) - нет прав на отправку сигнала",
    "RESUMED %s (pid %d) - %s": "ВОЗОБНОВЛЕНО %s (pid %d) - %s",
    "dropping stale pause entry: %s (pid %s) is running again "
    "- resumed outside the guard":
        "удаляю устаревшую запись о паузе: %s (pid %s) снова работает "
        "- возобновлён не защитой",
    "[DRY-RUN] would terminate %s (pid %d) - %s": "[НАБЛЮДЕНИЕ] завершил бы %s (pid %d) - %s",
    "TERMINATED (SIGTERM) %s (pid %d) - %s": "ЗАВЕРШЕНО (SIGTERM) %s (pid %d) - %s",
    "SIGKILL %s (pid %d)": "SIGKILL %s (pid %d)",
    "[DRY-RUN] would demote %s (pid %d)": "[НАБЛЮДЕНИЕ] понизил бы %s (pid %d)",
    "DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)": "ПОНИЖЕНО %s (pid %d) -> фоновый QoS/E-ядра (жарко дольше %d мин)",
    "PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)": "ПОВЫШЕНО %s (pid %d) -> обратно на P-ядра (машина остыла)",
    "unknown argument: %s": "неизвестный аргумент: %s",
    "usage: coffee-paladin [--once | status | --version]   (no arguments = run the daemon)": "использование: coffee-paladin [--once | status | --version]   (без аргументов = запуск демона)",
    "!!! HARD SHUTDOWN DETECTED - ": "!!! ОБНАРУЖЕНО ЖЁСТКОЕ ОТКЛЮЧЕНИЕ - ",
    "manual freeze: there was nothing to freeze": "ручная заморозка: замораживать было нечего",
    "PAUSE >%d min - terminating job %s (pid %s)": "ПАУЗА >%d мин - завершаю задачу %s (pid %s)",
    "LOOP ERROR: %r": "ОШИБКА ЦИКЛА: %r",
    "guard startup - nothing is left frozen": "запуск стража - ничего не осталось замороженным",
    "guard is shutting down": "страж завершает работу",
    "nothing to freeze": "нечего замораживать",
    "Mac went down without a clean shutdown. Guard's last heartbeat: %s, system booted: %s.": "Mac выключился без штатного завершения. Последний сигнал стража: %s, система загружена: %s.",
    "yes": "да",
    "NO (macmon missing - running on battery temperature only)": "НЕТ (нет macmon - работаем только по температуре батареи)",
    "coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s) | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery": "coffee-paladin старт | чип: пауза>=%.0fC возобновление<=%.0fC завершение>=%.0fC (датчик: %s) | батарея: пауза>=%.0fC завершение>=%.0fC | состояние>=%s | порог батареи: <=%d%% без зарядки",
    "state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)": "состояние=%s чип=%s батарея=%s вентиляторы=%s питание=%s лимит_CPU=%d%% load1=%.2f уровень=%d (%s)",
    "  candidate: %-20s pid=%-7d %.0f%% CPU": "  кандидат: %-20s pid=%-7d %.0f%% CPU",
    "AC": "сеть",
    "battery %s%%": "батарея %s%%",
    "calm": "спокойно",
    "gone before pause: %s (pid %d)": "исчез до паузы: %s (pid %d)",
    "FAILED to pause %s (pid %d) - errno %d, giving up on this pid": "НЕ УДАЛОСЬ поставить на паузу %s (pid %d) - errno %d, оставляю этот pid",
    "STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, type 'fg' in its window": "ВСЁ ЕЩЁ ОСТАНОВЛЕН после SIGCONT: %s (pid %d) - задача переднего плана, наберите 'fg' в её окне",
    "Thermal guard: job needs your hand": "Тепловой страж: задача требует вашего вмешательства",
    "%s cannot resume by itself - switch to its terminal and type 'fg'.": "%s не может продолжить сам - перейдите в его терминал и наберите 'fg'.",
    "Thermal guard: PROTECTION INCOMPLETE": "Тепловой страж: ЗАЩИТА НЕПОЛНАЯ",
    "No chip temperature sensor (macmon missing). Only battery temperature is watched, and it reacts minutes late. Fix: brew install macmon": "Нет датчика температуры чипа (отсутствует macmon). Отслеживается только батарея, а она реагирует с задержкой в несколько минут. Решение: brew install macmon",
    "Could not pause: %s (%s). The Mac stays hot - intervene manually.": "Не удалось поставить на паузу: %s (%s). Mac остаётся горячим - вмешайтесь вручную.",
    "CONFIDENCE: LOW - %s.":
        "ДОСТОВЕРНОСТЬ: НИЗКАЯ - %s.",
    "the last heartbeat is %d days before boot - the clock was most likely wrong (dead RTC, NTP jump) or the data came from a backup":
        "последний пульс на %d дн. раньше загрузки - часы почти наверняка были неверны (севший RTC, скачок NTP) либо данные из резервной копии",
    "%.1f h passed between the last heartbeat and boot - the guard may have been killed long before the Mac actually went down":
        "между последним пульсом и загрузкой прошло %.1f ч - защита могла быть убита задолго до того, как Mac реально погас",
}

ZH = {
    "Thermal guard: hot": "Thermal guard：过热",
    "Thermal guard: job slowed down": "Thermal guard：任务已降速",
    "%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools":
        "%s 已移至能效核心（可能慢数倍）- 机器冷却后自动恢复全速",
    "Thermal guard: full speed again": "Thermal guard：已恢复全速",
    "%s is back on P-cores": "%s 已回到性能核心",
    "Thermal guard (watch-only): hot": "Thermal guard（仅观察）：过热",
    "Would pause %s - %s. Protection is off.": "本应暂停 %s - %s。保护已关闭。",
    "Paused: %s (%s)": "已暂停:%s(%s)",
    "Thermal guard: cooled down": "Thermal guard:已降温",
    "Resumed paused jobs (%s)": "已恢复暂停的任务(%s)",
    "Thermal guard: STOPPED": "Thermal guard:已终止",
    "Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.":
        "任务已终止(%s)。等 Mac 降温后从检查点恢复。",
    "Mac shut down without warning": "Mac 毫无预警地关机了",
    "Evidence from the moment of the crash was saved - menu bar > Export report":
        "已保存崩溃时刻的证据 - 菜单栏 > 导出报告",
    "Nothing to freeze": "没有可暂停的任务",
    "No heavy job meets the conditions": "没有符合条件的繁重任务",
    "Fans stopped while the chip is hot": "芯片过热时风扇停转",
    "COOLING FAILURE? chip %.1f C while both fans report 0 rpm":
        "散热故障?芯片 %.1f C,而两个风扇均为 0 转/分",
    "chip %.1f C": "芯片 %.1f C",
    "battery %.1f C": "电池 %.1f C",
    "thermal state=%s": "热状态=%s",
    "thermal state=critical": "热状态=critical",
    "thermal state=fair": "热状态=fair",
    "CPU throttled to %d%%": "CPU 降频至 %d%%",
    "battery %d%% on battery power": "电池 %d%% 且未接电源",
    "CRITICAL: ": "危急:",
    "MANUAL FREEZE (from the menu bar)": "手动暂停(来自菜单栏)",
    "manual resume (from the menu bar)": "手动恢复(来自菜单栏)",
    "conditions are back to normal": "条件已恢复正常",
    "paused for longer than %d min": "暂停超过 %d 分钟",
    "Thermal guard: CRITICAL overheating": "Thermal guard:严重过热",
    "The Mac is critically hot (%s). Heavy jobs are being stopped.":
        "Mac 已严重过热(%s)。正在停止繁重任务。",
    "The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.":
        "Mac 已严重过热(%s)。仅观察模式 - 不停止任何任务。",
    "coffee-paladin: watch-only mode": "coffee-paladin:仅观察模式",
    "Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click).":
        "只测量和提醒 - 不暂停任何任务。请在菜单栏启用保护(一键)。",
    "another coffee-paladin daemon is already running - this one exits": "另一个 coffee-paladin 守护进程已在运行 - 本进程退出",
    "PAUSED %s (pid %d, %.0f%% CPU) - %s": "已暂停  %s (pid %d, %.0f%% CPU) - %s",
    "[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s": "[仅观察] 本会暂停 %s (pid %d, %.0f%% CPU) - %s",
    "FAILED to pause %s (pid %d) - not permitted to send the signal": "暂停失败 %s (pid %d) - 没有发送信号的权限",
    "RESUMED %s (pid %d) - %s": "已恢复 %s (pid %d) - %s",
    "dropping stale pause entry: %s (pid %s) is running again "
    "- resumed outside the guard":
        "清除过期的暂停记录：%s (pid %s) 已重新运行 - 由防护程序之外恢复",
    "[DRY-RUN] would terminate %s (pid %d) - %s": "[仅观察] 本会关闭 %s (pid %d) - %s",
    "TERMINATED (SIGTERM) %s (pid %d) - %s": "已关闭 (SIGTERM) %s (pid %d) - %s",
    "SIGKILL %s (pid %d)": "SIGKILL %s (pid %d)",
    "[DRY-RUN] would demote %s (pid %d)": "[仅观察] 本会降级 %s (pid %d)",
    "DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)": "已降级 %s (pid %d) -> 后台 QoS/能效核心(持续过热超过 %d 分钟)",
    "PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)": "已恢复 %s (pid %d) -> 回到性能核心(机器已降温)",
    "unknown argument: %s": "未知参数:%s",
    "usage: coffee-paladin [--once | status | --version]   (no arguments = run the daemon)": "用法:coffee-paladin [--once | status | --version]   (不带参数 = 运行守护进程)",
    "!!! HARD SHUTDOWN DETECTED - ": "!!! 检测到硬关机 - ",
    "manual freeze: there was nothing to freeze": "手动冻结:没有可冻结的进程",
    "PAUSE >%d min - terminating job %s (pid %s)": "暂停超过 %d 分钟 - 结束任务 %s (pid %s)",
    "LOOP ERROR: %r": "循环错误:%r",
    "guard startup - nothing is left frozen": "守卫启动 - 没有残留的冻结进程",
    "guard is shutting down": "守卫正在关闭",
    "nothing to freeze": "没有可冻结的进程",
    "Mac went down without a clean shutdown. Guard's last heartbeat: %s, system booted: %s.": "Mac 未经正常关机就断电。守卫最后心跳:%s,系统启动:%s。",
    "yes": "是",
    "NO (macmon missing - running on battery temperature only)": "否(缺少 macmon - 仅依据电池温度运行)",
    "coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s) | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery": "coffee-paladin 启动 | 芯片:暂停>=%.0fC 恢复<=%.0fC 终止>=%.0fC(传感器:%s)| 电池:暂停>=%.0fC 终止>=%.0fC | 状态>=%s | 电池阈值:未接电源时 <=%d%%",
    "state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)": "状态=%s 芯片=%s 电池=%s 风扇=%s 电源=%s CPU限制=%d%% load1=%.2f 级别=%d (%s)",
    "  candidate: %-20s pid=%-7d %.0f%% CPU": "  候选:%-20s pid=%-7d %.0f%% CPU",
    "AC": "电源",
    "battery %s%%": "电池 %s%%",
    "calm": "平静",
    "gone before pause: %s (pid %d)": "暂停前已消失:%s (pid %d)",
    "FAILED to pause %s (pid %d) - errno %d, giving up on this pid": "暂停失败 %s (pid %d) - errno %d,放弃该 pid",
    "STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, type 'fg' in its window": "SIGCONT 后仍处于停止状态:%s (pid %d) - 前台终端任务,请在其窗口输入 'fg'",
    "Thermal guard: job needs your hand": "热量守卫:任务需要你处理",
    "%s cannot resume by itself - switch to its terminal and type 'fg'.": "%s 无法自行恢复 - 切换到它的终端并输入 'fg'。",
    "Thermal guard: PROTECTION INCOMPLETE": "热量守卫:保护不完整",
    "No chip temperature sensor (macmon missing). Only battery temperature is watched, and it reacts minutes late. Fix: brew install macmon": "没有芯片温度传感器（缺少 macmon）。只能监测电池温度，而它要慢上几分钟才有反应。解决办法：brew install macmon",
    "Could not pause: %s (%s). The Mac stays hot - intervene manually.": "无法暂停:%s (%s)。Mac 仍然过热 - 请手动处理。",
    "CONFIDENCE: LOW - %s.":
        "可信度:低 - %s。",
    "the last heartbeat is %d days before boot - the clock was most likely wrong (dead RTC, NTP jump) or the data came from a backup":
        "最后一次心跳比开机早 %d 天 - 时钟很可能不正确(RTC 电池耗尽、NTP 跳变),或数据来自备份",
    "%.1f h passed between the last heartbeat and boot - the guard may have been killed long before the Mac actually went down":
        "最后一次心跳与开机之间相隔 %.1f 小时 - 守护可能在 Mac 真正断电之前很久就被杀掉了",
}

ES = {
    "Thermal guard: hot": "Thermal guard: caliente",
    "Thermal guard: job slowed down": "Thermal guard: tarea ralentizada",
    "%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools":
        "%s movido a nucleos E (hasta varias veces mas lento) - vuelve a plena velocidad cuando la maquina se enfrie",
    "Thermal guard: full speed again": "Thermal guard: plena velocidad de nuevo",
    "%s is back on P-cores": "%s vuelve a los nucleos P",
    "Thermal guard (watch-only): hot": "Thermal guard (solo observación): caliente",
    "Would pause %s - %s. Protection is off.":
        "Habría pausado %s - %s. La protección está desactivada.",
    "Paused: %s (%s)": "En pausa: %s (%s)",
    "Thermal guard: cooled down": "Thermal guard: enfriado",
    "Resumed paused jobs (%s)": "Tareas en pausa reanudadas (%s)",
    "Thermal guard: STOPPED": "Thermal guard: DETENIDO",
    "Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.":
        "Tareas terminadas (%s). Reanuda desde un checkpoint cuando el Mac se haya enfriado.",
    "Mac shut down without warning": "El Mac se apagó sin aviso",
    "Evidence from the moment of the crash was saved - menu bar > Export report":
        "Se guardaron las pruebas del momento del fallo - barra de menús > Exportar informe",
    "Nothing to freeze": "Nada que pausar",
    "No heavy job meets the conditions": "Ninguna tarea pesada cumple las condiciones",
    "Fans stopped while the chip is hot": "Ventiladores parados con el chip caliente",
    "COOLING FAILURE? chip %.1f C while both fans report 0 rpm":
        "¿FALLO DE REFRIGERACIÓN? chip a %.1f C y ambos ventiladores a 0 rpm",
    "chip %.1f C": "chip %.1f C",
    "battery %.1f C": "batería %.1f C",
    "thermal state=%s": "estado térmico=%s",
    "thermal state=critical": "estado térmico=critical",
    "thermal state=fair": "estado térmico=fair",
    "CPU throttled to %d%%": "CPU limitada al %d%%",
    "battery %d%% on battery power": "batería al %d%% sin adaptador",
    "CRITICAL: ": "CRÍTICO: ",
    "MANUAL FREEZE (from the menu bar)": "PAUSA MANUAL (desde la barra de menús)",
    "manual resume (from the menu bar)": "reanudación manual (desde la barra de menús)",
    "conditions are back to normal": "las condiciones volvieron a la normalidad",
    "paused for longer than %d min": "en pausa durante más de %d min",
    "Thermal guard: CRITICAL overheating": "Thermal guard: sobrecalentamiento CRÍTICO",
    "The Mac is critically hot (%s). Heavy jobs are being stopped.":
        "El Mac está críticamente caliente (%s). Se están deteniendo las tareas pesadas.",
    "The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.":
        "El Mac está críticamente caliente (%s). Modo observación: no se detiene nada.",
    "coffee-paladin: watch-only mode": "coffee-paladin: modo observación",
    "Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click).":
        "Solo mido y aviso: no se pausa nada. Activa la protección en la barra de menús (un clic).",
    "another coffee-paladin daemon is already running - this one exits": "ya se está ejecutando otro demonio coffee-paladin - este termina",
    "PAUSED %s (pid %d, %.0f%% CPU) - %s": "PAUSADO  %s (pid %d, %.0f%% CPU) - %s",
    "[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s": "[SOLO OBSERVAR] pausaría %s (pid %d, %.0f%% CPU) - %s",
    "FAILED to pause %s (pid %d) - not permitted to send the signal": "NO SE PUDO pausar %s (pid %d) - sin permiso para enviar la señal",
    "RESUMED %s (pid %d) - %s": "REANUDADO %s (pid %d) - %s",
    "dropping stale pause entry: %s (pid %s) is running again "
    "- resumed outside the guard":
        "descarto la entrada de pausa obsoleta: %s (pid %s) vuelve a ejecutarse "
        "- reanudado fuera del guardian",
    "[DRY-RUN] would terminate %s (pid %d) - %s": "[SOLO OBSERVAR] cerraría %s (pid %d) - %s",
    "TERMINATED (SIGTERM) %s (pid %d) - %s": "CERRADO (SIGTERM) %s (pid %d) - %s",
    "SIGKILL %s (pid %d)": "SIGKILL %s (pid %d)",
    "[DRY-RUN] would demote %s (pid %d)": "[SOLO OBSERVAR] degradaría %s (pid %d)",
    "DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)": "DEGRADADO %s (pid %d) -> QoS de fondo/núcleos de eficiencia (caliente durante más de %d min)",
    "PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)": "PROMOVIDO %s (pid %d) -> de vuelta a los núcleos de rendimiento (la máquina se enfrió)",
    "unknown argument: %s": "argumento desconocido: %s",
    "usage: coffee-paladin [--once | status | --version]   (no arguments = run the daemon)": "uso: coffee-paladin [--once | status | --version]   (sin argumentos = ejecuta el demonio)",
    "!!! HARD SHUTDOWN DETECTED - ": "!!! APAGADO BRUSCO DETECTADO - ",
    "manual freeze: there was nothing to freeze": "congelación manual: no había nada que congelar",
    "PAUSE >%d min - terminating job %s (pid %s)": "PAUSA de más de %d min - cierro la tarea %s (pid %s)",
    "LOOP ERROR: %r": "ERROR DEL BUCLE: %r",
    "guard startup - nothing is left frozen": "arranque del guardián - no queda nada congelado",
    "guard is shutting down": "el guardián se está cerrando",
    "nothing to freeze": "nada que congelar",
    "Mac went down without a clean shutdown. Guard's last heartbeat: %s, system booted: %s.": "El Mac se apagó sin un cierre limpio. Última señal del guardián: %s, sistema arrancado: %s.",
    "yes": "sí",
    "NO (macmon missing - running on battery temperature only)": "NO (falta macmon - funcionando solo con la temperatura de la batería)",
    "coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s) | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery": "coffee-paladin inicio | chip: pausa>=%.0fC reanudación<=%.0fC cierre>=%.0fC (sensor: %s) | batería: pausa>=%.0fC cierre>=%.0fC | estado>=%s | umbral de batería: <=%d%% sin cargador",
    "state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)": "estado=%s chip=%s batería=%s ventiladores=%s alimentación=%s límite_CPU=%d%% load1=%.2f nivel=%d (%s)",
    "  candidate: %-20s pid=%-7d %.0f%% CPU": "  candidato: %-20s pid=%-7d %.0f%% CPU",
    "AC": "red",
    "battery %s%%": "batería %s%%",
    "calm": "en calma",
    "gone before pause: %s (pid %d)": "desapareció antes de la pausa: %s (pid %d)",
    "FAILED to pause %s (pid %d) - errno %d, giving up on this pid": "NO SE PUDO pausar %s (pid %d) - errno %d, abandono este pid",
    "STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, type 'fg' in its window": "SIGUE DETENIDO tras SIGCONT: %s (pid %d) - tarea en primer plano, escribe 'fg' en su ventana",
    "Thermal guard: job needs your hand": "Guardián térmico: la tarea necesita tu intervención",
    "%s cannot resume by itself - switch to its terminal and type 'fg'.": "%s no puede reanudarse solo - ve a su terminal y escribe 'fg'.",
    "Thermal guard: PROTECTION INCOMPLETE": "Guardián térmico: PROTECCIÓN INCOMPLETA",
    "No chip temperature sensor (macmon missing). Only battery temperature is watched, and it reacts minutes late. Fix: brew install macmon": "No hay sensor de temperatura del chip (falta macmon). Solo se vigila la bateria, que reacciona con minutos de retraso. Solucion: brew install macmon",
    "Could not pause: %s (%s). The Mac stays hot - intervene manually.": "No se pudo pausar: %s (%s). El Mac sigue caliente - interviene manualmente.",
    "CONFIDENCE: LOW - %s.":
        "FIABILIDAD: BAJA - %s.",
    "the last heartbeat is %d days before boot - the clock was most likely wrong (dead RTC, NTP jump) or the data came from a backup":
        "el último latido es %d días anterior al arranque - el reloj casi seguro estaba mal (RTC agotada, salto de NTP) o los datos vienen de una copia de seguridad",
    "%.1f h passed between the last heartbeat and boot - the guard may have been killed long before the Mac actually went down":
        "pasaron %.1f h entre el último latido y el arranque - el guardián pudo morir mucho antes de que el Mac se apagara de verdad",
}

DICTS = {"pl": PL, "ru": RU, "zh": ZH, "es": ES}


def T(s):
    """Translate a message using the configured language.

    English is the source of truth. A missing dictionary entry means English, never an
    error.
    """
    return DICTS.get(LANG, {}).get(s, s)

def rotate(path):
    """Rotate with numbered generations: .1 is newest and .N is oldest.

    A single `os.replace(path, path + ".1")` meant every later rotation overwrote .1 and
    destroyed evidence permanently. A measured 98.7 C peak reached history.csv; after the
    first rotation, `thermal-report --days 2` showed 44.0 C because it read only the current
    file, and after the second rotation the 98.7 C reading no longer existed on disk. That
    evidence is the reason this file exists.

    Keeps MAX_LOG_GENERATIONS generations. At 5 MB per file, that is about 30 MB per stream,
    cheap for evidence that cannot be recreated.
    """
    try:
        if os.path.getsize(path) <= MAX_LOG_BYTES:
            return
    except OSError:
        return
    try:
        oldest = "%s.%d" % (path, MAX_LOG_GENERATIONS)
        if os.path.exists(oldest):
            os.remove(oldest)
        for n in range(MAX_LOG_GENERATIONS - 1, 0, -1):
            source = "%s.%d" % (path, n)
            if os.path.exists(source):
                os.replace(source, "%s.%d" % (path, n + 1))
        os.replace(path, path + ".1")
    except OSError:
        pass


def generations(path):
    """Return the current file and rotated generations, oldest first.

    Every evidence reader, including thermal-report and statistics, must use this list
    instead of `path` alone. Otherwise rotation silently cuts history out of the document.
    """
    rotated = []
    n = 1
    while True:
        p = "%s.%d" % (path, n)
        if not os.path.exists(p):
            break
        rotated.append(p)
        n += 1
    rotated.reverse()                    # .3, .2, .1 = chronological
    if os.path.exists(path):
        rotated.append(path)
    return rotated


_SILENT_FAILURES = {}


def silent_failure(location, e):
    """Record a swallowed exception from a critical path.

    In a safety daemon, `except Exception: pass` while writing evidence or state means the
    evidence did not exist and nobody found out. Ruff counted 107 such places, including
    14 in functions that decide protection or evidence. The flow is unchanged: the daemon
    must keep running when the disk is full. Each failure is logged once per 10 min per
    location and counted in status.json. Exceptions are still swallowed, but no longer
    silently.
    """
    _SILENT_FAILURES[location] = _SILENT_FAILURES.get(location, 0) + 1
    marker = "_ostatni_log_" + location
    current_time = now()
    if current_time - _SILENT_FAILURES.get(marker, 0) >= 600:
        _SILENT_FAILURES[marker] = current_time
        try:
            log("SWALLOWED in %s: %s: %s (%d time(s) so far)"
                % (location, type(e).__name__, e, _SILENT_FAILURES[location]))
        except Exception:
            pass


def log(msg, tag=None):
    """Write to guard.log with an optional stable ASCII event tag.

    Message text is translated into five languages, while evidence reports, menu-bar
    statistics, and `heat` parse this log. Parsers that searched for Polish and English
    words missed every hard shutdown on a Russian-language machine, losing the report's
    primary evidence. The [PAUSE]/[RESUME]/... tag is identical in every language and is
    the parser contract.
    """
    if tag:
        msg = "[%s] %s" % (tag, msg)
    rotate(LOG_PATH)
    line = "%s  %s\n" % (ts(), msg)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line)
    except Exception:
        pass
    if sys.stdout.isatty():
        sys.stdout.write(line)
        sys.stdout.flush()


def _kill_group(p):
    """Kill the child's whole process group and then reap it.

    `p.kill()` alone leaves grandchildren alive, and they can hang for hours. If the group
    cannot be read because the child already disappeared, falls back to a normal kill.
    """
    if p is None:
        return
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except OSError:
        try:
            p.kill()
        except Exception:
            pass
    try:
        p.communicate(timeout=2)          # reap it, otherwise it stays a zombie
    except Exception:
        pass


def run(cmd, timeout=10):
    """Run a command and always clean up after it.

    `communicate(timeout=...)` raises TimeoutExpired but does NOT kill the child. The
    process remains, and the daemon accumulates more. On a loaded Mac, guard had four
    hanging children, including two `macmon pipe` processes and `pmset -g therm`; the loop
    stalled for 90 seconds and status.json stopped refreshing. With a 15-second cycle, that
    meant nobody watched temperature during that window.
    """
    p = None
    try:
        # Own process group. `p.kill()` reaches only the direct child, so a command that
        # launches something else, such as a shell with a background job, left an orphaned
        # grandchild alive. Fuzzing reproduced a child still running after run() returned.
        # In a daemon that runs for years, those orphans accumulate.
        # None of the commands called by run() (ps, sysctl, pmset, ioreg, macmon) needs a
        # terminal, so detaching the session has no cost.
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        out, _ = p.communicate(timeout=timeout)
        return out.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        _kill_group(p)
        return ""
    except Exception:
        if p is not None and p.poll() is None:
            _kill_group(p)
        return ""


# A monotonic clock is meaningful only inside one process. A pause entry survives daemon
# restart, which is intentional; otherwise SIGKILL on the guard would leave frozen
# processes with no owner. The entry must therefore say whose measurement it is.
_MONO_ID = "%d:%d" % (os.getpid(), int(time.time()))

_last_notify = {}

# Short-lived helper processes (osascript/afplay/curl). Keep references and reap them every
# cycle; otherwise every alert stays a zombie until subprocess internals clean it up.
_bg_procs = []


def popen_bg(cmd, stdin_data=None):
    """Start a background process.

    Use `stdin_data` where an argument MUST NOT appear in `ps`: every local user can see
    argv, but not stdin.
    """
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.PIPE if stdin_data is not None else None)
        if stdin_data is not None:
            try:
                p.stdin.write(stdin_data.encode("utf-8"))
            finally:
                p.stdin.close()
        _bg_procs.append(p)
    except Exception:
        pass


def reap_bg():
    _bg_procs[:] = [p for p in _bg_procs if p.poll() is None]


SOUNDS = {
    "pause": "Basso",      # hot: low and serious
    "resume": "Hero",      # resume: recovered from heat, back to work
    "kill": "Sosumi",      # job termination
    "fan": "Basso",        # cooling failure
    "pad": "Basso",        # detected hard shutdown
    "freeze": "Tink",      # manual menu-bar actions
    "demote": "Submarine", # pushed to E-cores, going lower
    "promote": "Hero",     # back to P-cores, same fanfare as resume
    "awake": "Funk",       # keep-awake start
    "watchonly": "Basso",  # watch-only: would pause, but protection is off
}


# Different event keys can share one sound file.
SOUND_ALIAS = {"promote": "resume", "fan": "kill", "default": "pad"}
# If pause/resume cycles every ~40 s, the sound would fire constantly. Limit it to once
# every 10 minutes; notifications continue, only sound is throttled.
SOUND_MIN_GAP_S = {"pause": 600, "demote": 600, "resume": 600, "awake": 600}
_last_sound = {}


def play_sound(cfg, key):
    if not cfg.get("sound", True):
        return
    gap = SOUND_MIN_GAP_S.get(key, 0)
    if gap and now() - _last_sound.get(key, 0) < gap:
        return
    _last_sound[key] = now()
    # Prefer bundled files (CC0, see sounds/LICENSES.md). Fall back to system sounds so
    # old installs without sounds/ lose nothing.
    bundled_sound = os.path.join(BASE, "sounds", SOUND_ALIAS.get(key, key) + ".wav")
    if os.path.exists(bundled_sound):
        popen_bg(["afplay", bundled_sound])
        return
    name = SOUNDS.get(key, "Ping")
    path = "/System/Library/Sounds/%s.aiff" % name
    if os.path.exists(path):
        popen_bg(["afplay", path])


def push(cfg, title, text):
    """Send a phone push through ntfy.sh.

    Works anywhere the ntfy app subscribes to the same topic. Uses Popen plus timeout:
    missing internet must not stop the loop.
    """
    # `notify: false` must silence push too. The gate used to exist only in notify(), while
    # banner() called push() directly, so disabled notifications still sent a phone message
    # every 180 s during a critical level.
    if not cfg.get("notify", True):
        return
    topic = (cfg.get("ntfy_topic") or "").strip()
    # The topic goes into a URL without quoting, so it must be safe on its own.
    # Measured: "sekret#tajne" publishes to "sekret" because curl trims the fragment,
    # and "sekret?tajne" publishes to "sekret" with the tail as ntfy control parameters.
    # The user thinks they have a 12-character topic, but actually has a 6-character one.
    if not topic or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic):
        if topic:
            log("ntfy: temat %r ma niedozwolone znaki albo dlugosc - push wylaczony "
                "(dozwolone: litery, cyfry, _ i -, do 64 znakow)" % topic[:80])
        return
    # The topic MUST NOT appear in argv. Every local user can read `ps -Ao args=`, and the
    # ntfy topic is the only secret protecting this channel: whoever knows it can read
    # alerts (temperatures, job names, hard shutdowns) and send fake ones. Publish through
    # JSON on stdin so argv contains only "curl -s -m 10 -H Content-Type... -d @-
    # https://ntfy.sh/". `-d @-` reads the body from stdin, so neither topic nor content
    # leaks through argv.
    body = json.dumps({"topic": topic,
                        "title": title.replace("\n", " ").replace("\r", " "),
                        "message": text}, ensure_ascii=False)
    popen_bg(["curl", "-s", "-m", "10", "-H", "Content-Type: application/json",
              "-d", "@-", "https://ntfy.sh/"], stdin_data=body)


def notify(cfg, title, text, key="default"):
    if not cfg["notify"]:
        return
    t = now()
    if t - _last_notify.get(key, 0) < cfg["notify_min_gap_s"]:
        return
    _last_notify[key] = t
    play_sound(cfg, key)
    script = 'display notification %s with title %s' % (
        json.dumps(text), json.dumps(title))
    popen_bg(["osascript", "-e", script])
    # Same gap as the screen notification; the phone must not receive more than the screen.
    push(cfg, title, text)


_last_banner = {"t": 0.0}


def banner(cfg, title, text):
    """Show a modal alert above everything, only for critical level.

    Uses Popen, not call: osascript waits until OK is clicked, and the guard loop cannot
    block for even a second. `giving up after` closes the window by itself, so an overnight
    critical state does not leave a stack of windows. Each later alert is still governed by
    its own gap.
    """
    if not cfg.get("critical_banner", True):
        return
    t = now()
    gap = cfg.get("critical_banner_gap_s", 180)
    if t - _last_banner["t"] < gap:
        return
    _last_banner["t"] = t
    play_sound(cfg, "critical")   # fire: "critical" should sound different from "hot"
    script = 'display alert %s message %s as critical giving up after %d' % (
        json.dumps(title), json.dumps(text), int(gap))
    popen_bg(["osascript", "-e", script])
    push(cfg, title, text)


# ---------------------------------------------------------------- sensors

def thermal_state():
    for exe in (os.path.join(HOME, ".local/bin/thermalstate"), "thermalstate"):
        out = run([exe]).strip()
        if out in LEVELS:
            return out
    return "unknown"


def normalize_batt_temp(raw):
    """Return cell temperature in C, independent of controller units.

    Battery measurement units differ across Mac models: some report hundredths of a degree
    (3081 = 30.81 C), some tenths (444 = 44.4 C), and some whole degrees (41 = 41 C).
    Dividing by 100 unconditionally produces nonsense such as 444 C or 0.4 C on some
    machines, so the value is scaled into the physically possible range for a lithium cell.
    """
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    for _ in range(4):
        if v <= 100.0:
            break
        v /= 10.0
    return v if 5.0 < v <= 100.0 else None


def battery_temp_c():
    """Return battery-pack temperature in C, or None when there is no battery."""
    out = run(["ioreg", "-r", "-c", "AppleSmartBattery", "-d", "1", "-w", "0"], timeout=15)
    best = None
    for key in ('"Temperature"', '"VirtualTemperature"'):
        m = re.search(re.escape(key) + r"\s*=\s*(\d+)", out)
        if m:
            v = normalize_batt_temp(m.group(1))
            if v is not None and (best is None or v > best):
                best = v
    return best


# Be careful with the initial value. 0.0 was wrong: Apple's /usr/bin/python3, used by
# launchd to start the daemon, counts time.monotonic() from zero in each process. During
# the first 10 seconds, the freshness condition was true and soc_sensors() returned the
# initial None without calling macmon once. The guard reported "no chip sensor" and watched
# only the battery for the first cycle. None means "not read yet" regardless of where this
# Python starts counting.
_soc_cache = {"t": None, "val": None}


def soc_sensors(max_age=10.0):
    """Return chip temperature, fans, and power draw from `macmon`.

    Uses IOReport without sudo. Returns dict {"cpu": C, "gpu": C, "fans": [rpm],
    "watts": W}, or None when macmon is unavailable. The result is cached because one
    sample costs ~1 s, while the guard loop runs every 15 s and asks in several places.

    On macOS 26, sensors through IOHIDEventSystem are blocked for unprivileged processes,
    which made the custom Swift sensor return zero. IOReport still works.
    """
    if _soc_cache["t"] is not None and 0 <= time.monotonic() - _soc_cache["t"] < max_age:
        return _soc_cache["val"]
    val = None
    for exe in ("/opt/homebrew/bin/macmon", "macmon"):
        out = run([exe, "pipe", "-s", "1"], timeout=20)
        line = out.strip().split("\n")[0] if out.strip() else ""
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("temp") or {}
        cpu = t.get("cpu_temp_avg")
        gpu = t.get("gpu_temp_avg")
        fans = [int(f.get("rpm") or 0) for f in (d.get("fans") or [])]
        # An idle GPU can return junk (2-3 C); below 10 C means no reading.
        def sane(v):
            return float(v) if isinstance(v, (int, float)) and 10.0 < v < 130.0 else None

        mem = d.get("memory") or {}
        GB = float(1024 ** 3)
        val = {
            "cpu": sane(cpu),
            "gpu": sane(gpu),
            "ram_used": (mem.get("ram_usage") or 0) / GB,
            "ram_total": (mem.get("ram_total") or 0) / GB,
            "swap_used": (mem.get("swap_usage") or 0) / GB,
            "fans": fans,
            "watts": float(d.get("all_power") or 0.0),
        }
        break
    _soc_cache["t"] = time.monotonic()
    _soc_cache["val"] = val
    return val


def soc_temp_c():
    """Return the hottest SoC point, CPU or GPU, in C, or None."""
    s = soc_sensors()
    if not s:
        return None
    vals = [v for v in (s.get("cpu"), s.get("gpu")) if v is not None]
    return max(vals) if vals else None


def disk_usage():
    """Return system disk usage as (used_GB, total_GB, used_percent)."""
    try:
        st = os.statvfs("/System/Volumes/Data")
    except Exception:
        try:
            st = os.statvfs("/")
        except Exception:
            return None
    GB = float(1024 ** 3)
    total = st.f_blocks * st.f_frsize / GB
    # Use f_bavail, not f_bfree: this is space actually available to the user.
    free = st.f_bavail * st.f_frsize / GB
    if total <= 0:
        return None
    return (total - free, total, 100.0 * (total - free) / total)


def power_source():
    """Return (on_ac: bool, battery_percent: int|None)."""
    out = run(["pmset", "-g", "batt"], timeout=10)
    ac = "AC Power" in out
    m = re.search(r"(\d+)%", out)
    return ac, (int(m.group(1)) if m else None)


def cpu_speed_limit():
    """Return available CPU power percent according to macOS, where 100 means no throttling."""
    out = run(["pmset", "-g", "therm"])
    m = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", out)
    return int(m.group(1)) if m else 100


def load_avg():
    try:
        return os.getloadavg()[0]
    except Exception:
        return 0.0


def ncpu():
    out = run(["sysctl", "-n", "hw.ncpu"]).strip()
    try:
        return int(out)
    except Exception:
        return 8


def list_procs():
    """Return [(pid, ppid, cpu, comm, args)] for processes owned by the current user."""
    out = run(["ps", "-Ao", "pid=,ppid=,pcpu=,uid=,comm=", "-c"], timeout=15)
    uid = os.getuid()
    res = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        try:
            pid, ppid, cpu, puid = int(parts[0]), int(parts[1]), float(parts[2]), int(parts[3])
        except ValueError:
            continue
        if puid != uid:
            continue
        res.append((pid, ppid, cpu, parts[4].strip()))
    return res


def foreground_on_tty(pid):
    """Return whether a process leads its terminal foreground group.

    If pgid == tpgid, this process owns the keyboard. SIGSTOP makes its shell retake the
    terminal; a later SIGCONT resumes it in the background, so the first keyboard read gets
    SIGTTIN and stops again. The daemon cannot break that loop because it cannot tcsetpgrp
    someone else's tty. The only exit is a human typing `fg`. These processes MUST NOT be
    paused.
    """
    out = run(["ps", "-o", "pgid=,tpgid=", "-p", str(pid)]).split()
    if len(out) >= 2:
        try:
            pgid_, tpgid_ = int(out[0]), int(out[1])
            return tpgid_ > 0 and pgid_ == tpgid_
        except ValueError:
            return False
    return False


def full_args(pid):
    out = run(["ps", "-o", "args=", "-p", str(pid)])
    return out.strip()


# Programs whose own name says nothing. Their process identity is carried by the first
# argument, a script or module. Treat argv[1] as the program name for them.
INTERPRETERS = frozenset((
    "node", "nodejs", "deno", "bun", "python", "ruby", "perl", "php", "java",
    "sh", "bash", "zsh", "osascript", "tsx", "ts-node", "uv", "uvx", "pipx", "npx",
))

# Versioned names (python3.14, ruby3.3, node20, perl5.34). A hard-coded version list always
# falls behind the user's install. When the list ended at python3.13 and the machine already
# had Homebrew python3.14, `python3.14 /path/mcp_server.py` was not recognized as an
# interpreter, so the script path was discarded with data paths and the AI agent lost
# SIGSTOP protection. A version pattern does not age with every release.
VERSIONED_INTERPRETER = re.compile(
    r"^(python|ruby|perl|php|node|nodejs|deno|bun)[0-9]+(\.[0-9]+)*$")


def is_interpreter(name):
    """Return whether `nazwa` is a lowercased, dequoted basename of an interpreter argv[0]."""
    return name in INTERPRETERS or bool(VERSIONED_INTERPRETER.match(name))


def args_without_paths(pid):
    """Return the command-line part that identifies the process, without data paths.

    never_arg_patterns must recognize an agent, editor, or MCP server, not what the process
    reads. Matching the raw command line confused those: `ffmpeg -i
    ~/Desktop/claude_brain/wideo/rec.mkv` matched "claude", became untouchable, and kept
    heating the Mac.

    The first attempt, an extension allowlist for data, had many bypasses found by fuzzing:
    .braw, .r3d, .mxf, .heif, spaces in paths because ps joins argv with spaces, quoted
    paths, and directory arguments. Each made a normal encoder untouchable. The inverse
    also happened: `python3 ~/claude/agent.pt` lost protection because .pt was on the data
    list.

    The rule is therefore structural, not dictionary-based:
      argv[0]                     - always identity, the program name
      argv[1] with an interpreter - identity, a script or module
      arguments without slash     - identity, flags and module names such as -m mcp.server
      remaining paths             - data, excluded from matching
    """
    parts = full_args(pid).split()
    if not parts:
        return ""
    kept = [parts[0]]
    interpreter = is_interpreter(os.path.basename(parts[0].strip('"\'')).lower())
    script_taken = not interpreter
    for a in parts[1:]:
        if "/" not in a:
            kept.append(a)          # flag or module name (-m mcp.server)
        elif not script_taken and not a.startswith("-"):
            # The first non-flag interpreter argument is the SCRIPT BEING RUN, therefore
            # process identity, even when flags came before it:
            # `node --experimental-modules /path/mcp-server.js`.
            kept.append(a)
            script_taken = True
        # The rest is data path and is ignored.
    return " ".join(kept).lower()


def top_lists(n=3):
    """Return top CPU and RAM processes for the menu bar.

    CPU is the best available per-process heat proxy because per-process temperatures do
    not exist, and the menu bar labels it that way. RSS from ps is in KB.
    """
    out = run(["ps", "-Ao", "pcpu=,rss=,comm=", "-c", "-r"], timeout=15)
    rows = []
    for line in out.splitlines():
        p = line.split(None, 2)
        if len(p) < 3:
            continue
        try:
            rows.append((float(p[0]), int(p[1]), p[2].strip()))
        except ValueError:
            continue
    cpu = [{"name": c[:24], "cpu": round(v)} for v, r, c in rows[:n] if v >= 1]
    ram = [{"name": c[:24], "gb": round(r / 1048576.0, 1)}
           for v, r, c in sorted(rows, key=lambda x: -x[1])[:n] if r > 102400]
    return cpu, ram


# ---------------------------------------------------------------- process selection

def managed_pids_from_saferun():
    """Return PIDs registered by safe-run as ({pid: pgid}, {PIDs from --normal}).

    The "normal" set records explicit human decisions: this job should run on all cores.
    Demotion to E-cores must not silently override that.
    """
    res = {}
    normal = set()
    try:
        for name in os.listdir(MANAGED_DIR):
            if not name.endswith(".json"):
                continue
            path = os.path.join(MANAGED_DIR, name)
            try:
                # Registration controls signals, so it must belong to us and must not be
                # writable by anyone else. On a multi-account Mac, a 0666 file in managed/
                # is a ready lever: whoever replaces it points guard at a target to freeze.
                # The directory is 0700 via ensure_dirs, but a file may remain from an old
                # install or manual copy.
                file_stat = os.lstat(path)
                if file_stat.st_uid != os.getuid() or (file_stat.st_mode & 0o022):
                    log("ignoring managed registration with unsafe ownership/permissions: %s"
                        % name)
                    continue
                with open(path) as f:
                    d = json.load(f)
                # A queued pre-registration is the WRAPPER waiting for admission,
                # not a job: it must never become a pause or kill target. It
                # still gets the liveness and identity checks - a wrapper killed
                # while waiting leaves a queued:true file behind, and after pid
                # reuse a phantom entry would hold admission cores forever.
                if d.get("queued"):
                    pid = int(d["pid"])
                    stale_placeholder = not alive(pid)
                    if not stale_placeholder and d.get("started"):
                        age = proc_age_seconds(pid)
                        if age and abs((now() - age) - float(d["started"])) > 90:
                            stale_placeholder = True
                    if stale_placeholder:
                        os.unlink(path)
                    continue
                pid = int(d["pid"])
                if alive(pid):
                    # A PID can be reused after guard crashes, so check whether the current
                    # process still resembles the registered command.
                    # Identity is checked by process START TIME, not name. Comparing `ps
                    # comm` (the INTERPRETER name: bash, Python) with the command basename
                    # (compressor.sh) failed for every shebang script, so guard deleted its
                    # own registration right after it was created. The effect was managed/
                    # empty during live compression, `jobs: []` in status, and lost pgid and
                    # "normal" flag.
                    registered_start = d.get("started")
                    if registered_start:
                        age = proc_age_seconds(pid)
                        actual_start = now() - age
                        # 90 s slack: etime has one-second resolution, and registration is
                        # created shortly after process start.
                        if age and abs(actual_start - float(registered_start)) > 90:
                            os.unlink(path)     # PID was taken by another process
                            continue
                    # Read PGID from the kernel, not the file. Registration is plain JSON
                    # on disk; trusting its `pgid` literally sent SIGSTOP and SIGKILL to any
                    # process group someone wrote there. A file {"pid": A, "pgid": B} made
                    # guard signal group B, not the registered job. The kernel knows the
                    # truth, and editing the file cannot change it.
                    try:
                        res[pid] = os.getpgid(pid)
                    except OSError:
                        # The process disappeared between alive() and this call.
                        continue
                    if d.get("normal"):
                        normal.add(pid)
                else:
                    os.unlink(path)
            except Exception:
                try:
                    os.unlink(path)
                except Exception:
                    pass
    except Exception:
        pass
    return res, normal


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        import errno
        return e.errno == errno.EPERM


def sensor_latch(st, key, value, pause_threshold, resume_threshold):
    """Apply hysteresis for one sensor and return whether that sensor still holds hot.

    The latch turns on at its own pause threshold, turns off at its own resume threshold,
    and remembers the previous decision between them. That lets a sensor block resume only
    if it once requested pause itself. The older gate was asymmetric: any sensor could
    trigger pause, but every sensor blocked resume. A battery holding 37 C, three degrees
    below its own 40 C pause threshold and never having crossed it, kept a CHIP-paused job
    from resuming: 15 pauses, zero resumes, and two jobs terminated after 45 minutes.

    This latch is for the battery only. The chip keeps the old raw resume threshold, which
    is stricter than a latch because it blocks across the whole 87-95 C band regardless of
    what triggered pause. The chip also cannot have the battery pathology: a frozen chip
    drops from 95 to 71 C in twenty seconds. A chip latch would allow resume at 94 C if
    `thermalState` caused the pause, buying flicker for no benefit.

    Missing readings clear the latch, matching the previous `temp is None` meaning of "does
    not block". An absent sensor must not be the reason a computation waits until SIGTERM;
    missing measurement is visible separately through level and `sensor`, where the policy
    decision belongs.

    A threshold change at runtime clears the latch (calibration, slider, or config.json
    edit): it was set relative to the old threshold pair and no longer means anything under
    the new pair.

    Deliberate compromise: the latch lives in `st` and does not survive daemon restart.
    After restart, a battery in the 36-40 C band will not block resume, even if it caused
    pause before restart. The cost is a briefly more liberal gate once per restart. The
    alternative, persisting the latch to disk, creates the opposite failure: a latch from an
    old threshold era holding a job in T with no reason.
    """
    threshold_key = key + "_prog"
    thresholds = [pause_threshold, resume_threshold]
    if st.get(threshold_key) != thresholds:
        st[threshold_key] = thresholds
        st[key] = False
    if value is None:
        st[key] = False
    elif value >= pause_threshold:
        st[key] = True
    elif value <= resume_threshold:
        st[key] = False
    return bool(st.get(key, False))


def stopped_now():
    """Return stopped PIDs and groups with stopped members using one `ps` per cycle.

    A `st["paused"]` entry means only that guard once sent SIGSTOP, not that the process is
    stopped now. A human (`kill -CONT`), debugger, or safe-run duty limiter can wake it.
    A guard that trusts its own note instead of the system can send SIGTERM after
    `max_pause_minutes` to a job running at full speed.

    Groups matter as much as PIDs here: guard freezes the whole group (`killpg`), while a
    manual resume may signal only the entry process. If the entry were removed based only
    on the leader, a stopped child would lose the only note anyone could use to resume it,
    leaving it in T forever.

    One `ps -Ao` replaces one `ps` per entry. With dozens of frozen jobs, the loop used to
    fork that many processes every cycle.
    """
    lines = run(["ps", "-Ao", "pid=,pgid=,stat="]).splitlines()
    if not lines:
        # A failed measurement is not a measurement of "nothing is stopped". `run()`
        # returns an empty string for every error and timeout, while `ps -Ao` on a live
        # machine always has hundreds of lines. Reading emptiness literally would mark
        # EVERY entry as "resumed outside guard", delete it, and leave frozen jobs in T
        # without the only note anyone could use to resume them. None means "unknown" and
        # blocks decisions about another process's life.
        return None
    pids, groups = set(), set()
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) < 3 or not parts[2].startswith("T"):
            continue
        try:
            pids.add(int(parts[0]))
            groups.add(int(parts[1]))
        except ValueError:
            continue
    return pids, groups


def stale_entries(paused, stopped):
    """Return entries for jobs resumed outside guard, to be deleted."""
    if stopped is None:
        return []
    return [k for k, v in paused.items()
            if not v.get("manual") and not entry_stopped(k, v, *stopped)]


def expired_entries(paused, limit_s, stopped):
    """Return over-limit entries whose jobs are REALLY stopped; only those may be killed."""
    if stopped is None:
        return []
    return [k for k, v in paused.items()
            if _pause_age(v) > limit_s and not v.get("manual") and entry_stopped(k, v, *stopped)]


def resume_gate(cfg, st, temp, soc_t, state):
    """Return whether frozen jobs may resume.

    Every sensor must drop back: battery through the latch, which blocks only if it crossed
    its own pause threshold; chip through the raw resume threshold; system state through
    level. The full decision lives in one function so tests check what the daemon executes,
    not a copied expression that could pass after production logic is broken.
    """
    battery_holds = sensor_latch(st, "_batt_hot", temp,
                                    cfg["batt_pause_c"], cfg["batt_resume_c"])
    chip_holds = soc_t is not None and soc_t > cfg.get("soc_resume_c", 87.0)
    return not battery_holds and not chip_holds and LEVELS.get(state, 1) <= 1


def entry_stopped(key, info, pids, groups):
    """Return whether this entry's job is REALLY stopped, directly or through its group.

    Unknown state, such as a vanished process or unresponsive `ps`, means "not stopped":
    termination requires proof that something is stopped, not a lack of proof that it is not.
    """
    try:
        if int(key) in pids:
            return True
    except (TypeError, ValueError):
        return False
    pgid = (info or {}).get("pgid")
    try:
        return pgid is not None and int(pgid) in groups
    except (TypeError, ValueError):
        return False


def proc_age_seconds(pid):
    """Return process age in seconds from ps etime: [[dd-]hh:]mm:ss."""
    out = run(["ps", "-o", "etime=", "-p", str(pid)]).strip()
    if not out:
        return 0
    days = 0
    if "-" in out:
        d, out = out.split("-", 1)
        days = int(d)
    parts = [int(x) for x in out.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return days * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def cpu_with_children(procs):
    """Return CPU usage for each process including its whole child subtree.

    Without this, the guard is blind to the worst shape: an orchestrator (python) that uses
    no CPU itself but repeatedly spawns short, heavy children (cadical, solvers, ffmpeg).
    Each child lives for a second and disappears before hitting a threshold, while their sum
    heats the Mac. Counting the subtree exposes the real culprit and lets guard freeze the
    source, so new children stop appearing.
    """
    children = {}
    own_cpu = {}
    for pid, ppid, cpu, comm in procs:
        children.setdefault(ppid, []).append(pid)
        own_cpu[pid] = cpu
    totals = {}

    def count(pid, depth=0):
        if pid in totals:
            return totals[pid]
        if depth > 20:          # guard against a cycle in the process table
            return own_cpu.get(pid, 0.0)
        totals[pid] = own_cpu.get(pid, 0.0)   # insert early to guard against recursion
        total = own_cpu.get(pid, 0.0)
        for d in children.get(pid, []):
            if d != pid:
                total += count(d, depth + 1)
        totals[pid] = total
        return total

    for pid in list(own_cpu):
        count(pid)
    return totals


_UNTOUCHABLE_SUBSTRINGS = {}


def _log_untouchable_match(comm, pattern, cpu):
    """Log at most once per hour per process.

    The log should inform, not flood. 10 minutes was too often: corespotlightd can grind
    indexing all day and fill the log with repeated entries. One entry per hour still
    answers "why did guard not touch this".
    """
    current_time = now()
    if current_time - _UNTOUCHABLE_SUBSTRINGS.get(comm, 0) < 3600:
        return
    _UNTOUCHABLE_SUBSTRINGS[comm] = current_time
    log("%s uses %.0f%% CPU but is untouchable: its name contains the never-pause "
        "pattern %r (partial match). Rename it or narrow never_patterns if this is wrong."
        % (comm, cpu, pattern))


_DEMOTE_ONLY = []   # filled on every pick_targets; read by snapshot()


def pick_targets(cfg, procs, saferun):
    """Return pausable processes sorted by descending CPU.

    Side effect: reloads `_DEMOTE_ONLY` with system indexing daemons that MUST NOT be
    paused or killed (never list), but may be pushed to E-cores. They travel through a
    separate channel so they never reach do_pause, do_terminate, or the menu-bar manual
    freeze candidate list.
    """
    me = os.getpid()
    del _DEMOTE_ONLY[:]
    system_demote = [p.lower() for p in (cfg.get("system_demote_patterns") or [])]
    never = [p.lower() for p in list(cfg["never_patterns"]) + list(cfg.get("never_extra") or [])]
    patterns = [p.lower() for p in cfg["managed_patterns"]]
    cpu_tree = cpu_with_children(procs) if cfg.get("count_children", True) else {}
    out = []
    for pid, ppid, cpu, comm in procs:
        cpu = max(cpu, cpu_tree.get(pid, 0.0))   # evaluate the whole subtree
        if pid in (me, os.getppid()) or pid <= 1:
            continue
        if cpu < cfg["cpu_min_percent"]:
            continue
        low = comm.lower()
        if pid in saferun:
            # Untouchable stays untouchable REGARDLESS of source. A managed/ entry used
            # to bypass every list, so a stale or planted registration could freeze the
            # user's shell or AI agent, exactly what `never` is meant to prevent.
            if any(n in low for n in never):
                continue
            out.append((pid, cpu, comm, saferun[pid]))
            continue
        match = next((n for n in never if n in low), None)
        if match:
            # System indexing daemons remain UNTOUCHABLE for pause and termination, but
            # travel through a separate channel for E-core demotion. The "untouchable" log
            # is silent for them because the answer to "why did guard not touch this" is
            # now: it will, via taskpolicy -b.
            if any(w in low for w in system_demote):
                _DEMOTE_ONLY.append((pid, cpu, comm, None))
                continue
            # Substring matching is deliberate and must stay. The risk asymmetry is clear:
            # false protection means "the Mac keeps heating", while lost protection means
            # "frozen AI agent or user shell", process death, and lost work. AGENTS.md
            # forbids weakening this list for good reason.
            #
            # The cost is that `mds_solver` or `sshd-worker` are untouchable through `mds`
            # and `sshd`. Do not narrow matching; stop being silent about it. When a truly
            # hot process is skipped by PARTIAL matching, log it so the user can see why
            # the guard did not touch what is heating the Mac.
            if low != match and cpu >= cfg.get("unknown_cpu_percent", 50.0):
                _log_untouchable_match(comm, match, cpu)
            continue
        if not any(p in low for p in patterns):
            # A name list is inherently incomplete. Custom binaries (b3core, cadical,
            # solvers) never match it, so the guard could not see them while the Mac cooked.
            # As an emergency fallback, take EVERY owned process that has eaten high CPU for
            # long enough and is not untouchable. The guards are never_patterns, CPU
            # threshold, and process age; short compiles or `ls` do not qualify.
            if not cfg.get("manage_unknown_heavy", True):
                continue
            if cpu < cfg.get("unknown_cpu_percent", 50.0):
                continue
            if proc_age_seconds(pid) < cfg.get("unknown_min_seconds", 120):
                continue
        args = args_without_paths(pid)
        if any(n.lower() in args for n in (cfg.get("never_arg_patterns") or [])):
            continue
        if cfg.get("skip_foreground_tty", True) and foreground_on_tty(pid):
            continue          # interactive foreground session; see the function above
        out.append((pid, cpu, comm, None))
    out.sort(key=lambda x: -x[1])

    return out


def without_descendants(target_entries, procs):
    """Return the DISPLAY list, excluding processes whose ancestor is already listed.

    When child CPU is rolled up to the parent (`count_children`), the same processor lands
    in the list twice: once as the parent with subtree total, once as the child with its own
    usage. A measured case showed "bash 276% CPU" beside "ffmpeg 276% CPU", while `ps` for
    bash showed 0.0%. The heavy-process counter and confirmation window both lied by 2x.

    This function is ONLY for presentation. Filtering the target list is dangerous: `pgid`
    is known only for `safe-run` jobs, so for everything else `sig()` does
    `os.kill(pid, SIGSTOP)` on ONE process. SIGSTOP on the parent does not stop existing
    children; it only prevents new ones. An orchestrator with children can be reported as
    paused while the children keep grinding, giving false safety after overheating. Signals
    MUST still hit the whole subtree.
    """
    if not target_entries:
        return target_entries
    parent = {pid: ppid for pid, ppid, cpu, comm in procs}
    selected = {t[0] for t in target_entries}
    out = []
    for t in target_entries:
        p = parent.get(t[0])
        has_ancestor = False
        depth = 0
        while p and p > 1 and depth < 40:
            if p in selected:
                has_ancestor = True
                break
            p = parent.get(p)
            depth += 1
        if not has_ancestor:
            out.append(t)
    return out



# ---------------------------------------------------------------- actions

def load_state():
    """Load state and normalize types.

    Older daemon versions and the menu bar also write state. `paused` as a list (old
    format), or an entry with a non-numeric key, crashed `int(key)` or `.items()` in the
    main loop. That created a startup crash loop because KeepAlive restarted into the same
    wall. Bad fragments are cut out and logged; the rest of the state remains.
    """
    try:
        with open(STATE_PATH) as f:
            d = json.load(f)
        if isinstance(d, dict):
            if not isinstance(d.get("paused"), dict):
                if d.get("paused") is not None:
                    log("state: 'paused' had type %s - dropped (old or corrupted format)"
                        % type(d.get("paused")).__name__)
                d["paused"] = {}
            bad = [k for k, v in d["paused"].items()
                   if not str(k).lstrip("-").isdigit() or not isinstance(v, dict)]
            for k in bad:
                log("state: dropping malformed pause entry %r" % (k,))
                del d["paused"][k]
            if not isinstance(d.get("demoted"), list):
                d["demoted"] = []
            if not isinstance(d.get("demoted_info"), dict):
                d["demoted_info"] = {}
            return d
    except Exception as e:
        silent_failure("load_state", e)
    return {"paused": {}, "demoted": [], "demoted_info": {}}


def save_state(st):
    tmp = STATE_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(st, f, indent=1)
        os.replace(tmp, STATE_PATH)
    except Exception as e:
        # Without saved state, nobody can resume paused processes after restart.
        silent_failure("save_state", e)


def sig(pid, pgid, s):
    """Send a signal and return 0 on success or errno on failure.

    Error values include ESRCH, EPERM, and others. If signaling the GROUP bounces because
    one unsignalable member blocks the whole atomic killpg, try the single PID too: stopping
    part of the job is better than stopping nothing. The returned errno distinguishes
    "process already dead" (ESRCH, normal) from "not permitted" (EPERM, protection is
    actually incomplete).
    """
    import errno as _e
    error = 0
    if pgid:
        try:
            os.killpg(pgid, s)
            return 0
        except OSError as ex:
            error = ex.errno
    try:
        os.kill(pid, s)
        return 0
    except OSError as ex:
        return ex.errno or error or _e.EPERM


_nie_da_sie = {}          # pid -> comm: processes that CANNOT be paused (EPERM)


def licznik(st, key, amount=1):
    """Increment accumulated guard action counters in state.json.

    Amphetamine counts how long the Mac did NOT sleep. The valuable inverse here is how
    many times the guard actually acted. That proves the product is working instead of just
    sitting in the menu bar, and it is the one statistic competitors cannot have. Counters
    are NEVER reset automatically; a human button does that.
    """
    try:
        # Two sets: "stats" survives launches as the all-time total, while "stats_sesja"
        # resets at daemon start. The menu-bar window says "session statistics", so it must
        # have a session to show. Otherwise the label lies, like counting manual pauses as
        # guard achievements.
        for location in ("stats", "stats_sesja"):
            st.setdefault(location, {})
            st[location].setdefault("since", now())
            st[location][key] = int(st[location].get(key, 0)) + amount
    except Exception:
        pass


def do_pause(cfg, st, targets, reason, manual=False, critical_level=False):
    changed = False
    failed = []
    for pid, cpu, comm, pgid in targets:
        key = str(pid)
        if key in st["paused"] or pid in _nie_da_sie:
            continue
        if cfg["dry_run"]:
            log(T("[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s") % (comm, pid, cpu, reason))
            notify(cfg, T("Thermal guard (watch-only): hot"),
                   T("Would pause %s - %s. Protection is off.") % (comm, reason), "watchonly")
            continue
        # Intent entry before signal, not after it. Writing after SIGSTOP left a millisecond
        # window where a killed daemon (SIGKILL, update, kickstart -k) left a process frozen
        # WITHOUT state, forever, because nobody knew about it. Now the disk note comes
        # first, then the shot; if signaling fails, the note is removed. The only remaining
        # orphan direction is entry without pause, which the loop (stale_entries) or
        # startup do_resume cleans up. One fsync per pause is cheaper than a process in T
        # forever.
        # Store pause reason in the entry. Without it, the "resume only on AC" gate applied
        # to EVERY pause, including purely thermal ones: at battery 11-24%, a job paused for
        # hot chip never returned even though the 10% battery gate was not crossed.
        st["paused"][key] = {"since": now(), "since_mono": time.monotonic(),
                             "mono_id": _MONO_ID,
                             "powod": "bateria" if "batt" in (reason or "").lower()
                                      or "bateri" in (reason or "").lower() else "termika",
                             "comm": comm, "pgid": pgid, "cpu": cpu, "manual": manual}
        save_state(st)
        error = sig(pid, pgid, signal.SIGSTOP)
        if error == 0:
            changed = True
            log(T("PAUSED %s (pid %d, %.0f%% CPU) - %s") % (comm, pid, cpu, reason), tag="PAUSE")
            # Count ONLY guard work. Manual menu-bar freeze is a human decision, not a
            # product achievement, while the statistics window promises the latter.
            if not manual:
                licznik(st, "pauses")
        elif error == errno.ESRCH:
            # The process disappeared between ps and the signal. That is normal, not a
            # failure; remove the intent entry because it describes nothing alive.
            st["paused"].pop(key, None)
            save_state(st)
            log(T("gone before pause: %s (pid %d)") % (comm, pid))
        else:
            # EPERM and the rest mean protection is ACTUALLY INCOMPLETE. Put the name in
            # the skipped set to stop retrying every 15 s and polluting the log, and expose
            # it in status. Remove the intent entry because no pause actually happened.
            st["paused"].pop(key, None)
            save_state(st)
            _nie_da_sie[pid] = comm
            failed.append(comm)
            log(T("FAILED to pause %s (pid %d) - errno %d, giving up on this pid")
                % (comm, pid, error))
    st["_unpausable"] = sorted(set(_nie_da_sie.values()))
    if changed:
        names = ", ".join(sorted(set(v["comm"] for v in st["paused"].values())))
        notify(cfg, T("Thermal guard: hot"), T("Paused: %s (%s)") % (names, reason), "pause")
    if failed and critical_level:
        # Protection failed at critical level; the user MUST know.
        notify(cfg, T("Thermal guard: PROTECTION INCOMPLETE"),
               T("Could not pause: %s (%s). The Mac stays hot - intervene manually.")
               % (", ".join(sorted(set(failed))), reason), key="failpause")
    return changed


def do_resume(cfg, st, reason, only_keys=None, after_cooling=False):
    """Resume frozen jobs, optionally limited to `only_keys`.

    This parameter is critical. The main loop calls `do_resume(..., only_keys=gotowe)`;
    without it, the main resume-after-cooling path raised TypeError, which the loop's broad
    `except` swallowed. A job frozen for overheating never returned to work and only waited
    for SIGTERM after `max_pause_minutes`. Classic silent failure: no log entry looks the
    same as no need to act.
    """
    if not st["paused"]:
        return False
    for key, info in list(st["paused"].items()):
        if only_keys is not None and key not in only_keys:
            continue          # the rest stays frozen deliberately: min pause time or manual
        pid = int(key)
        if alive(pid):
            error = sig(pid, info.get("pgid"), signal.SIGCONT)
            status = run(["ps", "-o", "stat=", "-p", str(pid)]).strip()
            if error == 0 and not status.startswith("T"):
                log(T("RESUMED %s (pid %d) - %s") % (info.get("comm", "?"), pid, reason), tag="RESUME")
                # The stats window says "resumed AFTER COOLING", so manual resume, startup,
                # and daemon shutdown do not count. The label must be true.
                if after_cooling:
                    licznik(st, "resumes")
            elif status.startswith("T"):
                # SIGCONT was sent but the process is STILL stopped: classic SIGTTIN loop.
                # It resumed in the background and tried to read the keyboard. It will not
                # recover by itself.
                log(T("STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, "
                      "type 'fg' in its window") % (info.get("comm", "?"), pid))
                notify(cfg, T("Thermal guard: job needs your hand"),
                       T("%s cannot resume by itself - switch to its terminal and type 'fg'.")
                       % info.get("comm", "?"), key="ttin")
            else:
                log("FAILED to resume %s (pid %d) - errno %d"
                    % (info.get("comm", "?"), pid, error))
                # A failed SIGCONT must NOT delete the entry: the process would stay frozen
                # while guard forgot it, so even restart would not resume it. Count attempts
                # and give up after the fifth so the entry does not remain forever.
                info["proby_wznowienia"] = info.get("proby_wznowienia", 0) + 1
                if info["proby_wznowienia"] < 5:
                    continue
                log("giving up on resuming %s (pid %d) after 5 attempts"
                    % (info.get("comm", "?"), pid))
        del st["paused"][key]
    notify(cfg, T("Thermal guard: cooled down"), T("Resumed paused jobs (%s)") % reason, "resume")
    return True


def _pause_age(v):
    """Return how many seconds this pause has lasted.

    The monotonic clock is valid only inside the same process, see `mono_id`. Otherwise use
    wall time because only it means the same thing after restart.
    """
    m = v.get("since_mono")
    if m is not None and v.get("mono_id") == _MONO_ID:
        return max(0.0, time.monotonic() - m)
    return max(0.0, now() - v.get("since", now()))


def do_terminate(cfg, st, reason, only_keys=None):
    """Send SIGCONT plus SIGTERM, then SIGKILL after 20 s.

    A process in SIGSTOP cannot handle TERM. `only_keys` limits termination to those
    entries so a pause timeout cannot kill freshly stopped jobs. Manual entries, frozen from
    the menu bar, are ALWAYS skipped: a frozen process does not heat anything, so killing it
    cools nothing and would betray the user.

    Re-check right before signaling. The `ps` snapshot from the start of the cycle is
    several seconds old. A manual `kill -CONT` issued mid-cycle used to mean SIGTERM into a
    process running at full speed. Ask the system again HERE: terminate only what is truly
    stopped now. Delete the entry for a process that is running again; if it still heats the
    Mac, the next cycle will freeze it again. A failed measurement (`None`) postpones all
    execution: termination needs proof that something is stopped, and pause is already
    cooling the machine.
    """
    stopped = stopped_now()
    if stopped is None:
        log("ps unavailable - postponing termination decisions")
        return False
    victims = []
    for key, info in list(st["paused"].items()):
        if only_keys is not None and key not in only_keys:
            continue
        if info.get("manual"):
            continue
        pid = int(key)
        if not alive(pid):
            del st["paused"][key]
            continue
        if cfg["dry_run"]:
            log(T("[DRY-RUN] would terminate %s (pid %d) - %s") % (info.get("comm"), pid, reason))
            continue
        if not entry_stopped(key, info, *stopped):
            log(T("dropping stale pause entry: %s (pid %s) is running again "
                  "- resumed outside the guard") % (info.get("comm", "?"), key))
            del st["paused"][key]
            continue
        sig(pid, info.get("pgid"), signal.SIGCONT)
        sig(pid, info.get("pgid"), signal.SIGTERM)
        victims.append((pid, info))
        log(T("TERMINATED (SIGTERM) %s (pid %d) - %s") % (info.get("comm", "?"), pid, reason), tag="KILL")
        licznik(st, "kills")
        del st["paused"][key]
    if victims:
        notify(cfg, T("Thermal guard: STOPPED"),
               T("Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.")
               % reason, "kill")
        time.sleep(20)
        for pid, info in victims:
            # The group may live after the leader dies because children ignore TERM. killpg
            # on a dead group simply bounces with an error that we swallow.
            if info.get("pgid") or alive(pid):
                if sig(pid, info.get("pgid"), signal.SIGKILL) == 0:
                    log("SIGKILL %s (pid %d)" % (info.get("comm", "?"), pid))
    return bool(victims)


def demote_threshold(cfg):
    """Return the chip threshold where demotion has thermal value.

    Below it, the machine is cool and pushing anyone to E-cores cools nothing; it only cuts
    throughput. An overnight queue showed ffmpeg at 44 C running 11x slower while fans were
    stopped. Default is soc_resume_c + 4, with return at soc_resume_c, leaving a real
    hysteresis gap between demotion and promotion instead of one flickering line.
    """
    p = cfg.get("demote_above_c")
    if p is not None:
        return float(p)
    return float(cfg.get("soc_resume_c", 80.0)) + 4.0


_demote_nie_da_sie = set()    # PIDs taskpolicy rejected, usually another owner


def do_demote(cfg, st, targets, cpu_hist, soc_t, saferun_normal=frozenset()):
    """Move long-running hot processes to background QoS on E-cores.

    The cpu_hist clock counts ACCUMULATED seconds of active grinding, not time since first
    seen. A SIGSTOP-paused process leaves targets, and the old clock reset after every
    resume, so the hottest job never accumulated 5 minutes and escaped demotion.
    """
    limit = cfg["demote_after_minutes"] * 60
    for pid, cpu, comm, pgid in targets:
        if cpu < cfg["demote_cpu_percent"] or pid in _demote_nie_da_sie:
            continue
        # safe-run --normal means a human explicitly chose all cores. Demoting it 5 minutes
        # later would undo that decision behind their back. Pause on overheating still
        # applies; this exception covers ONLY demotion.
        if pid in saferun_normal or pgid in saferun_normal:
            continue
        zebral = cpu_hist.get(pid, 0.0) + cfg["poll_seconds"]
        cpu_hist[pid] = zebral
        if zebral < limit or pid in st["demoted"]:
            continue
        # Without a chip reading, demotion has no thermal justification. Do not guess.
        if soc_t is None or soc_t < demote_threshold(cfg):
            continue
        if cfg["dry_run"]:
            log(T("[DRY-RUN] would demote %s (pid %d)") % (comm, pid))
            continue
        # taskpolicy only, no renice: once nice is raised, it cannot be returned without
        # root because Unix lets unprivileged users only increase nice. taskpolicy -b/-B is
        # fully reversible, and background QoS is what does the work here (E-cores).
        rc = subprocess.call(["taskpolicy", "-b", "-p", str(pid)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc != 0:
            # Another user's process, often root: taskpolicy bounced. Without this check,
            # it would be added to demoted and reported as "slowed down" while still running
            # at full speed, so the log would lie. Add the PID to the skipped set; otherwise
            # almost every cycle would fork taskpolicy and write the same log line.
            if pid not in _demote_nie_da_sie:
                _demote_nie_da_sie.add(pid)
                log("DEMOTE failed for %s (pid %d) - taskpolicy rc=%d (not our process?)"
                    % (comm, pid, rc))
            continue
        st["demoted"].append(pid)
        # Name in state: demotion can cut throughput by 11x, so humans and agents MUST see
        # it in status.json. A PID alone tells them nothing.
        st.setdefault("demoted_info", {})[str(pid)] = {"comm": comm}
        log(T("DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)")
            % (comm, pid, cfg["demote_after_minutes"]), tag="DEMOTE")
        # Pause has sound and push, and demotion has a larger lasting effect on job time.
        # Pause passes; slowdown remains, so it must be audible too.
        notify(cfg, T("Thermal guard: job slowed down"),
               T("%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools") % comm,
               "demote")


def do_promote(cfg, st, cpu_hist, soc_t):
    """Promote demoted jobs back to P-cores after the machine cools.

    Without this hysteresis return, demotion was one-way: once pushed to E-cores, a process
    stayed there until death, even at 44 C with stopped fans.
    """
    if not st["demoted"] or cfg["dry_run"]:
        return
    if soc_t is None or soc_t > cfg.get("soc_resume_c", 80.0):
        return
    for pid in list(st["demoted"]):
        if not alive(pid):
            continue
        info = st.get("demoted_info", {}).get(str(pid), {})
        subprocess.call(["taskpolicy", "-B", "-p", str(pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st["demoted"].remove(pid)
        st.get("demoted_info", {}).pop(str(pid), None)
        # Reset the clock: promotion should be a real return, not a 15-second pause before
        # immediate demotion again.
        cpu_hist[pid] = 0.0
        log(T("PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)")
            % (info.get("comm", "?"), pid), tag="PROMOTE")
        notify(cfg, T("Thermal guard: full speed again"),
               T("%s is back on P-cores") % info.get("comm", "?"), "promote")


# ---------------------------------------------------------------- severity

def severity(cfg, state, temp, speed, soc=None, ac=True, pct=None):
    """Return severity level 0 cool, 1 warm, 2 hot (pause), or 3 critical (terminate).

    `temp` is battery temperature, slow and inertial. `soc` is chip temperature, fast.
    Use the stricter of the two: the chip catches load spikes within seconds, while the
    battery confirms that the whole chassis has warmed.
    """
    lvl = 0
    why = []
    if soc is not None:
        if soc >= cfg.get("soc_kill_c", 100.0):
            lvl = max(lvl, 3); why.append(T("chip %.1f C") % soc)
        elif soc >= cfg.get("soc_pause_c", 92.0):
            lvl = max(lvl, 2); why.append(T("chip %.1f C") % soc)
        elif soc >= cfg.get("soc_pause_c", 92.0) - 7:
            lvl = max(lvl, 1); why.append(T("chip %.1f C") % soc)
    # Battery gate: on battery power below the threshold, pause so a long computation does
    # not die with the laptop mid-block. Wait for AC.
    if not ac and pct is not None and pct <= cfg.get("batt_pct_pause", 10):
        lvl = max(lvl, 2); why.append(T("battery %d%% on battery power") % pct)
    s = LEVELS.get(state, 1)
    if s >= 3:
        lvl = max(lvl, 3); why.append(T("thermal state=critical"))
    elif s >= LEVELS.get(cfg["pause_on_thermal_state"], 2):
        lvl = max(lvl, 2); why.append(T("thermal state=%s") % state)
    elif s == 1:
        lvl = max(lvl, 1); why.append(T("thermal state=fair"))
    if temp is not None:
        if temp >= cfg["batt_kill_c"]:
            lvl = max(lvl, 3); why.append(T("battery %.1f C") % temp)
        elif temp >= cfg["batt_pause_c"]:
            lvl = max(lvl, 2); why.append(T("battery %.1f C") % temp)
        elif temp >= cfg["batt_pause_c"] - 3:
            lvl = max(lvl, 1); why.append(T("battery %.1f C") % temp)
    if speed < cfg["speed_limit_pause"]:
        lvl = max(lvl, 2); why.append(T("CPU throttled to %d%%") % speed)
    return lvl, ", ".join(why)


def boot_time():
    """Return the last system boot time as epoch seconds."""
    m = re.search(r"sec\s*=\s*(\d+)", run(["sysctl", "-n", "kern.boottime"]))
    return int(m.group(1)) if m else 0


def record_event(event_type, description, context=None, synthetic=False, when=None):
    """Write black-box events that must survive restart and enter the report.

    synthetic=True marks a test or harness entry. thermal-report skips it so a synthetic
    crash never enters warranty evidence.
    """
    try:
        with open(EVENTS_PATH, "a") as f:
            # `when` is the EVENT epoch. Without it, the file stored detection time, and a
            # hard shutdown is detected only at startup after reboot. A report for the crash
            # day then said "no hard shutdown detected in this period".
            # That is the worst possible false negative in an insurance document.
            t = when if when else now()
            entry = {"time": ts(t), "epoch": round(t, 3), "detected_at": ts(),
                    "type": event_type, "description": description}
            if synthetic:
                entry["synthetic"] = True
            if context:
                entry["context"] = context
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Evidence that silently failed to be written is worse than no evidence.
        silent_failure("record_event", e)


def crash_already_recorded(crash_epoch, tolerance=90.0):
    """Return whether the same hard shutdown is already in the black box.

    Compare the EVENT MOMENT (`epoch`), not detection time. The same crash detected on
    three later daemon starts has three different `detected_at` values but one `epoch`.
    The 90 s tolerance covers the case where one heartbeat came from file contents and
    another from mtime fallback: same event, slightly different number.

    Two REAL crashes with the same last-heartbeat time cannot exist: there must be a boot
    and at least one daemon cycle ticking heartbeat between them.
    """
    try:
        with open(EVENTS_PATH, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return False
    # Tail is enough: duplicates are created by consecutive starts, so they sit together.
    for line in reversed(lines[-200:]):
        try:
            z = json.loads(line)
        except ValueError:
            continue
        if not isinstance(z, dict) or z.get("type") != "HARD_SHUTDOWN" or z.get("synthetic"):
            continue
        e = z.get("epoch")
        if isinstance(e, (int, float)) and abs(e - crash_epoch) <= tolerance:
            return True
    return False


def detect_hard_shutdown():
    """Detect whether the previous session ended in a hard shutdown.

    Guard ticks `heartbeat` on every pass and writes `clean_stop` on clean shutdown. If,
    after reboot, the last heartbeat is from BEFORE this boot and has no clean shutdown next
    to it, the Mac died without warning. Store the event with the last measurements before
    the crash; this is the evidence system logs often do not preserve.
    """
    try:
        if not os.path.exists(HEARTBEAT_PATH):
            return None
        # The heartbeat CONTENT is authoritative: epoch is independent of timezone and DST.
        # A westbound flight or fall time change would move textual dates "forward" and
        # silence a crash. mtime is only a last resort: it survives cp -p, but restore
        # without -p sets "now" and would also mask a crash. Format: "<epoch> <human date>".
        # The older text-only format is read the old way during transition.
        boot = boot_time()
        puls = None
        raw = ""
        try:
            with open(HEARTBEAT_PATH) as f:
                raw = f.read().strip()
            puls = float(raw.split(None, 1)[0])
        except Exception:
            pass
        if puls is None:
            try:
                puls = time.mktime(time.strptime(raw, "%Y-%m-%d %H:%M:%S"))
                mt = os.path.getmtime(HEARTBEAT_PATH)
                # Legacy text carries no timezone. Read after a timezone change, it can
                # jump past boot and silence a crash. If mtime says the heartbeat was before
                # boot, trust mtime for this one post-upgrade detection window.
                if boot and puls >= boot > mt:
                    puls = mt
            except Exception:
                puls = os.path.getmtime(HEARTBEAT_PATH)
        if not boot or puls >= boot:
            return None                       # heartbeat from the current session; nothing happened

        # --- confidence level instead of silence -------------------------------------
        # Up to 2.1.7, every "suspicious" case ended with `return None`, meaning silence.
        # That is the worst behavior for a black box: a dead RTC or NTP jump permanently
        # erased evidence, and the 30-day floor threw it away instead of labeling it.
        # The opposite is also possible: a daemon killed by SIGKILL or `launchctl bootout`
        # before normal reboot leaves a heartbeat before boot with no clean_stop, and that
        # event was fabricated as a hard shutdown on a day when the Mac behaved correctly.
        #
        # None of these cases can be resolved locally and cheaply. Always write evidence,
        # but include explicit confidence. The evidence document must tell the truth about
        # how certain it is. A human service reviewer decides, not daemon heuristics.
        confidence, confidence_reason = "high", ""
        gap = boot - puls                    # elapsed time between last heartbeat and boot
        if gap > 30 * 86400:
            confidence = "low"
            confidence_reason = T(
                "the last heartbeat is %d days before boot - the clock was most likely wrong "
                "(dead RTC, NTP jump) or the data came from a backup") % int(gap // 86400)
        elif gap > 12 * 3600:
            confidence = "low"
            confidence_reason = T(
                "%.1f h passed between the last heartbeat and boot - the guard may have been "
                "killed long before the Mac actually went down") % (gap / 3600.0)
        clean_stop = os.path.getmtime(CLEAN_STOP_PATH) if os.path.exists(CLEAN_STOP_PATH) else 0
        # The clean-shutdown marker counts ONLY when it predates the current boot. A
        # clean_stop from the current session or an artifact (backup, cp -p, future clock)
        # must not silence a real hard shutdown.
        if puls - 60 <= clean_stop < boot:
            return None                       # guard was shut down cleanly
        # Last measurements before power loss; this is evidence.
        tail = []
        try:
            with open(HIST_PATH) as f:
                iter_lines = f.readlines()
            header = iter_lines[0].strip().split(",") if iter_lines else []
            for w in iter_lines[-8:]:
                if w.strip() and not w.startswith("time,"):
                    tail.append(dict(zip(header, w.strip().split(","))))
        except Exception:
            pass
        # Describe the same crash EXACTLY ONCE. If the daemon dies before it can tick
        # heartbeat, such as a crash in the first seconds after start or a launchd restart
        # loop, every later start sees the same old heartbeat and writes the same event
        # again. Three starts then look like three separate failures in a claim document.
        # An inflated failure count is worse than none because it undermines the report.
        if crash_already_recorded(puls):
            return None
        description = (T("Mac went down without a clean shutdown. Guard's last heartbeat: %s, "
                "system booted: %s.") % (ts(puls), ts(boot)))
        if confidence == "low":
            description += " " + T("CONFIDENCE: LOW - %s.") % confidence_reason
        record_event("HARD_SHUTDOWN", description,
                         {"last_readings": tail, "confidence": confidence,
                          "confidence_reason": confidence_reason,
                          "gap_to_boot_s": round(gap, 1)},
                         when=puls)
        log(T("!!! HARD SHUTDOWN DETECTED - ") + description, tag="CRASH")
        return {"time": ts(puls), "description": description, "readings": tail,
                "confidence": confidence}
    except Exception:
        return None


def handle_command(cfg, st, targets):
    """Handle menu-bar commands for manual freeze and resume."""
    try:
        if not os.path.exists(COMMAND_PATH):
            return
        with open(COMMAND_PATH) as f:
            command = f.read().strip()
        os.remove(COMMAND_PATH)
    except Exception:
        return
    if command == "freeze" or command.startswith("freeze:"):
        # "freeze" = everything eligible; "freeze:123,456" = only selected PIDs from the
        # confirmation window. Selection filters candidates and does NOT bypass any rule:
        # a process outside targets will still not be touched.
        if command.startswith("freeze:"):
            wanted_pids = set()
            for piece in command.split(":", 1)[1].split(","):
                piece = piece.strip()
                if piece.isdigit():
                    wanted_pids.add(int(piece))
            targets = [t for t in (targets or []) if t[0] in wanted_pids]
        # Set the flag ONLY when something was really frozen; otherwise the menu bar lies.
        if targets and do_pause(cfg, st, targets, T("MANUAL FREEZE (from the menu bar)"), manual=True):
            st["reczna_pauza"] = True
        else:
            log(T("manual freeze: there was nothing to freeze"))
            notify(cfg, T("Nothing to freeze"),
                   T("No heavy job meets the conditions"), key="freeze")
    elif command == "resume":
        st["reczna_pauza"] = False
        do_resume(cfg, st, T("manual resume (from the menu bar)"))


def day_stats():
    """Return how many times guard intervened today for menu-bar display."""
    today = time.strftime("%Y-%m-%d")
    pauses = resumes = kills = 0
    try:
        # errors="replace": one non-UTF-8 byte from a truncated write or crash junk used to
        # crash the decoder on the first readline and zero the whole daily statistic. The
        # menu bar showed "today 0 pauses" after a night full of pauses, with no signal.
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.startswith(today):
                    continue
                # Tags are the parser contract (see log()): identical in every
                # language, so no word matching is needed.
                if "[KILL]" in line:
                    kills += 1
                elif "[PAUSE]" in line:
                    pauses += 1
                elif "[RESUME]" in line:
                    resumes += 1
    except Exception:
        pass
    return {"pauses": pauses, "resumes": resumes, "kills": kills}


_trend = []


def trend_and_forecast(cfg, soc_t):
    """Return chip C/min growth and minutes until it reaches the pause threshold.

    This exposes the problem before freeze time instead of only when the pause happens.
    """
    if soc_t is None:
        return None, None
    _trend.append((now(), soc_t))
    while len(_trend) > 8 or (_trend and now() - _trend[0][0] > 300):
        _trend.pop(0)
    if len(_trend) < 3:
        return None, None
    dt = (_trend[-1][0] - _trend[0][0]) / 60.0
    if dt <= 0:
        return None, None
    slope = (_trend[-1][1] - _trend[0][1]) / dt      # C per minute
    threshold = cfg.get("soc_pause_c", 85.0)
    if slope <= 0.5 or soc_t >= threshold:
        return round(slope, 1), None
    return round(slope, 1), round((threshold - soc_t) / slope, 1)


def saferun_jobs():
    """Return active jobs started by safe-run, with name and runtime."""
    out = []
    try:
        for name in os.listdir(MANAGED_DIR):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(MANAGED_DIR, name)) as f:
                d = json.load(f)
            pid = int(d.get("pid", 0))
            if pid and alive(pid):
                out.append({"name": d.get("name") or d.get("comm") or "?",
                            "pid": pid,
                            "queued": bool(d.get("queued")),
                            "minutes": round(proc_age_seconds(pid) / 60.0)})
    except Exception:
        pass
    return out


def _admission_entries():
    """Return (running, queued) admission entries from managed/ registrations.

    running: jobs already started (queued flag absent or false), with their
    declared core count. A registration without a declaration counts as ALL
    performance cores: admission exists to protect the machine, so an
    undeclared job is assumed big, not small.
    queued: wrapper pre-registrations waiting for admission, oldest first.
    """
    running, queued = [], []
    try:
        p_cores = _admission_p_cores()
        for name in os.listdir(MANAGED_DIR):
            if not name.endswith(".json"):
                continue
            try:
                path = os.path.join(MANAGED_DIR, name)
                # Same trust bar as the signal path: a registration that
                # managed_pids_from_saferun would reject for unsafe ownership
                # or permissions must not consume the admission budget either,
                # or a planted file starves every honest job in the queue.
                file_stat = os.lstat(path)
                if file_stat.st_uid != os.getuid() or (file_stat.st_mode & 0o022):
                    continue
                with open(path) as f:
                    d = json.load(f)
                pid = int(d.get("pid", 0))
                if not pid or not alive(pid):
                    continue
                if d.get("started"):
                    age = proc_age_seconds(pid)
                    if age and abs((now() - age) - float(d["started"])) > 90:
                        continue          # recycled pid; the managed scan unlinks it
                cores = d.get("cores")
                try:
                    # Cap at the pool: a declaration above it could never be
                    # admitted and would freeze the queue from the head.
                    cores = min(max(1, int(cores)), p_cores)
                except (TypeError, ValueError):
                    cores = p_cores
                entry = {"pid": pid, "name": str(d.get("name") or "?")[:24],
                         "cores": cores}
                if d.get("queued"):
                    try:
                        entry["priority"] = int(d.get("priority", 5))
                    except (TypeError, ValueError):
                        entry["priority"] = 5
                    try:
                        entry["since"] = float(d.get("since") or 0)
                    except (TypeError, ValueError):
                        entry["since"] = 0.0
                    queued.append(entry)
                else:
                    running.append(entry)
            except Exception:
                continue
    except Exception:
        pass
    return running, queued


def _admission_p_cores():
    """Performance-core count for the admission budget, from hardware.json."""
    try:
        with open(HW_PATH) as f:
            p = int(json.load(f).get("p_cores") or 0)
        if p > 0:
            return p
    except Exception:
        pass
    return max(1, (os.cpu_count() or 8) // 2 + (os.cpu_count() or 8) % 2)


def admission_update(cfg, soc_t, lvl, load1):
    """Decide which queued safe-run jobs may start; return the published state.

    Budget in cores follows the thermal headroom: chip at or below the resume
    threshold means the full performance-core pool, between resume and pause
    half of it, at or above pause (or guard level >= 2) no new admissions.
    Load generated OUTSIDE registered jobs shrinks the budget too, so a bare
    process chewing six cores is not scheduled over.

    The arbiter only delays starts. On any internal error it admits everyone:
    a broken optimizer must never become a second kill switch that silently
    keeps jobs from ever starting. Thermal safety stays with the pause logic.
    """
    try:
        running, queued = _admission_entries()
        p_cores = _admission_p_cores()
        if lvl >= 2:
            budget = 0
        elif soc_t is None:
            budget = p_cores
        elif soc_t >= cfg.get("soc_pause_c", 85.0):
            budget = 0
        elif soc_t > cfg.get("soc_resume_c", 76.0):
            budget = max(1, p_cores // 2)
        else:
            budget = p_cores
        used = sum(e["cores"] for e in running)
        # Load of unregistered work: whatever load1 shows beyond the declared
        # sum. Rounded down so normal scheduling noise does not eat the budget.
        foreign = max(0, int((load1 or 0) - used))
        free = budget - used - foreign
        # Lower priority value goes first; equal priorities keep arrival order.
        # Head-of-line blocking is deliberate: a small job must not overtake,
        # simplicity beats cleverness here.
        queued.sort(key=lambda e: (e.get("priority", 5), e.get("since", 0.0)))
        admitted = []
        for e in queued:
            if e["cores"] > free:
                break
            admitted.append(e["pid"])
            free -= e["cores"]
        return {"enabled": True, "budget_cores": budget, "used_cores": used,
                "foreign_load": foreign, "admitted": admitted,
                "queued": [{"pid": e["pid"], "name": e["name"], "cores": e["cores"],
                            "priority": e.get("priority", 5),
                            "since": e.get("since", 0.0)} for e in queued]}
    except Exception as e:
        silent_failure("admission", e)
        _, queued = _admission_entries()
        return {"enabled": True, "budget_cores": -1, "used_cores": 0,
                "foreign_load": 0, "error": True,
                "admitted": [q["pid"] for q in queued], "queued": []}


# ---------------------------------------------------------------- hardware and calibration

def hardware_info():
    """Detect this Mac's hardware and write hardware.json.

    Used by About my Mac and calibration. Slow reads such as system_profiler (~2 s) happen
    ONCE at startup; the file is the cache.
    """
    def sysctl(k):
        return run(["sysctl", "-n", k]).strip()

    hw = {
        "chip": sysctl("machdep.cpu.brand_string") or "Apple Silicon",
        "model_id": sysctl("hw.model"),
        "p_cores": int(sysctl("hw.perflevel0.physicalcpu") or 0),
        "e_cores": int(sysctl("hw.perflevel1.physicalcpu") or 0),
        "cores": int(sysctl("hw.ncpu") or 0),
        "ram_gb": round(int(sysctl("hw.memsize") or 0) / 1024.0 ** 3),
        "macos": run(["sw_vers", "-productVersion"]).strip(),
    }
    prof = run(["system_profiler", "SPHardwareDataType"], timeout=30)
    m = re.search(r"Model Name:\s*(.+)", prof)
    hw["model_name"] = m.group(1).strip() if m else hw["model_id"]
    m = re.search(r"Serial Number.*?:\s*(\S+)", prof)
    hw["serial"] = m.group(1) if m else ""
    ioreg = run(["ioreg", "-r", "-c", "AppleSmartBattery", "-d", "1", "-w", "0"], timeout=15)
    m = re.search(r'"CycleCount"\s*=\s*(\d+)', ioreg)
    hw["battery_cycles"] = int(m.group(1)) if m else None
    m = re.search(r'"PermanentFailureStatus"\s*=\s*(\d+)', ioreg)
    hw["battery_failure"] = bool(int(m.group(1))) if m else None
    # Maximum capacity: how much of factory cell capacity remains.
    m1 = re.search(r'"NominalChargeCapacity"\s*=\s*(\d+)', ioreg)
    m2 = re.search(r'"DesignCapacity"\s*=\s*(\d+)', ioreg)
    if m1 and m2 and int(m2.group(1)) > 0:
        hw["battery_max_capacity_pct"] = round(100 * int(m1.group(1)) / int(m2.group(1)))
    # One failed macmon read must NOT decide calibration. Sampling can fail on a loaded
    # machine, and first daemon start often follows `install.sh`, which compiled the menu
    # bar. `max_age=0` bypasses the 10-second cache; otherwise retry would return the same
    # None. Use a BUDGET, not a retry count: `run()` gives macmon 20 s per path and
    # soc_sensors tries two paths. Blind retries could delay daemon start by two minutes,
    # with nobody watching temperature.
    s = soc_sensors()
    probe_deadline = time.monotonic() + 8.0
    while not s and time.monotonic() < probe_deadline:
        time.sleep(2.0)
        s = soc_sensors(max_age=0)
    hw["fan_count"] = len((s or {}).get("fans") or [])
    hw["chip_sensor"] = bool(s)
    try:
        with open(HW_PATH, "w") as f:
            json.dump(hw, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return hw


def auto_calibrate(cfg, hw):
    """Fit thresholds to THIS Mac, once per hardware identity.

    Never run after manual threshold changes. There is no single correct threshold. A Mac
    with fans tolerates 85-95 C; a fanless Mac (Air) dumps heat through the chassis and must
    be cut earlier, and a "fans stopped" alarm is meaningless. calibrated_for ensures
    calibration runs only on the first launch for this hardware; deliberate user thresholds
    are sacred.
    """
    # The tag must include sensor information too. Without macmon, `fan_count` is 0 just as
    # on a real Air, so calibration wrote tag "fans=0". After macmon was installed, the Air
    # had the same tag and never received fanless thresholds (78/70/88), on the machine
    # where those thresholds matter most.
    tag = "%s|%s|fans=%s|sensor=%s" % (hw.get("model_id"), hw.get("chip"),
                                       hw.get("fan_count"), bool(hw.get("chip_sensor")))
    try:
        with open(CFG_PATH) as f:
            _on_disk = json.load(f)
    except Exception:
        _on_disk = {}
    dry_hidden = "dry_run" not in _on_disk
    if cfg.get("calibrated_for") == tag:
        if not dry_hidden:
            return None
        # Hardware known, but dry_run is implicit from pre-v1.3 config. Write it explicitly.
        # Read-modify-write under lock because the menu bar may write concurrently.
        try:
            with config_lock():
                try:
                    with open(CFG_PATH) as f:
                        _on_disk = json.load(f)
                except Exception:
                    _on_disk = {}
                _on_disk["dry_run"] = True
                tmp = CFG_PATH + ".tmp"
                # 0600, not umask: config.json contains the ntfy topic. `ensure_dirs`
                # tightens permissions only at startup, so calibration/migration writes
                # otherwise relaxed the hardening until the next restart.
                with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                                       0o600), "w") as f:
                    json.dump(_on_disk, f, indent=2, ensure_ascii=False, sort_keys=True)
                os.replace(tmp, CFG_PATH)
        except Exception:
            pass
        log("MIGRATION: dry_run was implicit - written explicitly as true (watch-only)")
        return "watchonly"
    # Without a sensor read, `fan_count=0` means TWO different things: "fanless Mac" or
    # "macmon did not answer". Writing the tag in this state leaves an Air on fan-equipped
    # thresholds (85/76/90) and a 45 min pause limit until the next daemon restart. The
    # daemon has KeepAlive, so restart may be a week away. With a blind sensor, do NOT write
    # the tag; calibration must retry.
    blind_sensor = not hw.get("chip_sensor")
    changes = {} if blind_sensor else {"calibrated_for": tag}
    if dry_hidden:
        changes["dry_run"] = True
    # `soc_kill_c` MUST be in this condition: calibration overwrites it together with the
    # pause/resume pair, so a user who manually raised only the kill threshold lost it on
    # first calibration (95.0 -> 88.0).
    untouched = (cfg.get("soc_pause_c") == DEFAULTS["soc_pause_c"]
                 and cfg.get("soc_resume_c") == DEFAULTS["soc_resume_c"]
                 and cfg.get("soc_kill_c") == DEFAULTS["soc_kill_c"])
    if hw.get("fan_count") == 0 and hw.get("chip_sensor"):
        changes["fan_check"] = False          # fan alarm on an Air is always false
        if untouched:
            changes.update({"soc_pause_c": 78.0, "soc_resume_c": 70.0, "soc_kill_c": 88.0})
            log("CALIBRATION: fanless Mac detected (%s) - chip thresholds 78/70/88"
                % hw.get("model_name"))
        # Fanless Macs pause more often and longer because the chassis sheds heat slowly.
        # A 45 min pause limit would kill long jobs that are simply waiting to cool.
        if cfg.get("max_pause_minutes") == DEFAULTS["max_pause_minutes"]:
            changes["max_pause_minutes"] = 120
    elif blind_sensor:
        # Do not be silent: without this line, the log said "thresholds defaults OK" on a
        # machine that was NOT calibrated. A minute later `heat` can show chip temperature
        # and everything looks healthy, so nobody would notice.
        log("CALIBRATION DEFERRED: no chip sensor reading (macmon missing or busy) - "
            "cannot tell a fanless Mac from a failed probe; thresholds left at %s/%s, "
            "will retry on next start"
            % (cfg.get("soc_pause_c"), cfg.get("soc_resume_c")))
    else:
        log("CALIBRATION: %s, %s (%dP+%dE), %d GB RAM, fans: %s - thresholds %s"
            % (hw.get("model_name"), hw.get("chip"), hw.get("p_cores", 0),
               hw.get("e_cores", 0), hw.get("ram_gb", 0), hw.get("fan_count"),
               "left as user set them" if not untouched else "defaults OK"))
    # With a blind sensor and explicit dry_run, there is NOTHING to write. An empty write is
    # not harmless: this path uses plain open(), so every start would relax config.json
    # permissions (it contains the ntfy topic) until the next `ensure_dirs`.
    if not changes:
        return "watchonly" if dry_hidden else None
    # Read-modify-write under lock: a concurrent menu-bar write must not be lost.
    try:
        with config_lock():
            try:
                with open(CFG_PATH) as f:
                    disk_cfg = json.load(f)
            except Exception:
                disk_cfg = {}
            disk_cfg.update(changes)
            tmp = CFG_PATH + ".tmp"
            # 0600 through os.open, not plain open(): the migration path above has done
            # this for a long time, but this path did not. With umask(0), a 0600 config
            # left calibration as 0666, and it contains the ntfy topic.
            with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                                   0o600), "w") as f:
                json.dump(disk_cfg, f, indent=2, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, CFG_PATH)
    except Exception:
        pass
    return "watchonly" if dry_hidden else None


# ---------------------------------------------------------------- manual keep-awake

_net = {"t": 0.0, "bytes": 0, "last_active": 0.0}


def network_active(threshold_kbps=500):
    """Return whether network transfer is active.

    Uses a byte delta from netstat -ib. The 120 s hysteresis keeps a short silence between
    files from releasing the sleep assertion.
    """
    out = run(["netstat", "-ib"], timeout=10)
    total = 0
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) >= 10 and not p[0].startswith("lo") and "<Link" in line:
            try:
                total += int(p[6]) + int(p[9])
            except (ValueError, IndexError):
                pass
    t = now()
    prev_t, prev_b = _net["t"], _net["bytes"]
    _net["t"], _net["bytes"] = t, total
    if prev_t and total >= prev_b:
        kbps = (total - prev_b) / 1024.0 / max(t - prev_t, 1.0)
        if kbps >= threshold_kbps:
            _net["last_active"] = t
    return t - _net["last_active"] < 120


def manual_awake(cfg):
    """Return the manual keep-awake mode set from the menu bar.

    Reads awake.json modes timer, app, and download. Returns (active, description). An
    expired timer cleans itself up so the menu bar does not show dead state. The thermal
    guard is higher priority; the main loop decides that, not this helper.
    """
    try:
        with open(AWAKE_PATH) as f:
            a = json.load(f)
    except Exception:
        return False, None
    mode = a.get("mode")
    if mode == "timer":
        until = float(a.get("until") or 0)
        if now() < until:
            return True, a
        try:
            os.remove(AWAKE_PATH)
        except Exception:
            pass
        return False, None
    if mode == "forever":
        return True, a
    if mode == "app":
        app = (a.get("app") or "").strip()
        if app and run(["pgrep", "-if", app]).strip():
            return True, a
        return False, a
    if mode == "download":
        return network_active(cfg.get("download_kbps", 500)), a
    return False, None


_hostname_cache = {"v": None}


def hostname():
    if _hostname_cache["v"] is None:
        v = run(["scutil", "--get", "ComputerName"]).strip()
        if not v:
            import socket
            v = socket.gethostname()
        _hostname_cache["v"] = re.sub(r"[^A-Za-z0-9._ -]", "_", v) or "mac"
    return _hostname_cache["v"]


_caff = {"proc": None}


def keep_awake_update(cfg, targets, lvl, st=None):
    """Hold or release the sleep assertion through system caffeinate.

    Hold condition: (automatic mode with a heavy job OR manual menu-bar mode: timer, while
    an app runs, or while downloading) AND level < 2 (cool). Every other combination
    releases the assertion. This is the difference from Caffeine/Amphetamine: there, the
    human must remember to turn it off; here, physics turns it off.
    """
    manual, adesc = manual_awake(cfg)
    if st is not None:
        st["_awake_mode"] = (adesc or {}).get("mode") if manual else None
        st["_awake_until"] = (adesc or {}).get("until") if manual else None
        st["_awake_app"] = (adesc or {}).get("app") if manual else None
    proc = _caff["proc"]
    alive_now = proc is not None and proc.poll() is None
    auto = bool(cfg.get("keep_awake_auto")) and bool(targets)
    # Decay: queued files have gaps between old encoder exit and next encoder start.
    # Stopping immediately in that gap caused 45-59 switches per day, and an aggressively
    # sleeping Mac could go to sleep in the middle of an overnight queue. Keep wake for
    # keep_awake_hold_s after the last heavy job. Decay only EXTENDS a live assertion and
    # never starts one. It does NOT apply to heat release: the whole condition still rests
    # on `lvl < 2`, so heat drops the assertion immediately. Monotonic time is process-local;
    # an NTP jump must not extend wake.
    if auto:
        _caff["ostatni_job"] = time.monotonic()
    hold = max(0, cfg.get("keep_awake_hold_s", 300))
    decay_active = (not auto and bool(cfg.get("keep_awake_auto")) and alive_now
                and _caff.get("ostatni_job") is not None
                and time.monotonic() - _caff["ostatni_job"] < hold)
    want_awake = (auto or manual or decay_active) and lvl < 2
    # Display is a SEPARATE decision from system wake. `-is` keeps the system awake but lets
    # the display sleep; `-d` keeps the display on too (presentation, dashboard, render
    # preview). The display costs power and heat, so it defaults OFF and yields to the guard
    # like the rest of wake because the whole condition rests on `lvl < 2`.
    want_display = bool(cfg.get("keep_awake_display"))
    # Replace the process ONLY when wake should continue. Otherwise a display-mode change
    # coinciding with overheating would take the process away from the stop branch, and the
    # "wake yielded to heat" counter would miss the event.
    if want_awake and alive_now and _caff.get("display") != want_display:
        # Runtime change: caffeinate flags cannot be edited, so replace the process.
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=1)
            except Exception:
                pass
        _caff["proc"] = None
        proc = None
        alive_now = False
        _loguj_awake("KEEP-AWAKE restart (display mode changed to %s)"
                     % ("on" if want_display else "off"))
    if want_awake and not alive_now:
        try:
            _caff["proc"] = subprocess.Popen(
                ["caffeinate", "-isd"] if want_display else ["caffeinate", "-is"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _caff["display"] = want_display
            _loguj_awake("KEEP-AWAKE start (heavy job running, machine cool)%s"
                         % (" [screen stays on]" if want_display else ""))
            play_sound(cfg, "awake")   # Funk: guard takes the cup
        except Exception:
            _caff["proc"] = None
    elif not want_awake and alive_now:
        try:
            proc.terminate()
            proc.wait(timeout=3)      # without wait(), every start/stop cycle leaves a zombie
        except Exception:
            try:
                proc.kill()           # stubborn caffeinate, unlikely but cheap to handle
                proc.wait(timeout=1)
            except Exception:
                pass
        _caff["proc"] = None
        # Distinguish TWO stop reasons. "Job finished" is normal. "Machine too hot" is when
        # the guard did its job, and only that counts because only that proves the product
        # acted.
        due_to_heat = (auto or manual) and lvl >= 2
        if due_to_heat and st is not None:
            licznik(st, "awake_released_hot")
        _loguj_awake("KEEP-AWAKE stop (%s)"
                     % ("machine too hot" if due_to_heat else "job done or disabled"))
    return _caff["proc"] is not None and _caff["proc"].poll() is None


_awake_log = {"ostatni": "", "kiedy": 0.0, "pominiete": 0}


def _loguj_awake(msg):
    """Log keep-awake state changes without flooding.

    Keep-awake toggles in rhythm with pauses; one x265 encoder produced 209 entries per
    hour, more than the pauses themselves. The event is real, but as a log stream it is
    noise that drowns black-box entries. Log state changes no more than every 10 minutes,
    and on the next entry report how many switches fit into that time.
    """
    t = now()
    # The repeated-message condition MUST have a time limit. Without it, the same message
    # would never reach the log again. A negative difference from a clock rollback must not
    # silence it forever either.
    elapsed = t - _awake_log["kiedy"]
    if elapsed < 0:
        # The clock moved backward (NTP, wake from sleep, timezone change). Resetting the
        # gap here closed the throttle for another fresh 10 minutes, dropping an event that
        # landed exactly on the clock jump. A clock jump is itself a reason to let the entry
        # through because it is worth having in the black box.
        _awake_log["kiedy"] = t
        elapsed = 600
    if not isinstance(msg, str):
        msg = str(msg)
    if elapsed < 600:
        _awake_log["pominiete"] += 1
        _awake_log["ostatni"] = msg
        return
    amount = _awake_log["pominiete"]
    _awake_log.update({"ostatni": msg, "kiedy": t, "pominiete": 0})
    log(msg + (" [+%d przelaczen w miedzyczasie]" % amount if amount else ""))


_hw_fleet = {"v": None}


def _hw_cache_fleet():
    """Return model and serial from hardware.json, read once for the fleet snapshot."""
    if _hw_fleet["v"] is None:
        d = {}
        try:
            with open(HW_PATH) as f:
                j = json.load(f)
            d = {"model": "%s · %s" % (j.get("model_name", "?"), j.get("chip", "?")),
                 "serial": j.get("serial", "")}
        except Exception:
            pass
        _hw_fleet["v"] = d
    return _hw_fleet["v"]


def fleet_write(cfg, status):
    """Write this host's snapshot to the configured shared fleet folder."""
    d = os.path.expanduser(cfg.get("fleet_dir") or "")
    if not d:
        return
    try:
        if not os.path.isdir(d):
            os.makedirs(d, 0o755)
        out = dict(status)
        out["host"] = (cfg.get("fleet_label") or "").strip() or hostname()
        hw = _hw_cache_fleet()
        out["model"] = hw.get("model")
        out["serial"] = hw.get("serial")
        out["guard_version"] = GUARD_VERSION
        # Authoritative snapshot timestamp. File mtime in iCloud can stand still while
        # content is fresh, and `fleet` uses this to compute report age.
        out["epoch"] = round(time.time(), 3)
        _errors = {k: v for k, v in _SILENT_FAILURES.items() if not k.startswith("_ostatni_log_")}
        if _errors:
            out["swallowed_errors"] = _errors
        tmp = os.path.join(d, ".%s.tmp" % hostname())
        with open(tmp, "w") as f:
            json.dump(out, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(d, "%s.json" % hostname()))
    except Exception:
        pass                      # fleet is an add-on; it must not take down the guard


def status_write(state, temp, soc, soc_t, ac, pct, speed, load, lvl, why, targets, st, disk=None,
                 display=None):
    """Write the menu-bar (`heatbar`) snapshot.

    The menu bar measures nothing by itself; it reads this file, so it costs zero CPU and
    always shows exactly what guard sees.
    """
    # The DISPLAY list excludes children, otherwise the same processor is counted twice.
    # Signals go to the FULL `targets` list; see `without_descendants`. This distinction exists
    # because filtering targets created broken protection for process trees.
    display_targets = display if display is not None else (targets or [])
    top = targets[0] if targets else None
    data = {
        "time": ts(), "thermal_state": state, "level": lvl, "reason": why,
        "chip_c": round(soc_t, 1) if soc_t else None,
        "gpu_c": round(soc["gpu"], 1) if soc and soc.get("gpu") else None,
        "battery_c": round(temp, 1) if temp else None,
        "fans": (soc.get("fans") if soc else []) or [],
        "watts": round(soc["watts"], 1) if soc else None,
        "ram_used_gb": round(soc["ram_used"], 1) if soc and soc.get("ram_total") else None,
        "ram_total_gb": round(soc["ram_total"], 1) if soc and soc.get("ram_total") else None,
        # Swap used on a high-RAM machine is the best signal of real memory pressure.
        "swap_used_gb": round(soc["swap_used"], 2) if soc and soc.get("ram_total") else None,
        "disk_used_gb": round(disk[0]) if disk else None,
        "disk_total_gb": round(disk[1]) if disk else None,
        "disk_used_pct": round(disk[2]) if disk else None,
        "battery_pct": pct, "on_ac": bool(ac),
        "cpu_limit": speed, "load1": round(load, 2),
        "paused": [v.get("comm") for v in st.get("paused", {}).values()],
        # E-core demotion is INVISIBLE in temperature (44 C looks like cooling success) but
        # can cut job speed by 11x. It must be explicit in the snapshot.
        "demoted": [v.get("comm", "?") for v in st.get("demoted_info", {}).values()],
        "heavy_count": len(display_targets),
        "top_proc": top[2] if top else None,
        "top_cpu": round(top[1]) if top else None,
        "manual_pause": bool(st.get("reczna_pauza")),
        "dry_run": bool(st.get("_dry")),
        "keep_awake": bool(st.get("_awake")),
        "stats_total": st.get("stats", {}),
        "stats_session": st.get("stats_sesja", {}),
        "awake_mode": st.get("_awake_mode"),
        "awake_until": st.get("_awake_until"),
        "awake_app": st.get("_awake_app"),
        "trend_c_min": st.get("_trend_c_min"),
        "eta_pause_min": st.get("_eta_min"),
        "jobs": st.get("_zadania", []),
        "stats": st.get("_stat", {}),
        "unpausable": st.get("_unpausable", []),
        "top_cpu_list": st.get("_top_cpu", []),
        # Manual-freeze candidates: exactly what will receive SIGSTOP. The menu bar used
        # to show "top_cpu_list" here, the three heaviest system processes. That is a READ
        # list, not an ACTION list: it included WindowServer and the AI agent, both
        # untouchable. The confirmation dialog promised to stop processes the guard would
        # never touch, and showed a different count than the nearby counter.
        "freeze_candidates": [{"pid": t[0], "name": t[2], "cpu": round(t[1])}
                              for t in display_targets],
        "top_ram_list": st.get("_top_ram", []),
        "last_hard_shutdown": st.get("_ostatni_pad"),
        # "resume" is for safe-run --wait-cool. config.json may be corrected in memory by
        # sanity-clamp, so the resume threshold must come from the snapshot, not the file.
        # Otherwise waiting targets a threshold nobody enforces.
        "thresholds": {"pause": st.get("_prog_pauza"), "resume": st.get("_prog_wznowienia"),
                       "kill": st.get("_prog_ubicie")},
        # False means no chip sensor (macmon). The menu bar, fleet, and agents must know,
        # because protection then rests only on the battery, which reacts minutes later.
        "chip_sensor": soc is not None,
        # Non-empty list means the daemon runs on values DIFFERENT from config.json because
        # sanity-clamp corrected them in memory. Anyone reading config.json must check here
        # first, or they diagnose a different system from the one actually running.
        "config_corrections": list(_ostatnio_odrzucone["v"]),
    }
    if st.get("_admission"):
        data["admission"] = st["_admission"]
        # A plain counter for the fleet table; the full queue stays local.
        data["queued_count"] = len(st["_admission"].get("queued") or [])
    tmp = STATUS_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, STATUS_PATH)   # atomic replace; the menu bar never sees half a file
    except Exception as e:
        silent_failure("status_write", e)   # the menu bar then shows stale data as current
    return data


HIST_HEADER = ("time,thermal_state,chip_C,gpu_C,battery_C,fan_rpm,watts,"
               "battery_pct,on_ac,cpu_limit,load1,level,top_proc,top_cpu\n")


def hist_write(row):
    rotate(HIST_PATH)
    # When columns change, set aside the old file instead of mixing formats.
    try:
        if os.path.exists(HIST_PATH):
            with open(HIST_PATH) as f:
                if f.readline() != HIST_HEADER:
                    os.rename(HIST_PATH, HIST_PATH.replace(".csv", "_old.csv"))
    except Exception as e:
        silent_failure("hist_write/naglowek", e)
    new = not os.path.exists(HIST_PATH)
    try:
        with open(HIST_PATH, "a") as f:
            if new:
                f.write(HIST_HEADER)
            f.write(",".join(str(x) for x in row) + "\n")
    except Exception as e:
        silent_failure("hist_write", e)   # no measurements means an empty evidence timeline


# ---------------------------------------------------------------- loop

def snapshot(cfg):
    state = thermal_state()
    temp = battery_temp_c()
    speed = cpu_speed_limit()
    load = load_avg()
    soc = soc_sensors()
    soc_t = soc_temp_c()
    ac, pct = power_source()
    procs = list_procs()
    saferun, saferun_normal = managed_pids_from_saferun()
    targets = pick_targets(cfg, procs, saferun)
    lvl, why = severity(cfg, state, temp, speed, soc_t, ac, pct)
    # `display_targets` is separate from `targets`: signals go to the FULL list, otherwise
    # children do not receive SIGSTOP. The counter and confirmation window show the list
    # without descendants, otherwise the same processor is counted twice.
    return (state, temp, speed, load, targets, lvl, why, soc, soc_t, ac, pct,
            saferun_normal, without_descendants(targets, procs), list(_DEMOTE_ONLY))


_fan_zero = {"n": 0}


def fan_alarm(cfg, soc, soc_t, st):
    """Warn when the chip is hot and fans are stopped.

    This indicates cooling failure, such as a stuck fan, disconnected cable, or clogged
    cooling path. It only shouts; thermal logic owns pausing so a bad fan reading does not
    kill computations.
    """
    # This counter MUST NOT survive missing data or daemon restart. Otherwise "three
    # consecutive readings" means "three readings ever", and after restart with counter 2
    # the first fan spin-up alarms immediately. It lives in the module, not state.json.
    if not cfg.get("fan_check", True) or not soc or soc_t is None:
        _fan_zero["n"] = 0
        return
    fans = soc.get("fans") or []
    if not fans:
        _fan_zero["n"] = 0
        return
    hot = soc_t >= cfg.get("fan_alert_temp_c", 75.0)
    dead = max(fans) == 0
    # Fans ramp up from zero over several seconds. One "hot and 0 rpm" reading is usually
    # spin-up, not failure. A true cooling failure persists; a transient one does not. Count
    # consecutive readings.
    _fan_zero["n"] = (_fan_zero["n"] + 1) if (hot and dead) else 0
    st["_fan_zero_polls"] = _fan_zero["n"]          # state.json inspection only
    if hot and dead and _fan_zero["n"] >= cfg.get("fan_alert_polls", 3):
        if now() - st.get("fan_alarm_at", 0) > 600:
            st["fan_alarm_at"] = now()
            msg = (T("COOLING FAILURE? chip %.1f C while both fans report 0 rpm") % soc_t)
            log("!!! " + msg, tag="FANFAIL")
            # events.log is the black box for evidence reports. Fan alarms used to go only
            # to guard.log, while the report builds its critical section from events.log.
            # The document then said "no cooling alarm detected" while showing such alarms
            # elsewhere, contradicting itself.
            record_event("COOLING_ALARM", msg,
                             {"chip_c": round(soc_t, 1), "fans": list(fans)})
            notify(cfg, T("Fans stopped while the chip is hot"), msg, key="fan")


def acquire_exclusive():
    """Acquire the one-daemon-per-machine lock for this process lifetime.

    Two instances are not theoretical: each sees the other as an ordinary CPU-hungry Python
    process and can pause it. An orphaned `python3 guard.py` from a source directory
    survived tests once. Result: two writers in the log and the guard frozen by itself.

    Returns a file handle that must be kept open; closing it releases the lock.
    """
    import fcntl
    path = os.path.join(BASE, "guard.lock")
    try:
        # "a+", not "w": "w" truncates before flock, so every failed start erased the PID
        # of the lock owner, the only diagnostic for "who holds it". Write only after the
        # lock is acquired.
        f = open(path, "a+")
    except OSError as e:
        # Directory instead of file, no write permission. Without this, the daemon crashed
        # with a traceback at startup and launchd restarted it in a loop.
        log("nie moge otworzyc %s (%s) - demon startuje BEZ wylacznosci" % (path, e))
        return False
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    try:
        f.seek(0)
        f.truncate()
        f.write("%d\n" % os.getpid())
        f.flush()
    except OSError:
        pass
    return f


def main():
    # An install updated by git reset without --version forced guessing what is installed.
    # git describe works only in a clone. Check this before the exclusivity lock so it works
    # while the daemon is running.
    if "--version" in sys.argv:
        print("coffee-paladin %s" % GUARD_VERSION)
        return 0
    ensure_dirs()
    # Exclusivity applies ONLY to the daemon. `--once` and `status` are one-shot reads and
    # must always work, including while the daemon is running. Humans and tests use them.
    one_shot = ("--once" in sys.argv) or ("status" in sys.argv)
    _lock = None if one_shot else acquire_exclusive()
    # False means the lock file could not be opened (directory, no permission). Start
    # anyway: lack of exclusivity is bad, but lack of PROTECTION is worse. None means
    # somebody else holds it.
    if not one_shot and _lock is None:
        print(T("another coffee-paladin daemon is already running - this one exits"),
              file=sys.stderr)
        return 1
    cfg = load_cfg()
    st = load_state()

    # `coffee-paladin status` was a trap: exit code 0 with no output looked successful. It
    # is now an alias for --once, and every unknown argument prints what is supported.
    known = {"--once", "status", "--version"}
    unknown_args = [a for a in sys.argv[1:] if a not in known]
    if unknown_args:
        print(T("unknown argument: %s") % " ".join(unknown_args), file=sys.stderr)
        print(T("usage: coffee-paladin [--once | status | --version]   (no arguments = run the daemon)"),
              file=sys.stderr)
        return 2

    if "--once" in sys.argv or "status" in sys.argv:
        (state, temp, speed, load, targets, lvl, why,
         soc, soc_t, ac, pct, _saferun_normal, _pokaz, _demote_only) = snapshot(cfg)
        fans = ",".join(str(x) for x in (soc.get("fans") if soc else [])) or "n/d"
        print(T("state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)") % (
            state, ("%.1f C" % soc_t) if soc_t else "n/d",
            ("%.1f C" % temp) if temp else "n/d", fans,
            (T("AC") if ac else T("battery %s%%") % (pct if pct is not None else "?")),
            speed, load, lvl, why or T("calm")))
        for pid, cpu, comm, _ in targets[:5]:
            print(T("  candidate: %-20s pid=%-7d %.0f%% CPU") % (comm, pid, cpu))
        return 0

    # Cleanup after a previous daemon is done ONLY by the daemon. This block used to run
    # before --once/status handling, so `coffee-paladin status` resumed everything paused by
    # the RUNNING daemon and cleared its state.json while the daemon still believed it held
    # those processes frozen.
    if st["paused"]:
        try:
            state_mtime = os.path.getmtime(STATE_PATH)
        except Exception:
            state_mtime = 0
        if state_mtime >= boot_time():
            # Measure BEFORE resuming anything. Daemon restart (update, kickstart) can
            # happen on a hot machine. Blind resume gave a hot job ~15 s at full speed above
            # the chip threshold before the first loop cycle froze it again. Use the same
            # gate as the loop, not a copy.
            if resume_gate(cfg, st, battery_temp_c(), soc_temp_c(), thermal_state()):
                do_resume(cfg, st, T("guard startup - nothing is left frozen"))
            else:
                log("startup: machine still hot - %d paused entr(ies) stay frozen, "
                    "the loop will resume them after cooling" % len(st["paused"]))
        else:
            # State from before reboot: PIDs may belong to completely unrelated processes.
            log("stale state from before boot - dropping %d paused entries without signaling"
                % len(st["paused"]))
            st["paused"] = {}
        save_state(st)

    stop = {"flag": False}

    def on_signal(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    # Black box: did the previous session end in a hard shutdown?
    pad = detect_hard_shutdown()
    if pad:
        st["_ostatni_pad"] = pad
        notify(cfg, T("Mac shut down without warning"),
               T("Evidence from the moment of the crash was saved - menu bar > Export report"), key="pad")
    st["reczna_pauza"] = False
    # New daemon session means new session counters. The all-time total ("stats") remains.
    st["stats_sesja"] = {"since": now()}
    try:
        if os.path.exists(CLEAN_STOP_PATH):
            os.remove(CLEAN_STOP_PATH)
    except Exception:
        pass

    # Hardware and per-Mac calibration: once at startup because system_profiler is slow.
    hw = {}
    calibration_deferred = False   # must exist even when calibration raises
    try:
        hw = hardware_info()
        calibration_result = auto_calibrate(cfg, hw)
        # The sensor can come up AFTER daemon start, for example while macmon is busy after
        # `install.sh` compiled the menu bar. Calibration runs once at startup, so without
        # this a fanless Mac would wait for its thresholds until the next daemon restart,
        # and the daemon has KeepAlive. The loop finishes the work when the sensor returns.
        calibration_deferred = not hw.get("chip_sensor")
        cfg = load_cfg()          # calibration may have written thresholds
        if calibration_result == "watchonly" and cfg.get("dry_run"):
            notify(cfg, T("coffee-paladin: watch-only mode"),
                   T("Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click)."),
                   key="dryinfo")
    except Exception as e:
        log("CALIBRATION skipped: %r" % (e,))

    chip_sensor_label = T("yes") if soc_temp_c() is not None else T("NO (macmon missing - running on battery temperature only)")
    log(T("coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s)"
          " | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery")
        % (cfg.get("soc_pause_c", 92), cfg.get("soc_resume_c", 80), cfg.get("soc_kill_c", 100),
           chip_sensor_label, cfg["batt_pause_c"], cfg["batt_kill_c"],
           cfg["pause_on_thermal_state"], cfg.get("batt_pct_pause", 10)))

    # Missing chip sensor is not minor: only the battery remains, and it reacts several
    # minutes late. A single log line was not enough while `heat` and `fleet` still reported
    # that everything was fine.
    _no_sensor = soc_temp_c() is None
    if _no_sensor:
        notify(cfg, T("Thermal guard: PROTECTION INCOMPLETE"),
               T("No chip temperature sensor (macmon missing). Only battery temperature "
                 "is watched, and it reacts minutes late. Fix: brew install macmon"),
               key="nosensor")

    crit_polls = 0
    cpu_hist = {}
    tick = 0

    observed_cfg = None
    while not stop["flag"]:
        try:
            cfg = load_cfg()
            # Every threshold or behavior change leaves an old -> new trail. The first pass
            # only remembers state, without logging.
            observed_cfg = log_config_changes(observed_cfg, cfg)
            reap_bg()
            (state, temp, speed, load, targets, lvl, why,
             soc, soc_t, ac, pct, saferun_normal, display_targets, demote_only) = snapshot(cfg)
            # Sensor returned after startup? Finish deferred calibration. Without this, a
            # fanless Mac stays on fan-equipped thresholds until daemon restart. Use the
            # snapshot (`soc`) to avoid paying for macmon again; the rest of `hw` comes from
            # the system and does not change between ticks.
            if calibration_deferred and soc:
                hw["fan_count"] = len(soc.get("fans") or [])
                hw["chip_sensor"] = True
                auto_calibrate(cfg, hw)
                cfg = load_cfg()
                calibration_deferred = False

            fan_alarm(cfg, soc, soc_t, st)
            handle_command(cfg, st, targets)

            # Helper data for the menu bar: trend, jobs, daily counter.
            st["_trend_c_min"], st["_eta_min"] = trend_and_forecast(cfg, soc_t)
            st["_dry"] = bool(cfg.get("dry_run"))
            st["_awake"] = keep_awake_update(cfg, targets, lvl, st)
            st["_prog_pauza"] = cfg.get("soc_pause_c")
            st["_prog_ubicie"] = cfg.get("soc_kill_c")
            st["_prog_wznowienia"] = cfg.get("soc_resume_c")
            # Admission decisions every tick: a queued wrapper polls the
            # snapshot, so its start latency is one poll interval.
            st["_admission"] = admission_update(cfg, soc_t, lvl, load) \
                if cfg.get("admission_control") else None
            if tick % 4 == 0:                      # less often, this reads from disk
                st["_zadania"] = saferun_jobs()
                st["_stat"] = day_stats()
                st["_top_cpu"], st["_top_ram"] = top_lists()
            # Disk changes slowly; one read every ~5 min is enough.
            if tick % 20 == 0 or not st.get("_disk"):
                st["_disk"] = disk_usage()
            snap_dict = status_write(state, temp, soc, soc_t, ac, pct, speed, load, lvl, why,
                                     targets, st, st.get("_disk"), display=display_targets)
            if tick % 4 == 0 and snap_dict:      # fleet every ~1 min is enough
                fleet_write(cfg, snap_dict)

            # Black-box pulse. After a hard shutdown, this remains the last sign of life.
            try:
                with open(HEARTBEAT_PATH, "w") as f:
                    # Epoch first: timezone and DST fall out of the read path. Text after
                    # the space remains for humans.
                    f.write("%d %s" % (now(), ts()))
            except Exception:
                pass

            top = targets[0] if targets else None
            if tick % max(1, int(300 / cfg["poll_seconds"])) == 0 or lvl >= 2:
                fans = soc.get("fans") if soc else []
                hist_write([ts(), state,
                            "%.1f" % soc_t if soc_t else "",
                            "%.1f" % soc["gpu"] if soc and soc.get("gpu") else "",
                            "%.1f" % temp if temp else "",
                            max(fans) if fans else "",
                            "%.1f" % soc["watts"] if soc else "",
                            pct if pct is not None else "", 1 if ac else 0,
                            speed, "%.2f" % load, lvl,
                            top[2] if top else "", "%.0f" % top[1] if top else ""])

            # Repeat SIGSTOP for everything considered paused. Between freeze and
            # state.json write, the safe-run duty limiter or a manual kill -CONT can wake a
            # job while it remains "paused" in memory, so it would never be frozen again.
            # STOP on an already stopped process is harmless and cheap.
            if lvl >= 2 and not cfg["dry_run"]:
                for key, info in st["paused"].items():
                    pid = int(key)
                    if alive(pid):
                        sig(pid, info.get("pgid"), signal.SIGSTOP)

            # System-state confirmation. When the only reason for level >=2 is
            # `thermalState` and the chip threshold is NOT crossed, require several
            # consecutive readings. Minimum pause time reduced oscillation, but confirming
            # entry gives this trigger real hysteresis.
            chip_threshold = cfg.get("soc_pause_c", 95.0)
            state_only_hot = (lvl >= 2 and (soc_t is None or soc_t < chip_threshold)
                        and (temp is None or temp < cfg["batt_pause_c"]))
            st["_state_polls"] = (st.get("_state_polls", 0) + 1) if state_only_hot else 0
            if state_only_hot and st["_state_polls"] < cfg.get("state_confirm_polls", 2):
                lvl = 1        # do not trust a single thermalState spike yet

            # Per-sensor latch. A sensor can BLOCK resume only if it crossed its own pause
            # threshold and has not dropped to its own resume threshold yet. The old gate
            # was asymmetric: ANY sensor caused pause, but EVERY sensor blocked resume. A
            # battery cooling over minutes at ~37 C could hold a CHIP-paused job in T until
            # SIGTERM, even though it never crossed its own 40 C threshold. Sensor
            # hysteresis must protect against flicker at that sensor's threshold, not take
            # hostages for another sensor's threshold.
            # Snapshot really stopped processes with ONE `ps` per cycle, only when anything
            # is frozen. Both paths that decide another process's life use it: stale-entry
            # cleanup and SIGTERM after the pause limit.
            stopped = stopped_now() if st["paused"] else (set(), set())
            if stopped is None and not st.get("_ps_cicho"):
                log("ps unavailable - postponing decisions about paused jobs")
            st["_ps_cicho"] = stopped is None

            # Update latches in EVERY cycle, even while hot. Otherwise a battery crossing
            # 40 C during a pause would never turn on its latch.
            may_resume = resume_gate(cfg, st, temp, soc_t, state)

            if lvl >= 3:
                crit_polls += 1
                banner(cfg, T("Thermal guard: CRITICAL overheating"),
                       (T("The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.")
                        if cfg.get("dry_run") else
                        T("The Mac is critically hot (%s). Heavy jobs are being stopped.")) % why)
                do_pause(cfg, st, targets, T("CRITICAL: ") + why, critical_level=True)
                if crit_polls >= cfg["kill_after_polls"]:
                    do_terminate(cfg, st, why)
                    crit_polls = 0
            elif lvl == 2:
                crit_polls = 0
                do_pause(cfg, st, targets, why)
            else:
                crit_polls = 0
                cool = may_resume
                # After a battery pause, resume only on AC or after enough recharge.
                powered = ac or pct is None or pct >= cfg.get("batt_pct_resume", 25)
                # Clean dead entries HERE, independent of do_resume. Previously do_resume
                # was the only cleanup site, but manual-pause flag blocks it. That created
                # an absorbing state: a manual freeze, external kill, entry stays forever,
                # `reczna_pauza` stays forever, and from then on guard PAUSES but NEVER
                # resumes, so every later job gets SIGTERM after the time limit.
                for _k in [k for k in list(st["paused"]) if not alive(int(k))]:
                    del st["paused"][_k]
                # Entries woken outside guard. The machine is cool, so the process may run;
                # and if it already runs because a human sent `kill -CONT` or safe-run duty
                # limiter woke it, the entry is only a delayed sentence. The pause clock
                # keeps ticking and `max_pause_minutes` later sends SIGTERM into a job
                # running at full speed. Delete the entry and log it.
                for _k in stale_entries(st["paused"], stopped):
                    log(T("dropping stale pause entry: %s (pid %s) is running again "
                          "- resumed outside the guard")
                        % (st["paused"][_k].get("comm", "?"), _k))
                    del st["paused"][_k]
                # Compute the flag from data instead of storing it separately; it cannot drift.
                st["reczna_pauza"] = any(v.get("manual") for v in st["paused"].values())

                # Minimum pause time. Without this, the system-state trigger, which has no
                # hysteresis, oscillates: pause -> 15 s -> "conditions normal" -> pause
                # again, with the chip ten degrees below threshold. The job bounces while
                # nothing cools.
                min_p = max(0, cfg.get("min_pause_seconds", 60))
                # Per entry, not all-or-nothing. The old code used the youngest pause from
                # the whole batch, so a freshly frozen process held back ffmpeg that had
                # already waited an hour. With state flicker, new candidates appear
                # cyclically and the oldest pause could wait until SIGTERM. Manual menu-bar
                # freezes have priority and are not touched.
                ready_keys = [k for k, v in st["paused"].items()
                          if _pause_age(v) >= min_p and not v.get("manual")
                          and (powered or v.get("powod") != "bateria")]
                if ready_keys and cool:
                    do_resume(cfg, st, T("conditions are back to normal"), only_keys=ready_keys,
                              after_cooling=True)
                do_promote(cfg, st, cpu_hist, soc_t)
                # System indexing daemons are added ONLY here: demotion yes, pause/terminate
                # never. See system_demote_patterns.
                do_demote(cfg, st, targets + demote_only, cpu_hist, soc_t, saferun_normal)

            # Nothing may stay paused forever. BUT waiting for AC is not a failure. When
            # chip and battery are cool and low battery is the only pause reason, give much
            # more time so computation can wait for the user to plug in instead of dying
            # after 45 minutes.
            battery_only = (not ac and lvl >= 2
                             and (soc_t is None or soc_t < cfg.get("soc_pause_c", 88) - 10)
                             and (temp is None or temp < cfg["batt_pause_c"] - 3))
            limit_min = cfg.get("max_pause_minutes_batt", 240) if battery_only else cfg["max_pause_minutes"]
            # How long this pause REALLY lasted. Wall time can jump (NTP, RTC correction,
            # wake from sleep): a 3 h jump killed a job paused one minute earlier, and a
            # backward jump disabled the limit forever. monotonic() does not survive daemon
            # restart; a new process starts counting from scratch, exactly from zero under
            # Apple's Python, so an old measurement would go negative and the pause limit
            # would never fire. The entry carries a process marker, and a foreign
            # measurement falls back to wall time, the only clock that means the same thing
            # on both sides of restart.
            # Terminate ONLY what is really stopped. The entry is a guard note, not system
            # state: a process woken manually or by the safe-run limiter runs at full speed
            # while its entry keeps aging. SIGTERM after 45 minutes then hits a healthy job
            # mid-work. The clock starts at the FIRST stop, as intended; proof that the
            # process is running saves it, not rewinding the stopwatch.
            expired_keys = expired_entries(st["paused"], limit_min * 60, stopped)
            if expired_keys:
                for k in expired_keys:
                    log(T("PAUSE >%d min - terminating job %s (pid %s)")
                        % (limit_min, st["paused"][k].get("comm"), k), tag="KILL")
                do_terminate(cfg, st, T("paused for longer than %d min") % limit_min,
                             only_keys=expired_keys)

            for _p in [p for p in _nie_da_sie if not alive(p)]:
                del _nie_da_sie[_p]
            _demote_nie_da_sie.difference_update(
                p for p in list(_demote_nie_da_sie) if not alive(p))
            # Refresh the menu-bar and agent list HERE, not only on new pause attempts.
            # `unpausable` used to carry the name of a long-dead process until the next
            # pause attempt, so AI agents kept reporting incomplete protection.
            st["_unpausable"] = sorted(set(_nie_da_sie.values()))
            # Demotion clock survives pauses. Entries disappear only when the process DIES,
            # not when it falls out of targets. SIGSTOP zeros pcpu in <5 s, and with old
            # pruning the hottest job had its clock reset on every pause.
            live = set(p[0] for p in targets)
            cpu_hist = dict((k, v) for k, v in cpu_hist.items()
                            if k in live or alive(k))
            st["demoted"] = [p for p in st["demoted"] if alive(p)]
            live_demoted = set(str(p) for p in st["demoted"])
            st["demoted_info"] = {k: v for k, v in st.get("demoted_info", {}).items()
                                  if k in live_demoted}
            save_state(st)
        except Exception as e:
            log(T("LOOP ERROR: %r") % (e,))
        tick += 1
        # Interruptible nap: a menu-bar command or keep-awake change wakes the loop
        # IMMEDIATELY. Manual actions react in ~1 s while the full measurement cycle remains
        # sparse. Cost: two stat() calls every 0.5 s.
        def _mtime(p):
            try:
                return os.path.getmtime(p)
            except OSError:
                return None

        awake_before = _mtime(AWAKE_PATH)
        # Config changes wake the loop too. Without this, the menu-bar protection switch
        # waited a full tick because `dry_run` travels through config.json, not `command`,
        # so it was the only manual action without a wake path. With a 30 s interval slider,
        # it looked like a stuck toggle.
        cfg_before = _mtime(CFG_PATH)
        for _ in range(int(cfg["poll_seconds"] * 2)):
            if stop["flag"]:
                break
            if os.path.exists(COMMAND_PATH):
                break
            if _mtime(AWAKE_PATH) != awake_before:
                break
            if _mtime(CFG_PATH) != cfg_before:
                break
            time.sleep(0.5)

    do_resume(cfg, st, T("guard is shutting down"))
    # E-core demotion survived daemon shutdown: the process stayed pinned to E-cores for
    # the rest of its life, invisible in temperature and visible only in throughput. Undo it
    # just like pause.
    for _pid in list(st.get("demoted_info") or {}):
        try:
            run(["taskpolicy", "-B", "-p", str(_pid)], timeout=5)
        except Exception:
            pass
    # `caffeinate -is` is a daemon CHILD but survives it. After the guard dies, launchd
    # adopts it and the Mac never sleeps, with no visible trace in the interface.
    try:
        _c = _caff.get("proc")
        if _c is not None and _c.poll() is None:
            _c.terminate()
            try:
                _c.communicate(timeout=3)
            except Exception:
                _c.kill()
    except Exception:
        pass
    save_state(st)
    # Clean-shutdown marker. Without it, the next start treats this as a hard shutdown.
    try:
        with open(CLEAN_STOP_PATH, "w") as f:
            f.write(ts())
    except Exception:
        pass
    log("coffee-paladin stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
