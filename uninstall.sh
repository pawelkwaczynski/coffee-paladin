#!/bin/bash
# uninstall.sh - removes thermal-guard from this Mac.
# Keeps ~/.thermal-guard (config, history, black box) unless you pass --purge:
# the measurement history is exactly the thing you may still need for a warranty claim.
set -uo pipefail
BIN="$HOME/.local/bin"
for A in pl.pawel.heatbar pl.pawel.thermal-guard; do
  launchctl bootout "gui/$UID/$A" 2>/dev/null
  rm -f "$HOME/Library/LaunchAgents/$A.plist"
done
rm -f "$BIN/thermal-guard" "$BIN/heatbar" "$BIN/heat" "$BIN/safe-run" "$BIN/thermal-report" "$BIN/fleet" "$BIN/thermalstate"
echo "binaries and LaunchAgents removed"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$HOME/.thermal-guard"
  echo "data removed too (~/.thermal-guard)"
else
  echo "data kept in ~/.thermal-guard (history + black box; remove with: uninstall.sh --purge)"
fi
