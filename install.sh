#!/bin/bash
# install.sh - installs coffee-paladin on this Mac.
# Run: bash install.sh   (from the repository directory)
set -uo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
BASE="$HOME/.coffee-paladin"
AGENT="pl.pawel.coffee-paladin"
PLIST="$HOME/Library/LaunchAgents/$AGENT.plist"

sed_repl() {
  printf '%s' "$1" | sed 's/[&|\\]/\\&/g'
}

pick_app_dir() {
  if [ -n "${COFFEE_PALADIN_APP_PARENT:-}" ]; then
    printf '%s\n' "$COFFEE_PALADIN_APP_PARENT"
  elif [ -d /Applications ] && [ -w /Applications ]; then
    printf '%s\n' "/Applications"
  else
    printf '%s\n' "$HOME/Applications"
  fi
}

heatbar_version() {
  awk -F\" '/let VERSION = "/ {print $2; exit}' "$SRC/heatbar.swift"
}

write_info_plist() {
  local wersja="$1"
  local cel="$2"
  cat > "$cel" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>coffee-paladin-bar</string>
  <key>CFBundleIdentifier</key>
  <string>pl.pawel.coffee-paladin</string>
  <key>CFBundleName</key>
  <string>coffee-paladin</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleShortVersionString</key>
  <string>$wersja</string>
  <key>CFBundleVersion</key>
  <string>$wersja</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>LSUIElement</key>
  <true/>
</dict>
</plist>
PLIST
}

APP_PARENT="$(pick_app_dir)"
APP_BUNDLE="$APP_PARENT/coffee-paladin.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"
BAR_EXEC="$APP_MACOS/coffee-paladin-bar"

# Installs older than 2.0.0 kept data in ~/.thermal-guard under different
# service labels. Auto-migration is gone (nobody needs it), but leaving LOADED
# old services pointing at missing binaries is silent launchd garbage - and an
# orphaned measurement history is evidence the user may want to keep.
for OLD in pl.pawel.thermal-guard pl.pawel.heatbar; do
  launchctl bootout "gui/$(id -u)/$OLD" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$OLD.plist"
done
if [ -d "$HOME/.thermal-guard" ]; then
  echo "  ⚠️  found ~/.thermal-guard (data from before the rename)."
  echo "     The measurement history and black box are still there - move them"
  echo "     yourself if you need them:  mv ~/.thermal-guard/history.csv ~/.coffee-paladin/"
fi

echo "== coffee-paladin: installing on $(scutil --get ComputerName 2>/dev/null || hostname) =="
mkdir -p "$BIN" "$BASE" "$BASE/managed" "$HOME/Library/LaunchAgents"
# data directory owner-only: config.json holds the ntfy topic (the only
# protection for notifications) and managed/ holds full job command lines
chmod 700 "$BASE" "$BASE/managed" 2>/dev/null || true

# fresh account / incomplete package: check the sources BEFORE touching anything
for f in guard.py safe-run heat thermal-report fleet thermalstate.swift heatbar.swift \
         pl.pawel.coffee-paladin.plist pl.pawel.coffee-paladin-bar.plist \
         branding/paladin.png branding/app_icon.png tools/make_icon.sh; do
  if [ ! -f "$SRC/$f" ]; then
    echo "  ❌ missing source file: $SRC/$f - aborting (incomplete package/clone?)"
    exit 1
  fi
done
echo "  ℹ️  app bundle: $APP_BUNDLE"

# 0. DEPENDENCIES. Without swiftc you lose the chip sensor AND the menu bar
# at once - what remains is the battery-only fuse, half the product. So we ask
# UP FRONT instead of warning mid-install when the user is no longer watching.
#
# We run `xcode-select --install` ourselves: it is an Apple tool, opens a
# system dialog and never asks a foreign script for a password.
# HOMEBREW IS INSTALLED MANUALLY ONLY - its installer is `curl | bash` from an
# external address asking for sudo. A script doing that for the user without
# asking teaches a bad habit; we print the command and leave the decision to
# the human.
MISSING=""
if ! command -v swiftc >/dev/null 2>&1; then MISSING="$MISSING swiftc"; fi
if ! command -v brew   >/dev/null 2>&1; then MISSING="$MISSING brew"; fi

if [ -n "$MISSING" ]; then
  echo ""
  echo "  ⚠️  MISSING DEPENDENCIES:$MISSING"
  case "$MISSING" in *swiftc*)
    echo "     • swiftc (Xcode command line tools) - without it there is NO menu bar"
    echo "       and no chip temperature sensor. Only the battery fuse remains." ;;
  esac
  case "$MISSING" in *brew*)
    echo "     • Homebrew - needed to install macmon (chip temperature"
    echo "       and fan speeds)." ;;
  esac
  echo ""
  if [ -t 0 ] && [ -t 1 ]; then
    case "$MISSING" in *swiftc*)
      printf "  Run 'xcode-select --install' now? [Y/n] "
      read -r ANS
      case "${ANS:-Y}" in
        [TtYy]*|"")
          xcode-select --install 2>/dev/null \
            && echo "  → an Apple dialog opened. Finish that install and RUN THIS SCRIPT AGAIN." \
            || echo "  → the tools are already there or still installing. Wait and run the script again."
          echo ""
          echo "  Stopping here rather than installing half the product."
          exit 1 ;;
        *) echo "  → skipping. The menu bar and chip sensor will NOT be installed." ;;
      esac ;;
    esac
    case "$MISSING" in *brew*)
      echo "  Install Homebrew yourself (deliberately - it is an external script asking for sudo):"
      # shellcheck disable=SC2016  # deliberately NOT expanded: a command to copy-paste
      echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
      printf "  Continue WITHOUT macmon? [Y/n] "
      read -r ANS2
      case "${ANS2:-Y}" in [Nn]*) echo "  Aborted."; exit 1 ;; esac ;;
    esac
  else
    echo "  (non-interactive mode - installing what is possible)"
    case "$MISSING" in *swiftc*) echo "     fix:  xcode-select --install" ;; esac
    # shellcheck disable=SC2016  # deliberately NOT expanded: a command to copy-paste
    case "$MISSING" in *brew*)   echo '     fix:  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"' ;; esac
  fi
  echo ""
fi

# Redistributed binaries must not inherit the build host's minimum OS:
# without -target, swiftc stamps the host macOS version as minos and the
# resulting app refuses to launch on every older, still-supported system
# (Info.plist promises 14.0 - the executable has to honour it).
SWIFT_TARGET="arm64-apple-macosx14.0"

# 1. thermal state sensor (Swift, no sudo)
if command -v swiftc >/dev/null 2>&1; then
  swiftc -O -target "$SWIFT_TARGET" -o "$BIN/thermalstate" "$SRC/thermalstate.swift" && echo "  ✅ thermalstate compiled"
else
  echo "  ⚠️  no swiftc (xcode-select --install) - the guard will use battery temperature only"
fi

# 1b. macmon - CHIP temperature without sudo (via IOReport).
# The battery heats up minutes behind the SoC, so its reading alone reacts too
# late. IOHIDEventSystem sensors are blocked on macOS 26 for unprivileged
# processes - IOReport (macmon) still works. Without macmon the guard does not
# fail, it only loses chip thresholds and fan readings.
# The installer's own PATH is not the truth here, in either direction: with a
# fresh ARM brew the user's shell often still lacks /opt/homebrew/bin (so a
# macmon installed seconds earlier as a dependency looked missing), while a copy
# under /usr/local/bin from an Intel Homebrew looks present to the shell and
# stays invisible to the daemon. Only these locations count, because they are
# the ones the daemon searches: /opt/homebrew/bin plus the PATH in its plist.
macmon_visible_to_daemon() {
  for candidate in /opt/homebrew/bin/macmon "$HOME/.local/bin/macmon" \
                   /usr/bin/macmon /bin/macmon /usr/sbin/macmon /sbin/macmon; do
    [ -x "$candidate" ] && return 0
  done
  return 1
}

if macmon_visible_to_daemon; then
  echo "  ℹ️  macmon already installed"
elif command -v brew >/dev/null 2>&1; then
  # An Intel Homebrew installs into /usr/local, which the daemon never reads, so
  # a successful install is not yet a working sensor: confirm the file landed
  # somewhere the daemon looks before claiming the chip is being watched.
  if ! brew install macmon >/dev/null 2>&1; then
    echo "  ⚠️  could not install macmon - the guard will use battery temperature only"
  elif macmon_visible_to_daemon; then
    echo "  ✅ macmon installed (chip temperature + fans)"
  else
    echo "  ⚠️  macmon went to a prefix the daemon does not read (it reads /opt/homebrew/bin/macmon), most likely an Intel Homebrew under /usr/local - the guard will use battery temperature only"
  fi
else
  echo "  ⚠️  no brew and no macmon - the guard will use battery temperature only"
fi

# 1c. menu bar - a compile error must be VISIBLE, not swallowed
if command -v swiftc >/dev/null 2>&1; then
  HB_VERSION="$(heatbar_version)"
  if [ -z "$HB_VERSION" ]; then
    echo "  ⚠️  menu bar NOT built - no let VERSION in heatbar.swift"
  else
    mkdir -p "$APP_MACOS" "$APP_RESOURCES"
  fi
  if [ -n "${HB_VERSION:-}" ] && swiftc -O -target "$SWIFT_TARGET" -o "$BAR_EXEC" "$SRC/heatbar.swift" 2>"$BASE/heatbar_build.err"; then
    write_info_plist "$HB_VERSION" "$APP_CONTENTS/Info.plist"
    # The app icon is the SHIELD, not the mascot: a character portrait turns
    # into a blob at 16 px. The shield fills the frame, so it stays legible at
    # 16 px and needs no simplified variant (measured: with and without the
    # flames - indistinguishable at 16 px). `make_icon.sh` still accepts an
    # optional third argument in case one is ever needed.
    if "$SRC/tools/make_icon.sh" "$SRC/branding/app_icon.png" "$APP_RESOURCES/AppIcon.icns" \
        >/dev/null 2>"$BASE/icon_build.err"; then
      echo "  ✅ AppIcon.icns built from branding/app_icon.png"
    else
      echo "  ⚠️  icon NOT built - details: $BASE/icon_build.err"
    fi
    if command -v codesign >/dev/null 2>&1; then
      codesign -s - -f "$APP_BUNDLE" >/dev/null 2>"$BASE/codesign.err" \
        && echo "  ✅ bundle signed ad hoc" \
        || echo "  ⚠️  ad hoc signing failed - details: $BASE/codesign.err"
    else
      echo "  ⚠️  no codesign - the bundle is left unsigned"
    fi
    rm -f "$BIN/coffee-paladin-bar"
    ln -s "$BAR_EXEC" "$BIN/coffee-paladin-bar"
    echo "  ✅ coffee-paladin.app (menu bar) -> $APP_BUNDLE"
    echo "  ✅ coffee-paladin-bar -> $BAR_EXEC"
  else
    echo "  ⚠️  menu bar NOT built - details: $BASE/heatbar_build.err (the daemon works without it)"
  fi
fi

# 2. skrypty
install -m 755 "$SRC/guard.py"  "$BIN/coffee-paladin"
install -m 755 "$SRC/safe-run"  "$BIN/safe-run"
install -m 755 "$SRC/heat"      "$BIN/heat"
install -m 755 "$SRC/thermal-report" "$BIN/thermal-report"
install -m 755 "$SRC/fleet" "$BIN/fleet"
echo "  ✅ coffee-paladin, safe-run, heat, thermal-report, fleet -> $BIN"

# 2b. dzwieki (CC0, patrz sounds/LICENSES.md) - nadpisujemy: to czesc produktu
if [ -d "$SRC/sounds" ]; then
  mkdir -p "$BASE/sounds"
  cp "$SRC/sounds/"*.wav "$BASE/sounds/" 2>/dev/null || true
  cp "$SRC/sounds/LICENSES.md" "$BASE/sounds/" 2>/dev/null || true
  echo "  ✅ sounds -> $BASE/sounds"
fi

# 3. configuration (never overwrites an existing one)
if [ ! -f "$BASE/config.json" ]; then
  cat > "$BASE/config.json" <<'JSON'
{
  "poll_seconds": 15,
  "dry_run": true,
  "soc_pause_c": 85.0,
  "soc_resume_c": 76.0,
  "soc_kill_c": 90.0,
  "fan_alert_temp_c": 70.0,
  "batt_pause_c": 40.0,
  "batt_resume_c": 36.0,
  "batt_kill_c": 45.0,
  "batt_pct_pause": 10,
  "batt_pct_resume": 25,
  "pause_on_thermal_state": "serious",
  "cpu_min_percent": 20.0,
  "max_pause_minutes": 45,
  "max_pause_minutes_batt": 240,
  "demote_after_minutes": 5,
  "notify": true
}
JSON
  chmod 600 "$BASE/config.json"
  echo "  ✅ config.json (chip 85/90 °C, battery 40/45 °C, gate 10 %)"
  echo "  ℹ️  STARTING IN WATCH-ONLY MODE: the guard measures and alerts but pauses nothing."
  echo "      Enable protection in the menu bar (🌡 > one click) or: dry_run=false in config.json"
else
  echo "  ℹ️  config.json already exists - leaving it alone"
  # An existing install kept every readout on the bar, because that used to be the
  # default. The default is now the chip alone, so without this the upgrade would
  # quietly take GPU, battery, fans, watts, RAM and disk away from someone who
  # never asked for that. Write the old set down explicitly, once, and only when
  # the user has no preferences of their own yet.
  if [ ! -f "$BASE/heatbar.json" ]; then
    cat > "$BASE/heatbar.json" <<'JSON'
{
  "show": {
    "chip": true, "gpu": true, "battery": true, "fans": true, "watts": true,
    "ram": true, "disk": true, "throttle": true, "paused": true,
    "flame": true, "awakeLeft": true, "agent": true
  }
}
JSON
    echo "  ℹ️  bar layout kept as it was (a new install now starts with chip + RAM and conditional markers)"
  fi
fi

# The menu offers "Uninstall", so the script has to be somewhere the app can
# find it. The sources may be a brew cellar, a clone, or a folder the user has
# since deleted; the data directory is the one place that is always there.
if [ -f "$SRC/uninstall.sh" ]; then
  cp "$SRC/uninstall.sh" "$BASE/uninstall.sh" && chmod 755 "$BASE/uninstall.sh"
fi

# 3b. branding: header/footer logos + the paladin (welcome window, menu icon).
# Copy ONLY what the app uses - full-resolution originals
# (branding/paladin.png, branding/paladin.gif) stay in the repo, not in the
# working directory. Swap the files for your own to rebrand your install.
if [ -d "$SRC/branding" ]; then
  for g in logo_footer.png logo_footer_dark.png \
           paladin_welcome.gif paladin_welcome.png; do
    [ -f "$SRC/branding/$g" ] && cp "$SRC/branding/$g" "$BASE/"
  done
  echo "  ✅ artwork (logos + the paladin) copied"
fi

# The header wordmark we shipped up to 3.2.7 is gone from the repo, but every
# install from that era still has a copy, and the menu would keep drawing it.
# Match the hash before deleting: a logo.png someone put there themselves is
# their rebrand (see README, Branding) and must survive the upgrade.
if [ -f "$BASE/logo.png" ] && \
   [ "$(shasum -a 256 "$BASE/logo.png" | cut -d' ' -f1)" = \
     "f9ce4edcd706735f4c67a3dd9efa687425dade2db7986b6956aed899f9a9d3df" ]; then
  rm -f "$BASE/logo.png"
fi

# 3c. skill for AI agents (Claude Code and compatible): teaches the agent to
# read the thermal state, launch heavy jobs through safe-run and NOT fight a
# guard pause. This is a real problem: an agent that launches eight parallel
# jobs without watching the temperature is exactly what this program protects
# against.
if [ -f "$SRC/skills/coffee-paladin/SKILL.md" ] && [ -d "$HOME/.claude" ]; then
  mkdir -p "$HOME/.claude/skills/coffee-paladin"
  cp "$SRC/skills/coffee-paladin/SKILL.md" "$HOME/.claude/skills/coffee-paladin/SKILL.md"
  echo "  ✅ Claude Code skill installed (the agent will cooperate with the guard)"
fi

# The same skill, same AgentSkills format, for the other hosts that read it.
# Only into trees that already exist: an absent ~/.agents or ~/.grok means the
# user never installed that tool, and planting its config is not our call.
if [ -f "$SRC/skills/coffee-paladin/SKILL.md" ]; then
  for SKILL_ROOT in "$HOME/.agents/skills" "$HOME/.grok/skills"; do
    [ -d "$(dirname "$SKILL_ROOT")" ] || continue
    mkdir -p "$SKILL_ROOT/coffee-paladin"
    cp "$SRC/skills/coffee-paladin/SKILL.md" "$SKILL_ROOT/coffee-paladin/SKILL.md"
    echo "  ✅ agent skill installed in $SKILL_ROOT"
  done
fi

# 3d. Claude Code statusline: one line with the thermal state inside the coding
# session. The script is always copied (harmless without Claude Code); the
# user's ~/.claude/settings.json is touched ONLY when it has no statusLine of
# its own - somebody else's statusline is never overwritten without --replace.
if [ -f "$SRC/integrations/claude-code/statusline.sh" ]; then
  cp "$SRC/integrations/claude-code/statusline.sh" "$BASE/statusline.sh"
  cp "$SRC/integrations/claude-code/settings_wire.py" "$BASE/settings_wire.py"
  cp "$SRC/integrations/claude-code/agent_hook.py" "$BASE/agent_hook.py"
  chmod 0755 "$BASE/statusline.sh" "$BASE/settings_wire.py" "$BASE/agent_hook.py"
  # Gate adapters for the other agent CLIs (Codex, Gemini, Grok, Antigravity).
  # Copied so `coffee-paladin-wire` and uninstall.sh can run them later; the
  # gate itself stays OPT-IN everywhere - nothing is wired here.
  for AGENT_WIRE in codex gemini grok antigravity; do
    if [ -f "$SRC/integrations/$AGENT_WIRE/hooks_wire.py" ]; then
      cp "$SRC/integrations/$AGENT_WIRE/hooks_wire.py" "$BASE/${AGENT_WIRE}_hooks_wire.py"
      chmod 0755 "$BASE/${AGENT_WIRE}_hooks_wire.py"
    fi
  done
  if [ -d "$HOME/.claude" ]; then
    REPLACE_FLAG=""
    for a in "$@"; do [ "$a" = "--replace" ] && REPLACE_FLAG="--replace"; done
    case "$(/usr/bin/python3 "$BASE/settings_wire.py" wire "$BASE/statusline.sh" $REPLACE_FLAG)" in
      ok)      echo "  ✅ Claude Code statusline wired (thermal state inside the session)" ;;
      foreign) echo "  ℹ️  Claude Code already has its own statusline - left untouched."
               echo "     To use the paladin's instead:  bash install.sh --replace" ;;
      skip)    echo "  ℹ️  ~/.claude/settings.json is not valid JSON - statusline not wired" ;;
    esac
  fi
fi

# a service counts as running ONLY with a PID - "loaded" is not enough
# (found in the field: the bar was listed without a PID while the installer
# reported success)
has_pid() { launchctl list | awk -v l="$1" '$3==l && $1 != "-" {found=1} END {exit !found}'; }

# 4. LaunchAgent (demon)
HOME_SED="$(sed_repl "$HOME")"
BAR_EXEC_SED="$(sed_repl "$BAR_EXEC")"
sed "s|__HOME__|$HOME_SED|g" "$SRC/pl.pawel.coffee-paladin.plist" > "$PLIST"
launchctl bootout "gui/$UID/$AGENT" 2>/dev/null
sleep 3   # bootout is asynchronous - without this, bootstrap returns an I/O error
for _ in 1 2 3; do
  launchctl bootstrap "gui/$UID" "$PLIST" 2>/dev/null || launchctl load "$PLIST" 2>/dev/null
  sleep 3
  has_pid "$AGENT" && break
done
if has_pid "$AGENT"; then
  echo "  ✅ daemon started and will start at every login"
else
  echo "  ❌ daemon did not start - check $BASE/stderr.log"
fi

# 5. menu bar (separate agent - can be disabled without touching the fuse)
if [ -x "$BAR_EXEC" ] && [ -f "$SRC/pl.pawel.coffee-paladin-bar.plist" ]; then
  HB="$HOME/Library/LaunchAgents/pl.pawel.coffee-paladin-bar.plist"
  sed -e "s|__HOME__|$HOME_SED|g" -e "s|__BAR_EXEC__|$BAR_EXEC_SED|g" \
    "$SRC/pl.pawel.coffee-paladin-bar.plist" > "$HB"
  launchctl bootout "gui/$UID/pl.pawel.coffee-paladin-bar" 2>/dev/null
  sleep 3   # bootout is asynchronous - same as for the daemon
  for _ in 1 2 3; do
    launchctl bootstrap "gui/$UID" "$HB" 2>/dev/null || launchctl load "$HB" 2>/dev/null
    sleep 3
    has_pid "pl.pawel.coffee-paladin-bar" && break
    launchctl kickstart "gui/$UID/pl.pawel.coffee-paladin-bar" 2>/dev/null
    sleep 2
    has_pid "pl.pawel.coffee-paladin-bar" && break
  done
  has_pid "pl.pawel.coffee-paladin-bar" \
    && { echo "  ✅ menu bar is running - look for the THERMOMETER with temperatures in the top-right corner (the shield is only the Finder icon)"; \
         echo "     cannot see it? A menu bar with a notch may have no room, and macOS then draws nothing:"; \
         echo "       $BIN/coffee-paladin bar icon-only     (shrinks it to a single icon)"; } \
    || echo "  ⚠️  menu bar did not start - check $BASE/heatbar.err and: launchctl kickstart gui/$UID/pl.pawel.coffee-paladin-bar"
fi

echo
# Every hint below is a command someone will copy. If $BIN is not on their PATH
# the bare name fails, and the failure looks like a broken install rather than a
# missing directory - so print the full path exactly when it is needed, and say
# once how to stop needing it.
case ":$PATH:" in
  *":$BIN:"*) P="" ;;
  *)          P="$BIN/" ;;
esac
echo "Check the state now:   ${P}heat"
echo "Run heavy jobs with:   ${P}safe-run -- <command>"
echo "Disable the menu bar:  launchctl bootout gui/$UID/pl.pawel.coffee-paladin-bar"
echo "Fleet (several Macs):  ${P}fleet --setup"
echo "Uninstall:             bash $BASE/uninstall.sh"
if [ -n "$P" ]; then
  echo ""
  echo "  ℹ️  $BIN is not on your PATH, hence the full paths above. To use short names:"
  echo "       echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.zshrc && exec zsh"
fi
