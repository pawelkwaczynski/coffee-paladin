#!/bin/bash
# install.sh — instaluje coffee-paladin na tym Macu.
# Uruchom: bash install.sh   (z katalogu repozytorium)
set -uo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
BASE="$HOME/.coffee-paladin"
AGENT="pl.pawel.coffee-paladin"
PLIST="$HOME/Library/LaunchAgents/$AGENT.plist"

sed_repl() {
  printf '%s' "$1" | sed 's/[&|\\]/\\&/g'
}

wybierz_katalog_aplikacji() {
  if [ -n "${COFFEE_PALADIN_APP_PARENT:-}" ]; then
    printf '%s\n' "$COFFEE_PALADIN_APP_PARENT"
  elif [ -d /Applications ] && [ -w /Applications ]; then
    printf '%s\n' "/Applications"
  else
    printf '%s\n' "$HOME/Applications"
  fi
}

wersja_heatbar() {
  awk -F\" '/let VERSION = "/ {print $2; exit}' "$SRC/heatbar.swift"
}

zapisz_info_plist() {
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

APP_PARENT="$(wybierz_katalog_aplikacji)"
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
  echo "  ⚠️  znaleziono ~/.thermal-guard (dane sprzed zmiany nazwy)."
  echo "     Historia pomiarow i czarna skrzynka zostaly tam - przenies je recznie,"
  echo "     jesli sa Ci potrzebne:  mv ~/.thermal-guard/history.csv ~/.coffee-paladin/"
fi

echo "== coffee-paladin: instalacja na $(scutil --get ComputerName 2>/dev/null || hostname) =="
mkdir -p "$BIN" "$BASE" "$BASE/managed" "$HOME/Library/LaunchAgents"
# data directory owner-only: config.json holds the ntfy topic (the only
# protection for notifications) and managed/ holds full job command lines
chmod 700 "$BASE" "$BASE/managed" 2>/dev/null || true

# fresh account / incomplete package: check the sources BEFORE touching anything
for f in guard.py safe-run heat thermal-report fleet thermalstate.swift heatbar.swift \
         pl.pawel.coffee-paladin.plist pl.pawel.coffee-paladin-bar.plist \
         branding/paladin.png branding/app_icon.png tools/zrob_ikone.sh; do
  if [ ! -f "$SRC/$f" ]; then
    echo "  ❌ brak pliku zrodlowego: $SRC/$f — przerwano (niepelna paczka/klon?)"
    exit 1
  fi
done
echo "  ℹ️  bundle aplikacji: $APP_BUNDLE"

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
BRAKI=""
if ! command -v swiftc >/dev/null 2>&1; then BRAKI="$BRAKI swiftc"; fi
if ! command -v brew   >/dev/null 2>&1; then BRAKI="$BRAKI brew"; fi

if [ -n "$BRAKI" ]; then
  echo ""
  echo "  ⚠️  BRAKUJE ZALEZNOSCI:$BRAKI"
  case "$BRAKI" in *swiftc*)
    echo "     • swiftc (Xcode command line tools) — bez niego NIE BEDZIE paska menu"
    echo "       ani czujnika temperatury chipa. Zostanie sam bezpiecznik bateryjny." ;;
  esac
  case "$BRAKI" in *brew*)
    echo "     • Homebrew — bez niego nie da sie pobrac macmon (temperatura chipa"
    echo "       i obroty wentylatorow)." ;;
  esac
  echo ""
  if [ -t 0 ] && [ -t 1 ]; then
    case "$BRAKI" in *swiftc*)
      printf "  Uruchomic teraz 'xcode-select --install'? [T/n] "
      read -r ODP
      case "${ODP:-T}" in
        [TtYy]*|"")
          xcode-select --install 2>/dev/null \
            && echo "  → otworzylo sie okno Apple. Dokoncz instalacje i URUCHOM TEN SKRYPT PONOWNIE." \
            || echo "  → narzedzia juz sa albo instalacja trwa. Poczekaj i uruchom skrypt ponownie."
          echo ""
          echo "  Przerywam, zeby nie zainstalowac polowy produktu."
          exit 1 ;;
        *) echo "  → pomijam. Pasek menu i czujnik chipa NIE zostana zainstalowane." ;;
      esac ;;
    esac
    case "$BRAKI" in *brew*)
      echo "  Homebrew zainstalujesz sam (swiadomie - to skrypt z zewnatrz, prosi o sudo):"
      # shellcheck disable=SC2016  # celowo BEZ rozwijania: to komenda do skopiowania
      echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
      printf "  Kontynuowac BEZ macmon? [T/n] "
      read -r ODP2
      case "${ODP2:-T}" in [Nn]*) echo "  Przerwano."; exit 1 ;; esac ;;
    esac
  else
    echo "  (tryb nieinteraktywny — instaluje to, co sie da)"
    case "$BRAKI" in *swiftc*) echo "     napraw:  xcode-select --install" ;; esac
    # shellcheck disable=SC2016  # celowo BEZ rozwijania: to komenda do skopiowania
    case "$BRAKI" in *brew*)   echo '     napraw:  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"' ;; esac
  fi
  echo ""
fi

# 1. thermal state sensor (Swift, no sudo)
if command -v swiftc >/dev/null 2>&1; then
  swiftc -O -o "$BIN/thermalstate" "$SRC/thermalstate.swift" && echo "  ✅ thermalstate skompilowany"
else
  echo "  ⚠️  brak swiftc (xcode-select --install) — guard użyje samej temperatury baterii"
fi

# 1b. macmon - CHIP temperature without sudo (via IOReport).
# The battery heats up minutes behind the SoC, so its reading alone reacts too
# late. IOHIDEventSystem sensors are blocked on macOS 26 for unprivileged
# processes - IOReport (macmon) still works. Without macmon the guard does not
# fail, it only loses chip thresholds and fan readings.
if command -v macmon >/dev/null 2>&1; then
  echo "  ℹ️  macmon już jest"
elif command -v brew >/dev/null 2>&1; then
  brew install macmon >/dev/null 2>&1 && echo "  ✅ macmon zainstalowany (temperatura chipa + wentylatory)" \
    || echo "  ⚠️  nie udało się zainstalować macmon — guard użyje samej baterii"
else
  echo "  ⚠️  brak brew i macmon — guard użyje samej temperatury baterii"
fi

# 1c. menu bar - a compile error must be VISIBLE, not swallowed
if command -v swiftc >/dev/null 2>&1; then
  HB_VERSION="$(wersja_heatbar)"
  if [ -z "$HB_VERSION" ]; then
    echo "  ⚠️  pasek NIE zbudowany — brak let VERSION w heatbar.swift"
  else
    mkdir -p "$APP_MACOS" "$APP_RESOURCES"
  fi
  if [ -n "${HB_VERSION:-}" ] && swiftc -O -o "$BAR_EXEC" "$SRC/heatbar.swift" 2>"$BASE/heatbar_build.err"; then
    zapisz_info_plist "$HB_VERSION" "$APP_CONTENTS/Info.plist"
    # The app icon is the SHIELD, not the mascot: a character portrait turns
    # into a blob at 16 px. The shield fills the frame, so it stays legible at
    # 16 px and needs no simplified variant (measured: with and without the
    # flames - indistinguishable at 16 px). `zrob_ikone.sh` still accepts an
    # optional third argument in case one is ever needed.
    if "$SRC/tools/zrob_ikone.sh" "$SRC/branding/app_icon.png" "$APP_RESOURCES/AppIcon.icns" \
        >/dev/null 2>"$BASE/icon_build.err"; then
      echo "  ✅ AppIcon.icns zbudowany z branding/app_icon.png"
    else
      echo "  ⚠️  ikona NIE zbudowana — szczegoly: $BASE/icon_build.err"
    fi
    if command -v codesign >/dev/null 2>&1; then
      codesign -s - -f "$APP_BUNDLE" >/dev/null 2>"$BASE/codesign.err" \
        && echo "  ✅ bundle podpisany ad hoc" \
        || echo "  ⚠️  podpis ad hoc nieudany — szczegoly: $BASE/codesign.err"
    else
      echo "  ⚠️  brak codesign — bundle zostal bez podpisu ad hoc"
    fi
    rm -f "$BIN/coffee-paladin-bar"
    ln -s "$BAR_EXEC" "$BIN/coffee-paladin-bar"
    echo "  ✅ coffee-paladin.app (pasek menu) -> $APP_BUNDLE"
    echo "  ✅ coffee-paladin-bar -> $BAR_EXEC"
  else
    echo "  ⚠️  pasek NIE zbudowany — szczegoly: $BASE/heatbar_build.err (demon dziala bez paska)"
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
  echo "  ✅ dzwieki -> $BASE/sounds"
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
  echo "  ✅ config.json (chip 85/90 °C, bateria 40/45 °C, bramka 10 %)"
  echo "  ℹ️  START W TRYBIE OBSERWACJI: guard mierzy i alarmuje, ale niczego nie wstrzymuje."
  echo "      Ochronę włączysz w menu paska (🌡 > jeden klik) albo: dry_run=false w config.json"
else
  echo "  ℹ️  config.json już istnieje — zostawiam"
fi

# 3b. branding: header/footer logos + the paladin (welcome window, menu icon).
# Copy ONLY what the app uses - full-resolution originals
# (branding/paladin.png, branding/paladin.gif) stay in the repo, not in the
# working directory. Swap the files for your own to rebrand your install.
if [ -d "$SRC/branding" ]; then
  for g in logo.png logo_footer.png logo_footer_dark.png \
           paladin_welcome.gif paladin_welcome.png; do
    [ -f "$SRC/branding/$g" ] && cp "$SRC/branding/$g" "$BASE/"
  done
  echo "  ✅ grafika (logotypy + paladyn) skopiowana"
fi

# 3c. skill for AI agents (Claude Code and compatible): teaches the agent to
# read the thermal state, launch heavy jobs through safe-run and NOT fight a
# guard pause. This is a real problem: an agent that launches eight parallel
# jobs without watching the temperature is exactly what this program protects
# against.
if [ -f "$SRC/skills/coffee-paladin/SKILL.md" ] && [ -d "$HOME/.claude" ]; then
  mkdir -p "$HOME/.claude/skills/coffee-paladin"
  cp "$SRC/skills/coffee-paladin/SKILL.md" "$HOME/.claude/skills/coffee-paladin/SKILL.md"
  echo "  ✅ skill dla Claude Code zainstalowany (agent bedzie wspolpracowal z guardem)"
fi

# a service counts as running ONLY with a PID - "loaded" is not enough
# (found in the field: the bar was listed without a PID while the installer
# reported success)
ma_pid() { launchctl list | awk -v l="$1" '$3==l && $1 != "-" {found=1} END {exit !found}'; }

# 4. LaunchAgent (demon)
HOME_SED="$(sed_repl "$HOME")"
BAR_EXEC_SED="$(sed_repl "$BAR_EXEC")"
sed "s|__HOME__|$HOME_SED|g" "$SRC/pl.pawel.coffee-paladin.plist" > "$PLIST"
launchctl bootout "gui/$UID/$AGENT" 2>/dev/null
sleep 3   # bootout is asynchronous - without this, bootstrap returns an I/O error
for _ in 1 2 3; do
  launchctl bootstrap "gui/$UID" "$PLIST" 2>/dev/null || launchctl load "$PLIST" 2>/dev/null
  sleep 3
  ma_pid "$AGENT" && break
done
if ma_pid "$AGENT"; then
  echo "  ✅ demon wystartował i wstaje po każdym logowaniu"
else
  echo "  ❌ demon nie wstał — sprawdź $BASE/stderr.log"
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
    ma_pid "pl.pawel.coffee-paladin-bar" && break
    launchctl kickstart "gui/$UID/pl.pawel.coffee-paladin-bar" 2>/dev/null
    sleep 2
    ma_pid "pl.pawel.coffee-paladin-bar" && break
  done
  ma_pid "pl.pawel.coffee-paladin-bar" \
    && echo "  ✅ pasek menu działa (🌡 w prawym górnym rogu)" \
    || echo "  ⚠️  pasek menu nie wstał — sprawdź $BASE/heatbar.err i: launchctl kickstart gui/$UID/pl.pawel.coffee-paladin-bar"
fi

echo
echo "Sprawdź teraz:  heat"
echo "Ciężkie zadania odpalaj:  safe-run -- <polecenie>"
echo "Pasek menu wyłączysz:  launchctl bootout gui/$UID/pl.pawel.coffee-paladin-bar"
echo "Flota (wiele Maków):   fleet --setup"
echo "Odinstalowanie:        bash uninstall.sh"
