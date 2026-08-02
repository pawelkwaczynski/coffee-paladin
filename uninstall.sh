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
rm -f "$BIN/coffee-paladin" "$BIN/coffee-paladin-bar" "$BIN/heat" "$BIN/safe-run" "$BIN/thermal-report" "$BIN/fleet" "$BIN/thermalstate"
echo "binaries and LaunchAgents removed"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$HOME/.coffee-paladin"
  echo "data removed too (~/.coffee-paladin)"
else
  echo "data kept in ~/.coffee-paladin (history + black box; remove with: uninstall.sh --purge)"
fi
