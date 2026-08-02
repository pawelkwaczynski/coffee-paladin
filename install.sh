#!/bin/bash
# install.sh — instaluje coffee-paladin na tym Macu.
# Uruchom: bash install.sh   (z katalogu repozytorium)
set -uo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
BASE="$HOME/.coffee-paladin"
AGENT="pl.pawel.coffee-paladin"
PLIST="$HOME/Library/LaunchAgents/$AGENT.plist"

# Instalacje sprzed 2.0.0 trzymaly dane w ~/.thermal-guard i mialy inne etykiety uslug.
# Automigracji juz nie ma (nikt jej nie potrzebuje), ale zostawienie WCZYTANYCH starych
# uslug wskazujacych na nieistniejace binarki to cichy smiec w launchd - a osierocona
# historia pomiarow to material dowodowy, ktory user moze chciec zachowac.
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
# katalog danych tylko dla wlasciciela: config.json trzyma temat ntfy (jedyne
# zabezpieczenie powiadomien), a managed/ pelne linie polecen zadan
chmod 700 "$BASE" "$BASE/managed" 2>/dev/null || true

# swieze konto / niekompletna paczka: sprawdz zrodla ZANIM cokolwiek ruszymy
for f in guard.py safe-run heat thermal-report fleet thermalstate.swift heatbar.swift \
         pl.pawel.coffee-paladin.plist pl.pawel.coffee-paladin-bar.plist; do
  if [ ! -f "$SRC/$f" ]; then
    echo "  ❌ brak pliku zrodlowego: $SRC/$f — przerwano (niepelna paczka/klon?)"
    exit 1
  fi
done

# 0. ZALEZNOSCI. Bez swiftc tracisz NARAZ czujnik chipa i pasek menu - zostaje sam
# bezpiecznik bateryjny, czyli polowa produktu. Dlatego pytamy o to NA POCZATKU,
# a nie ostrzegamy w polowie instalacji, gdy uzytkownik juz nie patrzy.
#
# `xcode-select --install` uruchamiamy sami: to narzedzie Apple, otwiera systemowe
# okno i nie wymaga podawania hasla obcemu skryptowi.
# HOMEBREW INSTALUJEMY TYLKO RECZNIE - jego instalator to `curl | bash` z zewnetrznego
# adresu, proszacy o sudo. Skrypt, ktory robi to za uzytkownika bez pytania, uczy zlego
# nawyku; podajemy komende i zostawiamy decyzje czlowiekowi.
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

# 1c. pasek menu — blad kompilacji ma byc WIDOCZNY, nie polkniety
if command -v swiftc >/dev/null 2>&1; then
  if swiftc -O -o "$BIN/coffee-paladin-bar" "$SRC/heatbar.swift" 2>"$BASE/heatbar_build.err"; then
    echo "  ✅ coffee-paladin-bar (pasek menu) zbudowany"
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
  chmod 600 "$BASE/config.json"
  echo "  ✅ config.json (chip 85/90 °C, bateria 40/45 °C, bramka 10 %)"
  echo "  ℹ️  START W TRYBIE OBSERWACJI: guard mierzy i alarmuje, ale niczego nie wstrzymuje."
  echo "      Ochronę włączysz w menu paska (🌡 > jeden klik) albo: dry_run=false w config.json"
else
  echo "  ℹ️  config.json już istnieje — zostawiam"
fi

# 3b. branding: logo naglowka/stopki + paladyn (okno powitalne, ikona menu).
# Kopiujemy TYLKO to, czego uzywa aplikacja — oryginaly w pelnej rozdzielczosci
# (branding/paladin.png, branding/paladin.gif) zostaja w repo, nie w katalogu roboczym.
# Podmien pliki na wlasne, jesli chcesz przebrandowac swoja instalacje.
if [ -d "$SRC/branding" ]; then
  for g in logo.png logo_footer.png logo_footer_dark.png \
           paladin_welcome.gif paladin_welcome.png; do
    [ -f "$SRC/branding/$g" ] && cp "$SRC/branding/$g" "$BASE/"
  done
  echo "  ✅ grafika (logotypy + paladyn) skopiowana"
fi

# 3c. skill dla agentow AI (Claude Code i zgodne): uczy agenta czytac stan termiczny,
# odpalac ciezkie zadania przez safe-run i NIE walczyc z pauza guarda. To jest realny
# problem: agent, ktory odpala osiem rownoleglych zadan i nie patrzy na temperature,
# jest dokladnie tym, przed czym ten program ma chronic.
if [ -f "$SRC/skills/coffee-paladin/SKILL.md" ] && [ -d "$HOME/.claude" ]; then
  mkdir -p "$HOME/.claude/skills/coffee-paladin"
  cp "$SRC/skills/coffee-paladin/SKILL.md" "$HOME/.claude/skills/coffee-paladin/SKILL.md"
  echo "  ✅ skill dla Claude Code zainstalowany (agent bedzie wspolpracowal z guardem)"
fi

# uslugu uznajemy za dzialajaca TYLKO gdy ma PID — "wczytana" to za malo
# (znalezisko z Neo: pasek byl wyliczony bez PID, a instalator raportowal sukces)
ma_pid() { launchctl list | awk -v l="$1" '$3==l && $1 != "-" {found=1} END {exit !found}'; }

# 4. LaunchAgent (demon)
sed "s|__HOME__|$HOME|g" "$SRC/pl.pawel.coffee-paladin.plist" > "$PLIST"
launchctl bootout "gui/$UID/$AGENT" 2>/dev/null
sleep 3   # bootout jest asynchroniczny — bez tego bootstrap zwraca I/O error
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

# 5. pasek menu (osobny agent — mozna wylaczyc nie ruszajac bezpiecznika)
if [ -x "$BIN/coffee-paladin-bar" ] && [ -f "$SRC/pl.pawel.coffee-paladin-bar.plist" ]; then
  HB="$HOME/Library/LaunchAgents/pl.pawel.coffee-paladin-bar.plist"
  sed "s|__HOME__|$HOME|g" "$SRC/pl.pawel.coffee-paladin-bar.plist" > "$HB"
  launchctl bootout "gui/$UID/pl.pawel.coffee-paladin-bar" 2>/dev/null
  sleep 3   # bootout jest asynchroniczny — jak przy demonie
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
