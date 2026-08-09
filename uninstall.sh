#!/bin/bash
# uninstall.sh - removes coffee-paladin from this Mac.
# Keeps ~/.coffee-paladin (config, history, black box) unless you pass --purge:
# the measurement history is exactly the thing you may still need for a warranty claim.
set -uo pipefail
BIN="$HOME/.local/bin"
for A in pl.pawel.coffee-paladin-bar pl.pawel.coffee-paladin; do
  launchctl bootout "gui/$UID/$A" 2>/dev/null
  rm -f "$HOME/Library/LaunchAgents/$A.plist"
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
for pid in (st.get("paused") or {}):
    try:
        os.kill(int(pid), signal.SIGCONT)
        print("  ▶️  wznowione przed deinstalacja: pid %s" % pid)
    except Exception:
        pass
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
# old names from versions <=2.1.0 (compatibility symlinks, no longer created)
rm -f "$BIN/thermal-guard" "$BIN/heatbar"
rm -f "$BIN/coffee-paladin" "$BIN/coffee-paladin-bar" "$BIN/heat" "$BIN/safe-run" "$BIN/thermal-report" "$BIN/fleet" "$BIN/thermalstate"
echo "binaries and LaunchAgents removed"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$HOME/.coffee-paladin"
  echo "data removed too (~/.coffee-paladin)"
else
  echo "data kept in ~/.coffee-paladin (history + black box; remove with: uninstall.sh --purge)"
fi
