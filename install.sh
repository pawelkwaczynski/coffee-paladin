#!/bin/bash
# install.sh — instaluje thermal-guard na tym Macu.
# Uruchom: bash install.sh   (z katalogu repozytorium)
set -uo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
BASE="$HOME/.thermal-guard"
AGENT="pl.pawel.thermal-guard"
PLIST="$HOME/Library/LaunchAgents/$AGENT.plist"

echo "== thermal-guard: instalacja na $(scutil --get ComputerName 2>/dev/null || hostname) =="
mkdir -p "$BIN" "$BASE" "$BASE/managed"

# 1. czujnik stanu termicznego (Swift, bez sudo)
if command -v swiftc >/dev/null 2>&1; then
  swiftc -O -o "$BIN/thermalstate" "$SRC/thermalstate.swift" && echo "  ✅ thermalstate skompilowany"
else
  echo "  ⚠️  brak swiftc (xcode-select --install) — guard użyje samej temperatury baterii"
fi

# 1b. macmon — temperatura CHIPA bez sudo (przez IOReport).
# Bateria grzeje sie z kilkuminutowym opoznieniem wzgledem SoC, wiec sam jej odczyt
# reaguje za pozno. Sensory przez IOHIDEventSystem sa na macOS 26 zablokowane dla
# procesow bez uprawnien — IOReport (macmon) nadal dziala. Bez macmona guard nie padnie,
# tylko straci progi chipa i wentylatory.
if command -v macmon >/dev/null 2>&1; then
  echo "  ℹ️  macmon już jest"
elif command -v brew >/dev/null 2>&1; then
  brew install macmon >/dev/null 2>&1 && echo "  ✅ macmon zainstalowany (temperatura chipa + wentylatory)" \
    || echo "  ⚠️  nie udało się zainstalować macmon — guard użyje samej baterii"
else
  echo "  ⚠️  brak brew i macmon — guard użyje samej temperatury baterii"
fi

# 1c. pasek menu
if command -v swiftc >/dev/null 2>&1; then
  swiftc -O -o "$BIN/heatbar" "$SRC/heatbar.swift" 2>/dev/null && echo "  ✅ heatbar (pasek menu) zbudowany"
fi

# 2. skrypty
install -m 755 "$SRC/guard.py"  "$BIN/thermal-guard"
install -m 755 "$SRC/safe-run"  "$BIN/safe-run"
install -m 755 "$SRC/heat"      "$BIN/heat"
install -m 755 "$SRC/thermal-report" "$BIN/thermal-report"
install -m 755 "$SRC/fleet" "$BIN/fleet"
echo "  ✅ thermal-guard, safe-run, heat, thermal-report, fleet -> $BIN"

# 3. konfiguracja (nie nadpisuje istniejącej)
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
  echo "  ✅ config.json (chip 85/90 °C, bateria 40/45 °C, bramka 10 %)"
  echo "  ℹ️  START W TRYBIE OBSERWACJI: guard mierzy i alarmuje, ale niczego nie wstrzymuje."
  echo "      Ochronę włączysz w menu paska (🌡 > jeden klik) albo: dry_run=false w config.json"
else
  echo "  ℹ️  config.json już istnieje — zostawiam"
fi

# 3b. branding (opcjonalny): logo do naglowka i stopki menu. Katalog branding/ nie jest
# czescia publicznego repo — jesli istnieje (paczka prywatna), kopiujemy logotypy.
if [ -d "$SRC/branding" ]; then
  cp "$SRC/branding/"*.png "$BASE/" 2>/dev/null && echo "  ✅ logotypy (naglowek + stopka) skopiowane"
fi

# 4. LaunchAgent (demon)
sed "s|__HOME__|$HOME|g" "$SRC/pl.pawel.thermal-guard.plist" > "$PLIST"
launchctl bootout "gui/$UID/$AGENT" 2>/dev/null
sleep 3   # bootout jest asynchroniczny — bez tego bootstrap zwraca I/O error
for _ in 1 2 3; do
  launchctl bootstrap "gui/$UID" "$PLIST" 2>/dev/null || launchctl load "$PLIST" 2>/dev/null
  sleep 3
  launchctl list | grep -q "$AGENT" && break
done
if launchctl list | grep -q "$AGENT"; then
  echo "  ✅ demon wystartował i wstaje po każdym logowaniu"
else
  echo "  ❌ demon nie wstał — sprawdź $BASE/stderr.log"
fi

# 5. pasek menu (osobny agent — mozna wylaczyc nie ruszajac bezpiecznika)
if [ -x "$BIN/heatbar" ] && [ -f "$SRC/pl.pawel.heatbar.plist" ]; then
  HB="$HOME/Library/LaunchAgents/pl.pawel.heatbar.plist"
  sed "s|__HOME__|$HOME|g" "$SRC/pl.pawel.heatbar.plist" > "$HB"
  launchctl bootout "gui/$UID/pl.pawel.heatbar" 2>/dev/null
  sleep 2
  launchctl bootstrap "gui/$UID" "$HB" 2>/dev/null || launchctl load "$HB" 2>/dev/null
  sleep 2
  launchctl list | grep -q "pl.pawel.heatbar" \
    && echo "  ✅ pasek menu działa (🌡 w prawym górnym rogu)" \
    || echo "  ⚠️  pasek menu nie wstał — sprawdź $BASE/heatbar.err"
fi

echo
echo "Sprawdź teraz:  heat"
echo "Ciężkie zadania odpalaj:  safe-run -- <polecenie>"
echo "Pasek menu wyłączysz:  launchctl bootout gui/$UID/pl.pawel.heatbar"
echo "Flota (wiele Maków):   fleet --setup"
echo "Odinstalowanie:        bash uninstall.sh"
