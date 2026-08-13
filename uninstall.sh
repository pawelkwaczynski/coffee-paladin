#!/bin/bash
# uninstall.sh - removes coffee-paladin from this Mac.
# Keeps ~/.coffee-paladin (config, history, black box) unless you pass --purge:
# the measurement history is exactly the thing you may still need for a warranty claim.
set -uo pipefail
BIN="$HOME/.local/bin"
# The DAEMON goes first. Stopping the bar first would leave a Mac where nothing
# shows the temperature while something is still pausing processes, and if the
# second bootout then failed, the user would never learn about it.
STILL_RUNNING=""
for A in pl.pawel.coffee-paladin pl.pawel.coffee-paladin-bar; do
  launchctl bootout "gui/$UID/$A" 2>/dev/null
  rm -f "$HOME/Library/LaunchAgents/$A.plist"
  # A bootout that failed is not a detail: it means that part is still alive.
  launchctl print "gui/$UID/$A" >/dev/null 2>&1 && STILL_RUNNING="$STILL_RUNNING $A"
done
for APP in "/Applications/coffee-paladin.app" "$HOME/Applications/coffee-paladin.app"; do
  rm -rf "$APP"
done
# Nothing may stay frozen. The daemon resumes everything on SIGTERM, but if
# launchd finishes it with SIGKILL (loop stuck on macmon/system_profiler),
# processes remain in SIGSTOP and --purge deletes state.json - the only trace
# of them. Nobody would ever resume them then.
if [ -f "$HOME/.coffee-paladin/state.json" ]; then
  /usr/bin/python3 - "$HOME/.coffee-paladin/state.json" <<'PY' 2>/dev/null || true
import json, os, signal, sys
try:
    st = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for pid, info in (st.get("paused") or {}).items():
    # The guard freezes the whole process GROUP, so resuming the leader alone
    # leaves its children stopped forever with nothing left on the Mac that
    # knows about them. Group first, leader as the fallback.
    pgid = (info or {}).get("pgid") if isinstance(info, dict) else None
    resumed = False
    if pgid:
        try:
            os.killpg(int(pgid), signal.SIGCONT)
            resumed = True
        except Exception:
            pass
    try:
        os.kill(int(pid), signal.SIGCONT)
        resumed = True
    except Exception:
        pass
    if resumed:
        print("  ▶️  wznowione przed deinstalacja: pid %s" % pid)
PY
fi

# this machine's snapshot in the SHARED fleet folder carries a serial number -
# after uninstall there is no reason for it to stay there forever
/usr/bin/python3 - <<'PY' 2>/dev/null || true
import json, os, socket
cfg = os.path.expanduser("~/.coffee-paladin/config.json")
try:
    d = json.load(open(cfg)).get("fleet_dir") or ""
except Exception:
    d = ""
if d:
    host = socket.gethostname().split(".")[0]
    for nazwa in os.listdir(os.path.expanduser(d)):
        if nazwa in (host + ".json",):
            os.remove(os.path.join(os.path.expanduser(d), nazwa))
            print("  🗑  usunieta migawka floty: %s" % nazwa)
PY

# AI-agent skill: install.sh creates it, so uninstall must take it away -
# otherwise Claude Code keeps invoking a `safe-run` that no longer exists
rm -rf "$HOME/.claude/skills/coffee-paladin"
# Claude Code statusline: remove OUR entry from settings.json before deleting
# the script it points at - a dangling entry would break somebody's Claude Code
# on every session start. A foreign statusLine is never touched.
if [ -f "$HOME/.coffee-paladin/settings_wire.py" ]; then
  case "$(/usr/bin/python3 "$HOME/.coffee-paladin/settings_wire.py" unwire 2>/dev/null)" in
    ok) echo "  🗑  statusline removed from Claude Code settings" ;;
  esac
  # The pre-exec gate too: a dangling PreToolUse entry would run a deleted
  # binary at every tool call of every future session.
  case "$(/usr/bin/python3 "$HOME/.coffee-paladin/settings_wire.py" unhook 2>/dev/null)" in
    ok) echo "  🗑  hook-gate removed from Claude Code settings" ;;
  esac
fi
rm -f "$HOME/.coffee-paladin/statusline.sh" "$HOME/.coffee-paladin/settings_wire.py" "$HOME/.coffee-paladin/agent_hook.py"
# old names from versions <=2.1.0 (compatibility symlinks, no longer created)
rm -f "$BIN/thermal-guard" "$BIN/heatbar"
rm -f "$BIN/coffee-paladin" "$BIN/coffee-paladin-bar" "$BIN/heat" "$BIN/safe-run" "$BIN/thermal-report" "$BIN/fleet" "$BIN/thermalstate"
echo "binaries and LaunchAgents removed"
if [ -n "$STILL_RUNNING" ]; then
  echo "⚠️  still loaded:$STILL_RUNNING - log out and back in, or: launchctl bootout gui/$UID/<name>"
fi
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$HOME/.coffee-paladin"
  echo "data removed too (~/.coffee-paladin)"
else
  echo "data kept in ~/.coffee-paladin (history + black box; remove with: uninstall.sh --purge)"
  # The installed copy of this script is not data. It cannot be deleted while
  # bash is still reading it - the shell reads a script in pieces - so hand the
  # removal to a detached child that waits for this one to finish.
  SELF="$HOME/.coffee-paladin/uninstall.sh"
  if [ "$(cd "$(dirname "$0")" && pwd)/$(basename "$0")" = "$SELF" ]; then
    ( sleep 2; rm -f "$SELF" ) >/dev/null 2>&1 &
  else
    rm -f "$SELF"
  fi
fi
