#!/bin/bash
# coffee-paladin statusline for Claude Code.
#
# One line that answers, in a second: is this machine safe to load right now?
# It only READS ~/.coffee-paladin/status.json (written by the daemon every
# cycle) plus the session JSON Claude Code pipes to stdin; it never signals,
# never starts services, and exits silently when the guard is not installed.
#
# States: file missing -> empty line (the segment does not exist);
# stale >60 s -> red OFF with the age (a guard that died must be LOUD);
# dry_run -> an eye, never a lying shield.
#
# Icons: emoji by default - a patched font is guaranteed nowhere, and a row of
# tofu boxes on someone's first day is exactly the kind of field failure this
# project keeps relearning. Opt in via COFFEE_PALADIN_STATUSLINE_ICONS=nerd
# (Nerd Font glyphs) or =ascii (plain words, also used for TERM=dumb).
# NO_COLOR disables ANSI. COFFEE_PALADIN_STATUS overrides the file for tests.
#
# The heredoc below IS python's stdin, so the session JSON Claude Code pipes in
# must be captured here first or it silently never arrives. Guarded with -t 0:
# a manual run in a terminal must not block waiting for input.
if [ ! -t 0 ]; then SESSION_JSON="$(cat)"; else SESSION_JSON=""; fi
export SESSION_JSON
# System python first, any python3 second, and silence when there is none: a
# statusline that prints a traceback under every session is worse than absent.
if [ -x /usr/bin/python3 ]; then PY_BIN=/usr/bin/python3
elif command -v python3 >/dev/null 2>&1; then PY_BIN=python3
else exit 0; fi
exec "$PY_BIN" - "$@" <<'PY'
import json, os, re, sys, time

BASE = os.path.expanduser(os.environ.get("TG_BASE") or "~/.coffee-paladin")
path = os.environ.get("COFFEE_PALADIN_STATUS", os.path.join(BASE, "status.json"))

STYLE = os.environ.get("COFFEE_PALADIN_STATUSLINE_ICONS", "emoji")
if os.environ.get("TERM") == "dumb":
    STYLE = "ascii"
PLAIN = STYLE == "ascii" or bool(os.environ.get("NO_COLOR"))

RED, YEL, ORG, GRN, DIM, RST = ("", "", "", "", "", "") if PLAIN else (
    "\033[31m", "\033[33m", "\033[38;5;208m", "\033[32m", "\033[2m", "\033[0m")

ICONS = {
    "emoji": {"temp": "\U0001f321", "fan": "\U0001f300", "ram": "\U0001f9e0",
              "disk": "\U0001f4be", "coffee": "☕", "pause": "⏸", "slow": "\U0001f422",
              "warn": "⚠", "shield": "\U0001f6e1", "eye": "\U0001f441",
              "ai": "\U0001f916"},
    "nerd": {"temp": chr(0xF050F), "fan": chr(0xF0210), "ram": chr(0xF035B),
             "disk": chr(0xF02CA), "coffee": chr(0xF0176), "pause": chr(0xF03E4),
             "slow": "\U0001f422", "warn": "⚠", "shield": chr(0xF0565),
             "eye": chr(0xF0208), "ai": chr(0xF06A9)},
    "ascii": {"temp": "chip", "fan": "fan", "ram": "RAM", "disk": "disk",
              "coffee": "coffee", "pause": "paused", "slow": "slow",
              "warn": "!", "shield": "ON", "eye": "WATCH", "ai": "AI"},
}
I = ICONS.get(STYLE, ICONS["emoji"])

WORDS = {
    "en": {"off": "paladin OFF (%d min of silence)", "watch": "watch-only",
           "level": "level %d", "nosensor": "no chip sensor",
           "crash": "hard shutdown"},
    "pl": {"off": "paladyn OFF (%d min ciszy)", "watch": "obserwacja",
           "level": "poziom %d", "nosensor": "brak czujnika chipa",
           "crash": "nagle wylaczenie"},
    "ru": {"off": "паладин OFF (%d мин тишины)", "watch": "наблюдение",
           "level": "уровень %d", "nosensor": "нет датчика чипа",
           "crash": "внезапное выключение"},
    "zh": {"off": "paladin OFF（静默 %d 分钟）", "watch": "仅观察",
           "level": "级别 %d", "nosensor": "无芯片传感器",
           "crash": "异常关机"},
    "es": {"off": "paladín OFF (%d min de silencio)", "watch": "observación",
           "level": "nivel %d", "nosensor": "sin sensor del chip",
           "crash": "apagón repentino"},
}


def lang():
    v = (os.environ.get("TG_LANG") or "").lower()[:2]
    if v in WORDS:
        return v
    try:
        v = (json.load(open(os.path.join(BASE, "config.json"))).get("lang") or "").lower()[:2]
    except Exception:
        v = ""
    return v if v in WORDS else "en"


W = WORDS[lang()]


def clean(text, limit=24):
    """Names come from process tables and session JSON: strip ANSI, control
    bytes AND Unicode format characters. Category "C" covers C0/C1 controls and
    the bidi overrides (U+202E and friends) that can visually reorder or hide
    the rest of the line - a directory name must not restyle the statusline."""
    import unicodedata
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", str(text or ""))
    return "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")[:limit]


def num(value):
    try:
        v = float(value)
        return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError):
        return None


def stamp_epoch(text):
    """Epoch from a guard timestamp; 0.0 for junk (copy of the tools' parser)."""
    if not isinstance(text, str) or len(text.strip()) < 19:
        return 0.0
    text = text.strip()
    try:
        import datetime
        if len(text) >= 24 and text[19] in "+-":
            return datetime.datetime.strptime(text[:24], "%Y-%m-%d %H:%M:%S%z").timestamp()
        return time.mktime(time.strptime(text[:19], "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return 0.0


try:
    # A snapshot is a few kilobytes; a huge file is corruption or mischief, and
    # parsing it would hang the statusline under every session. Do not try.
    if os.path.getsize(path) > 1024 * 1024:
        sys.exit(0)
    age = time.time() - os.path.getmtime(path)
    s = json.load(open(path))
    if not isinstance(s, dict):
        raise ValueError
except (OSError, ValueError):
    sys.exit(0)

if age > 60:
    print(f"{RED}{I['warn']} {W['off'] % int(age // 60)}{RST}")
    sys.exit(0)

level_raw = num(s.get("level"))
level = int(level_raw) if level_raw is not None else 0
color = {0: DIM, 1: YEL, 2: ORG, 3: RED}.get(level, RED)
dry = bool(s.get("dry_run", False))
sensor = s.get("chip_sensor", True) is not False
chip = num(s.get("chip_c"))

head = [f"{YEL}{I['eye']} {W['watch']}{RST}" if dry else f"{GRN}{I['shield']}{RST}"]

if chip is not None and sensor:
    head.append(f"{color}{I['temp']} {round(chip)}°{RST}")
else:
    batt = num(s.get("battery_c"))
    label = f"B{round(batt)}°" if batt is not None else "?"
    head.append(f"{color}{I['temp']} {label}{RST}")
if level >= 2:
    head.append(f"{color}{W['level'] % level}{RST}")
    top, cpu = clean(s.get("top_proc"), 16), num(s.get("top_cpu"))
    if top:
        head.append(f"{color}{top}{RST}" + (f"{color} {round(cpu)}%{RST}" if cpu else ""))

alarms = []
paused = len(s.get("paused") or [])
if paused:
    alarms.append(f"{ORG}{I['pause']} {paused}{RST}")
slow = len(s.get("demoted") or [])
if slow:
    alarms.append(f"{ORG}{I['slow']} {slow}{RST}")
queued = sum(1 for j in (s.get("jobs") or []) if isinstance(j, dict) and j.get("queued"))
if queued:
    alarms.append(f"{YEL}Q {queued}{RST}")
if not sensor:
    alarms.append(f"{YEL}{I['warn']} {W['nosensor']}{RST}")
crash = s.get("last_hard_shutdown")
if isinstance(crash, dict):
    when = stamp_epoch(crash.get("time", ""))
    if when and time.time() - when <= 24 * 3600:
        alarms.append(f"{RED}{I['warn']} {W['crash']}{RST}")

body = []
fans = [f for f in (s.get("fans") or []) if num(f)]
if fans:
    body.append(f"{DIM}{I['fan']} {max(num(f) for f in fans) / 1000:.1f}k{RST}")
ram_used, ram_total = num(s.get("ram_used_gb")), num(s.get("ram_total_gb"))
if ram_used and ram_total:
    pct = round(100 * ram_used / ram_total)
    body.append(f"{YEL if pct >= 75 else DIM}{I['ram']} {pct}%{RST}")
disk = num(s.get("disk_used_pct"))
if disk is not None:
    disk = round(disk)
    body.append(f"{RED if disk >= 90 else (YEL if disk >= 80 else DIM)}{I['disk']} {disk}%{RST}")
if s.get("keep_awake"):
    body.append(f"{DIM}{I['coffee']}{RST}")

# Second line: the AI session, from Claude Code's stdin JSON. Our command
# REPLACES the default statusline, so the model and directory the user had
# there come back here, together with the account limits Claude Code started
# publishing to statuslines (rate_limits.*, subscription logins only, present
# after the first API response of a session - every field may be absent).
def pct(value):
    v = num(value)
    return None if v is None or not (0 <= v <= 100) else round(v)


def reset_txt(value, fmt):
    """resets_at is documented as unix epoch seconds; tolerate ISO strings from
    other Claude Code versions and print nothing rather than a wrong time."""
    v = num(value)
    if v is None and isinstance(value, str):
        try:
            import datetime
            v = datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            v = None
    if v is None or not (0 < v < 4102444800):
        return ""
    return time.strftime(fmt, time.localtime(v))


def limit_color(value):
    return RED if value >= 90 else (YEL if value >= 75 else DIM)


ai = []
usage = {}
try:
    session = json.loads(os.environ.get("SESSION_JSON") or "{}")
    if not isinstance(session, dict):
        session = {}
    model = clean((session.get("model") or {}).get("display_name"), 16)
    cwd = clean(os.path.basename((session.get("workspace") or {}).get("current_dir")
                                 or session.get("cwd") or ""), 20)
    limits = session.get("rate_limits") or {}
    five = limits.get("five_hour") or {} if isinstance(limits, dict) else {}
    week = limits.get("seven_day") or {} if isinstance(limits, dict) else {}
    ctx = session.get("context_window") or {}
    five_pct = pct(five.get("used_percentage"))
    week_pct = pct(week.get("used_percentage"))
    ctx_pct = pct(ctx.get("used_percentage") if isinstance(ctx, dict) else None)
    if model:
        ai.append(f"{DIM}{I['ai']} {model}{RST}")
        usage["model"] = model
    if five_pct is not None:
        when = reset_txt(five.get("resets_at"), "%H:%M")
        ai.append(f"{limit_color(five_pct)}5h {five_pct}%{RST}"
                  + (f"{DIM} ↺{when}{RST}" if when else ""))
        usage["five_hour_pct"] = five_pct
        usage["five_hour_reset"] = when
    if week_pct is not None:
        when = reset_txt(week.get("resets_at"), "%a")
        ai.append(f"{limit_color(week_pct)}7d {week_pct}%{RST}"
                  + (f"{DIM} ↺{when}{RST}" if when else ""))
        usage["seven_day_pct"] = week_pct
        usage["seven_day_reset"] = when
    if ctx_pct is not None:
        ai.append(f"{limit_color(ctx_pct)}ctx {ctx_pct}%{RST}")
        usage["context_pct"] = ctx_pct
    if cwd:
        ai.append(f"{DIM}{cwd}{RST}")
except Exception:
    ai, usage = [], {}

# Snapshot for the menu bar: the statusline is the only process that ever sees
# this JSON, so it leaves a whitelisted copy the bar can read (same contract as
# the ccusage cache: a file, never a query). Only the fields printed above are
# written - no paths, no session ids, no transcript locations.
if usage:
    try:
        usage["epoch"] = time.time()
        cache = os.path.join(BASE, "claude_usage_cache.json")
        tmp = "%s.tmp.%d" % (cache, os.getpid())
        with open(tmp, "w") as f:
            json.dump(usage, f)
        os.replace(tmp, cache)
    except OSError:
        pass

try:
    width = int(os.environ.get("COLUMNS", "100"))
except ValueError:
    width = 100
def plain_len(items):
    return len(re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", "  ".join(items)))
parts = head + alarms + body
# Thermal truth is never trimmed; the AI line degrades from its tail (the
# directory goes first, the model last) and vanishes entirely when it cannot
# fit, because a wrapped statusline is worse than a shorter one.
while ai and plain_len(ai) > width:
    ai.pop()

print("  ".join(parts))
if ai:
    print("  ".join(ai))
PY
