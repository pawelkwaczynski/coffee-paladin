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
# Nic nie moze zostac zamrozone. Demon wznawia wszystko przy SIGTERM, ale gdy launchd
# dobije go SIGKILL-em (petla stala na macmon/system_profiler), procesy zostaja w SIGSTOP,
# a --purge kasuje state.json - czyli jedyny slad po nich. Wtedy nikt ich juz nie wznowi.
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

# migawka tej maszyny we WSPOLDZIELONYM folderze floty zawiera numer seryjny -
# po deinstalacji nie ma powodu, zeby zostawala tam na zawsze
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

# skill dla agentow AI: install.sh go tworzy, wiec uninstall musi go zabrac -
# inaczej Claude Code dalej kaze sobie odpalac `safe-run`, ktorego juz nie ma
rm -rf "$HOME/.claude/skills/coffee-paladin"
# stare nazwy z wersji <=2.1.0 (symlinki zgodnosciowe, dzis nietworzone)
rm -f "$BIN/thermal-guard" "$BIN/heatbar"
rm -f "$BIN/coffee-paladin" "$BIN/coffee-paladin-bar" "$BIN/heat" "$BIN/safe-run" "$BIN/thermal-report" "$BIN/fleet" "$BIN/thermalstate"
echo "binaries and LaunchAgents removed"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$HOME/.coffee-paladin"
  echo "data removed too (~/.coffee-paladin)"
else
  echo "data kept in ~/.coffee-paladin (history + black box; remove with: uninstall.sh --purge)"
fi
