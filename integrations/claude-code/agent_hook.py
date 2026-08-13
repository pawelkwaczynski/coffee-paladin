#!/usr/bin/env python3
"""Event recorder for Claude Code hooks: the data layer of Agent Activity.

Claude Code pipes one JSON object per event to stdin. One line lands in
~/.coffee-paladin/agent_events/YYYY-MM-DD.jsonl with a WHITELISTED subset:
event and tool names, ids, durations, the project basename - never full
paths, never command lines, never file contents. The thermal context (level,
chip) is attached from status.json so later analysis can say "that tool ran
while the chip was at 91".

On SessionEnd, and only when `agent_obsidian_vault_path` is set in the
guard's config.json, a one-page Markdown summary of the session is written
into the vault. Default is off; an unwritable vault never breaks the hook.

Exit code is ALWAYS 0: a recorder that blocks a session is worse than no
recorder. Old event files are pruned opportunistically after 7 days.
"""
import json
import os
import sys
import time

BASE = os.path.expanduser(os.environ.get("TG_BASE") or "~/.coffee-paladin")
EVENTS_DIR = os.path.join(BASE, "agent_events")
KEEP_DAYS = 7

# Everything else in the payload is somebody's data, not telemetry.
FIELDS = ("hook_event_name", "session_id", "tool_name", "tool_use_id",
          "agent_id", "agent_type", "duration_ms", "stop_hook_active")
# `reason` is an enum ONLY on SessionEnd per the docs; recording it as free
# text would let an adapter smuggle a path or prompt fragment into the JSONL
# and the vault. Anything unknown collapses to "other".
END_REASONS = frozenset(("clear", "resume", "logout", "prompt_input_exit",
                         "bypass_permissions_disabled", "other"))


def thermal_context():
    try:
        s = json.load(open(os.path.join(BASE, "status.json")))
        return {"level": s.get("level"), "chip_c": s.get("chip_c")}
    except Exception:
        return {}


def prune():
    try:
        cutoff = time.time() - KEEP_DAYS * 86400
        for name in os.listdir(EVENTS_DIR):
            p = os.path.join(EVENTS_DIR, name)
            if name.endswith(".jsonl") and os.path.getmtime(p) < cutoff:
                os.unlink(p)
    except OSError:
        pass


def session_markdown(rec, payload):
    """One honest page per finished session; nothing the vault owner would
    not want synced (names and counts, no transcript, no tool input)."""
    vault = ""
    try:
        vault = (json.load(open(os.path.join(BASE, "config.json")))
                 .get("agent_obsidian_vault_path") or "")
    except Exception:
        return
    if not vault:
        return
    try:
        target = os.path.join(os.path.expanduser(vault), "Coffee Paladin", "Agent Activity")
        os.makedirs(target, exist_ok=True)
        import hashlib
        raw_sid = str(rec.get("session_id") or "session")
        sid = "".join(ch for ch in raw_sid
                      if ch.isascii() and (ch.isalnum() or ch in "-_"))[:40]
        # A session id made of "../" sanitises to nothing, and 12 characters
        # can collide; the hash of the RAW id keeps names unique and safe.
        sid = (sid or "session") + "-" + hashlib.sha256(raw_sid.encode()).hexdigest()[:8]
        day = time.strftime("%Y-%m-%d")
        tools = {}
        events = 0
        project = rec.get("project")
        daily = os.path.join(EVENTS_DIR, day + ".jsonl")
        if os.path.exists(daily):
            for line in open(daily):
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("session_id") != rec.get("session_id"):
                    continue
                events += 1
                t = e.get("tool_name")
                if t:
                    tools[t] = tools.get(t, 0) + 1
                # SessionEnd itself carries no cwd; the session's earlier
                # events do, and the page should name the project they name.
                project = e.get("project") or project
        lines = ["---",
                 "created: %s" % time.strftime("%Y-%m-%d %H:%M"),
                 "source: coffee-paladin",
                 "session: %s" % sid,
                 "project: %s" % (project or "?"),
                 "---", "",
                 "# Agent session %s" % sid[:12], "",
                 "- project: %s" % (project or "?"),
                 "- events recorded today: %d" % events,
                 "- end reason: %s" % (rec.get("reason") or "?")]
        if rec.get("thermal"):
            lines.append("- thermal at end: level %s, chip %s °C"
                         % (rec["thermal"].get("level"), rec["thermal"].get("chip_c")))
        if tools:
            lines.append("")
            lines.append("## Tools used")
            for t, n in sorted(tools.items(), key=lambda kv: -kv[1]):
                lines.append("- %s: %d" % (t, n))
        # tmp + replace: never write THROUGH a symlink somebody planted in
        # the vault, and never leave a half-written page on a crash.
        path = os.path.join(target, "%s %s.md" % (day, sid[:21]))
        tmp = path + ".tmp.%d" % os.getpid()
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
    except OSError:
        pass


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    rec = {"time": time.strftime("%Y-%m-%d %H:%M:%S%z"),
           "epoch": round(time.time(), 1)}
    for key in FIELDS:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            rec[key] = value if not isinstance(value, str) else value[:120]
    if rec.get("hook_event_name") == "SessionEnd":
        raw_reason = payload.get("reason")
        rec["reason"] = raw_reason if raw_reason in END_REASONS else "other"
    cwd = payload.get("cwd") or (payload.get("workspace") or {}).get("current_dir")
    if isinstance(cwd, str) and cwd:
        rec["project"] = os.path.basename(cwd)[:60]
    rec["thermal"] = thermal_context()
    try:
        os.makedirs(EVENTS_DIR, mode=0o700, exist_ok=True)
        day_file = os.path.join(EVENTS_DIR, time.strftime("%Y-%m-%d") + ".jsonl")
        fd = os.open(day_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        return 0
    if rec.get("hook_event_name") == "SessionEnd":
        session_markdown(rec, payload)
        prune()
    return 0


if __name__ == "__main__":
    sys.exit(main())
