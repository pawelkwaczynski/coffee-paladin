#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coffee-paladin - watches temperature and load on a Mac, without sudo.

Every N seconds it reads:
  * macOS thermal pressure (thermalstate: nominal/fair/serious/critical)
  * chip and GPU temperature, fan rpm and power draw (macmon -> IOReport)
  * battery temperature (ioreg AppleSmartBattery)
  * CPU throttling (pmset -g therm -> CPU_Speed_Limit)
  * load average and processes, with CPU rolled up across each process subtree (ps)

When it gets hot: SIGSTOP on heavy jobs. When it cools down: SIGCONT. In a critical state:
SIGCONT + SIGTERM so jobs can checkpoint, then SIGKILL after a grace period. The system,
Finder and interactive shells are never touched.

Measurement history: ~/.coffee-paladin/history.csv   (evidence for "what happened at 3 a.m.")
Events:              ~/.coffee-paladin/events.log    (hard shutdowns, cooling alarms)
Log:                 ~/.coffee-paladin/guard.log
State (pauses):      ~/.coffee-paladin/state.json    (restored on start -> nothing stays frozen)
Snapshot for the menu bar: ~/.coffee-paladin/status.json

Usage:
  guard.py            # the loop (this is how the LaunchAgent starts it)
  guard.py --once     # a single pass, prints the reading (for testing)

Language of messages: TG_LANG=en|pl, or "lang" in config.json. Default: en.
"""

import datetime
import json
import os
import re
import errno
import signal
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
BASE = os.environ.get("TG_BASE") or os.path.join(HOME, ".coffee-paladin")
BASE = os.path.expanduser(BASE)   # TG_BASE sluzy do testow w izolacji
CFG_PATH = os.path.join(BASE, "config.json")
STATE_PATH = os.path.join(BASE, "state.json")
LOG_PATH = os.path.join(BASE, "guard.log")
HIST_PATH = os.path.join(BASE, "history.csv")
STATUS_PATH = os.path.join(BASE, "status.json")   # migawka dla paska menu
HEARTBEAT_PATH = os.path.join(BASE, "heartbeat")  # zywy puls — po twardym padzie zostaje ostatni
CLEAN_STOP_PATH = os.path.join(BASE, "clean_stop")
EVENTS_PATH = os.path.join(BASE, "events.log")    # czarna skrzynka: pady, alarmy
COMMAND_PATH = os.path.join(BASE, "command")      # rozkazy z paska menu
AWAKE_PATH = os.path.join(BASE, "awake.json")     # reczny keep-awake z paska (timer/app/download)
HW_PATH = os.path.join(BASE, "hardware.json")     # wykryty sprzet (dla About my Mac i kalibracji)
MANAGED_DIR = os.path.join(BASE, "managed")   # pliki <pid>.json od safe-run
MAX_LOG_BYTES = 5 * 1024 * 1024
MAX_LOG_GENERACJI = 5        # ile zrotowanych pokolen trzymamy (patrz rotate())

# "unknown" to NIE jest "lekko cieplo". To znaczy, ze thermalstate nie odpowiedzial.
# Mapowanie na 1 sprawialo, ze Mac bez baterii i bez macmona (mini, Studio) siedzial
# na poziomie 1 w nieskonczonosc: nigdy nie osiagal 2, wiec nigdy niczego nie pauzowal,
# a w pasku i we flocie wygladal na zdrowa, lekko cieplawa maszyne.
LEVELS = {"nominal": 0, "fair": 1, "serious": 2, "critical": 3, "unknown": 0}

DEFAULTS = {
    "poll_seconds": 15,
    # temperatura baterii w stopniach C (bateria = najlepszy dostepny bez sudo czujnik obudowy)
    "batt_pause_c": 40.0,       # >= tego: pauzujemy ciezkie zadania
    "batt_resume_c": 36.0,      # <= tego: wznawiamy (histereza)
    "batt_kill_c": 45.0,        # >= tego: ubijamy (po grace)
    "pause_on_thermal_state": "serious",   # serious | critical
    "speed_limit_pause": 60,    # CPU_Speed_Limit ponizej tego % = mocny throttling
    # temperatura CHIPA (SoC) — reaguje w sekundach, bateria dopiero po kilku minutach.
    # Czytana przez `macmon` (IOReport, bez sudo). Gdy brak macmon, te progi sa ignorowane.
    # Progi sa celowo ostrzejsze niz fabryczne dlawienie macOS (~100-108 C). Pauza chlodzi
    # chip w kilkanascie sekund (zmierzone: 89 -> 60 C w 19 s), wiec do ubicia w praktyce
    # nie dochodzi — a SIGSTOP niczego nie niszczy. NIE ustawiaj tu 45 C: bezczynny chip
    # M-serii ma 40-55 C, wiec taki prog oznacza permanentna pauze.
    "soc_pause_c": 85.0,        # >= tego: pauza
    "soc_resume_c": 76.0,       # <= tego: wznowienie
    "soc_kill_c": 90.0,         # >= tego: ubicie, ale dopiero po kill_after_polls z rzedu
    # BRAMKA NA BATERIE — zeby dlugie obliczenia nie zjadly laptopa do zera i nie zgasly
    # w polowie bloku. Wznowienie dopiero po podpieciu zasilania.
    "batt_pct_pause": 10,       # <= tego % na baterii: pauza
    "batt_pct_resume": 25,      # wznowienie gdy AC albo naladowane powyzej tego
    # KONTROLA WENTYLATOROW — chip goracy, a wentylatory stoja = awaria chlodzenia.
    # Tylko ostrzega (glosno), nie pauzuje: falszywy alarm nie moze zabijac obliczen.
    # AWARYJNY WYLAPYWACZ: lista nazw nizej zawsze bedzie dziurawa (b3core, cadical...).
    # Kazdy wlasny proces powyzej tego CPU i starszy niz tyle sekund traktujemy jak ciezkie
    # zadanie, nawet jesli nie znamy jego nazwy. never_patterns nadal go chroni.
    # nie pauzuj procesu, ktory trzyma klawiature swojego terminala (SIGTTIN-pulapka)
    "skip_foreground_tty": True,
    "manage_unknown_heavy": True,
    "unknown_cpu_percent": 50.0,
    "unknown_min_seconds": 120,
    # czekanie na zasilacz to nie awaria — pauza z powodu baterii moze trwac duzo dluzej
    "max_pause_minutes_batt": 240,
    "fan_check": True,
    "fan_alert_temp_c": 70.0,   # powyzej tej temperatury chipa wentylatory MUSZA sie krecic
    "cpu_min_percent": 20.0,    # tylko procesy powyzej tego zuzycia sa ruszane
    "max_pause_minutes": 45,    # dluzej niz to w pauzie -> lagodne ubicie (jest checkpoint)
    "fan_alert_polls": 3,       # tyle odczytow z rzedu "goraco + 0 obr/min" -> alarm
    "kill_after_polls": 4,      # tyle kolejnych odczytow krytycznych -> SIGTERM
    # Progi chipu maja histereze (pauza 95 / wznowienie 87), ale drugi wyzwalacz —
    # stan termiczny systemu (`thermalState`) — jest binarny i histerezy NIE MA.
    # Efekt zmierzony 02.08 10:46-10:48: szesc par pauza/wznowienie w cyklach
    # 15-sekundowych przy chipie 84-85 C, czyli DZIESIEC stopni ponizej progu pauzy.
    # Zadanie skakalo, a nic sie nie chlodzilo. Raz wstrzymany proces zostaje
    # wstrzymany co najmniej tyle sekund, zeby pauza mogla cokolwiek dac.
    "min_pause_seconds": 60,
    # ...a pauza z samego stanu systemowego (bez przekroczenia progu chipu) wymaga
    # POTWIERDZENIA w kolejnym cyklu. Pojedynczy skok `thermalState` na "serious"
    # potrafi trwac jeden odczyt.
    "state_confirm_polls": 2,
    "demote_after_minutes": 5,  # goracy chip + proces mielacy dluzej niz to -> background QoS (E-cores)
    "demote_cpu_percent": 60.0,
    # degradacja TYLKO gdy chip >= tego progu (None = soc_resume_c + 4); powrot na
    # rdzenie P przy chip <= soc_resume_c - para progow jak przy pauzie/wznowieniu
    "demote_above_c": None,
    # Systemowe demony indeksowania: nietykalne dla PAUZY i UBICIA (lista never
    # zostaje swieta - decyzja Pawla 06.08.2026, wariant A), ale WOLNO je zepchnac
    # na E-cores, gdy graja i maszyna jest ciepla. Powod: corespotlightd potrafil
    # grzac do 215% CPU przez cala noc jako "untouchable" (165 wpisow, 04/05.08).
    # Domyslnie TYLKO demony per-user (taskpolicy na cudzym procesie i tak by odbil).
    "system_demote_patterns": ["corespotlightd", "spotlightknowledged",
                               "photoanalysisd", "mediaanalysisd"],
    "notify": True,
    "notify_min_gap_s": 300,
    # BANER przy poziomie krytycznym: zwykle powiadomienie latwo przeoczyc (Skupienie,
    # aplikacja na pelnym ekranie) — modalny alert systemowy przebija sie zawsze.
    # Osobny odstep, bo to najwyzszy kaliber alarmu i nie moze spamowac.
    "critical_banner": True,
    "critical_banner_gap_s": 180,
    # PUSH NA TELEFON (ntfy.sh, darmowe, bez konta): wpisz wlasny sekretny temat, zainstaluj
    # aplikacje ntfy i zasubskrybuj ten sam temat — pauzy, ubicia, awarie chlodzenia i twarde
    # pady przychodza jako push. Pusty = wylaczone.
    "ntfy_topic": "",
    # CIEZKIE ZADANIA (safe-run): na jakich rdzeniach i z jakim limitem CPU.
    # "efficiency" = tylko rdzenie E (chlodno, wolno), "all" = wszystkie (szybko, cieplej —
    # temperature i tak pilnuje guard). Limit w % realizowany mikropauzami calej grupy
    # procesow (jak cpulimit); 95 = praktycznie pelna predkosc z odrobina oddechu dla UI.
    "job_cores_mode": "all",   # default wszystkie rdzenie (Pawel, 01.08) - temperatura i tak pod straza
    "job_cpu_percent": 95,
    # prog aktywnosci sieci dla keep-awake "dopoki trwa pobieranie" (KB/s)
    "download_kbps": 500,
    # dzwieki systemowe przy zdarzeniach (afplay — dziala nawet gdy powiadomienia sa
    # wyciszone przez Skupienie). Rozne zdarzenia maja rozne dzwieki, zeby dalo sie
    # rozpoznac bez patrzenia: pauza=nisko, wznowienie=szklo, ubicie/pad=powaznie.
    "sound": False,   # default cisza (Pawel, 01.08) - kto chce, wlaczy w Ustawieniach
    # NIE USYPIAJ, GDY LICZY — jak Caffeine/Amphetamine, ale z bezpiecznikiem: czuwanie
    # trzymamy TYLKO gdy realnie dziala ciezkie zadanie i jest chlodno; przy pauzie/goracu
    # blokade zwalniamy (sen chlodzi najszybciej), po zakonczeniu zadania Mac normalnie
    # zasypia. Amphetamine trzymane bezwarunkowo to klasyczna droga do ugotowania laptopa
    # w plecaku — dlatego domyslnie wylaczone, wlacza sie swiadomie w Ustawieniach.
    "keep_awake_auto": False,
    "keep_awake_display": False,   # -d: ekran tez nie gasnie (prezentacje); wiecej ciepla
    # Wygaszanie: po zejsciu ostatniego ciezkiego zadania czuwanie trzyma jeszcze tyle
    # sekund. Bez tego przerwa miedzy plikami kolejki (ffmpeg konczy, nastepny jeszcze
    # nie wystartowal) zwalniala blokade snu - Mac z agresywnym usypianiem potrafilby
    # zasnac W SRODKU kolejki, a licznik przelaczen robil 45-59 wpisow na dobe.
    # Upal ma pierwszenstwo: przy poziomie >=2 czuwanie pada NATYCHMIAST, bez wygaszania.
    "keep_awake_hold_s": 300,
    # DOMYSLNIE TYLKO OBSERWACJA: swieza instalacja mierzy, loguje i ALARMUJE, ale nie
    # wstrzymuje niczyich procesow. Ochrone wlacza sie swiadomie — jednym kliknieciem w menu
    # paska albo "dry_run": false. Narzedzie, ktore od wejscia rusza cudza prace, traci
    # zaufanie przy pierwszym falszywym alarmie; narzedzie, ktore najpierw pokazuje, CO by
    # zrobilo, zdobywa je.
    "dry_run": True,
    # WLASNA NAZWA tego Maca we flocie (tabela fleet + menu). Pusta = nazwa systemowa.
    # Przy 5 maszynach "MacBook Pro (3)" nic nie mowi — "render-01" albo "Neo" mowi wszystko.
    "fleet_label": "",
    # FLOTA: sciezka wspolnego folderu (iCloud/Dropbox/SMB/SharePoint). Gdy ustawiona,
    # guard publikuje tam migawke <hostname>.json — narzedzie `fleet` sklada z nich
    # tabele calej floty. Celowo folder, nie serwer: kazda firma jakis wspolny dysk juz ma.
    "fleet_dir": "",
    # co wolno pauzowac (dopasowanie po nazwie procesu, case-insensitive)
    "managed_patterns": [
        "ffmpeg", "ffprobe", "handbrake", "x265", "x264", "compressor",
        "python", "python3", "uv", "julia", "z3", "geng", "nauty", "lean", "lake",
        "ollama", "llama", "mlx", "whisper", "node", "java", "rustc", "cargo",
        "blender", "rclone", "7z", "zstd", "xz", "tar", "bsdtar", "make", "cc1plus", "clang",
    ],
    # wlasne wzorce doklejane do never_patterns — tu wpisz narzedzia, ktorych u siebie
    # nie chcesz zamrazac (np. dlugo dzialajace CLI, wlasne demony, edytory)
    "never_extra": [],
    # jak wyzej, ale dopasowanie po PELNEJ linii polecenia, nie po nazwie procesu —
    # przydatne, gdy ciezkie zadanie jest uruchamiane przez interpreter (python, node)
    # i sama nazwa procesu nic nie mowi. Tedy chronimy zaplecze agentow AI i edytorow
    # (node z claude/mcp/language-server w argumentach), NIE kazdy node - zwykly
    # `node build.js` ma byc pauzowalny, bo to dokladnie ten przypadek, dla ktorego
    # narzedzie powstalo (znalazl Codex przy recenzji skilla, 01.08.2026)
    "never_arg_patterns": ["coffee-paladin", "guard.py", "safe-run",
                           "claude", "codex", "cursor", "mcp", "language-server", ".vscode"],
    # czego NIE wolno ruszac nigdy (nadrzedne wobec powyzszego)
    "never_patterns": [
        "kernel_task", "windowserver", "launchd", "loginwindow", "logd", "opendirectoryd",
        "backupd", "mds", "mdworker", "spotlight", "fileproviderd", "cloudd", "bird",
        "finder", "dock", "terminal", "ghostty", "iterm", "zsh", "bash", "sshd", "ssh",
        "guard.py", "coffee-paladin", "safe-run", "code helper", "electron",
        # demony systemowe: potrafia dlugo zjadac rdzen, ale odrzucaja SIGSTOP albo psuja
        # sie po zamrozeniu — probowanie ich tylko zasmieca log i blokuje prawdziwe cele
        "duetexpertd", "suggestd", "photoanalysisd", "mediaanalysisd", "coreaudiod",
        "bluetoothd", "powerd", "syspolicyd", "xprotect", "trustd", "nsurlsessiond",
        # INTERAKTYWNE narzedzia i ich zaplecze: SIGSTOP na sesji terminalowej odbiera jej
        # terminal, a SIGCONT wznawia ja JUZ W TLE -> SIGTTIN -> proces stoi na zawsze,
        # mimo ze log mowi "RESUMED". Zamrozenie takiej sesji to jej smierc (Neo, 31.07.2026).
        # Po NAZWIE tylko to, co nigdy nie jest zadaniem obliczeniowym. node/npm/npx/bun/deno
        # celowo TU NIE SA: ciezki build w Node ma byc pauzowalny; zaplecze agentow chronia
        # never_arg_patterns (linia polecen) + skip_foreground_tty (cokolwiek przy klawiaturze).
        "claude", "codex", "cursor",
        "hermes", "hermes-secret", "mcp", "caffeinate", "tmux", "screen", "vim", "nvim",
    ],
}


# ---------------------------------------------------------------- narzedzia

# Klucze configu, ktorych zmiana MUSI zostawic slad w logu. Lekcja z nocy 31.07/01.08:
# progi zmienily sie dwa razy i przez pol nocy nie dalo sie ustalic, kto i kiedy.
LOGOWANE_KLUCZE = (
    "soc_pause_c", "soc_resume_c", "soc_kill_c",
    "batt_pause_c", "batt_resume_c", "batt_kill_c",
    "demote_after_minutes", "demote_above_c", "demote_cpu_percent",
    "max_pause_minutes", "max_pause_minutes_batt", "cpu_min_percent",
    "job_cores_mode", "job_cpu_percent", "dry_run", "lang",
    "keep_awake_hold_s", "system_demote_patterns",
)


def migawka_logowanych(cfg):
    return {k: cfg.get(k) for k in LOGOWANE_KLUCZE}


def loguj_zmiany_configu(poprzednie, cfg):
    """Kazda zmiana obserwowanego klucza -> wpis stara -> nowa. Zwraca nowa migawke."""
    biezace = migawka_logowanych(cfg)
    if poprzednie is not None:
        for k in LOGOWANE_KLUCZE:
            if poprzednie.get(k) != biezace.get(k):
                log("CONFIG CHANGED %s: %r -> %r" % (k, poprzednie.get(k), biezace.get(k)))
    return biezace


class config_lock:
    """flock na czas czytaj-zmien-zapisz configu. Osobny plik .lock, nie sam config:
    config podmieniamy atomowo przez os.replace, wiec lock na jego deskryptorze
    wskazywalby stary inode. Pasek (Swift) bierze ten sam lock przed zapisem."""

    def __enter__(self):
        import fcntl
        self._f = open(os.path.join(BASE, "config.lock"), "w")
        fcntl.flock(self._f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        import fcntl
        try:
            fcntl.flock(self._f, fcntl.LOCK_UN)
        finally:
            self._f.close()
        return False


def now():
    return time.time()


def ts(t=None):
    """Stempel czasu do artefaktow dowodowych - ZAWSZE z offsetem strefy.

    Do 2.1.7 wlacznie bylo to gole `%Y-%m-%d %H:%M:%S`, czyli czas lokalny bez informacji,
    ktory to lokalny. Zdarzenia w events.log filtrowane sa po polu `epoch`
    (absolutnym), a historia i guard.log po TEKSCIE - wiec ten sam katalog danych
    dawal dwa rozne dokumenty. Odtworzone 02.08.2026: pad zapisany 23:30 w Warszawie,
    raport `--from/--to` na ten sam dzien pokazuje w Auckland ZERO zdarzen
    krytycznych, a tuz obok drukuje oś czasu i `[KILL]` z tej samej sekundy oraz
    chip 98,7 C. Dokument roszczeniowy sam sobie przeczy.

    Format ma 24 znaki, a jego pierwsze 19 to dokladnie stary stempel - dzieki temu
    kazdy istniejacy parser bioracy `linia[:19]` dziala dalej bez zmian, a nowy
    moze wziac `linia[:24]` i policzyc czas absolutny.
    """
    return time.strftime("%Y-%m-%d %H:%M:%S%z", time.localtime(t if t else now()))


def czas_abs(s):
    """Epoch ABSOLUTNY ze stempla `ts()` - z offsetem albo bez (pliki sprzed 2.1.8).

    Ze stemplem z offsetem wynik jest ten sam w kazdej strefie na swiecie. Bez
    offsetu nie da sie zgadnac, wiec interpretujemy lokalnie (tak jak dzialalo
    do tej pory) - i to jest dokladnie ta niejednoznacznosc, dla ktorej offset
    zostal dopisany. Zwraca 0.0 przy smieciu, nigdy nie rzuca.
    """
    # Parser danych z pliku dowodowego: MA nigdy nie rzucac, bo jeden smieciowy wiersz
    # nie moze wywalic calego dokumentu. Pierwsza wersja tej funkcji zawezila `except`
    # do (ValueError, OverflowError) i stracila odpornosc na nie-stringi - fuzzer
    # rundy 1 zlapal to od razu: wejscie 123 dawalo AttributeError, b"..." TypeError.
    if not isinstance(s, str):
        return 0.0
    s = s.strip()
    if len(s) < 19:
        return 0.0
    try:
        if len(s) >= 24 and s[19] in "+-":
            return datetime.datetime.strptime(s[:24], "%Y-%m-%d %H:%M:%S%z").timestamp()
        return time.mktime(time.strptime(s[:19], "%Y-%m-%d %H:%M:%S"))
    except Exception:      # noqa: BLE001 - kontrakt: nigdy nie rzuca
        return 0.0


def ensure_dirs():
    """Katalog danych tylko dla wlasciciela.

    Na Macu z kilkoma kontami 0755 znaczylo, ze kazdy lokalny uzytkownik czyta
    `config.json` - a tam siedzi `ntfy_topic`, ktory dokumentacja sama nazywa
    JEDYNYM zabezpieczeniem powiadomien: kto go zna, czyta cudze alerty i moze
    wysylac falszywe. W `managed/` leza dodatkowo pelne linie polecen zadan.
    """
    for d in (BASE, MANAGED_DIR):
        if not os.path.isdir(d):
            try:
                os.makedirs(d, 0o700)
            except OSError as e:
                # Bez tego demon wywalal sie tracebackiem w pierwszej linii main(),
                # a launchd wskrzeszal go co 30 s w nieskonczonosc. Traceback szedl do
                # stderr.log, czyli do pliku w katalogu, do ktorego wlasnie nie da sie
                # pisac - wiec uzytkownik nie widzial ani jednego slowa diagnostyki.
                print("coffee-paladin: nie moge utworzyc %s (%s)" % (d, e), file=sys.stderr)
    # istniejace instalacje: zaciesniamy prawa przy kazdym starcie (tanie, idempotentne)
    for sciezka, prawa in ((BASE, 0o700), (MANAGED_DIR, 0o700), (CFG_PATH, 0o600)):
        try:
            if os.path.exists(sciezka) and (os.stat(sciezka).st_mode & 0o077):
                os.chmod(sciezka, prawa)
        except OSError:
            pass


# Nazwy, ktorymi wola sie samo narzedzie. Musza byc na liscie nietykalnych ZAWSZE,
# nawet gdy config zostal zapisany przed zmiana nazwy - inaczej druga instancja
# (albo instancja z innego katalogu) widzi demona jako zwykly proces "Python"
# zzerajacy CPU i pauzuje go. Zdarzylo sie naprawde, 02.08.2026.
WLASNE_NAZWY = ("coffee-paladin", "guard.py", "safe-run")

# klucze configu, ktore mialy zly typ i zostaly zastapione defaultem (do zalogowania)
_zle_typy = []
_ostatnio_odrzucone = {"v": None}


def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH) as f:
            user = json.load(f)
        if isinstance(user, dict):
            cfg.update(user)
    except Exception:
        pass
    # Wartosci z configu maja typ DEFAULTU, nie ten, ktory wpisal czlowiek.
    # Bez tego jedna literowka ("cpu_min_percent": "dwadziescia") wywala petle
    # przy kazdym cyklu: status.json przestaje byc zapisywany, nic nie jest
    # pauzowane, a `heat` dalej melduje "dziala". Czyli strazak zywy i slepy.
    for klucz, wzor in DEFAULTS.items():
        wart = cfg.get(klucz)
        if isinstance(wzor, bool):
            if not isinstance(wart, bool):
                cfg[klucz] = wzor
                _zle_typy.append(klucz)
        elif isinstance(wzor, (int, float)):
            # bool jest w Pythonie podklasa int, wiec `poll_seconds: true` przeszloby
            # jako 1 sekunda - demon odpytywalby 15x czesciej, na goracym chipie.
            if isinstance(wart, bool):
                cfg[klucz] = wzor
                _zle_typy.append(klucz)
            else:
                try:
                    # OverflowError, bo 1e400 i 400-cyfrowy int wywalaly cala funkcje,
                    # a load_cfg leci w main() bez oslony: demon w ogole nie wstawal.
                    # NaN i nieskonczonosc przechodzily WSZYSTKIE porownania jako falsz,
                    # wiec prog "nan" zamienial pick_targets w maszynke lapiaca kazdy
                    # proces powyzej zera procent CPU - bez jednego slowa w logu.
                    nowa = type(wzor)(wart)
                    if isinstance(nowa, float) and (nowa != nowa or nowa in (float("inf"), float("-inf"))):
                        raise ValueError("NaN albo nieskonczonosc")
                    cfg[klucz] = nowa
                except (TypeError, ValueError, OverflowError):
                    cfg[klucz] = wzor
                    _zle_typy.append(klucz)
        elif isinstance(wzor, list) and not isinstance(wart, list):
            cfg[klucz] = list(wzor)
            _zle_typy.append(klucz)
        elif isinstance(wzor, str) and not isinstance(wart, str):
            cfg[klucz] = wzor
            _zle_typy.append(klucz)

    # Progi MUSZA rosnac: wznowienie < pauza < ubicie. Bez tego jedna literowka
    # zamienia bezpiecznik w mlynek (resume >= pause: pauza i wznowienie co cykl)
    # albo w zabojce zadan (kill <= pause: SIGTERM przy zupelnie zdrowych 82 C).
    PARY_PROGOW = (("soc_resume_c", "soc_pause_c"), ("soc_pause_c", "soc_kill_c"),
                   ("batt_resume_c", "batt_pause_c"), ("batt_pause_c", "batt_kill_c"))
    # Korekta MUSI byc powtarzana: obnizenie soc_pause_c w drugiej parze potrafi
    # zlamac relacje ustalona w pierwszej. Trzy przebiegi wystarczaja na cztery pary.
    for _ in range(3):
        zmienione = False
        for nizszy, wyzszy in PARY_PROGOW:
            try:
                n, w = float(cfg[nizszy]), float(cfg[wyzszy])
            except (KeyError, TypeError, ValueError):
                continue
            if n >= w:
                cfg[nizszy] = w - 2.0
                _zle_typy.append("%s (>= %s, obnizone do %.1f)" % (nizszy, wyzszy, cfg[nizszy]))
                zmienione = True
        if not zmienione:
            break
    # Po korekcie prog moze wyladowac poza fizycznym sensem (ktos wpisuje soc_kill_c: 0,
    # zeby "wylaczyc ubijanie", i przeciaga za soba pauze na -2 C). Wtedy cala rodzina
    # progow wraca do wartosci domyslnych - lepiej znane 85/76/90 niz wlasny absurd.
    for rodzina, zakres in ((("soc_resume_c", "soc_pause_c", "soc_kill_c"), (40.0, 110.0)),
                            (("batt_resume_c", "batt_pause_c", "batt_kill_c"), (20.0, 60.0))):
        if any(k in cfg and not (zakres[0] <= float(cfg[k]) <= zakres[1]) for k in rodzina
               if isinstance(cfg.get(k), (int, float))):
            for k in rodzina:
                if k in DEFAULTS:
                    cfg[k] = DEFAULTS[k]
            _zle_typy.append("progi %s poza zakresem %.0f-%.0f - przywrocone domyslne"
                             % (rodzina[0].split("_")[0], zakres[0], zakres[1]))

    # Progi temperatur mialy zakresy, liczniki i interwaly nie mialy zadnych. A to
    # wlasnie one potrafia zrobic najwiecej szkody, bo nie brzmia grozne:
    #   poll_seconds: 0        -> petla bez ani jednego sleepa, jeden rdzen pod korek
    #                             NA MACU, KTOREGO TEN PROGRAM MA PILNOWAC PRZED GRZANIEM
    #   max_pause_minutes: -1  -> kazda pauza od razu przekracza limit, wiec swiezo
    #                             wstrzymane zadanie dostaje SIGTERM w tej samej sekundzie
    #   kill_after_polls: 0    -> ubicie przy pierwszym krytycznym odczycie, bez laski
    # Zamiast odrzucac cala konfiguracje, przycinamy pojedyncza wartosc do sensownej
    # granicy i mowimy o tym w logu.
    for klucz, dolna, gorna in (("poll_seconds", 1, 300),
                                ("min_pause_seconds", 0, 3600),
                                ("fan_alert_polls", 1, 100),
                                ("state_confirm_polls", 1, 100),
                                ("max_pause_minutes", 1, 10080),
                                ("max_pause_minutes_batt", 1, 10080),
                                ("kill_after_polls", 1, 100),
                                ("job_cpu_percent", 5, 100),
                                ("batt_pct_pause", 0, 100),
                                ("batt_pct_resume", 0, 100),
                                ("keep_awake_hold_s", 0, 86400)):
        v = cfg.get(klucz)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if v < dolna or v > gorna:
                cfg[klucz] = type(DEFAULTS[klucz])(min(max(v, dolna), gorna)) \
                             if klucz in DEFAULTS else min(max(v, dolna), gorna)
                _zle_typy.append("%s = %s poza zakresem %s-%s - przyciete do %s"
                                 % (klucz, v, dolna, gorna, cfg[klucz]))

    # Minimalny czas pauzy dluzszy niz limit pauzy to maszynka do zabijania: wznowienie
    # nigdy nie nastapi, a kazda pauza konczy sie SIGTERM-em. Przycinamy i mowimy o tym.
    _limit_s = cfg.get("max_pause_minutes", 45) * 60
    if isinstance(cfg.get("min_pause_seconds"), (int, float)) and cfg["min_pause_seconds"] >= _limit_s:
        cfg["min_pause_seconds"] = max(0, int(_limit_s / 3))
        _zle_typy.append("min_pause_seconds >= max_pause_minutes - przyciete do %d s"
                         % cfg["min_pause_seconds"])

    # listy nietykalnych sa UZUPELNIANE o wlasne nazwy, nigdy nimi nie nadpisywane:
    # uzytkownik moze dopisac swoje wzorce, ale nie moze przypadkiem odslonic demona.
    # Puste stringi wylatuja: "" pasuje do KAZDEJ nazwy procesu, wiec jedna pusta
    # linia na liscie oslepia bezpiecznik i nic tego nie sygnalizuje.
    # Lista odrzuconych wartosci jest LOGOWANA i czyszczona przy kazdym wczytaniu.
    # Wczesniej tylko rosla (load_cfg leci co cykl petli, ~5760 wpisow na dobe),
    # a uzytkownik nie dostawal zadnego sygnalu, ze jego prog zostal po cichu zmieniony.
    if _zle_typy:
        odrzucone = sorted(set(_zle_typy))
        del _zle_typy[:]
        if odrzucone != _ostatnio_odrzucone["v"]:
            _ostatnio_odrzucone["v"] = odrzucone
            log("CONFIG: odrzucone albo poprawione wartosci: %s" % ", ".join(odrzucone))
            # Klamp naprawia wartosci W PAMIECI, plik zostaje jaki byl - i to jest
            # pulapka: druga sesja (czlowiek albo agent AI) czyta config.json i widzi
            # co innego, niz demon wykonuje. Dokladnie tak 05.08.2026 sesja kolejki
            # wpisala soc_pause_c=100, guard chodzil na sklampowanym 98, a plik dalej
            # mowil 100. Pliku celowo NIE nadpisujemy (guard nie edytuje configu
            # czlowieka za jego plecami) - zamiast tego mowimy wprost, co poprawic.
            notify(cfg, "coffee-paladin: config corrected in memory",
                   "config.json still holds the old values. Fix: %s" % "; ".join(odrzucone),
                   key="cfgclamp")
    else:
        # korekty znikly (czlowiek naprawil plik) - status nie moze wiecznie straszyc
        _ostatnio_odrzucone["v"] = []
    for klucz in ("never_patterns", "never_arg_patterns", "never_extra",
                  "managed_patterns", "system_demote_patterns"):
        lista = [w for w in (cfg.get(klucz) or []) if isinstance(w, str) and w.strip()]
        if klucz in ("never_patterns", "never_arg_patterns"):
            for nazwa in WLASNE_NAZWY:
                if nazwa not in lista:
                    lista.append(nazwa)
        cfg[klucz] = lista
    return cfg


# ---------------------------------------------------------------- jezyk

SUPPORTED_LANGS = ("en", "pl", "ru", "zh", "es")


def _lang():
    """Jezyk komunikatow: TG_LANG, potem "lang" w config.json, domyslnie angielski."""
    v = (os.environ.get("TG_LANG") or "").lower()[:2]
    if v in SUPPORTED_LANGS:
        return v
    try:
        with open(CFG_PATH) as f:
            v = (json.load(f).get("lang") or "").lower()[:2]
        if v in SUPPORTED_LANGS:
            return v
    except Exception:
        pass
    return "en"


LANG = _lang()

# Katalog tlumaczen. Kluczem jest angielski oryginal z kodu — dzieki temu brak wpisu
# oznacza po prostu wyswietlenie angielskiego, a nie bledu.
PL = {
    "PAUSED %s (pid %d, %.0f%% CPU) - %s": "PAUZA  %s (pid %d, %.0f%% CPU) - %s",
    "[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s": "[DRY-RUN] pauza %s (pid %d, %.0f%% CPU) - %s",
    "FAILED to pause %s (pid %d) - not permitted to send the signal": "NIE UDALO SIE wstrzymac %s (pid %d) - brak uprawnien do sygnalu",
    "RESUMED %s (pid %d) - %s": "WZNOWIONE %s (pid %d) - %s",
    "dropping stale pause entry: %s (pid %s) is running again "
    "- resumed outside the guard":
        "kasuje nieaktualny wpis pauzy: %s (pid %s) znowu pracuje "
        "- wznowiony poza bezpiecznikiem",
    "[DRY-RUN] would terminate %s (pid %d) - %s": "[DRY-RUN] ubicie %s (pid %d) - %s",
    "TERMINATED (SIGTERM) %s (pid %d) - %s": "STOP (SIGTERM) %s (pid %d) - %s",
    "SIGKILL %s (pid %d)": "SIGKILL %s (pid %d)",
    "[DRY-RUN] would demote %s (pid %d)": "[DRY-RUN] demote %s (pid %d)",
    "DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)":
        "DEMOTE %s (pid %d) -> tlo/E-cores (goraco i mieli >%d min)",
    "PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)":
        "PROMOTE %s (pid %d) -> z powrotem na rdzenie P (maszyna ostygla)",
    "Thermal guard: hot": "Thermal guard: goraco",
    "unknown argument: %s": "nieznany argument: %s",
    "usage: coffee-paladin [--once | status]   (no arguments = run the daemon)":
        "uzycie: coffee-paladin [--once | status]   (bez argumentow = uruchom demona)",
    "Thermal guard: job slowed down": "Thermal guard: zadanie zwolnione",
    "%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools":
        "%s zepchniete na rdzenie E (nawet kilka razy wolniej) - wroci na pelna predkosc, gdy maszyna ostygnie",
    "Thermal guard: full speed again": "Thermal guard: znow pelna predkosc",
    "%s is back on P-cores": "%s wrocil na rdzenie P",
    "Thermal guard (watch-only): hot": "Thermal guard (obserwacja): goraco",
    "Would pause %s - %s. Protection is off.":
        "Wstrzymalbym %s - %s. Ochrona jest wylaczona.",
    "Paused: %s (%s)": "Wstrzymano: %s (%s)",
    "Thermal guard: cooled down": "Thermal guard: ochlodzone",
    "Resumed paused jobs (%s)": "Wznowiono wstrzymane zadania (%s)",
    "Thermal guard: STOPPED": "Thermal guard: ZATRZYMANE",
    "Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.":
        "Ubito zadania (%s). Wznow z checkpointu, gdy Mac ostygnie.",
    "!!! HARD SHUTDOWN DETECTED - ": "!!! WYKRYTO TWARDY PAD - ",
    "Mac shut down without warning": "Mac zgasl bez ostrzezenia",
    "Evidence from the moment of the crash was saved - menu bar > Export report":
        "Zapisalem dowody z chwili padu - menu paska > Eksportuj raport",
    "manual freeze: there was nothing to freeze": "reczne zamrozenie: nie bylo czego zamrozic",
    "Nothing to freeze": "Nie ma czego zamrozic",
    "No heavy job meets the conditions": "Zadne ciezkie zadanie nie spelnia warunkow",
    "COOLING FAILURE? chip %.1f C while both fans report 0 rpm":
        "AWARIA CHLODZENIA? chip %.1f C, a oba wentylatory 0 obr/min",
    "Fans stopped while the chip is hot": "Wentylatory stoja przy goracym chipie",
    "PAUSE >%d min - terminating job %s (pid %s)": "PAUZA >%d min - koncze zadanie %s (pid %s)",
    "paused for longer than %d min": "pauza dluzsza niz %d min",
    "LOOP ERROR: %r": "BLAD petli: %r",
    "MANUAL FREEZE (from the menu bar)": "ZAMROZENIE RECZNE (z paska menu)",
    "manual resume (from the menu bar)": "wznowienie reczne (z paska menu)",
    "conditions are back to normal": "warunki wrocily do normy",
    "guard startup - nothing is left frozen": "start guarda - nic nie zostaje zamrozone",
    "guard is shutting down": "guard konczy prace",
    "CRITICAL: ": "KRYTYCZNIE: ",
    "chip %.1f C": "chip %.1f C",
    "battery %.1f C": "bateria %.1f C",
    "thermal state=%s": "stan termiczny=%s",
    "thermal state=critical": "stan termiczny=critical",
    "thermal state=fair": "stan termiczny=fair",
    "CPU throttled to %d%%": "CPU dlawione do %d%%",
    "battery %d%% on battery power": "bateria %d%% bez zasilacza",
    "nothing to freeze": "nie ma czego zamrazac",
    "Mac went down without a clean shutdown. Guard's last heartbeat: %s, system booted: %s.":
        "Mac zgasl bez czystego zamkniecia. Ostatni puls guarda: %s, system wstal: %s.",
    "yes": "tak",
    "NO (macmon missing - running on battery temperature only)":
        "NIE (brak macmon - lecimy na samej baterii)",
    "coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s)"
    " | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery":
        "coffee-paladin start | chip: pauza>=%.0fC wznow<=%.0fC ubicie>=%.0fC (czujnik: %s)"
        " | bateria: pauza>=%.0fC ubicie>=%.0fC | stan>=%s | bramka baterii: <=%d%% bez zasilacza",
    "state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)":
        "stan=%s chip=%s bateria=%s wentylatory=%s zasilanie=%s CPU_limit=%d%% load1=%.2f poziom=%d (%s)",
    "  candidate: %-20s pid=%-7d %.0f%% CPU": "  kandydat: %-20s pid=%-7d %.0f%% CPU",
    "AC": "AC",
    "battery %s%%": "bateria %s%%",
    "calm": "spokoj",
    "gone before pause: %s (pid %d)": "zniknal przed pauza: %s (pid %d)",
    "FAILED to pause %s (pid %d) - errno %d, giving up on this pid":
        "NIE UDALO SIE wstrzymac %s (pid %d) - errno %d, rezygnuje z tego pid",
    "STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, type 'fg' in its window":
        "NADAL WSTRZYMANY po SIGCONT: %s (pid %d) - zadanie pierwszoplanowe terminala, wpisz 'fg' w jego oknie",
    "Thermal guard: job needs your hand": "Thermal guard: zadanie wymaga Twojej reki",
    "%s cannot resume by itself - switch to its terminal and type 'fg'.":
        "%s nie wznowi sie samo - przejdz do jego terminala i wpisz 'fg'.",
    "Thermal guard: PROTECTION INCOMPLETE": "Thermal guard: OCHRONA NIEPELNA",
    "No chip temperature sensor (macmon missing). Only battery temperature is watched, and it reacts minutes late. Fix: brew install macmon": "Brak czujnika temperatury chipa (nie ma macmona). Pilnowana jest tylko bateria, a ona reaguje z kilkuminutowym opoznieniem. Naprawa: brew install macmon",
    "Could not pause: %s (%s). The Mac stays hot - intervene manually.":
        "Nie udalo sie wstrzymac: %s (%s). Mac zostaje goracy - zareaguj recznie.",
    "Thermal guard: CRITICAL overheating": "Thermal guard: KRYTYCZNE przegrzanie",
    "The Mac is critically hot (%s). Heavy jobs are being stopped.":
        "Mac jest krytycznie gorący (%s). Ciężkie zadania są zatrzymywane.",
    "The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.":
        "Mac jest krytycznie gorący (%s). Tryb obserwacji - nic nie jest zatrzymywane.",
    "coffee-paladin: watch-only mode": "coffee-paladin: tryb obserwacji",
    "Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click).":
        "Tylko mierzę i alarmuję - nic nie jest wstrzymywane. Włącz ochronę w menu paska (jeden klik).",
    "another coffee-paladin daemon is already running - this one exits": "inny demon coffee-paladin juz dziala - ten sie wylacza",
    "CONFIDENCE: LOW - %s.":
        "WIARYGODNOSC: NISKA - %s.",
    "the last heartbeat is %d days before boot - the clock was most likely wrong (dead RTC, NTP jump) or the data came from a backup":
        "ostatni puls jest %d dni przed startem systemu - zegar byl najpewniej zly (rozladowany RTC, skok NTP) albo dane pochodza z kopii zapasowej",
    "%.1f h passed between the last heartbeat and boot - the guard may have been killed long before the Mac actually went down":
        "miedzy ostatnim pulsem a startem systemu uplynelo %.1f h - bezpiecznik mogl zostac ubity dlugo przed tym, jak Mac naprawde zgasl",
}

# Powiadomienia i alerty w pozostalych jezykach paska (ru/zh/es). Tlumaczymy to, co widzi
# czlowiek (powiadomienia, baner, powody) — log techniczny zostaje po angielsku/polsku.
RU = {
    "Thermal guard: hot": "Thermal guard: горячо",
    "Thermal guard: job slowed down": "Thermal guard: задача замедлена",
    "%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools":
        "%s переведён на E-ядра (в несколько раз медленнее) - вернётся на полную скорость, когда машина остынет",
    "Thermal guard: full speed again": "Thermal guard: снова полная скорость",
    "%s is back on P-cores": "%s снова на P-ядрах",
    "Thermal guard (watch-only): hot": "Thermal guard (наблюдение): горячо",
    "Would pause %s - %s. Protection is off.":
        "Приостановил бы %s - %s. Защита выключена.",
    "Paused: %s (%s)": "Приостановлено: %s (%s)",
    "Thermal guard: cooled down": "Thermal guard: остыло",
    "Resumed paused jobs (%s)": "Возобновлены приостановленные задачи (%s)",
    "Thermal guard: STOPPED": "Thermal guard: ОСТАНОВЛЕНО",
    "Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.":
        "Задачи завершены (%s). Возобновите с контрольной точки, когда Mac остынет.",
    "Mac shut down without warning": "Mac выключился без предупреждения",
    "Evidence from the moment of the crash was saved - menu bar > Export report":
        "Данные с момента сбоя сохранены - строка меню > Экспорт отчёта",
    "Nothing to freeze": "Нечего приостанавливать",
    "No heavy job meets the conditions": "Ни одна тяжёлая задача не подходит под условия",
    "Fans stopped while the chip is hot": "Вентиляторы стоят при горячем чипе",
    "COOLING FAILURE? chip %.1f C while both fans report 0 rpm":
        "ОТКАЗ ОХЛАЖДЕНИЯ? чип %.1f C, а оба вентилятора 0 об/мин",
    "chip %.1f C": "чип %.1f C",
    "battery %.1f C": "батарея %.1f C",
    "thermal state=%s": "термосостояние=%s",
    "thermal state=critical": "термосостояние=critical",
    "thermal state=fair": "термосостояние=fair",
    "CPU throttled to %d%%": "CPU ограничен до %d%%",
    "battery %d%% on battery power": "батарея %d%% без адаптера",
    "CRITICAL: ": "КРИТИЧНО: ",
    "MANUAL FREEZE (from the menu bar)": "РУЧНАЯ ПАУЗА (из строки меню)",
    "manual resume (from the menu bar)": "ручное возобновление (из строки меню)",
    "conditions are back to normal": "условия вернулись в норму",
    "paused for longer than %d min": "в паузе дольше %d мин",
    "Thermal guard: CRITICAL overheating": "Thermal guard: КРИТИЧЕСКИЙ перегрев",
    "The Mac is critically hot (%s). Heavy jobs are being stopped.":
        "Mac критически горячий (%s). Тяжёлые задачи останавливаются.",
    "The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.":
        "Mac критически горячий (%s). Режим наблюдения - ничего не останавливается.",
    "coffee-paladin: watch-only mode": "coffee-paladin: режим наблюдения",
    "Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click).":
        "Только измеряю и предупреждаю - ничего не приостанавливается. Включите защиту в меню (один клик).",
    "another coffee-paladin daemon is already running - this one exits": "другой демон coffee-paladin уже работает - этот завершается",
    "PAUSED %s (pid %d, %.0f%% CPU) - %s": "ПАУЗА  %s (pid %d, %.0f%% CPU) - %s",
    "[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s": "[НАБЛЮДЕНИЕ] поставил бы на паузу %s (pid %d, %.0f%% CPU) - %s",
    "FAILED to pause %s (pid %d) - not permitted to send the signal": "НЕ УДАЛОСЬ поставить на паузу %s (pid %d) - нет прав на отправку сигнала",
    "RESUMED %s (pid %d) - %s": "ВОЗОБНОВЛЕНО %s (pid %d) - %s",
    "dropping stale pause entry: %s (pid %s) is running again "
    "- resumed outside the guard":
        "удаляю устаревшую запись о паузе: %s (pid %s) снова работает "
        "- возобновлён не защитой",
    "[DRY-RUN] would terminate %s (pid %d) - %s": "[НАБЛЮДЕНИЕ] завершил бы %s (pid %d) - %s",
    "TERMINATED (SIGTERM) %s (pid %d) - %s": "ЗАВЕРШЕНО (SIGTERM) %s (pid %d) - %s",
    "SIGKILL %s (pid %d)": "SIGKILL %s (pid %d)",
    "[DRY-RUN] would demote %s (pid %d)": "[НАБЛЮДЕНИЕ] понизил бы %s (pid %d)",
    "DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)": "ПОНИЖЕНО %s (pid %d) -> фоновый QoS/E-ядра (жарко дольше %d мин)",
    "PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)": "ПОВЫШЕНО %s (pid %d) -> обратно на P-ядра (машина остыла)",
    "unknown argument: %s": "неизвестный аргумент: %s",
    "usage: coffee-paladin [--once | status]   (no arguments = run the daemon)": "использование: coffee-paladin [--once | status]   (без аргументов = запуск демона)",
    "!!! HARD SHUTDOWN DETECTED - ": "!!! ОБНАРУЖЕНО ЖЁСТКОЕ ОТКЛЮЧЕНИЕ - ",
    "manual freeze: there was nothing to freeze": "ручная заморозка: замораживать было нечего",
    "PAUSE >%d min - terminating job %s (pid %s)": "ПАУЗА >%d мин - завершаю задачу %s (pid %s)",
    "LOOP ERROR: %r": "ОШИБКА ЦИКЛА: %r",
    "guard startup - nothing is left frozen": "запуск стража - ничего не осталось замороженным",
    "guard is shutting down": "страж завершает работу",
    "nothing to freeze": "нечего замораживать",
    "Mac went down without a clean shutdown. Guard's last heartbeat: %s, system booted: %s.": "Mac выключился без штатного завершения. Последний сигнал стража: %s, система загружена: %s.",
    "yes": "да",
    "NO (macmon missing - running on battery temperature only)": "НЕТ (нет macmon - работаем только по температуре батареи)",
    "coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s) | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery": "coffee-paladin старт | чип: пауза>=%.0fC возобновление<=%.0fC завершение>=%.0fC (датчик: %s) | батарея: пауза>=%.0fC завершение>=%.0fC | состояние>=%s | порог батареи: <=%d%% без зарядки",
    "state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)": "состояние=%s чип=%s батарея=%s вентиляторы=%s питание=%s лимит_CPU=%d%% load1=%.2f уровень=%d (%s)",
    "  candidate: %-20s pid=%-7d %.0f%% CPU": "  кандидат: %-20s pid=%-7d %.0f%% CPU",
    "AC": "сеть",
    "battery %s%%": "батарея %s%%",
    "calm": "спокойно",
    "gone before pause: %s (pid %d)": "исчез до паузы: %s (pid %d)",
    "FAILED to pause %s (pid %d) - errno %d, giving up on this pid": "НЕ УДАЛОСЬ поставить на паузу %s (pid %d) - errno %d, оставляю этот pid",
    "STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, type 'fg' in its window": "ВСЁ ЕЩЁ ОСТАНОВЛЕН после SIGCONT: %s (pid %d) - задача переднего плана, наберите 'fg' в её окне",
    "Thermal guard: job needs your hand": "Тепловой страж: задача требует вашего вмешательства",
    "%s cannot resume by itself - switch to its terminal and type 'fg'.": "%s не может продолжить сам - перейдите в его терминал и наберите 'fg'.",
    "Thermal guard: PROTECTION INCOMPLETE": "Тепловой страж: ЗАЩИТА НЕПОЛНАЯ",
    "No chip temperature sensor (macmon missing). Only battery temperature is watched, and it reacts minutes late. Fix: brew install macmon": "Нет датчика температуры чипа (отсутствует macmon). Отслеживается только батарея, а она реагирует с задержкой в несколько минут. Решение: brew install macmon",
    "Could not pause: %s (%s). The Mac stays hot - intervene manually.": "Не удалось поставить на паузу: %s (%s). Mac остаётся горячим - вмешайтесь вручную.",
    "CONFIDENCE: LOW - %s.":
        "ДОСТОВЕРНОСТЬ: НИЗКАЯ - %s.",
    "the last heartbeat is %d days before boot - the clock was most likely wrong (dead RTC, NTP jump) or the data came from a backup":
        "последний пульс на %d дн. раньше загрузки - часы почти наверняка были неверны (севший RTC, скачок NTP) либо данные из резервной копии",
    "%.1f h passed between the last heartbeat and boot - the guard may have been killed long before the Mac actually went down":
        "между последним пульсом и загрузкой прошло %.1f ч - защита могла быть убита задолго до того, как Mac реально погас",
}

ZH = {
    "Thermal guard: hot": "Thermal guard：过热",
    "Thermal guard: job slowed down": "Thermal guard：任务已降速",
    "%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools":
        "%s 已移至能效核心（可能慢数倍）- 机器冷却后自动恢复全速",
    "Thermal guard: full speed again": "Thermal guard：已恢复全速",
    "%s is back on P-cores": "%s 已回到性能核心",
    "Thermal guard (watch-only): hot": "Thermal guard（仅观察）：过热",
    "Would pause %s - %s. Protection is off.": "本应暂停 %s - %s。保护已关闭。",
    "Paused: %s (%s)": "已暂停:%s(%s)",
    "Thermal guard: cooled down": "Thermal guard:已降温",
    "Resumed paused jobs (%s)": "已恢复暂停的任务(%s)",
    "Thermal guard: STOPPED": "Thermal guard:已终止",
    "Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.":
        "任务已终止(%s)。等 Mac 降温后从检查点恢复。",
    "Mac shut down without warning": "Mac 毫无预警地关机了",
    "Evidence from the moment of the crash was saved - menu bar > Export report":
        "已保存崩溃时刻的证据 - 菜单栏 > 导出报告",
    "Nothing to freeze": "没有可暂停的任务",
    "No heavy job meets the conditions": "没有符合条件的繁重任务",
    "Fans stopped while the chip is hot": "芯片过热时风扇停转",
    "COOLING FAILURE? chip %.1f C while both fans report 0 rpm":
        "散热故障?芯片 %.1f C,而两个风扇均为 0 转/分",
    "chip %.1f C": "芯片 %.1f C",
    "battery %.1f C": "电池 %.1f C",
    "thermal state=%s": "热状态=%s",
    "thermal state=critical": "热状态=critical",
    "thermal state=fair": "热状态=fair",
    "CPU throttled to %d%%": "CPU 降频至 %d%%",
    "battery %d%% on battery power": "电池 %d%% 且未接电源",
    "CRITICAL: ": "危急:",
    "MANUAL FREEZE (from the menu bar)": "手动暂停(来自菜单栏)",
    "manual resume (from the menu bar)": "手动恢复(来自菜单栏)",
    "conditions are back to normal": "条件已恢复正常",
    "paused for longer than %d min": "暂停超过 %d 分钟",
    "Thermal guard: CRITICAL overheating": "Thermal guard:严重过热",
    "The Mac is critically hot (%s). Heavy jobs are being stopped.":
        "Mac 已严重过热(%s)。正在停止繁重任务。",
    "The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.":
        "Mac 已严重过热(%s)。仅观察模式 - 不停止任何任务。",
    "coffee-paladin: watch-only mode": "coffee-paladin:仅观察模式",
    "Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click).":
        "只测量和提醒 - 不暂停任何任务。请在菜单栏启用保护(一键)。",
    "another coffee-paladin daemon is already running - this one exits": "另一个 coffee-paladin 守护进程已在运行 - 本进程退出",
    "PAUSED %s (pid %d, %.0f%% CPU) - %s": "已暂停  %s (pid %d, %.0f%% CPU) - %s",
    "[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s": "[仅观察] 本会暂停 %s (pid %d, %.0f%% CPU) - %s",
    "FAILED to pause %s (pid %d) - not permitted to send the signal": "暂停失败 %s (pid %d) - 没有发送信号的权限",
    "RESUMED %s (pid %d) - %s": "已恢复 %s (pid %d) - %s",
    "dropping stale pause entry: %s (pid %s) is running again "
    "- resumed outside the guard":
        "清除过期的暂停记录：%s (pid %s) 已重新运行 - 由防护程序之外恢复",
    "[DRY-RUN] would terminate %s (pid %d) - %s": "[仅观察] 本会关闭 %s (pid %d) - %s",
    "TERMINATED (SIGTERM) %s (pid %d) - %s": "已关闭 (SIGTERM) %s (pid %d) - %s",
    "SIGKILL %s (pid %d)": "SIGKILL %s (pid %d)",
    "[DRY-RUN] would demote %s (pid %d)": "[仅观察] 本会降级 %s (pid %d)",
    "DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)": "已降级 %s (pid %d) -> 后台 QoS/能效核心(持续过热超过 %d 分钟)",
    "PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)": "已恢复 %s (pid %d) -> 回到性能核心(机器已降温)",
    "unknown argument: %s": "未知参数:%s",
    "usage: coffee-paladin [--once | status]   (no arguments = run the daemon)": "用法:coffee-paladin [--once | status]   (不带参数 = 运行守护进程)",
    "!!! HARD SHUTDOWN DETECTED - ": "!!! 检测到硬关机 - ",
    "manual freeze: there was nothing to freeze": "手动冻结:没有可冻结的进程",
    "PAUSE >%d min - terminating job %s (pid %s)": "暂停超过 %d 分钟 - 结束任务 %s (pid %s)",
    "LOOP ERROR: %r": "循环错误:%r",
    "guard startup - nothing is left frozen": "守卫启动 - 没有残留的冻结进程",
    "guard is shutting down": "守卫正在关闭",
    "nothing to freeze": "没有可冻结的进程",
    "Mac went down without a clean shutdown. Guard's last heartbeat: %s, system booted: %s.": "Mac 未经正常关机就断电。守卫最后心跳:%s,系统启动:%s。",
    "yes": "是",
    "NO (macmon missing - running on battery temperature only)": "否(缺少 macmon - 仅依据电池温度运行)",
    "coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s) | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery": "coffee-paladin 启动 | 芯片:暂停>=%.0fC 恢复<=%.0fC 终止>=%.0fC(传感器:%s)| 电池:暂停>=%.0fC 终止>=%.0fC | 状态>=%s | 电池阈值:未接电源时 <=%d%%",
    "state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)": "状态=%s 芯片=%s 电池=%s 风扇=%s 电源=%s CPU限制=%d%% load1=%.2f 级别=%d (%s)",
    "  candidate: %-20s pid=%-7d %.0f%% CPU": "  候选:%-20s pid=%-7d %.0f%% CPU",
    "AC": "电源",
    "battery %s%%": "电池 %s%%",
    "calm": "平静",
    "gone before pause: %s (pid %d)": "暂停前已消失:%s (pid %d)",
    "FAILED to pause %s (pid %d) - errno %d, giving up on this pid": "暂停失败 %s (pid %d) - errno %d,放弃该 pid",
    "STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, type 'fg' in its window": "SIGCONT 后仍处于停止状态:%s (pid %d) - 前台终端任务,请在其窗口输入 'fg'",
    "Thermal guard: job needs your hand": "热量守卫:任务需要你处理",
    "%s cannot resume by itself - switch to its terminal and type 'fg'.": "%s 无法自行恢复 - 切换到它的终端并输入 'fg'。",
    "Thermal guard: PROTECTION INCOMPLETE": "热量守卫:保护不完整",
    "No chip temperature sensor (macmon missing). Only battery temperature is watched, and it reacts minutes late. Fix: brew install macmon": "没有芯片温度传感器（缺少 macmon）。只能监测电池温度，而它要慢上几分钟才有反应。解决办法：brew install macmon",
    "Could not pause: %s (%s). The Mac stays hot - intervene manually.": "无法暂停:%s (%s)。Mac 仍然过热 - 请手动处理。",
    "CONFIDENCE: LOW - %s.":
        "可信度:低 - %s。",
    "the last heartbeat is %d days before boot - the clock was most likely wrong (dead RTC, NTP jump) or the data came from a backup":
        "最后一次心跳比开机早 %d 天 - 时钟很可能不正确(RTC 电池耗尽、NTP 跳变),或数据来自备份",
    "%.1f h passed between the last heartbeat and boot - the guard may have been killed long before the Mac actually went down":
        "最后一次心跳与开机之间相隔 %.1f 小时 - 守护可能在 Mac 真正断电之前很久就被杀掉了",
}

ES = {
    "Thermal guard: hot": "Thermal guard: caliente",
    "Thermal guard: job slowed down": "Thermal guard: tarea ralentizada",
    "%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools":
        "%s movido a nucleos E (hasta varias veces mas lento) - vuelve a plena velocidad cuando la maquina se enfrie",
    "Thermal guard: full speed again": "Thermal guard: plena velocidad de nuevo",
    "%s is back on P-cores": "%s vuelve a los nucleos P",
    "Thermal guard (watch-only): hot": "Thermal guard (solo observación): caliente",
    "Would pause %s - %s. Protection is off.":
        "Habría pausado %s - %s. La protección está desactivada.",
    "Paused: %s (%s)": "En pausa: %s (%s)",
    "Thermal guard: cooled down": "Thermal guard: enfriado",
    "Resumed paused jobs (%s)": "Tareas en pausa reanudadas (%s)",
    "Thermal guard: STOPPED": "Thermal guard: DETENIDO",
    "Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.":
        "Tareas terminadas (%s). Reanuda desde un checkpoint cuando el Mac se haya enfriado.",
    "Mac shut down without warning": "El Mac se apagó sin aviso",
    "Evidence from the moment of the crash was saved - menu bar > Export report":
        "Se guardaron las pruebas del momento del fallo - barra de menús > Exportar informe",
    "Nothing to freeze": "Nada que pausar",
    "No heavy job meets the conditions": "Ninguna tarea pesada cumple las condiciones",
    "Fans stopped while the chip is hot": "Ventiladores parados con el chip caliente",
    "COOLING FAILURE? chip %.1f C while both fans report 0 rpm":
        "¿FALLO DE REFRIGERACIÓN? chip a %.1f C y ambos ventiladores a 0 rpm",
    "chip %.1f C": "chip %.1f C",
    "battery %.1f C": "batería %.1f C",
    "thermal state=%s": "estado térmico=%s",
    "thermal state=critical": "estado térmico=critical",
    "thermal state=fair": "estado térmico=fair",
    "CPU throttled to %d%%": "CPU limitada al %d%%",
    "battery %d%% on battery power": "batería al %d%% sin adaptador",
    "CRITICAL: ": "CRÍTICO: ",
    "MANUAL FREEZE (from the menu bar)": "PAUSA MANUAL (desde la barra de menús)",
    "manual resume (from the menu bar)": "reanudación manual (desde la barra de menús)",
    "conditions are back to normal": "las condiciones volvieron a la normalidad",
    "paused for longer than %d min": "en pausa durante más de %d min",
    "Thermal guard: CRITICAL overheating": "Thermal guard: sobrecalentamiento CRÍTICO",
    "The Mac is critically hot (%s). Heavy jobs are being stopped.":
        "El Mac está críticamente caliente (%s). Se están deteniendo las tareas pesadas.",
    "The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.":
        "El Mac está críticamente caliente (%s). Modo observación: no se detiene nada.",
    "coffee-paladin: watch-only mode": "coffee-paladin: modo observación",
    "Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click).":
        "Solo mido y aviso: no se pausa nada. Activa la protección en la barra de menús (un clic).",
    "another coffee-paladin daemon is already running - this one exits": "ya se está ejecutando otro demonio coffee-paladin - este termina",
    "PAUSED %s (pid %d, %.0f%% CPU) - %s": "PAUSADO  %s (pid %d, %.0f%% CPU) - %s",
    "[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s": "[SOLO OBSERVAR] pausaría %s (pid %d, %.0f%% CPU) - %s",
    "FAILED to pause %s (pid %d) - not permitted to send the signal": "NO SE PUDO pausar %s (pid %d) - sin permiso para enviar la señal",
    "RESUMED %s (pid %d) - %s": "REANUDADO %s (pid %d) - %s",
    "dropping stale pause entry: %s (pid %s) is running again "
    "- resumed outside the guard":
        "descarto la entrada de pausa obsoleta: %s (pid %s) vuelve a ejecutarse "
        "- reanudado fuera del guardian",
    "[DRY-RUN] would terminate %s (pid %d) - %s": "[SOLO OBSERVAR] cerraría %s (pid %d) - %s",
    "TERMINATED (SIGTERM) %s (pid %d) - %s": "CERRADO (SIGTERM) %s (pid %d) - %s",
    "SIGKILL %s (pid %d)": "SIGKILL %s (pid %d)",
    "[DRY-RUN] would demote %s (pid %d)": "[SOLO OBSERVAR] degradaría %s (pid %d)",
    "DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)": "DEGRADADO %s (pid %d) -> QoS de fondo/núcleos de eficiencia (caliente durante más de %d min)",
    "PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)": "PROMOVIDO %s (pid %d) -> de vuelta a los núcleos de rendimiento (la máquina se enfrió)",
    "unknown argument: %s": "argumento desconocido: %s",
    "usage: coffee-paladin [--once | status]   (no arguments = run the daemon)": "uso: coffee-paladin [--once | status]   (sin argumentos = ejecuta el demonio)",
    "!!! HARD SHUTDOWN DETECTED - ": "!!! APAGADO BRUSCO DETECTADO - ",
    "manual freeze: there was nothing to freeze": "congelación manual: no había nada que congelar",
    "PAUSE >%d min - terminating job %s (pid %s)": "PAUSA de más de %d min - cierro la tarea %s (pid %s)",
    "LOOP ERROR: %r": "ERROR DEL BUCLE: %r",
    "guard startup - nothing is left frozen": "arranque del guardián - no queda nada congelado",
    "guard is shutting down": "el guardián se está cerrando",
    "nothing to freeze": "nada que congelar",
    "Mac went down without a clean shutdown. Guard's last heartbeat: %s, system booted: %s.": "El Mac se apagó sin un cierre limpio. Última señal del guardián: %s, sistema arrancado: %s.",
    "yes": "sí",
    "NO (macmon missing - running on battery temperature only)": "NO (falta macmon - funcionando solo con la temperatura de la batería)",
    "coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s) | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery": "coffee-paladin inicio | chip: pausa>=%.0fC reanudación<=%.0fC cierre>=%.0fC (sensor: %s) | batería: pausa>=%.0fC cierre>=%.0fC | estado>=%s | umbral de batería: <=%d%% sin cargador",
    "state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)": "estado=%s chip=%s batería=%s ventiladores=%s alimentación=%s límite_CPU=%d%% load1=%.2f nivel=%d (%s)",
    "  candidate: %-20s pid=%-7d %.0f%% CPU": "  candidato: %-20s pid=%-7d %.0f%% CPU",
    "AC": "red",
    "battery %s%%": "batería %s%%",
    "calm": "en calma",
    "gone before pause: %s (pid %d)": "desapareció antes de la pausa: %s (pid %d)",
    "FAILED to pause %s (pid %d) - errno %d, giving up on this pid": "NO SE PUDO pausar %s (pid %d) - errno %d, abandono este pid",
    "STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, type 'fg' in its window": "SIGUE DETENIDO tras SIGCONT: %s (pid %d) - tarea en primer plano, escribe 'fg' en su ventana",
    "Thermal guard: job needs your hand": "Guardián térmico: la tarea necesita tu intervención",
    "%s cannot resume by itself - switch to its terminal and type 'fg'.": "%s no puede reanudarse solo - ve a su terminal y escribe 'fg'.",
    "Thermal guard: PROTECTION INCOMPLETE": "Guardián térmico: PROTECCIÓN INCOMPLETA",
    "No chip temperature sensor (macmon missing). Only battery temperature is watched, and it reacts minutes late. Fix: brew install macmon": "No hay sensor de temperatura del chip (falta macmon). Solo se vigila la bateria, que reacciona con minutos de retraso. Solucion: brew install macmon",
    "Could not pause: %s (%s). The Mac stays hot - intervene manually.": "No se pudo pausar: %s (%s). El Mac sigue caliente - interviene manualmente.",
    "CONFIDENCE: LOW - %s.":
        "FIABILIDAD: BAJA - %s.",
    "the last heartbeat is %d days before boot - the clock was most likely wrong (dead RTC, NTP jump) or the data came from a backup":
        "el último latido es %d días anterior al arranque - el reloj casi seguro estaba mal (RTC agotada, salto de NTP) o los datos vienen de una copia de seguridad",
    "%.1f h passed between the last heartbeat and boot - the guard may have been killed long before the Mac actually went down":
        "pasaron %.1f h entre el último latido y el arranque - el guardián pudo morir mucho antes de que el Mac se apagara de verdad",
}

DICTS = {"pl": PL, "ru": RU, "zh": ZH, "es": ES}


def T(s):
    """Tlumaczy komunikat wg jezyka z konfiguracji. Angielski jest zrodlem prawdy —
    brak wpisu w slowniku oznacza po prostu angielski, nigdy blad."""
    return DICTS.get(LANG, {}).get(s, s)

def rotate(path):
    """Rotacja z NUMEROWANYMI pokoleniami: .1 najswiezsze, .N najstarsze.

    Wczesniej bylo jedno `os.replace(path, path + ".1")`, wiec KAZDA kolejna rotacja
    nadpisywala .1 i kasowala dowody bezpowrotnie. Odtworzone 02.08.2026: szczyt
    98,7 C wpadal do history.csv, po pierwszej rotacji `thermal-report --days 2`
    pokazywal 44,0 C (bo czytal tylko plik biezacy), a po drugiej rotacji odczyt
    98,7 C nie istnial juz nigdzie na dysku. To jest jedyny powod, dla ktorego ten
    plik w ogole powstaje - dokument do serwisu albo do roszczenia gwarancyjnego.

    Pokolen trzymamy MAX_LOG_GENERACJI; przy 5 MB na plik to ~30 MB sufitu na
    strumien, czyli tanio za dowod, ktorego nie da sie odtworzyc.
    """
    try:
        if os.path.getsize(path) <= MAX_LOG_BYTES:
            return
    except OSError:
        return
    try:
        najstarszy = "%s.%d" % (path, MAX_LOG_GENERACJI)
        if os.path.exists(najstarszy):
            os.remove(najstarszy)
        for n in range(MAX_LOG_GENERACJI - 1, 0, -1):
            zrodlo = "%s.%d" % (path, n)
            if os.path.exists(zrodlo):
                os.replace(zrodlo, "%s.%d" % (path, n + 1))
        os.replace(path, path + ".1")
    except OSError:
        pass


def pokolenia(path):
    """Plik biezacy razem ze zrotowanymi pokoleniami, OD NAJSTARSZEGO.

    Kazdy czytelnik dowodow (thermal-report, statystyki) ma isc przez te liste,
    a nie przez sam `path` - inaczej rotacja ucina dokumentowi historie w polowie
    bez jednego slowa ostrzezenia.
    """
    zrotowane = []
    n = 1
    while True:
        p = "%s.%d" % (path, n)
        if not os.path.exists(p):
            break
        zrotowane.append(p)
        n += 1
    zrotowane.reverse()                    # .3, .2, .1 = chronologicznie
    if os.path.exists(path):
        zrotowane.append(path)
    return zrotowane


_CICHE_AWARIE = {}


def cicha_awaria(gdzie, e):
    """Polkniety wyjatek w sciezce krytycznej PRZESTAJE byc cichy.

    W demonie bezpieczenstwa `except Exception: pass` w zapisie dowodu albo stanu
    znaczy: "dowod nie powstal, a nikt sie nie dowie". Ruff naliczyl 107 takich miejsc,
    z czego 14 w funkcjach, ktore decyduja o ochronie albo o materiale dowodowym.
    Przeplywu NIE zmieniamy - demon ma dzialac dalej takze wtedy, gdy dysk jest pelny -
    ale kazda taka awaria trafia do logu (raz na 10 min na miejsce) i do licznika
    widocznego w status.json. Nadal polykamy, juz nie milczymy.
    """
    _CICHE_AWARIE[gdzie] = _CICHE_AWARIE.get(gdzie, 0) + 1
    znacznik = "_ostatni_log_" + gdzie
    teraz = now()
    if teraz - _CICHE_AWARIE.get(znacznik, 0) >= 600:
        _CICHE_AWARIE[znacznik] = teraz
        try:
            log("SWALLOWED in %s: %s: %s (%d time(s) so far)"
                % (gdzie, type(e).__name__, e, _CICHE_AWARIE[gdzie]))
        except Exception:
            pass


def log(msg, tag=None):
    """Wpis do guard.log. `tag` to STABILNY znacznik ASCII zdarzenia.

    Tresc komunikatu jest tlumaczona na piec jezykow, a raport dowodowy, statystyki
    w pasku i `heat` parsuja ten log. Dopoki szukaly polskich i angielskich slow,
    maszyna z jezykiem rosyjskim gubila w raporcie KAZDY wykryty twardy pad - czyli
    jedyny powod, dla ktorego ten dokument istnieje. Znacznik [PAUSE]/[RESUME]/...
    jest ten sam we wszystkich jezykach i to po nim maja szukac parsery.
    """
    if tag:
        msg = "[%s] %s" % (tag, msg)
    rotate(LOG_PATH)
    line = "%s  %s\n" % (ts(), msg)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line)
    except Exception:
        pass
    if sys.stdout.isatty():
        sys.stdout.write(line)
        sys.stdout.flush()


def _ubij_grupe(p):
    """Ubija CALA grupe procesow dziecka, potem zbiera zwloki.

    Sam `p.kill()` zostawia wnuki przy zyciu - a to one potrafia wisiec godzinami.
    Gdy grupy nie da sie odczytac (dziecko juz zniknelo), spadamy na zwykly kill.
    """
    if p is None:
        return
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except OSError:
        try:
            p.kill()
        except Exception:
            pass
    try:
        p.communicate(timeout=2)          # zbieramy zwloki, inaczej zostaje zombie
    except Exception:
        pass


def run(cmd, timeout=10):
    """Uruchamia polecenie i ZAWSZE po sobie sprzata.

    `communicate(timeout=...)` rzuca TimeoutExpired, ale NIE zabija dziecka - proces
    zostaje, a demon zbiera kolejne. Zaobserwowane na zywo 02.08.2026 przy obciazonym
    Macu: guard mial czworke wiszacych dzieci (dwa `macmon pipe`, `pmset -g therm`),
    petla stala 90 sekund i status.json przestal byc odswiezany. Przy 15-sekundowym
    cyklu to znaczy, ze przez ten czas nikt nie pilnowal temperatury.
    """
    p = None
    try:
        # WLASNA GRUPA PROCESOW. `p.kill()` siega tylko bezposredniego dziecka, wiec
        # polecenie, ktore samo cos odpali (np. powloka z zadaniem w tle), zostawialo
        # osieroconego WNUKA zyjacego dalej. Odtworzone 02.08.2026 i zglaszane przez
        # fuzzer rundy 2: po powrocie z run() zostawal proces potomny. Przy demonie
        # dzialajacym latami takie osierocone procesy sie kumuluja.
        # Zadne z polecen wolanych przez run() (ps, sysctl, pmset, ioreg, macmon)
        # nie potrzebuje terminala, wiec odlaczenie sesji nic nie kosztuje.
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        out, _ = p.communicate(timeout=timeout)
        return out.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        _ubij_grupe(p)
        return ""
    except Exception:
        if p is not None and p.poll() is None:
            _ubij_grupe(p)
        return ""


# Zegar monotoniczny ma sens tylko WEWNATRZ jednego procesu. Wpis o pauzie
# przezywa restart demona (i dobrze - inaczej SIGKILL na straznika zostawialby
# zamrozone procesy bez opiekuna), wiec trzeba wiedziec, czyj to pomiar.
_MONO_ID = "%d:%d" % (os.getpid(), int(time.time()))

_last_notify = {}

# Krotko zyjace procesy pomocnicze (osascript/afplay/curl). Trzymamy referencje
# i zbieramy zwloki co cykl — bez tego kazdy alert zostawal zombie az do sprzatania
# wewnatrz modulu subprocess (znalezisko z niezaleznej recenzji Codex, 30.07.2026).
_bg_procs = []


def popen_bg(cmd, stdin_data=None):
    """Proces w tle. `stdin_data` podajemy tam, gdzie argumentu NIE WOLNO pokazac
    w `ps` - argv widzi kazdy uzytkownik maszyny, stdin nie."""
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.PIPE if stdin_data is not None else None)
        if stdin_data is not None:
            try:
                p.stdin.write(stdin_data.encode("utf-8"))
            finally:
                p.stdin.close()
        _bg_procs.append(p)
    except Exception:
        pass


def reap_bg():
    _bg_procs[:] = [p for p in _bg_procs if p.poll() is None]


SOUNDS = {
    "pause": "Basso",      # goraco — niski, powazny
    "resume": "Hero",      # wznowienie = triumf: przetrwalismy goraco, wracamy do roboty
    "kill": "Sosumi",      # ubicie zadania
    "fan": "Basso",        # awaria chlodzenia
    "pad": "Basso",        # wykryty twardy pad
    "freeze": "Tink",      # reczne akcje z paska
    "demote": "Submarine", # zepchniecie na E-cores — "schodzimy nizej"
    "promote": "Hero",     # powrot na P-cores — ta sama fanfara co wznowienie
    "awake": "Funk",       # start keep-awake — kubek stuka o blat
    "watchonly": "Basso",  # obserwacja: "wstrzymalbym, ale ochrona wylaczona" — powazny ton
}


# rozne klucze zdarzen, wspolny plik dzwiekowy
SOUND_ALIAS = {"promote": "resume", "fan": "kill", "default": "pad"}
# przy cyklowaniu pauza/wznowienie co ~40 s miecz cialby non stop - decyzja Pawla:
# max raz na 10 minut (powiadomienia chodza dalej, tylko dzwiek jest przycinany)
SOUND_MIN_GAP_S = {"pause": 600, "demote": 600, "resume": 600, "awake": 600}
_last_sound = {}


def play_sound(cfg, key):
    if not cfg.get("sound", True):
        return
    gap = SOUND_MIN_GAP_S.get(key, 0)
    if gap and now() - _last_sound.get(key, 0) < gap:
        return
    _last_sound[key] = now()
    # najpierw wlasne pliki (wybory Pawla 01.08, CC0 - patrz sounds/LICENSES.md);
    # fallback na dzwieki systemowe - stara instalacja bez sounds/ nic nie traci
    wlasny = os.path.join(BASE, "sounds", SOUND_ALIAS.get(key, key) + ".wav")
    if os.path.exists(wlasny):
        popen_bg(["afplay", wlasny])
        return
    name = SOUNDS.get(key, "Ping")
    path = "/System/Library/Sounds/%s.aiff" % name
    if os.path.exists(path):
        popen_bg(["afplay", path])


def push(cfg, title, text):
    """Push na telefon przez ntfy.sh — dziala wszedzie, gdzie stoi aplikacja ntfy z tym
    samym tematem. Popen + limit czasu: brak internetu nie moze zatrzymac petli."""
    # `notify: false` musi wyciszyc TAKZE push. Bramka byla dotad tylko w notify(),
    # a banner() wolal push() bezposrednio - wiec przy wylaczonych powiadomieniach
    # telefon i tak dostawal wiadomosc co 180 s przez caly czas poziomu krytycznego.
    if not cfg.get("notify", True):
        return
    topic = (cfg.get("ntfy_topic") or "").strip()
    # Temat idzie do URL-a bez cytowania, wiec musi byc bezpieczny sam z siebie.
    # Zmierzone: "sekret#tajne" publikuje na "sekret" (curl obcina fragment), a
    # "sekret?tajne" - na "sekret" z ogonem jako parametrami sterujacymi ntfy.
    # Czyli uzytkownik mysli, ze ma temat 12-znakowy, a ma 6-znakowy.
    if not topic or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic):
        if topic:
            log("ntfy: temat %r ma niedozwolone znaki albo dlugosc - push wylaczony "
                "(dozwolone: litery, cyfry, _ i -, do 64 znakow)" % topic[:80])
        return
    # TEMAT NIE MOZE STAC W ARGV. `ps -Ao args=` czyta kazdy uzytkownik maszyny, a temat
    # ntfy jest JEDYNYM zabezpieczeniem tego kanalu: kto go zna, czyta cudze alerty
    # (temperatury, nazwy zadan, twarde pady) i moze wysylac falszywe. Dotad siedzial
    # w URL-u przy KAZDYM powiadomieniu. Dlatego publikujemy przez JSON na stdin:
    # w argv zostaje samo "curl -s -m 10 -H Content-Type... -d @- https://ntfy.sh/".
    # `-d @-` czyta cialo ze stdin, wiec ani temat, ani tresc nie wychodza na zewnatrz.
    cialo = json.dumps({"topic": topic,
                        "title": title.replace("\n", " ").replace("\r", " "),
                        "message": text}, ensure_ascii=False)
    popen_bg(["curl", "-s", "-m", "10", "-H", "Content-Type: application/json",
              "-d", "@-", "https://ntfy.sh/"], stdin_data=cialo)


def notify(cfg, title, text, key="default"):
    if not cfg["notify"]:
        return
    t = now()
    if t - _last_notify.get(key, 0) < cfg["notify_min_gap_s"]:
        return
    _last_notify[key] = t
    play_sound(cfg, key)
    script = 'display notification %s with title %s' % (
        json.dumps(text), json.dumps(title))
    popen_bg(["osascript", "-e", script])
    # ten sam odstep czasowy co powiadomienie — telefon nie moze dostawac wiecej niz ekran
    push(cfg, title, text)


_last_banner = {"t": 0.0}


def banner(cfg, title, text):
    """Modalny alert na wierzchu wszystkiego — tylko poziom krytyczny.

    Popen, nie call: osascript wisi do klikniecia OK, a petla guarda nie moze stac
    ani sekundy. `giving up after` zdejmuje okno samo, wiec po nocy nie zastaje sie
    stosu okien — a kazdy kolejny alert i tak jest trzymany wlasnym odstepem czasowym.
    """
    if not cfg.get("critical_banner", True):
        return
    t = now()
    gap = cfg.get("critical_banner_gap_s", 180)
    if t - _last_banner["t"] < gap:
        return
    _last_banner["t"] = t
    play_sound(cfg, "critical")   # ogien: "krytycznie" ma brzmiec inaczej niz "goraco"
    script = 'display alert %s message %s as critical giving up after %d' % (
        json.dumps(title), json.dumps(text), int(gap))
    popen_bg(["osascript", "-e", script])
    push(cfg, title, text)


# ---------------------------------------------------------------- czujniki

def thermal_state():
    for exe in (os.path.join(HOME, ".local/bin/thermalstate"), "thermalstate"):
        out = run([exe]).strip()
        if out in LEVELS:
            return out
    return "unknown"


def normalize_batt_temp(raw):
    """Temperatura ogniwa w C, niezaleznie od jednostki raportowanej przez kontroler.

    Uklady pomiarowe baterii roznia sie miedzy modelami Makow: jedne podaja setne stopnia
    (3081 = 30,81 C), inne dziesiate (444 = 44,4 C), a niektore pola cale stopnie (41 = 41 C).
    Sztywne dzielenie przez 100 daje na czesci maszyn absurdy w rodzaju 444 C albo 0,4 C,
    dlatego skalujemy do przedzialu fizycznie mozliwego dla ogniwa litowego.
    """
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    for _ in range(4):
        if v <= 100.0:
            break
        v /= 10.0
    return v if 5.0 < v <= 100.0 else None


def battery_temp_c():
    """Temperatura pakietu baterii w C (None gdy brak baterii)."""
    out = run(["ioreg", "-r", "-c", "AppleSmartBattery", "-d", "1", "-w", "0"], timeout=15)
    best = None
    for key in ('"Temperature"', '"VirtualTemperature"'):
        m = re.search(re.escape(key) + r"\s*=\s*(\d+)", out)
        if m:
            v = normalize_batt_temp(m.group(1))
            if v is not None and (best is None or v > best):
                best = v
    return best


# UWAGA na wartosc startowa. Wczesniej bylo 0.0 i to sie zemscilo: Apple'owy
# /usr/bin/python3 (tym launchd uruchamia demona) liczy time.monotonic() OD ZERA
# w kazdym procesie, wiec przez pierwsze 10 sekund zycia demona warunek swiezosci
# wychodzil prawdziwy i soc_sensors() oddawalo startowe None, ani razu nie pytajac
# macmona. Straznik meldowal wtedy "brak czujnika chipa" i przez pierwszy cykl
# pilnowal wylacznie baterii. None znaczy "jeszcze nie czytalem" niezaleznie od
# tego, od czego dany Python zaczyna liczyc.
_soc_cache = {"t": None, "val": None}


def soc_sensors(max_age=10.0):
    """Temperatura chipa, wentylatory i pobor mocy przez `macmon` (IOReport, bez sudo).

    Zwraca dict: {"cpu": C, "gpu": C, "fans": [rpm], "watts": W} albo None gdy macmon
    niedostepny. Wynik jest cache'owany, bo jedno probkowanie kosztuje ~1 s — a petla
    guarda chodzi co 15 s i pyta o to w kilku miejscach.

    UWAGA: na macOS 26 sensory przez IOHIDEventSystem sa juz zablokowane dla procesow
    bez uprawnien (dlatego wlasny czujnik Swift zwracal zero) — IOReport nadal dziala.
    """
    if _soc_cache["t"] is not None and 0 <= time.monotonic() - _soc_cache["t"] < max_age:
        return _soc_cache["val"]
    val = None
    for exe in ("/opt/homebrew/bin/macmon", "macmon"):
        out = run([exe, "pipe", "-s", "1"], timeout=20)
        line = out.strip().split("\n")[0] if out.strip() else ""
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("temp") or {}
        cpu = t.get("cpu_temp_avg")
        gpu = t.get("gpu_temp_avg")
        fans = [int(f.get("rpm") or 0) for f in (d.get("fans") or [])]
        # bezczynne GPU potrafi zwrocic smiec (2-3 C) — ponizej 10 C traktujemy jako brak odczytu
        def sane(v):
            return float(v) if isinstance(v, (int, float)) and 10.0 < v < 130.0 else None

        mem = d.get("memory") or {}
        GB = float(1024 ** 3)
        val = {
            "cpu": sane(cpu),
            "gpu": sane(gpu),
            "ram_used": (mem.get("ram_usage") or 0) / GB,
            "ram_total": (mem.get("ram_total") or 0) / GB,
            "swap_used": (mem.get("swap_usage") or 0) / GB,
            "fans": fans,
            "watts": float(d.get("all_power") or 0.0),
        }
        break
    _soc_cache["t"] = time.monotonic()
    _soc_cache["val"] = val
    return val


def soc_temp_c():
    """Najgoretszy punkt ukladu (CPU albo GPU) w C, albo None."""
    s = soc_sensors()
    if not s:
        return None
    vals = [v for v in (s.get("cpu"), s.get("gpu")) if v is not None]
    return max(vals) if vals else None


def disk_usage():
    """Miejsce na dysku systemowym: (zajete_GB, calosc_GB, procent_zajety)."""
    try:
        st = os.statvfs("/System/Volumes/Data")
    except Exception:
        try:
            st = os.statvfs("/")
        except Exception:
            return None
    GB = float(1024 ** 3)
    total = st.f_blocks * st.f_frsize / GB
    # f_bavail, nie f_bfree: to miejsce realnie dostepne dla uzytkownika
    free = st.f_bavail * st.f_frsize / GB
    if total <= 0:
        return None
    return (total - free, total, 100.0 * (total - free) / total)


def power_source():
    """(na_zasilaczu: bool, procent_baterii: int|None)."""
    out = run(["pmset", "-g", "batt"], timeout=10)
    ac = "AC Power" in out
    m = re.search(r"(\d+)%", out)
    return ac, (int(m.group(1)) if m else None)


def cpu_speed_limit():
    """Procent dostepnej mocy CPU wg macOS (100 = brak throttlingu)."""
    out = run(["pmset", "-g", "therm"])
    m = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", out)
    return int(m.group(1)) if m else 100


def load_avg():
    try:
        return os.getloadavg()[0]
    except Exception:
        return 0.0


def ncpu():
    out = run(["sysctl", "-n", "hw.ncpu"]).strip()
    try:
        return int(out)
    except Exception:
        return 8


def list_procs():
    """[(pid, ppid, cpu, comm, args)] procesow biezacego uzytkownika."""
    out = run(["ps", "-Ao", "pid=,ppid=,pcpu=,uid=,comm=", "-c"], timeout=15)
    uid = os.getuid()
    res = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        try:
            pid, ppid, cpu, puid = int(parts[0]), int(parts[1]), float(parts[2]), int(parts[3])
        except ValueError:
            continue
        if puid != uid:
            continue
        res.append((pid, ppid, cpu, parts[4].strip()))
    return res


def pierwszoplanowy_na_tty(pid):
    """Czy proces jest liderem PIERWSZOPLANOWEJ grupy swojego terminala?

    Jesli pgid == tpgid, to wlasnie ten proces ma klawiature. SIGSTOP na nim sprawia,
    ze powloka odbiera terminal; pozniejszy SIGCONT wznawia go w TLE, wiec przy pierwszej
    probie czytania klawiatury dostaje SIGTTIN i znow staje - petla, ktorej demon nie
    przerwie (nie moze zrobic tcsetpgrp na cudzym tty). Jedyne wyjscie to `fg` wpisane
    przez czlowieka. Takich procesow NIE WOLNO pauzowac (Neo, 31.07.2026: 8 zabitych
    procesow, dwie sesje Claude Code).
    """
    out = run(["ps", "-o", "pgid=,tpgid=", "-p", str(pid)]).split()
    if len(out) >= 2:
        try:
            pgid_, tpgid_ = int(out[0]), int(out[1])
            return tpgid_ > 0 and pgid_ == tpgid_
        except ValueError:
            return False
    return False


def full_args(pid):
    out = run(["ps", "-o", "args=", "-p", str(pid)])
    return out.strip()


# Programy, ktore SAME nic nie znacza - tozsamosc procesu niesie ich pierwszy argument
# (skrypt albo modul). Dla nich argv[1] traktujemy jak nazwe programu.
INTERPRETERY = frozenset((
    "node", "nodejs", "deno", "bun", "python", "ruby", "perl", "php", "java",
    "sh", "bash", "zsh", "osascript", "tsx", "ts-node", "uv", "uvx", "pipx", "npx",
))

# Nazwy z numerem wersji (python3.14, ruby3.3, node20, perl5.34). Twarda lista wersji
# ZAWSZE zostaje w tyle za instalacja uzytkownika: 02.08.2026 lista konczyla sie na
# python3.13, a `python3` na tej maszynie to juz 3.14 z homebrew. Skutek byl odwrotny
# do zamierzonego - proces `python3.14 /sciezka/mcp_server.py` NIE byl rozpoznawany
# jako interpreter, wiec sciezka skryptu leciala do kosza razem z danymi i agent AI
# tracil ochrone przed SIGSTOP. Regula wersjonowana nie starzeje sie z kazdym wydaniem.
INTERPRETER_WERSJONOWANY = re.compile(
    r"^(python|ruby|perl|php|node|nodejs|deno|bun)[0-9]+(\.[0-9]+)*$")


def jest_interpreterem(nazwa):
    """`nazwa` to basename argv[0] po zdjeciu cudzyslowow, malymi literami."""
    return nazwa in INTERPRETERY or bool(INTERPRETER_WERSJONOWANY.match(nazwa))


def args_bez_sciezek(pid):
    """Ta czesc linii polecen, ktora mowi CZYM jest proces - bez danych, ktore przerabia.

    never_arg_patterns ma rozpoznawac agenta, edytor albo serwer MCP, a nie to, co
    proces czyta. Dopasowanie do surowej linii mylilo jedno z drugim: `ffmpeg -i
    ~/Desktop/claude_brain/wideo/rec.mkv` trafialo we wzorzec "claude" i stawalo sie
    nietykalne, wiec Mac grzal sie dalej.

    Pierwsza proba (biala lista rozszerzen danych) miala dwadziescia obejsc, ktore
    znalazl fuzzer: .braw, .r3d, .mxf, .heif, spacja w sciezce (ps skleja argv
    spacjami), sciezka w cudzyslowach, argument bedacy katalogiem. Kazde z nich
    czynilo zwykly enkoder nietykalnym. Odwrotnie tez: `python3 ~/claude/agent.pt`
    tracil ochrone, bo .pt bylo na liscie danych.

    Dlatego regula jest teraz strukturalna, nie slownikowa:
      argv[0]                     - zawsze tozsamosc (nazwa programu),
      argv[1] przy interpreterze  - tozsamosc (to skrypt albo modul),
      argumenty bez ukosnika      - tozsamosc (flagi, nazwy modulow: -m mcp.server),
      pozostale sciezki           - DANE, nie biora udzialu w dopasowaniu.
    """
    czesci = full_args(pid).split()
    if not czesci:
        return ""
    zostaw = [czesci[0]]
    interpreter = jest_interpreterem(os.path.basename(czesci[0].strip('"\'')).lower())
    skrypt_wziety = not interpreter
    for a in czesci[1:]:
        if "/" not in a:
            zostaw.append(a)          # flaga albo nazwa modulu (-m mcp.server)
        elif not skrypt_wziety and not a.startswith("-"):
            # pierwszy niebedacy flaga argument interpretera to URUCHAMIANY SKRYPT,
            # czyli tozsamosc procesu - takze wtedy, gdy przed nim byly flagi
            # (`node --experimental-modules /sciezka/mcp-server.js`)
            zostaw.append(a)
            skrypt_wziety = True
        # reszta to sciezka do danych - pomijamy
    return " ".join(zostaw).lower()


def top_lists(n=3):
    """Top procesy po CPU i po RAM — do menu paska ("co grzeje / co zjada pamiec").

    CPU to najlepsze dostepne przyblizenie ciepla per proces (per-proces temperatury
    nie istnieja) i tak wlasnie pasek to opisuje. RSS z ps jest w KB.
    """
    out = run(["ps", "-Ao", "pcpu=,rss=,comm=", "-c", "-r"], timeout=15)
    rows = []
    for line in out.splitlines():
        p = line.split(None, 2)
        if len(p) < 3:
            continue
        try:
            rows.append((float(p[0]), int(p[1]), p[2].strip()))
        except ValueError:
            continue
    cpu = [{"name": c[:24], "cpu": round(v)} for v, r, c in rows[:n] if v >= 1]
    ram = [{"name": c[:24], "gb": round(r / 1048576.0, 1)}
           for v, r, c in sorted(rows, key=lambda x: -x[1])[:n] if r > 102400]
    return cpu, ram


# ---------------------------------------------------------------- wybor procesow

def managed_pids_from_saferun():
    """PID-y zarejestrowane przez safe-run: ({pid: pgid}, {pidy z --normal}).

    Zbior "normal" to jawne decyzje czlowieka "ten job na wszystkich rdzeniach" -
    degradacja na E-cores nie moze ich po cichu cofac (B1.4)."""
    res = {}
    normalne = set()
    try:
        for name in os.listdir(MANAGED_DIR):
            if not name.endswith(".json"):
                continue
            path = os.path.join(MANAGED_DIR, name)
            try:
                # Rejestracja steruje sygnalami, wiec musi nalezec do NAS i nie moze byc
                # zapisywalna dla nikogo innego. Na Macu z kilkoma kontami plik 0666
                # w managed/ to gotowa dzwignia: kto go podmieni, wskazuje guardowi
                # cel do zamrozenia. Katalog jest 0700 (ensure_dirs), ale plik moze
                # zostac z wczesniejszej instalacji albo z recznego kopiowania.
                st_pliku = os.lstat(path)
                if st_pliku.st_uid != os.getuid() or (st_pliku.st_mode & 0o022):
                    log("ignoring managed registration with unsafe ownership/permissions: %s"
                        % name)
                    continue
                with open(path) as f:
                    d = json.load(f)
                pid = int(d["pid"])
                if alive(pid):
                    # PID moze zostac ponownie uzyty po padzie guarda: sprawdzamy, czy
                    # biezacy proces w ogole przypomina zarejestrowane polecenie
                    # Tozsamosc sprawdzamy po CZASIE STARTU procesu, nie po nazwie.
                    # Poprzednio porownywalismy `ps comm` (nazwa INTERPRETERA: bash,
                    # Python) z basename polecenia (kompresor.sh) - dla kazdego skryptu
                    # z shebangiem to sie nie zgadzalo, wiec guard kasowal wlasna
                    # rejestracje zaraz po jej powstaniu. Skutek zaobserwowany na zywym
                    # zadaniu 02.08.2026: managed/ pusty przy dzialajacej kompresji,
                    # `jobs: []` w statusie, utracony pgid i flaga "normal".
                    zarejestrowany_start = d.get("started")
                    if zarejestrowany_start:
                        wiek = proc_age_seconds(pid)
                        realny_start = now() - wiek
                        # 90 s luzu: etime ma rozdzielczosc sekundy, a rejestracja
                        # powstaje chwile po starcie procesu
                        if wiek and abs(realny_start - float(zarejestrowany_start)) > 90:
                            os.unlink(path)     # PID przejety przez inny proces
                            continue
                    # PGID BIERZEMY Z JADRA, nie z pliku. Rejestracja to zwykly JSON
                    # na dysku; `pgid` przepisany z niej doslownie kierowal SIGSTOP
                    # i SIGKILL do DOWOLNEJ grupy procesow, ktora ktos tam wpisal.
                    # Odtworzone 02.08.2026: plik {"pid": A, "pgid": B} - guard
                    # sygnalizowal grupe B, czyli NIE zarejestrowane zadanie.
                    # Jadro zna prawde i nie da sie jej podmienic edycja pliku.
                    try:
                        res[pid] = os.getpgid(pid)
                    except OSError:
                        # proces zniknal miedzy alive() a tym wywolaniem
                        continue
                    if d.get("normal"):
                        normalne.add(pid)
                else:
                    os.unlink(path)
            except Exception:
                try:
                    os.unlink(path)
                except Exception:
                    pass
    except Exception:
        pass
    return res, normalne


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        import errno
        return e.errno == errno.EPERM


def zatrzask_czujnika(st, klucz, wartosc, prog_pauzy, prog_wznowienia):
    """Histereza JEDNEGO czujnika: czy on sam trzyma jeszcze maszyne w stanie goracym.

    Zatrzask zapala sie na WLASNYM progu pauzy i gasnie na WLASNYM progu wznowienia,
    a miedzy nimi pamieta poprzednia decyzje. Dzieki temu czujnik moze blokowac
    wznowienie tylko wtedy, gdy sam kiedys kazal pauzowac. Wczesniej bramka byla
    niesymetryczna - pauze wywolywal dowolny czujnik, a wznowienie blokowal kazdy -
    wiec bateria trzymajaca 37 C (trzy stopnie ponizej wlasnego progu 40 C, ktorego
    nigdy nie przekroczyla) nie pozwalala wrocic zadaniu zapauzowanemu przez CHIP.
    Log Pawla 04.08.2026: 15 pauz, ZERO wznowien, dwa zadania ubite po 45 minutach.

    DLACZEGO TYLKO BATERIA. Chipowi zostaje stary, surowy prog wznowienia i tak ma byc:
    jest OSTRZEJSZY od zatrzasku (blokuje w calym pasmie 87-95 C, niezaleznie od tego,
    co wywolalo pauze), a patologii baterii miec nie moze, bo zamrozony chip schodzi
    z 95 do 71 C w dwadziescia sekund. Zatrzask na chipie pozwalalby wznowic zadanie
    przy 94 C, gdyby pauze wywolal `thermalState` - czyli kupowalibysmy migotanie
    za nic (zarzut Codeksa, 04.08.2026, sluszny).

    Brak odczytu gasi zatrzask - dokladnie jak w kodzie sprzed zmiany, gdzie `temp is None`
    znaczylo "nie blokuje". Nieobecny czujnik nie moze byc powodem, dla ktorego obliczenie
    stoi az do SIGTERM-a; brak pomiaru widac osobno (poziom, `sensor`) i tam ma byc decyzja.

    Zmiana progu w locie kasuje zatrzask (kalibracja, suwak, edycja `config.json`):
    zapalil sie wzgledem STAREJ pary progow, wiec wobec nowej nie znaczy juz nic.

    SWIADOMY KOMPROMIS: zatrzask zyje w `st` i NIE przezywa restartu demona. Po
    restarcie bateria w pasmie 36-40 C nie blokuje wznowienia, nawet jesli przed
    restartem sama wywolala pauze. Cena jest niska (chwilowo liberalniejsza bramka
    raz na restart), a alternatywa - utrwalanie zatrzasku na dysku - dawalaby
    odwrotna patologie: zatrzask z poprzedniej epoki progow trzymajacy zadanie
    w T bez powodu (glowa 1, runda 3, 05.08.2026).
    """
    prog_klucz = klucz + "_prog"
    progi = [prog_pauzy, prog_wznowienia]
    if st.get(prog_klucz) != progi:
        st[prog_klucz] = progi
        st[klucz] = False
    if wartosc is None:
        st[klucz] = False
    elif wartosc >= prog_pauzy:
        st[klucz] = True
    elif wartosc <= prog_wznowienia:
        st[klucz] = False
    return bool(st.get(klucz, False))


def zatrzymane_teraz():
    """JEDEN `ps` na cykl: (zbior zatrzymanych pidow, zbior grup z zatrzymanym czlonkiem).

    Wpis w `st["paused"]` mowi tylko, ze guard KIEDYS wyslal SIGSTOP - nie, ze proces
    stoi TERAZ. Obudzic go moze czlowiek (`kill -CONT`), debugger albo duty-limiter
    safe-run. Guard, ktory ufa wlasnej notatce zamiast systemowi, po `max_pause_minutes`
    strzela SIGTERM-em w zadanie pracujace pelna para - i tak zginal pomiar Pawla
    04.08.2026 o 20:27, 25 minut po tym, jak recznie je wznowil.

    GRUPY sa tu rownie wazne jak pidy: guard mrozi cala grupe (`killpg`), a wznowic
    recznie mozna sam jej sygnal wejsciowy. Gdyby wpis kasowac po samym liderze,
    zatrzymane dziecko zostaloby bez jedynej notatki, przez ktora ktokolwiek mogby
    je wznowic - czyli w stanie T na zawsze (zarzut Codeksa, 04.08.2026).

    Jeden `ps -Ao` zamiast jednego `ps` na wpis: przy kilkudziesieciu zamrozonych
    zadaniach petla forkowala tyle samo procesow co cykl.
    """
    linie = run(["ps", "-Ao", "pid=,pgid=,stat="]).splitlines()
    if not linie:
        # NIEUDANY POMIAR TO NIE JEST POMIAR "nic nie stoi". `run()` zwraca pusty napis
        # przy kazdym bledzie i timeoucie, a na zywej maszynie `ps -Ao` ma zawsze
        # kilkaset linii. Gdyby pustke czytac doslownie, guard uznalby KAZDY wpis za
        # "obudzony poza guardem", skasowal go - i zamrozone zadanie zostaloby w stanie T
        # bez jedynej notatki, przez ktora ktokolwiek mogby je wznowic (zarzut Codeksa,
        # runda 2). None znaczy "nie wiem" i wstrzymuje decyzje o cudzym zyciu.
        return None
    pidy, grupy = set(), set()
    for linia in linie:
        czesci = linia.split(None, 2)
        if len(czesci) < 3 or not czesci[2].startswith("T"):
            continue
        try:
            pidy.add(int(czesci[0]))
            grupy.add(int(czesci[1]))
        except ValueError:
            continue
    return pidy, grupy


def wpisy_nieaktualne(paused, stoja):
    """Wpisy po zadaniach, ktore ktos wznowil poza guardem - do skasowania."""
    if stoja is None:
        return []
    return [k for k, v in paused.items()
            if not v.get("manual") and not wpis_stoi(k, v, *stoja)]


def wpisy_przeterminowane(paused, limit_s, stoja):
    """Wpisy starsze niz limit, ktorych zadanie NAPRAWDE stoi - tylko te wolno ubic."""
    if stoja is None:
        return []
    return [k for k, v in paused.items()
            if _wiek_pauzy(v) > limit_s and not v.get("manual") and wpis_stoi(k, v, *stoja)]


def bramka_wznowienia(cfg, st, temp, soc_t, state):
    """Czy wolno wznowic zamrozone zadania: KAZDY czujnik musi zejsc z powrotem.

    Bateria przez zatrzask (blokuje tylko gdy sama przekroczyla swoj prog pauzy),
    chip przez surowy prog wznowienia, stan systemowy przez poziom. Cala decyzja
    siedzi w jednej funkcji, zeby test sprawdzal TO, co wykonuje demon - a nie
    wlasna kopie tego wyrazenia (uwaga Codeksa, runda 2: skopiowany warunek w tescie
    przechodzi takze wtedy, gdy w produkcji ktos zepsuje oryginal).
    """
    batt_trzyma = zatrzask_czujnika(st, "_batt_hot", temp,
                                    cfg["batt_pause_c"], cfg["batt_resume_c"])
    chip_trzyma = soc_t is not None and soc_t > cfg.get("soc_resume_c", 87.0)
    return not batt_trzyma and not chip_trzyma and LEVELS.get(state, 1) <= 1


def wpis_stoi(key, info, pidy, grupy):
    """Czy zadanie z tego wpisu NAPRAWDE stoi - samo albo czymkolwiek ze swojej grupy.

    Nieznany stan (proces zniknal, `ps` nie odpowiada) znaczy "nie stoi": do ubicia
    potrzebujemy DOWODU, ze cos stoi, a nie braku dowodu, ze nie stoi.
    """
    try:
        if int(key) in pidy:
            return True
    except (TypeError, ValueError):
        return False
    pgid = (info or {}).get("pgid")
    try:
        return pgid is not None and int(pgid) in grupy
    except (TypeError, ValueError):
        return False


def proc_age_seconds(pid):
    """Ile sekund proces zyje (ps etime: [[dd-]hh:]mm:ss)."""
    out = run(["ps", "-o", "etime=", "-p", str(pid)]).strip()
    if not out:
        return 0
    dni = 0
    if "-" in out:
        d, out = out.split("-", 1)
        dni = int(d)
    czesci = [int(x) for x in out.split(":")]
    while len(czesci) < 3:
        czesci.insert(0, 0)
    return dni * 86400 + czesci[0] * 3600 + czesci[1] * 60 + czesci[2]


def cpu_z_dziecmi(procs):
    """CPU procesu wraz z calym poddrzewem potomkow.

    Bez tego bezpiecznik jest slepy na najgrozniejszy uklad: orkiestrator (python), ktory
    sam nie zuzywa nic, ale w petli rozsiewa krotkie, ciezkie procesy (cadical, solvery,
    ffmpeg). Pojedyncze dziecko zyje sekunde i znika, wiec nigdy nie zlapie sie na prog,
    a Mac grzeje sie od ich sumy. Liczac poddrzewo widzimy prawdziwego sprawce i mozemy
    zamrozic ZRODLO — wtedy nowe dzieci przestaja powstawac.
    """
    dzieci = {}
    wlasne = {}
    for pid, ppid, cpu, comm in procs:
        dzieci.setdefault(ppid, []).append(pid)
        wlasne[pid] = cpu
    suma = {}

    def licz(pid, glebokosc=0):
        if pid in suma:
            return suma[pid]
        if glebokosc > 20:          # zabezpieczenie przed cyklem w tablicy procesow
            return wlasne.get(pid, 0.0)
        suma[pid] = wlasne.get(pid, 0.0)   # wstawiamy wczesniej = ochrona przed rekurencja
        total = wlasne.get(pid, 0.0)
        for d in dzieci.get(pid, []):
            if d != pid:
                total += licz(d, glebokosc + 1)
        suma[pid] = total
        return total

    for pid in list(wlasne):
        licz(pid)
    return suma


_NIETYKALNI_PODCIAG = {}


def _loguj_nietykalny_podciag(comm, wzorzec, cpu):
    """Raz na godzine na proces - log ma informowac, nie zalewac.

    10 minut bylo za czesto: corespotlightd potrafi mielec indeksowanie caly dzien
    i sam zapelnial log (kilkanascie wpisow na dobe o tym samym, 05.08.2026).
    Jeden wpis na godzine dalej odpowiada na pytanie "czemu guard tego nie rusza"."""
    teraz = now()
    if teraz - _NIETYKALNI_PODCIAG.get(comm, 0) < 3600:
        return
    _NIETYKALNI_PODCIAG[comm] = teraz
    log("%s uses %.0f%% CPU but is untouchable: its name contains the never-pause "
        "pattern %r (partial match). Rename it or narrow never_patterns if this is wrong."
        % (comm, cpu, wzorzec))


_DEMOTE_ONLY = []   # napelniane przy kazdym pick_targets; czyta je snapshot()


def pick_targets(cfg, procs, saferun):
    """Procesy ktore wolno pauzowac, posortowane po CPU malejaco.

    Efekt uboczny: przeladowuje `_DEMOTE_ONLY` - systemowe demony indeksowania,
    ktorych NIE WOLNO pauzowac ani ubijac (lista never), ale wolno je zepchnac
    na E-cores. Ida OSOBNYM kanalem, zeby nigdy nie trafily do do_pause,
    do_terminate ani do listy kandydatow do recznego zamrozenia w pasku.
    """
    me = os.getpid()
    del _DEMOTE_ONLY[:]
    system_demote = [p.lower() for p in (cfg.get("system_demote_patterns") or [])]
    never = [p.lower() for p in list(cfg["never_patterns"]) + list(cfg.get("never_extra") or [])]
    patterns = [p.lower() for p in cfg["managed_patterns"]]
    drzewo = cpu_z_dziecmi(procs) if cfg.get("count_children", True) else {}
    out = []
    for pid, ppid, cpu, comm in procs:
        cpu = max(cpu, drzewo.get(pid, 0.0))   # ocena po calym poddrzewie
        if pid in (me, os.getppid()) or pid <= 1:
            continue
        if cpu < cfg["cpu_min_percent"]:
            continue
        low = comm.lower()
        if pid in saferun:
            # Nietykalny zostaje nietykalny NIEZALEZNIE od zrodla. Wpis w managed/
            # omijal dotad wszystkie listy, wiec nieaktualna albo podlozona rejestracja
            # potrafila zamrozic powloke uzytkownika albo agenta AI - czyli dokladnie
            # to, przed czym lista `never` mial bronic.
            if any(n in low for n in never):
                continue
            out.append((pid, cpu, comm, saferun[pid]))
            continue
        trafienie = next((n for n in never if n in low), None)
        if trafienie:
            # Wariant A (decyzja Pawla 06.08.2026): systemowy demon indeksowania jest
            # dalej NIETYKALNY dla pauzy i ubicia, ale idzie osobnym kanalem do
            # degradacji na E-cores. Log "untouchable" dla niego milknie, bo odpowiedz
            # na "czemu guard tego nie rusza" brzmi teraz: ruszy, taskpolicy -b.
            if any(w in low for w in system_demote):
                _DEMOTE_ONLY.append((pid, cpu, comm, None))
                continue
            # DOPASOWANIE PO PODCIAGU JEST SWIADOME i ma zostac. Asymetria ryzyka jest
            # jednoznaczna: falszywa ochrona znaczy "Mac grzeje sie dalej", a utrata
            # ochrony znaczy "zamrozony agent AI albo powloka uzytkownika" - czyli
            # smierc procesu i utrata pracy (Neo, 31.07.2026). AGENTS.md zakazuje
            # oslabiania tej listy i to jest sluszne.
            #
            # Kosztem jest to, ze `mds_solver` czy `sshd-worker` sa nietykalne przez
            # `mds` i `sshd`. Nie zawezamy dopasowania - ale przestajemy o tym MILCZEC:
            # gdy naprawde goracy proces jest pomijany przez CZESCIOWE dopasowanie,
            # mowimy o tym w logu. Uzytkownik dostaje odpowiedz na pytanie "dlaczego
            # bezpiecznik nie rusza tego, co mi grzeje Maca", zamiast ciszy.
            if low != trafienie and cpu >= cfg.get("unknown_cpu_percent", 50.0):
                _loguj_nietykalny_podciag(comm, trafienie, cpu)
            continue
        if not any(p in low for p in patterns):
            # Lista nazw jest z natury dziurawa — wlasne binarki (b3core, cadical, solvery)
            # nigdy do niej nie pasuja, wiec bezpiecznik ich nie widzial i Mac sie gotowal.
            # Awaryjnie bierzemy KAZDY wlasny proces, ktory dlugo zjada duzo CPU i nie jest
            # na liscie nietykalnych. Chronia nas: never_patterns, prog CPU i czas zycia
            # (krotkie kompilacje czy `ls` nigdy sie nie zalapia).
            if not cfg.get("manage_unknown_heavy", True):
                continue
            if cpu < cfg.get("unknown_cpu_percent", 50.0):
                continue
            if proc_age_seconds(pid) < cfg.get("unknown_min_seconds", 120):
                continue
        args = args_bez_sciezek(pid)
        if any(n.lower() in args for n in (cfg.get("never_arg_patterns") or [])):
            continue
        if cfg.get("skip_foreground_tty", True) and pierwszoplanowy_na_tty(pid):
            continue          # interaktywna sesja na pierwszym planie - patrz funkcja wyzej
        out.append((pid, cpu, comm, None))
    out.sort(key=lambda x: -x[1])

    return out


def bez_potomkow(cele, procs):
    """Lista DO POKAZANIA: bez procesow, ktorych przodek juz na niej jest.

    Gdy CPU potomkow jest rolowane do rodzica (`count_children`), ten sam procesor
    trafia na liste dwa razy: raz jako rodzic z suma poddrzewa, raz jako dziecko
    z wlasnym zuzyciem. Zmierzone: "bash 276% CPU" obok "ffmpeg 276% CPU", przy
    `ps` dla basha 0,0%. Licznik ciezkich procesow i okno potwierdzenia klamaly
    dwukrotnie.

    UWAGA, kosztowna lekcja: ta funkcja sluzy WYLACZNIE do prezentacji. Przez dwie
    godziny 02.08 filtrowala liste CELOW i to bylo grozne - `pgid` jest znany tylko
    dla zadan z `safe-run`, wiec dla reszty `sig()` robi `os.kill(pid, SIGSTOP)` na
    JEDNYM procesie. SIGSTOP na rodzicu nie zatrzymuje istniejacych dzieci, tylko
    powstrzymuje powstawanie nowych. Orkiestrator z dziecmi byl wiec meldowany jako
    zapauzowany, podczas gdy dzieci mielily dalej - falszywe poczucie bezpieczenstwa
    na maszynie po przegrzaniu. Sygnal MUSI trafiac w cale poddrzewo.
    """
    if not cele:
        return cele
    rodzic = {pid: ppid for pid, ppid, cpu, comm in procs}
    wybrane = {t[0] for t in cele}
    out = []
    for t in cele:
        p = rodzic.get(t[0])
        ma_przodka = False
        glebokosc = 0
        while p and p > 1 and glebokosc < 40:
            if p in wybrane:
                ma_przodka = True
                break
            p = rodzic.get(p)
            glebokosc += 1
        if not ma_przodka:
            out.append(t)
    return out



# ---------------------------------------------------------------- akcje

def load_state():
    """Wczytuje stan i NORMALIZUJE typy. Stan pisza tez starsze wersje demona i pasek;
    `paused` jako lista (stary format) albo wpis z kluczem nie-liczba dawaly
    `int(key)`/`.items()` w petli glownej - czyli crashloop przy kazdym starcie,
    z ktorego demon sam nie wychodzi (KeepAlive restartuje go w ten sam mur).
    Zly fragment wycinamy i mowimy o tym w logu; reszta stanu zostaje."""
    try:
        with open(STATE_PATH) as f:
            d = json.load(f)
        if isinstance(d, dict):
            if not isinstance(d.get("paused"), dict):
                if d.get("paused") is not None:
                    log("state: 'paused' had type %s - dropped (old or corrupted format)"
                        % type(d.get("paused")).__name__)
                d["paused"] = {}
            zle = [k for k, v in d["paused"].items()
                   if not str(k).lstrip("-").isdigit() or not isinstance(v, dict)]
            for k in zle:
                log("state: dropping malformed pause entry %r" % (k,))
                del d["paused"][k]
            if not isinstance(d.get("demoted"), list):
                d["demoted"] = []
            if not isinstance(d.get("demoted_info"), dict):
                d["demoted_info"] = {}
            return d
    except Exception as e:
        cicha_awaria("load_state", e)
    return {"paused": {}, "demoted": [], "demoted_info": {}}


def save_state(st):
    tmp = STATE_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(st, f, indent=1)
        os.replace(tmp, STATE_PATH)
    except Exception as e:
        # bez zapisu stanu po restarcie nikt nie wznowi zapauzowanych procesow
        cicha_awaria("save_state", e)


def sig(pid, pgid, s):
    """Wysyla sygnal; zwraca 0 przy sukcesie albo errno bledu (ESRCH/EPERM/...).

    Gdy sygnal do GRUPY odbije sie (jeden niesygnalizowalny czlonek blokuje calosc —
    killpg jest atomowy), probujemy jeszcze pojedynczego pid: lepiej wstrzymac czesc
    niz nic. Zwracany errno pozwala odroznic "proces juz nie zyje" (ESRCH, normalne)
    od "brak uprawnien" (EPERM, ochrona realnie niepelna).
    """
    import errno as _e
    blad = 0
    if pgid:
        try:
            os.killpg(pgid, s)
            return 0
        except OSError as ex:
            blad = ex.errno
    try:
        os.kill(pid, s)
        return 0
    except OSError as ex:
        return ex.errno or blad or _e.EPERM


_nie_da_sie = {}          # pid -> comm: procesy, ktorych NIE DA SIE wstrzymac (EPERM)


def licznik(st, klucz, ile=1):
    """Skumulowane liczniki pracy bezpiecznika (state.json).

    Amphetamine liczy, ile Mac NIE spal. Dla nas wartosciowa jest liczba odwrotna:
    ile razy bezpiecznik faktycznie zadzialal. To jest dowod, ze produkt pracuje,
    a nie tylko wisi na pasku - i jedyna statystyka, ktorej konkurencja miec nie moze.
    Licznikow NIGDY nie zerujemy sami; od tego jest przycisk u czlowieka.
    """
    try:
        # DWA zestawy: "stats" zyje miedzy uruchomieniami (suma od zawsze), "stats_sesja"
        # jest zerowany przy starcie demona. Okno w pasku nazywa sie "Statystyki sesji",
        # wiec musi miec czym pokazac SESJE - inaczej nazwa by klamala, a to ten sam blad,
        # co liczenie recznych pauz jako zaslugi bezpiecznika.
        for gdzie in ("stats", "stats_sesja"):
            st.setdefault(gdzie, {})
            st[gdzie].setdefault("since", now())
            st[gdzie][klucz] = int(st[gdzie].get(klucz, 0)) + ile
    except Exception:
        pass


def do_pause(cfg, st, targets, reason, manual=False, lvl_krytyczny=False):
    changed = False
    nieudane = []
    for pid, cpu, comm, pgid in targets:
        key = str(pid)
        if key in st["paused"] or pid in _nie_da_sie:
            continue
        if cfg["dry_run"]:
            log(T("[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s") % (comm, pid, cpu, reason))
            notify(cfg, T("Thermal guard (watch-only): hot"),
                   T("Would pause %s - %s. Protection is off.") % (comm, reason), "watchonly")
            continue
        # WPIS-INTENCJA PRZED SYGNALEM, nie po nim. Zapis po SIGSTOP zostawial okno
        # kilku milisekund: demon ubity w nim (SIGKILL, aktualizacja, kickstart -k)
        # zostawial proces zamrozony BEZ wpisu w stanie - czyli na zawsze, bo nikt by
        # o nim nie wiedzial. Teraz najpierw notatka na dysku, potem strzal; gdy sygnal
        # sie nie uda, notatke kasujemy. Sierota moze powstac juz tylko w druga strone:
        # wpis bez pauzy, ktory sprzatnie petla (wpisy_nieaktualne) albo startowy
        # do_resume. Jeden fsync na pauze jest tanszy niz proces w stanie T na wieki.
        # POWOD pauzy trafia do wpisu. Bez tego bramka "wznawiaj dopiero na
        # zasilaczu" stosowala sie do KAZDEJ pauzy, takze czysto termicznej:
        # przy baterii 11-24% zadanie zapauzowane z powodu goracego chipu nie
        # wracalo nigdy, mimo ze bramka baterii (10%) nie zostala przekroczona.
        st["paused"][key] = {"since": now(), "since_mono": time.monotonic(),
                             "mono_id": _MONO_ID,
                             "powod": "bateria" if "batt" in (reason or "").lower()
                                      or "bateri" in (reason or "").lower() else "termika",
                             "comm": comm, "pgid": pgid, "cpu": cpu, "manual": manual}
        save_state(st)
        blad = sig(pid, pgid, signal.SIGSTOP)
        if blad == 0:
            changed = True
            log(T("PAUSED %s (pid %d, %.0f%% CPU) - %s") % (comm, pid, cpu, reason), tag="PAUSE")
            # Liczymy TYLKO prace bezpiecznika. Reczne zamrozenie z paska to decyzja
            # czlowieka, nie zasluga produktu - a okno statystyk obiecuje to drugie.
            if not manual:
                licznik(st, "pauses")
        elif blad == errno.ESRCH:
            # proces zdazyl zniknac miedzy odczytem ps a sygnalem - to normalne, nie awaria;
            # wpis-intencja schodzi z dysku, bo nie opisuje niczego zywego
            st["paused"].pop(key, None)
            save_state(st)
            log(T("gone before pause: %s (pid %d)") % (comm, pid))
        else:
            # EPERM i reszta: ochrona jest REALNIE NIEPELNA - nazwa idzie do zbioru
            # pominietych (koniec ponawiania co 15 s i zasmiecania logu) i do statusu;
            # wpis-intencja schodzi z dysku, bo pauzy faktycznie NIE BYLO
            st["paused"].pop(key, None)
            save_state(st)
            _nie_da_sie[pid] = comm
            nieudane.append(comm)
            log(T("FAILED to pause %s (pid %d) - errno %d, giving up on this pid")
                % (comm, pid, blad))
    st["_unpausable"] = sorted(set(_nie_da_sie.values()))
    if changed:
        names = ", ".join(sorted(set(v["comm"] for v in st["paused"].values())))
        notify(cfg, T("Thermal guard: hot"), T("Paused: %s (%s)") % (names, reason), "pause")
    if nieudane and lvl_krytyczny:
        # ochrona zawiodla przy poziomie krytycznym - uzytkownik MUSI o tym wiedziec
        notify(cfg, T("Thermal guard: PROTECTION INCOMPLETE"),
               T("Could not pause: %s (%s). The Mac stays hot - intervene manually.")
               % (", ".join(sorted(set(nieudane))), reason), key="failpause")
    return changed


def do_resume(cfg, st, reason, only_keys=None, po_ostygnieciu=False):
    """Wznawia zamrozone zadania; `only_keys` ogranicza to do wskazanych wpisow.

    KRYTYCZNE (znalezione 04.08.2026 przez runde testowa): parametru tu NIE BYLO, a petla
    glowna wolala `do_resume(..., only_keys=gotowe)` — czyli GLOWNA sciezka wznowienia po
    ostygnieciu rzucala TypeError, ktory ogolny `except` petli polykal. Skutek: zadanie
    zamrozone przy przegrzaniu NIE wracalo do pracy nigdy, tylko czekalo na SIGTERM po
    `max_pause_minutes`. W logu Pawla: trzy pauzy po wprowadzeniu bledu, ZERO wznowien.
    Nie zauwazono tego przez dwa dni, bo tego samego dnia podniesiono progi i maszyna
    przestala dobijac do progu pauzy. Klasyczna cicha awaria: brak wpisu wyglada tak samo
    jak brak potrzeby.
    """
    if not st["paused"]:
        return False
    for key, info in list(st["paused"].items()):
        if only_keys is not None and key not in only_keys:
            continue          # reszta zostaje zamrozona swiadomie (min. czas pauzy, reczne)
        pid = int(key)
        if alive(pid):
            blad = sig(pid, info.get("pgid"), signal.SIGCONT)
            stan = run(["ps", "-o", "stat=", "-p", str(pid)]).strip()
            if blad == 0 and not stan.startswith("T"):
                log(T("RESUMED %s (pid %d) - %s") % (info.get("comm", "?"), pid, reason), tag="RESUME")
                # Okno statystyk mowi "wznowione PO OSTYGNIECIU", wiec reczne wznowienie,
                # start i zamkniecie demona sie nie licza. Etykieta ma byc prawdziwa.
                if po_ostygnieciu:
                    licznik(st, "resumes")
            elif stan.startswith("T"):
                # SIGCONT poszedl, ale proces DALEJ stoi - klasyczna petla SIGTTIN
                # (wznowiony w tle, chce czytac klawiature). Sam z tego nie wyjdzie.
                log(T("STILL STOPPED after SIGCONT: %s (pid %d) - foreground terminal job, "
                      "type 'fg' in its window") % (info.get("comm", "?"), pid))
                notify(cfg, T("Thermal guard: job needs your hand"),
                       T("%s cannot resume by itself - switch to its terminal and type 'fg'.")
                       % info.get("comm", "?"), key="ttin")
            else:
                log("FAILED to resume %s (pid %d) - errno %d"
                    % (info.get("comm", "?"), pid, blad))
                # Nieudany SIGCONT NIE moze kasowac wpisu: proces zostaje zamrozony,
                # a guard o nim zapomina - nie wznowi go nawet po restarcie. Liczymy
                # proby i po piatej odpuszczamy, zeby wpis nie zostal tam na wieki.
                info["proby_wznowienia"] = info.get("proby_wznowienia", 0) + 1
                if info["proby_wznowienia"] < 5:
                    continue
                log("giving up on resuming %s (pid %d) after 5 attempts"
                    % (info.get("comm", "?"), pid))
        del st["paused"][key]
    notify(cfg, T("Thermal guard: cooled down"), T("Resumed paused jobs (%s)") % reason, "resume")
    return True


def _wiek_pauzy(v):
    """Ile sekund trwa ta pauza. Zegar monotoniczny tylko w obrebie tego procesu
    (patrz `mono_id`), inaczej scienny — bo tylko on znaczy to samo po restarcie."""
    m = v.get("since_mono")
    if m is not None and v.get("mono_id") == _MONO_ID:
        return max(0.0, time.monotonic() - m)
    return max(0.0, now() - v.get("since", now()))


def do_terminate(cfg, st, reason, only_keys=None):
    """SIGCONT + SIGTERM (proces w SIGSTOP nie obsluzy TERM), po 20 s SIGKILL.

    only_keys: ubij TYLKO te wpisy (timeout pauzy nie moze zabijac swiezo wstrzymanych).
    Wpisy reczne (zamrozone z paska) sa pomijane ZAWSZE: zamrozony proces nie grzeje,
    wiec jego ubicie niczego nie chlodzi — a bylby to cios w plecy uzytkownika.

    RE-CHECK TUZ PRZED STRZALEM: migawka `ps` z poczatku cyklu ma kilkanascie sekund.
    Reczny `kill -CONT` wydany w srodku cyklu znaczyl SIGTERM w proces chodzacy pelna
    para (runda 3 Codeksa, 05.08.2026). Dlatego pytamy system jeszcze raz TUTAJ:
    ubijamy wylacznie to, co w tej chwili naprawde stoi; wpis po procesie, ktory znow
    pracuje, kasujemy - jesli dalej grzeje, nastepny cykl zamrozi go od nowa.
    Nieudany pomiar (`None`) wstrzymuje egzekucje w calosci: do ubicia potrzebny jest
    DOWOD, ze cos stoi, a pauza i tak juz chlodzi maszyne.
    """
    stoja = zatrzymane_teraz()
    if stoja is None:
        log("ps unavailable - postponing termination decisions")
        return False
    victims = []
    for key, info in list(st["paused"].items()):
        if only_keys is not None and key not in only_keys:
            continue
        if info.get("manual"):
            continue
        pid = int(key)
        if not alive(pid):
            del st["paused"][key]
            continue
        if cfg["dry_run"]:
            log(T("[DRY-RUN] would terminate %s (pid %d) - %s") % (info.get("comm"), pid, reason))
            continue
        if not wpis_stoi(key, info, *stoja):
            log(T("dropping stale pause entry: %s (pid %s) is running again "
                  "- resumed outside the guard") % (info.get("comm", "?"), key))
            del st["paused"][key]
            continue
        sig(pid, info.get("pgid"), signal.SIGCONT)
        sig(pid, info.get("pgid"), signal.SIGTERM)
        victims.append((pid, info))
        log(T("TERMINATED (SIGTERM) %s (pid %d) - %s") % (info.get("comm", "?"), pid, reason), tag="KILL")
        licznik(st, "kills")
        del st["paused"][key]
    if victims:
        notify(cfg, T("Thermal guard: STOPPED"),
               T("Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.")
               % reason, "kill")
        time.sleep(20)
        for pid, info in victims:
            # grupa moze zyc mimo smierci lidera (dzieci ignoruja TERM) — killpg
            # na martwej grupie po prostu odbije sie bledem, ktory polykamy
            if info.get("pgid") or alive(pid):
                if sig(pid, info.get("pgid"), signal.SIGKILL) == 0:
                    log("SIGKILL %s (pid %d)" % (info.get("comm", "?"), pid))
    return bool(victims)


def prog_demote(cfg):
    """Prog chipu, od ktorego degradacja w ogole ma sens termiczny.

    Ponizej niego maszyna jest chlodna i spychanie kogokolwiek na E-cores
    nie chlodzi niczego - tylko tnie tempo (nocna kolejka: ffmpeg przy 44 C
    zwolnil 11x, wentylatory stały). Domyslnie soc_resume_c + 4: powrot jest
    przy soc_resume_c, wiec miedzy degradacja a powrotem zostaje realna
    szczelina histerezy, nie jedna kreska, na ktorej się trzepocze."""
    p = cfg.get("demote_above_c")
    if p is not None:
        return float(p)
    return float(cfg.get("soc_resume_c", 80.0)) + 4.0


_demote_nie_da_sie = set()    # pidy, ktorych taskpolicy nie przyjal (cudzy wlasciciel)


def do_demote(cfg, st, targets, cpu_hist, soc_t, saferun_normal=frozenset()):
    """Cieplo + dlugo mielacy proces -> background QoS (E-cores).

    Zegar (cpu_hist) liczy SKUMULOWANE sekundy aktywnego mielenia, nie czas
    od pierwszego zobaczenia: proces pauzowany SIGSTOP-em wypada z targets
    i przy starym liczeniu zegar startowal od zera po kazdym wznowieniu -
    najgoretszy job NIGDY nie zbieral 5 minut i uciekal degradacji (B3)."""
    limit = cfg["demote_after_minutes"] * 60
    for pid, cpu, comm, pgid in targets:
        if cpu < cfg["demote_cpu_percent"] or pid in _demote_nie_da_sie:
            continue
        # safe-run --normal = czlowiek jawnie kazal leciec na wszystkich rdzeniach;
        # degradowanie go 5 minut pozniej cofaloby jego decyzje za jego plecami.
        # Pauza przy przegrzaniu dalej obowiazuje - wyjatek dotyczy TYLKO degradacji.
        if pid in saferun_normal or pgid in saferun_normal:
            continue
        zebral = cpu_hist.get(pid, 0.0) + cfg["poll_seconds"]
        cpu_hist[pid] = zebral
        if zebral < limit or pid in st["demoted"]:
            continue
        # bez odczytu chipu nie ma jak uzasadnic degradacji termicznie - nie zgadujemy
        if soc_t is None or soc_t < prog_demote(cfg):
            continue
        if cfg["dry_run"]:
            log(T("[DRY-RUN] would demote %s (pid %d)") % (comm, pid))
            continue
        # TYLKO taskpolicy, bez renice: nice podniesiony raz nie da sie oddac bez roota
        # (Unix pozwala nieuprzywilejowanym wylacznie podnosic nice), a taskpolicy -b/-B
        # jest w pelni odwracalne i to QoS background robi tu cala robote (E-cores)
        rc = subprocess.call(["taskpolicy", "-b", "-p", str(pid)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc != 0:
            # cudzy proces (root) - taskpolicy odbil. Bez tego sprawdzenia wpisalibysmy
            # go do demoted i powiadomili "spowolnione", a on mielilby dalej pelna para:
            # log by klamal. Pid idzie do zbioru pominietych: bez tego prawie kazdy cykl
            # forkowalby taskpolicy i pisal te sama linie logu co 15 sekund.
            if pid not in _demote_nie_da_sie:
                _demote_nie_da_sie.add(pid)
                log("DEMOTE failed for %s (pid %d) - taskpolicy rc=%d (not our process?)"
                    % (comm, pid, rc))
            continue
        st["demoted"].append(pid)
        # nazwa do stanu - degradacja tnie tempo nawet 11x, wiec czlowiek
        # i agent MUSZA ja widziec w status.json, a pid nikomu nic nie mowi
        st.setdefault("demoted_info", {})[str(pid)] = {"comm": comm}
        log(T("DEMOTED %s (pid %d) -> background QoS/E-cores (hot for >%d min)")
            % (comm, pid, cfg["demote_after_minutes"]), tag="DEMOTE")
        # pauza ma dzwiek i push, a degradacja ma WIEKSZY trwaly wplyw na czas
        # zadania (pauza mija, spowolnienie zostaje) - wiec tez musi byc slyszalna
        notify(cfg, T("Thermal guard: job slowed down"),
               T("%s moved to E-cores (up to several times slower) - returns to full speed when the machine cools") % comm,
               "demote")


def do_promote(cfg, st, cpu_hist, soc_t):
    """Histereza powrotu: maszyna ostygla -> zdegradowane wracaja na rdzenie P.

    Bez tego degradacja byla jednokierunkowa: proces raz zepchniety na E-cores
    zostawal tam do smierci, nawet przy 44 C i stojacych wentylatorach."""
    if not st["demoted"] or cfg["dry_run"]:
        return
    if soc_t is None or soc_t > cfg.get("soc_resume_c", 80.0):
        return
    for pid in list(st["demoted"]):
        if not alive(pid):
            continue
        info = st.get("demoted_info", {}).get(str(pid), {})
        subprocess.call(["taskpolicy", "-B", "-p", str(pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st["demoted"].remove(pid)
        st.get("demoted_info", {}).pop(str(pid), None)
        # zegar od zera: powrot ma byc powrotem, a nie 15-sekundowa przerwa
        # przed natychmiastowa ponowna degradacja
        cpu_hist[pid] = 0.0
        log(T("PROMOTED %s (pid %d) -> back on P-cores (machine cooled down)")
            % (info.get("comm", "?"), pid), tag="PROMOTE")
        notify(cfg, T("Thermal guard: full speed again"),
               T("%s is back on P-cores") % info.get("comm", "?"), "promote")


# ---------------------------------------------------------------- ocena

def severity(cfg, state, temp, speed, soc=None, ac=True, pct=None):
    """0 spokoj, 1 ciepło, 2 gorąco (pauza), 3 krytycznie (ubicie).

    temp = bateria (wolna, bezwladna), soc = chip (szybka). Bierzemy ostrzejszy z dwoch:
    chip lapie skok obciazenia w sekundy, bateria potwierdza, ze cala obudowa sie zagrzala.
    """
    lvl = 0
    why = []
    if soc is not None:
        if soc >= cfg.get("soc_kill_c", 100.0):
            lvl = max(lvl, 3); why.append(T("chip %.1f C") % soc)
        elif soc >= cfg.get("soc_pause_c", 92.0):
            lvl = max(lvl, 2); why.append(T("chip %.1f C") % soc)
        elif soc >= cfg.get("soc_pause_c", 92.0) - 7:
            lvl = max(lvl, 1); why.append(T("chip %.1f C") % soc)
    # bramka na baterie: na zasilaniu bateryjnym ponizej progu pauzujemy, zeby dlugie
    # obliczenie nie zgaslo razem z laptopem w polowie bloku (czekamy na zasilacz)
    if not ac and pct is not None and pct <= cfg.get("batt_pct_pause", 10):
        lvl = max(lvl, 2); why.append(T("battery %d%% on battery power") % pct)
    s = LEVELS.get(state, 1)
    if s >= 3:
        lvl = max(lvl, 3); why.append(T("thermal state=critical"))
    elif s >= LEVELS.get(cfg["pause_on_thermal_state"], 2):
        lvl = max(lvl, 2); why.append(T("thermal state=%s") % state)
    elif s == 1:
        lvl = max(lvl, 1); why.append(T("thermal state=fair"))
    if temp is not None:
        if temp >= cfg["batt_kill_c"]:
            lvl = max(lvl, 3); why.append(T("battery %.1f C") % temp)
        elif temp >= cfg["batt_pause_c"]:
            lvl = max(lvl, 2); why.append(T("battery %.1f C") % temp)
        elif temp >= cfg["batt_pause_c"] - 3:
            lvl = max(lvl, 1); why.append(T("battery %.1f C") % temp)
    if speed < cfg["speed_limit_pause"]:
        lvl = max(lvl, 2); why.append(T("CPU throttled to %d%%") % speed)
    return lvl, ", ".join(why)


def boot_time():
    """Moment ostatniego startu systemu (epoch)."""
    m = re.search(r"sec\s*=\s*(\d+)", run(["sysctl", "-n", "kern.boottime"]))
    return int(m.group(1)) if m else 0


def zapisz_zdarzenie(rodzaj, opis, kontekst=None, synthetic=False, kiedy=None):
    """Czarna skrzynka — zdarzenia, ktore maja przezyc restart i trafic do raportu.

    synthetic=True oznacza wpis z testu/harnessu: thermal-report go POMIJA, zeby zaden
    sztuczny pad nie trafil do dowodu na gwarancje (lekcja 30.07: test skaza dowod
    rownie latwo jak config).
    """
    try:
        with open(EVENTS_PATH, "a") as f:
            # `kiedy` to epoch ZDARZENIA. Bez tego do pliku szedl moment WYKRYCIA, a pad
            # wykrywa sie dopiero przy starcie po restarcie - wiec raport za dzien padu
            # odpowiadal "w tym okresie nie wykryto zadnego twardego wylaczenia".
            # Najgorszy mozliwy falszywy negatyw w dokumencie dla ubezpieczyciela.
            t = kiedy if kiedy else now()
            wpis = {"time": ts(t), "epoch": round(t, 3), "detected_at": ts(),
                    "type": rodzaj, "description": opis}
            if synthetic:
                wpis["synthetic"] = True
            if kontekst:
                wpis["context"] = kontekst
            f.write(json.dumps(wpis, ensure_ascii=False) + "\n")
    except Exception as e:
        # dowod, ktory nie powstal, jest gorszy niz brak dowodu - musi zostac slad
        cicha_awaria("zapisz_zdarzenie", e)


def pad_juz_zapisany(epoch_padu, tolerancja=90.0):
    """Czy ten sam twardy pad juz jest w czarnej skrzynce?

    Rozstrzyga MOMENT ZDARZENIA (`epoch`), nie moment wykrycia: ten sam pad wykryty
    przy trzech kolejnych startach demona ma trzy rozne `detected_at`, ale jeden
    `epoch`. Tolerancja 90 s obejmuje przypadek, w ktorym puls raz przyszedl z tresci
    pliku, a raz z mtime (fallback) - to samo zdarzenie, minimalnie inna liczba.

    Dwa PRAWDZIWE pady o tym samym czasie ostatniego pulsu nie istnieja: miedzy nimi
    musi byc boot i przynajmniej jeden przebieg demona, ktory tyka heartbeat.
    """
    try:
        with open(EVENTS_PATH, encoding="utf-8", errors="replace") as f:
            linie = f.readlines()
    except OSError:
        return False
    # ogon wystarczy: duble powstaja przy kolejnych startach, czyli obok siebie
    for linia in reversed(linie[-200:]):
        try:
            z = json.loads(linia)
        except ValueError:
            continue
        if not isinstance(z, dict) or z.get("type") != "HARD_SHUTDOWN" or z.get("synthetic"):
            continue
        e = z.get("epoch")
        if isinstance(e, (int, float)) and abs(e - epoch_padu) <= tolerancja:
            return True
    return False


def wykryj_twardy_pad():
    """Czy poprzednia sesja skonczyla sie twardym zgasnieciem?

    Guard tyka `heartbeat` przy kazdym przebiegu, a przy czystym zamknieciu zapisuje
    `clean_stop`. Jesli po restarcie ostatni puls jest z CZASU SPRZED tego bootu i nie ma
    przy nim czystego zamkniecia — znaczy, ze Mac zgasl bez uprzedzenia. Wtedy zapisujemy
    zdarzenie razem z ostatnimi pomiarami sprzed padu; to jest dokladnie ten dowod, ktorego
    zabraklo 29.07.2026 (dziennik systemowy urwal sie i nie dalo sie nic odtworzyc).
    """
    try:
        if not os.path.exists(HEARTBEAT_PATH):
            return None
        # AUTORYTATYWNA jest TRESC pulsu (epoch — niezalezny od strefy i DST; lot na zachod
        # albo jesienna zmiana czasu przesuwalyby tekstowa date "w przod" i wyciszaly pad).
        # mtime tylko jako ostatecznosc: przezywa cp -p, ale restore bez -p ustawia "teraz"
        # i rowniez maskowalby pad. Format: "<epoch> <czytelna data>"; starszy format (sam
        # tekst) czytamy przejsciowo po staremu.
        boot = boot_time()
        puls = None
        raw = ""
        try:
            with open(HEARTBEAT_PATH) as f:
                raw = f.read().strip()
            puls = float(raw.split(None, 1)[0])
        except Exception:
            pass
        if puls is None:
            try:
                puls = time.mktime(time.strptime(raw, "%Y-%m-%d %H:%M:%S"))
                mt = os.path.getmtime(HEARTBEAT_PATH)
                # legacy-tekst nie niesie strefy: przeczytany po zmianie strefy moze
                # "przeskoczyc" boot i wyciszyc pad — gdy mtime mowi, ze puls byl
                # sprzed bootu, ufamy mtime (okno jednej detekcji po upgrade; Neo 30.07)
                if boot and puls >= boot > mt:
                    puls = mt
            except Exception:
                puls = os.path.getmtime(HEARTBEAT_PATH)
        if not boot or puls >= boot:
            return None                       # puls z biezacej sesji — nic sie nie stalo

        # --- poziom pewnosci zamiast milczenia ---------------------------------------
        # Do 2.1.7 wlacznie kazdy przypadek "podejrzany" konczyl sie `return None`, czyli CISZA.
        # To najgorsze mozliwe zachowanie czarnej skrzynki: rozladowany RTC albo skok NTP
        # kasowal dowod bezpowrotnie, a podloga 30-dniowa WYRZUCALA go zamiast oznaczyc.
        # W druga strone: demon ubity SIGKILL-em albo `launchctl bootout` przed normalnym
        # restartem zostawia puls sprzed bootu bez clean_stop - i zdarzenie bylo
        # FABRYKOWANE jako twardy pad w dniu, w ktorym Mac dzialal poprawnie.
        #
        # Zadnego z tych przypadkow nie da sie rozstrzygnac lokalnie i tanio. Dlatego
        # dowod zapisujemy ZAWSZE, ale z jawna ocena wiarygodnosci - dokument dowodowy
        # ma mowic prawde takze o tym, jak bardzo jest pewny. Rozstrzyga czlowiek
        # w serwisie, nie heurystyka w demonie.
        pewnosc, powod_pewnosci = "high", ""
        luka = boot - puls                    # ile uplynelo miedzy ostatnim pulsem a bootem
        if luka > 30 * 86400:
            pewnosc = "low"
            powod_pewnosci = T(
                "the last heartbeat is %d days before boot - the clock was most likely wrong "
                "(dead RTC, NTP jump) or the data came from a backup") % int(luka // 86400)
        elif luka > 12 * 3600:
            pewnosc = "low"
            powod_pewnosci = T(
                "%.1f h passed between the last heartbeat and boot - the guard may have been "
                "killed long before the Mac actually went down") % (luka / 3600.0)
        czyste = os.path.getmtime(CLEAN_STOP_PATH) if os.path.exists(CLEAN_STOP_PATH) else 0
        # znacznik czystego zamkniecia liczy sie TYLKO gdy pochodzi sprzed biezacego bootu —
        # clean_stop z aktualnej sesji albo artefakt (backup, cp -p, zegar z przyszlosci)
        # nie moze wyciszyc prawdziwego twardego padu (finalny przeglad Codex, 30.07)
        if puls - 60 <= czyste < boot:
            return None                       # guard zostal zamkniety po ludzku
        # ostatnie pomiary sprzed zgasniecia — to jest material dowodowy
        ogon = []
        try:
            with open(HIST_PATH) as f:
                wiersze = f.readlines()
            naglowek = wiersze[0].strip().split(",") if wiersze else []
            for w in wiersze[-8:]:
                if w.strip() and not w.startswith("time,"):
                    ogon.append(dict(zip(naglowek, w.strip().split(","))))
        except Exception:
            pass
        # Ten sam pad wolno opisac DOKLADNIE RAZ. Jesli demon ginie zanim zdazy tyknac
        # heartbeat (pad w pierwszych sekundach po starcie, launchd restartujacy w petli),
        # to przy kazdym kolejnym starcie widzi ten sam stary puls i zapisuje to samo
        # zdarzenie od nowa. Odtworzone 02.08.2026: trzy starty = trzy identyczne wpisy
        # z tym samym `epoch`, ktore w dokumencie roszczeniowym wygladaja jak TRZY osobne
        # awarie. Zawyzony licznik awarii jest w takim dokumencie gorszy niz jego brak -
        # druga strona wykaze, ze dane sa niewiarygodne, i podwazy caly raport.
        if pad_juz_zapisany(puls):
            return None
        opis = (T("Mac went down without a clean shutdown. Guard's last heartbeat: %s, "
                "system booted: %s.") % (ts(puls), ts(boot)))
        if pewnosc == "low":
            opis += " " + T("CONFIDENCE: LOW - %s.") % powod_pewnosci
        zapisz_zdarzenie("HARD_SHUTDOWN", opis,
                         {"last_readings": ogon, "confidence": pewnosc,
                          "confidence_reason": powod_pewnosci,
                          "gap_to_boot_s": round(luka, 1)},
                         kiedy=puls)
        log(T("!!! HARD SHUTDOWN DETECTED - ") + opis)
        return {"time": ts(puls), "description": opis, "readings": ogon,
                "confidence": pewnosc}
    except Exception:
        return None


def obsluz_rozkaz(cfg, st, targets):
    """Rozkazy z paska menu: reczne zamrozenie i wznowienie."""
    try:
        if not os.path.exists(COMMAND_PATH):
            return
        with open(COMMAND_PATH) as f:
            rozkaz = f.read().strip()
        os.remove(COMMAND_PATH)
    except Exception:
        return
    if rozkaz == "freeze" or rozkaz.startswith("freeze:"):
        # "freeze" = wszystko co kwalifikuje; "freeze:123,456" = tylko wskazane PID-y
        # (uzytkownik wybiera je w oknie potwierdzenia). Wybor filtruje kandydatow,
        # NIE omija zadnej reguly: proces spoza listy targets i tak nie zostanie ruszony.
        if rozkaz.startswith("freeze:"):
            chciane = set()
            for kawalek in rozkaz.split(":", 1)[1].split(","):
                kawalek = kawalek.strip()
                if kawalek.isdigit():
                    chciane.add(int(kawalek))
            targets = [t for t in (targets or []) if t[0] in chciane]
        # flage stawiamy TYLKO gdy naprawde cos zamrozilismy — inaczej pasek klamie
        if targets and do_pause(cfg, st, targets, T("MANUAL FREEZE (from the menu bar)"), manual=True):
            st["reczna_pauza"] = True
        else:
            log(T("manual freeze: there was nothing to freeze"))
            notify(cfg, T("Nothing to freeze"),
                   T("No heavy job meets the conditions"), key="freeze")
    elif rozkaz == "resume":
        st["reczna_pauza"] = False
        do_resume(cfg, st, T("manual resume (from the menu bar)"))


def statystyki_dnia():
    """Ile razy dzis guard interweniowal — do pokazania w pasku."""
    dzis = time.strftime("%Y-%m-%d")
    pauzy = wznowienia = ubicia = 0
    try:
        # errors="replace": jeden bajt spoza UTF-8 (uciety zapis, smiec po padzie) wywalal
        # dekoder przy pierwszym readline i zerowal calą statystyke dnia - pasek pokazywal
        # "dzis 0 pauz" po nocy pelnej pauz, bez zadnego sygnalu.
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.startswith(dzis):
                    continue
                # Znacznik jest jezykowo neutralny; slowa zostaja dla wpisow sprzed
                # wprowadzenia znacznikow (log rotuje sie, wiec to przejsciowe).
                if "[KILL]" in line or "SIGTERM" in line or "koncze zadanie" in line:
                    ubicia += 1
                elif "[PAUSE]" in line or "PAUZA " in line or "PAUSED " in line:
                    pauzy += 1
                elif "[RESUME]" in line or "WZNOWIONE" in line or "RESUMED" in line:
                    wznowienia += 1
    except Exception:
        pass
    return {"pauses": pauzy, "resumes": wznowienia, "kills": ubicia}


_trend = []


def trend_i_prognoza(cfg, soc_t):
    """Ile stopni na minute rosnie chip i za ile minut dobije do progu pauzy.

    Zamiast dowiadywac sie o problemie w chwili zamrozenia, widac go wczesniej.
    """
    if soc_t is None:
        return None, None
    _trend.append((now(), soc_t))
    while len(_trend) > 8 or (_trend and now() - _trend[0][0] > 300):
        _trend.pop(0)
    if len(_trend) < 3:
        return None, None
    dt = (_trend[-1][0] - _trend[0][0]) / 60.0
    if dt <= 0:
        return None, None
    nachylenie = (_trend[-1][1] - _trend[0][1]) / dt      # C na minute
    prog = cfg.get("soc_pause_c", 85.0)
    if nachylenie <= 0.5 or soc_t >= prog:
        return round(nachylenie, 1), None
    return round(nachylenie, 1), round((prog - soc_t) / nachylenie, 1)


def zadania_saferun():
    """Aktywne zadania uruchomione przez safe-run — nazwa i jak dlugo chodza."""
    out = []
    try:
        for nazwa in os.listdir(MANAGED_DIR):
            if not nazwa.endswith(".json"):
                continue
            with open(os.path.join(MANAGED_DIR, nazwa)) as f:
                d = json.load(f)
            pid = int(d.get("pid", 0))
            if pid and alive(pid):
                out.append({"name": d.get("name") or d.get("comm") or "?",
                            "pid": pid,
                            "minutes": round(proc_age_seconds(pid) / 60.0)})
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- sprzet i kalibracja

def hardware_info():
    """Wykrywa sprzet tego Maca i zapisuje do hardware.json (About my Mac + kalibracja).

    Wolne odczyty (system_profiler ~2 s) robimy RAZ przy starcie — plik jest cache'em.
    """
    def sysctl(k):
        return run(["sysctl", "-n", k]).strip()

    hw = {
        "chip": sysctl("machdep.cpu.brand_string") or "Apple Silicon",
        "model_id": sysctl("hw.model"),
        "p_cores": int(sysctl("hw.perflevel0.physicalcpu") or 0),
        "e_cores": int(sysctl("hw.perflevel1.physicalcpu") or 0),
        "cores": int(sysctl("hw.ncpu") or 0),
        "ram_gb": round(int(sysctl("hw.memsize") or 0) / 1024.0 ** 3),
        "macos": run(["sw_vers", "-productVersion"]).strip(),
    }
    prof = run(["system_profiler", "SPHardwareDataType"], timeout=30)
    m = re.search(r"Model Name:\s*(.+)", prof)
    hw["model_name"] = m.group(1).strip() if m else hw["model_id"]
    m = re.search(r"Serial Number.*?:\s*(\S+)", prof)
    hw["serial"] = m.group(1) if m else ""
    ioreg = run(["ioreg", "-r", "-c", "AppleSmartBattery", "-d", "1", "-w", "0"], timeout=15)
    m = re.search(r'"CycleCount"\s*=\s*(\d+)', ioreg)
    hw["battery_cycles"] = int(m.group(1)) if m else None
    m = re.search(r'"PermanentFailureStatus"\s*=\s*(\d+)', ioreg)
    hw["battery_failure"] = bool(int(m.group(1))) if m else None
    # maks. pojemnosc = ile fabrycznej pojemnosci ogniwo jeszcze trzyma
    m1 = re.search(r'"NominalChargeCapacity"\s*=\s*(\d+)', ioreg)
    m2 = re.search(r'"DesignCapacity"\s*=\s*(\d+)', ioreg)
    if m1 and m2 and int(m2.group(1)) > 0:
        hw["battery_max_capacity_pct"] = round(100 * int(m1.group(1)) / int(m2.group(1)))
    # Jeden nieudany odczyt macmona NIE moze przesadzic o kalibracji. Probkowanie
    # potrafi pasc na obciazonej maszynie (znane z kolejki kompresji), a wlasnie tak
    # wyglada pierwszy start demona: zaraz po `install.sh`, ktory kompilowal pasek.
    # `max_age=0` omija 10-sekundowy cache — bez tego powtorka oddawalaby to samo None.
    # BUDZET, nie liczba prob: `run()` daje macmonowi 20 s na sciezke, a soc_sensors
    # probuje dwoch sciezek. Same ponowienia moglyby wiec opoznic start demona
    # o dwie minuty, czyli o czas, w ktorym nikt nie pilnuje temperatury (Codex 03.08).
    s = soc_sensors()
    koniec_prob = time.monotonic() + 8.0
    while not s and time.monotonic() < koniec_prob:
        time.sleep(2.0)
        s = soc_sensors(max_age=0)
    hw["fan_count"] = len((s or {}).get("fans") or [])
    hw["chip_sensor"] = bool(s)
    try:
        with open(HW_PATH, "w") as f:
            json.dump(hw, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return hw


def auto_calibrate(cfg, hw):
    """Dopasowanie progow do TEGO Maca — raz na sprzet, nigdy po recznej zmianie progow.

    Zasada: nie ma jednego slusznego progu. Mac z wentylatorami znosi 85-95 C bez klopotu;
    Mac bezwentylatorowy (Air) oddaje cieplo obudowa i trzeba go ciac wczesniej, a alarm
    "wentylatory stoja" jest na nim bez sensu. Znacznik calibrated_for pilnuje, zeby
    kalibracja odpalila sie tylko przy pierwszym uruchomieniu na danym sprzecie —
    swiadome, reczne progi uzytkownika sa swiete.
    """
    # Znacznik musi zawierac TAKZE informacje o czujniku. Bez macmona `fan_count`
    # wynosi 0 tak samo jak na prawdziwym Airze - wiec kalibracja zapisywala tag
    # "fans=0", a po doinstalowaniu macmona Air dostawal ten sam tag i progi
    # bezwentylatorowe (78/70/88) nie byly nadawane NIGDY. Akurat na maszynie,
    # dla ktorej prog ma najwieksze znaczenie.
    tag = "%s|%s|fans=%s|sensor=%s" % (hw.get("model_id"), hw.get("chip"),
                                       hw.get("fan_count"), bool(hw.get("chip_sensor")))
    try:
        with open(CFG_PATH) as f:
            _na_dysku = json.load(f)
    except Exception:
        _na_dysku = {}
    dry_ukryty = "dry_run" not in _na_dysku
    if cfg.get("calibrated_for") == tag:
        if not dry_ukryty:
            return None
        # sprzet znany, ale klucz dry_run niejawny (config sprzed v1.3) — dopisz go jawnie
        # (czytaj-zmien-zapisz pod lockiem: pasek moze pisac rownolegle — B5)
        try:
            with config_lock():
                try:
                    with open(CFG_PATH) as f:
                        _na_dysku = json.load(f)
                except Exception:
                    _na_dysku = {}
                _na_dysku["dry_run"] = True
                tmp = CFG_PATH + ".tmp"
                # 0600, nie umask: w config.json siedzi temat ntfy. `ensure_dirs`
                # zaciska prawa tylko przy starcie, wiec zapis kalibracyjny/migracyjny
                # cofal utwardzenie az do nastepnego restartu.
                with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                                       0o600), "w") as f:
                    json.dump(_na_dysku, f, indent=2, ensure_ascii=False, sort_keys=True)
                os.replace(tmp, CFG_PATH)
        except Exception:
            pass
        log("MIGRATION: dry_run was implicit - written explicitly as true (watch-only)")
        return "watchonly"
    # Bez odczytu z czujnika `fan_count=0` znaczy DWIE rozne rzeczy: "Mac bezwentylatorowy"
    # albo "macmon nie odpowiedzial". Zapisanie znacznika w tym stanie zostawia Aira
    # na progach wentylatorowych (85/76/90) i limicie pauzy 45 min az do nastepnego
    # restartu demona — a demon ma KeepAlive, wiec restart moze byc za tydzien.
    # Dlatego przy slepym czujniku znacznika NIE zapisujemy: kalibracja ma sie powtorzyc.
    slepy = not hw.get("chip_sensor")
    changes = {} if slepy else {"calibrated_for": tag}
    if dry_ukryty:
        changes["dry_run"] = True
    # `soc_kill_c` MUSI byc w tym warunku: kalibracja nadpisuje go razem z para
    # pauza/wznowienie, wiec uzytkownik, ktory recznie podniosl sam prog ubicia,
    # tracil go przy pierwszej kalibracji. Odtworzone 03.08 (95.0 -> 88.0).
    untouched = (cfg.get("soc_pause_c") == DEFAULTS["soc_pause_c"]
                 and cfg.get("soc_resume_c") == DEFAULTS["soc_resume_c"]
                 and cfg.get("soc_kill_c") == DEFAULTS["soc_kill_c"])
    if hw.get("fan_count") == 0 and hw.get("chip_sensor"):
        changes["fan_check"] = False          # alarm wentylatorow na Airze = zawsze falszywy
        if untouched:
            changes.update({"soc_pause_c": 78.0, "soc_resume_c": 70.0, "soc_kill_c": 88.0})
            log("CALIBRATION: fanless Mac detected (%s) - chip thresholds 78/70/88"
                % hw.get("model_name"))
        # fanless pauzuje czesciej i dluzej (obudowa oddaje cieplo powoli) — 45 min limitu
        # pauzy ubijaloby dlugie joby, ktore po prostu czekaja na ostygniecie
        if cfg.get("max_pause_minutes") == DEFAULTS["max_pause_minutes"]:
            changes["max_pause_minutes"] = 120
    elif slepy:
        # NIE MILCZ: bez tej linijki log mowil "thresholds defaults OK" na maszynie,
        # ktora wlasnie NIE zostala skalibrowana. Minute pozniej `heat` pokazuje juz
        # temperature chipa i wszystko wyglada zdrowo — nikt by tego nie zauwazyl.
        log("CALIBRATION DEFERRED: no chip sensor reading (macmon missing or busy) - "
            "cannot tell a fanless Mac from a failed probe; thresholds left at %s/%s, "
            "will retry on next start"
            % (cfg.get("soc_pause_c"), cfg.get("soc_resume_c")))
    else:
        log("CALIBRATION: %s, %s (%dP+%dE), %d GB RAM, fans: %s - thresholds %s"
            % (hw.get("model_name"), hw.get("chip"), hw.get("p_cores", 0),
               hw.get("e_cores", 0), hw.get("ram_gb", 0), hw.get("fan_count"),
               "left as user set them" if not untouched else "defaults OK"))
    # Przy slepym czujniku i jawnym dry_run nie ma CZEGO zapisac. Pusty zapis nie jest
    # niewinny: ten tor uzywa golego open(), wiec co start rozluznialby prawa
    # config.json (siedzi w nim temat ntfy) az do nastepnego `ensure_dirs`.
    if not changes:
        return "watchonly" if dry_ukryty else None
    # czytaj-zmien-zapisz pod lockiem: rownolegly zapis paska nie moze zginac (B5)
    try:
        with config_lock():
            try:
                with open(CFG_PATH) as f:
                    disk_cfg = json.load(f)
            except Exception:
                disk_cfg = {}
            disk_cfg.update(changes)
            tmp = CFG_PATH + ".tmp"
            # 0600 przez os.open, nie gole open(): tor migracyjny wyzej robi to od
            # dawna, ten NIE robil. Odtworzone przy umask(0): config 0600 wychodzil
            # z kalibracji jako 0666, a siedzi w nim temat ntfy. Znalazl Codex 03.08.
            with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                                   0o600), "w") as f:
                json.dump(disk_cfg, f, indent=2, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, CFG_PATH)
    except Exception:
        pass
    return "watchonly" if dry_ukryty else None


# ---------------------------------------------------------------- reczny keep-awake

_net = {"t": 0.0, "bytes": 0, "last_active": 0.0}


def network_active(threshold_kbps=500):
    """Czy trwa transfer sieciowy (pobieranie/wysylka)? Delta bajtow z netstat -ib.

    Histereza 120 s: chwilowa cisza miedzy plikami nie zwalnia blokady snu.
    """
    out = run(["netstat", "-ib"], timeout=10)
    total = 0
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) >= 10 and not p[0].startswith("lo") and "<Link" in line:
            try:
                total += int(p[6]) + int(p[9])
            except (ValueError, IndexError):
                pass
    t = now()
    prev_t, prev_b = _net["t"], _net["bytes"]
    _net["t"], _net["bytes"] = t, total
    if prev_t and total >= prev_b:
        kbps = (total - prev_b) / 1024.0 / max(t - prev_t, 1.0)
        if kbps >= threshold_kbps:
            _net["last_active"] = t
    return t - _net["last_active"] < 120


def manual_awake(cfg):
    """Reczny keep-awake ustawiony z paska (awake.json): timer / aplikacja / pobieranie.

    Zwraca (aktywny, opis). Wygasly timer sprzata sam po sobie, zeby pasek nie pokazywal
    martwego stanu. Bezpiecznik termiczny jest NADRZEDNY — o tym decyduje petla, nie my.
    """
    try:
        with open(AWAKE_PATH) as f:
            a = json.load(f)
    except Exception:
        return False, None
    mode = a.get("mode")
    if mode == "timer":
        until = float(a.get("until") or 0)
        if now() < until:
            return True, a
        try:
            os.remove(AWAKE_PATH)
        except Exception:
            pass
        return False, None
    if mode == "forever":
        return True, a
    if mode == "app":
        app = (a.get("app") or "").strip()
        if app and run(["pgrep", "-if", app]).strip():
            return True, a
        return False, a
    if mode == "download":
        return network_active(cfg.get("download_kbps", 500)), a
    return False, None


_hostname_cache = {"v": None}


def hostname():
    if _hostname_cache["v"] is None:
        v = run(["scutil", "--get", "ComputerName"]).strip()
        if not v:
            import socket
            v = socket.gethostname()
        _hostname_cache["v"] = re.sub(r"[^A-Za-z0-9._ -]", "_", v) or "mac"
    return _hostname_cache["v"]


_caff = {"proc": None}


def keep_awake_update(cfg, targets, lvl, st=None):
    """Utrzymuje/zwalnia blokade snu przez systemowy caffeinate.

    Warunek trzymania: (tryb automatyczny z ciezkim zadaniem LUB reczny tryb z paska —
    timer / dopoki dziala aplikacja / dopoki trwa pobieranie) ORAZ poziom < 2 (chlodno).
    Kazde inne polaczenie = blokada w dol. To jest cala roznica wzgledem
    Caffeine/Amphetamine: tam czlowiek musi pamietac o wylaczeniu, tu wylacza fizyka.
    """
    manual, adesc = manual_awake(cfg)
    if st is not None:
        st["_awake_mode"] = (adesc or {}).get("mode") if manual else None
        st["_awake_until"] = (adesc or {}).get("until") if manual else None
        st["_awake_app"] = (adesc or {}).get("app") if manual else None
    proc = _caff["proc"]
    zywy = proc is not None and proc.poll() is None
    auto = bool(cfg.get("keep_awake_auto")) and bool(targets)
    # WYGASZANIE (TODO 8, 06.08.2026): miedzy plikami kolejki jest przerwa - stary
    # enkoder zszedl, nowy jeszcze nie wystartowal. Natychmiastowy stop w tej przerwie
    # robil 45-59 przelaczen na dobe, a na Macu z agresywnym usypianiem potrafilby
    # oddac system snu W SRODKU nocnej kolejki. Trzymamy wiec czuwanie jeszcze przez
    # keep_awake_hold_s po ostatnim ciezkim zadaniu. Wygaszanie tylko PRZEDLUZA zywe
    # czuwanie (nigdy go nie wszczyna) i NIE dotyczy uwolnienia przez cieplo:
    # caly warunek dalej stoi na `lvl < 2`, upal zwalnia blokade natychmiast.
    # Zegar monotoniczny, w obrebie tego procesu - skok NTP nie przedluzy czuwania.
    if auto:
        _caff["ostatni_job"] = time.monotonic()
    hold = max(0, cfg.get("keep_awake_hold_s", 300))
    dogrzewa = (not auto and bool(cfg.get("keep_awake_auto")) and zywy
                and _caff.get("ostatni_job") is not None
                and time.monotonic() - _caff["ostatni_job"] < hold)
    chcemy = (auto or manual or dogrzewa) and lvl < 2
    # Ekran to OSOBNA decyzja od systemu. `-is` trzyma system, ale pozwala zgasic ekran;
    # `-d` trzyma takze ekran (prezentacja, dashboard, podglad renderu). Ekran kosztuje
    # prad i cieplo, wiec domyslnie WYLACZONE - i tak samo jak reszta czuwania ustepuje
    # bezpiecznikowi, bo caly warunek stoi na `lvl < 2`.
    chce_ekran = bool(cfg.get("keep_awake_display"))
    # Wymiana procesu TYLKO wtedy, gdy czuwanie ma dalej trwac. Inaczej zmiana trybu
    # ekranu zbiegajaca sie z przegrzaniem zabralaby galezi stopu jej proces - i licznik
    # "czuwanie ustapilo przed cieplem" nie zauwazylby zdarzenia. Znalazl Codex 04.08.
    if chcemy and zywy and _caff.get("display") != chce_ekran:
        # Zmiana w locie: flag caffeinate nie da sie przestawic, trzeba go wymienic.
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=1)
            except Exception:
                pass
        _caff["proc"] = None
        proc = None
        zywy = False
        _loguj_awake("KEEP-AWAKE restart (display mode changed to %s)"
                     % ("on" if chce_ekran else "off"))
    if chcemy and not zywy:
        try:
            _caff["proc"] = subprocess.Popen(
                ["caffeinate", "-isd"] if chce_ekran else ["caffeinate", "-is"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _caff["display"] = chce_ekran
            _loguj_awake("KEEP-AWAKE start (heavy job running, machine cool)%s"
                         % (" [screen stays on]" if chce_ekran else ""))
            play_sound(cfg, "awake")   # Funk: paladyn bierze kubek
        except Exception:
            _caff["proc"] = None
    elif not chcemy and zywy:
        try:
            proc.terminate()
            proc.wait(timeout=3)      # bez wait() kazdy cykl start/stop zostawialby zombie
        except Exception:
            try:
                proc.kill()           # oporny caffeinate (nierealne, ale za darmo)
                proc.wait(timeout=1)
            except Exception:
                pass
        _caff["proc"] = None
        # Rozrozniamy DWA powody stopu. "Zadanie sie skonczylo" to normalna kolej rzeczy;
        # "maszyna za goraca" to moment, w ktorym bezpiecznik zrobil swoja robote - i tylko
        # to liczymy, bo tylko to jest dowodem, ze produkt dziala.
        przez_termike = (auto or manual) and lvl >= 2
        if przez_termike and st is not None:
            licznik(st, "awake_released_hot")
        _loguj_awake("KEEP-AWAKE stop (%s)"
                     % ("machine too hot" if przez_termike else "job done or disabled"))
    return _caff["proc"] is not None and _caff["proc"].poll() is None


_awake_log = {"ostatni": "", "kiedy": 0.0, "pominiete": 0}


def _loguj_awake(msg):
    """Keep-awake wlacza sie i wylacza w rytm pauz - przy jednym enkoderze x265
    to bylo 209 wpisow na godzine, wiecej niz samych pauz. Zdarzenie jest prawdziwe,
    ale jako log to szum, ktory topi wpisy istotne dla czarnej skrzynki. Logujemy
    wiec zmiane stanu nie czesciej niz co 10 minut, a przy nastepnym wpisie mowimy,
    ile przelaczen sie w tym czasie zmiescilo.
    """
    t = now()
    # Warunek na powtorzenie MUSI miec limit czasu: bez niego ten sam komunikat nie
    # trafialby do logu juz nigdy (sprawdzone: co 24 h przez 5 dni = zero linii).
    # Ujemna roznica (cofniety zegar) tez nie moze wyciszac na zawsze.
    odstep = t - _awake_log["kiedy"]
    if odstep < 0:
        # Zegar skoczyl w tyl (NTP, powrot z uspienia, zmiana strefy). Wczesniej
        # zerowalismy tu odstep, co ZAMYKALO tlumik na kolejne 10 minut liczone od
        # nowa - czyli zdarzenie wypadajace dokladnie na skok zegara przepadalo, a
        # keep-awake nie zostawial sladu w logu. Skok zegara to sam w sobie powod,
        # zeby wpis PRZEPUSCIC: to anomalia, ktora warto miec w czarnej skrzynce.
        _awake_log["kiedy"] = t
        odstep = 600
    if not isinstance(msg, str):
        msg = str(msg)
    if odstep < 600:
        _awake_log["pominiete"] += 1
        _awake_log["ostatni"] = msg
        return
    ile = _awake_log["pominiete"]
    _awake_log.update({"ostatni": msg, "kiedy": t, "pominiete": 0})
    log(msg + (" [+%d przelaczen w miedzyczasie]" % ile if ile else ""))


_hw_fleet = {"v": None}


def _hw_cache_fleet():
    """Model i serial z hardware.json — czytane raz, do migawki floty."""
    if _hw_fleet["v"] is None:
        d = {}
        try:
            with open(HW_PATH) as f:
                j = json.load(f)
            d = {"model": "%s · %s" % (j.get("model_name", "?"), j.get("chip", "?")),
                 "serial": j.get("serial", "")}
        except Exception:
            pass
        _hw_fleet["v"] = d
    return _hw_fleet["v"]


def fleet_write(cfg, status):
    """Migawka hosta do wspolnego folderu floty (jesli skonfigurowany)."""
    d = os.path.expanduser(cfg.get("fleet_dir") or "")
    if not d:
        return
    try:
        if not os.path.isdir(d):
            os.makedirs(d, 0o755)
        out = dict(status)
        out["host"] = (cfg.get("fleet_label") or "").strip() or hostname()
        hw = _hw_cache_fleet()
        out["model"] = hw.get("model")
        out["serial"] = hw.get("serial")
        out["guard_version"] = "2.3.3"
        _bledy = {k: v for k, v in _CICHE_AWARIE.items() if not k.startswith("_ostatni_log_")}
        if _bledy:
            out["swallowed_errors"] = _bledy
        tmp = os.path.join(d, ".%s.tmp" % hostname())
        with open(tmp, "w") as f:
            json.dump(out, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(d, "%s.json" % hostname()))
    except Exception:
        pass                      # flota jest dodatkiem — nie moze polozyc bezpiecznika


def status_write(state, temp, soc, soc_t, ac, pct, speed, load, lvl, why, targets, st, disk=None,
                 pokaz=None):
    """Migawka dla paska menu (`heatbar`). Pasek nic sam nie mierzy — czyta ten plik,
    wiec kosztuje zero CPU i zawsze pokazuje dokladnie to, co widzi guard."""
    # Do POKAZANIA idzie lista bez potomkow (inaczej ten sam procesor liczy sie dwa
    # razy), ale sygnaly leca do PELNEJ listy `targets` — patrz komentarz przy
    # `bez_potomkow`, to rozroznienie kosztowalo nas dziurawa ochrone drzew procesow.
    do_pokazania = pokaz if pokaz is not None else (targets or [])
    top = targets[0] if targets else None
    data = {
        "time": ts(), "thermal_state": state, "level": lvl, "reason": why,
        "chip_c": round(soc_t, 1) if soc_t else None,
        "gpu_c": round(soc["gpu"], 1) if soc and soc.get("gpu") else None,
        "battery_c": round(temp, 1) if temp else None,
        "fans": (soc.get("fans") if soc else []) or [],
        "watts": round(soc["watts"], 1) if soc else None,
        "ram_used_gb": round(soc["ram_used"], 1) if soc and soc.get("ram_total") else None,
        "ram_total_gb": round(soc["ram_total"], 1) if soc and soc.get("ram_total") else None,
        # swap uzywany na maszynie z duzym RAM-em to najlepszy sygnal realnej presji pamieci
        "swap_used_gb": round(soc["swap_used"], 2) if soc and soc.get("ram_total") else None,
        "disk_used_gb": round(disk[0]) if disk else None,
        "disk_total_gb": round(disk[1]) if disk else None,
        "disk_used_pct": round(disk[2]) if disk else None,
        "battery_pct": pct, "on_ac": bool(ac),
        "cpu_limit": speed, "load1": round(load, 2),
        "paused": [v.get("comm") for v in st.get("paused", {}).values()],
        # degradacja na E-cores jest NIEWIDOCZNA w temperaturze (44 C wyglada jak sukces
        # chlodzenia), a tnie tempo zadania nawet 11x - musi byc jawna w migawce
        "demoted": [v.get("comm", "?") for v in st.get("demoted_info", {}).values()],
        "heavy_count": len(do_pokazania),
        "top_proc": top[2] if top else None,
        "top_cpu": round(top[1]) if top else None,
        "manual_pause": bool(st.get("reczna_pauza")),
        "dry_run": bool(st.get("_dry")),
        "keep_awake": bool(st.get("_awake")),
        "stats_total": st.get("stats", {}),
        "stats_session": st.get("stats_sesja", {}),
        "awake_mode": st.get("_awake_mode"),
        "awake_until": st.get("_awake_until"),
        "awake_app": st.get("_awake_app"),
        "trend_c_min": st.get("_trend_c_min"),
        "eta_pause_min": st.get("_eta_min"),
        "jobs": st.get("_zadania", []),
        "stats": st.get("_stat", {}),
        "unpausable": st.get("_unpausable", []),
        "top_cpu_list": st.get("_top_cpu", []),
        # Kandydaci do RECZNEGO zamrozenia - dokladnie to, co dostanie SIGSTOP.
        # Pasek pokazywal tu wczesniej "top_cpu_list", czyli trzy najciezsze procesy
        # w systemie. To byla lista do CZYTANIA, nie do dzialania: siedzialy w niej
        # WindowServer i agent AI, oba na liscie nietykalnych. Okno potwierdzenia
        # obiecywalo wiec zatrzymac procesy, ktorych straznik nigdy by nie ruszyl,
        # i podawalo inna liczbe niz licznik obok.
        "freeze_candidates": [{"pid": t[0], "name": t[2], "cpu": round(t[1])}
                              for t in do_pokazania],
        "top_ram_list": st.get("_top_ram", []),
        "last_hard_shutdown": st.get("_ostatni_pad"),
        "thresholds": {"pause": st.get("_prog_pauza"), "kill": st.get("_prog_ubicie")},
        # False = brak czujnika chipa (macmon). Pasek, flota i agenci maja o tym wiedziec,
        # bo wtedy ochrona opiera sie na samej baterii, ktora reaguje minuty pozniej.
        "chip_sensor": soc is not None,
        # Niepusta lista = demon chodzi na wartosciach INNYCH niz w config.json
        # (sanity-clamp poprawil je w pamieci). Kazdy, kto czyta config.json,
        # ma najpierw spojrzec tutaj - inaczej diagnozuje nie ten system, ktory dziala.
        "config_corrections": list(_ostatnio_odrzucone["v"]),
    }
    tmp = STATUS_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, STATUS_PATH)   # podmiana atomowa — pasek nigdy nie zlapie polowy pliku
    except Exception as e:
        cicha_awaria("status_write", e)   # pasek pokazuje wtedy stare dane jako biezace
    return data


HIST_HEADER = ("time,thermal_state,chip_C,gpu_C,battery_C,fan_rpm,watts,"
               "battery_pct,on_ac,cpu_limit,load1,level,top_proc,top_cpu\n")


def hist_write(row):
    rotate(HIST_PATH)
    # przy zmianie zestawu kolumn odkladamy stary plik zamiast mieszac formaty
    try:
        if os.path.exists(HIST_PATH):
            with open(HIST_PATH) as f:
                if f.readline() != HIST_HEADER:
                    os.rename(HIST_PATH, HIST_PATH.replace(".csv", "_old.csv"))
    except Exception as e:
        cicha_awaria("hist_write/naglowek", e)
    new = not os.path.exists(HIST_PATH)
    try:
        with open(HIST_PATH, "a") as f:
            if new:
                f.write(HIST_HEADER)
            f.write(",".join(str(x) for x in row) + "\n")
    except Exception as e:
        cicha_awaria("hist_write", e)   # brak pomiarow = pusta os czasu w dowodzie


# ---------------------------------------------------------------- petla

def snapshot(cfg):
    state = thermal_state()
    temp = battery_temp_c()
    speed = cpu_speed_limit()
    load = load_avg()
    soc = soc_sensors()
    soc_t = soc_temp_c()
    ac, pct = power_source()
    procs = list_procs()
    saferun, saferun_normal = managed_pids_from_saferun()
    targets = pick_targets(cfg, procs, saferun)
    lvl, why = severity(cfg, state, temp, speed, soc_t, ac, pct)
    # `do_pokazania` jedzie osobno od `targets`: sygnaly leca do PELNEJ listy (inaczej
    # dzieci nie dostaja SIGSTOP), a licznik i okno potwierdzenia pokazuja liste bez
    # potomkow (inaczej ten sam procesor liczy sie dwa razy).
    return (state, temp, speed, load, targets, lvl, why, soc, soc_t, ac, pct,
            saferun_normal, bez_potomkow(targets, procs), list(_DEMOTE_ONLY))


_fan_zero = {"n": 0}


def fan_alarm(cfg, soc, soc_t, st):
    """Chip goracy, a wentylatory stoja = awaria chlodzenia (zatarty wentylator,
    odlaczona tasma, zapchany uklad). Tylko krzyczy — pauzowanie zostawiamy termice,
    zeby blad odczytu nie zabijal obliczen."""
    # Licznik NIE moze przezyc braku danych ani restartu demona: inaczej "trzy odczyty
    # z rzedu" znaczy "trzy odczyty kiedykolwiek", a po restarcie z licznikiem 2 pierwszy
    # rozbieg wentylatorow alarmuje natychmiast. Dlatego zyje w module, nie w state.json.
    if not cfg.get("fan_check", True) or not soc or soc_t is None:
        _fan_zero["n"] = 0
        return
    fans = soc.get("fans") or []
    if not fans:
        _fan_zero["n"] = 0
        return
    hot = soc_t >= cfg.get("fan_alert_temp_c", 75.0)
    dead = max(fans) == 0
    # Wentylatory rozbiegaja sie z zera przez kilka sekund. Pojedynczy odczyt
    # "goraco i 0 obr/min" to najczesciej ROZBIEG, nie awaria - alarm z 02.08 10:32:43
    # (75,9 C, oba na zerze) okazal sie wlasnie tym: chwile pozniej kręcily 2300-2900.
    # Prawdziwa awaria chlodzenia utrzymuje sie; przelotna nie. Liczymy z rzedu.
    _fan_zero["n"] = (_fan_zero["n"] + 1) if (hot and dead) else 0
    st["_fan_zero_polls"] = _fan_zero["n"]          # tylko do podgladu w state.json
    if hot and dead and _fan_zero["n"] >= cfg.get("fan_alert_polls", 3):
        if now() - st.get("fan_alarm_at", 0) > 600:
            st["fan_alarm_at"] = now()
            msg = (T("COOLING FAILURE? chip %.1f C while both fans report 0 rpm") % soc_t)
            log("!!! " + msg, tag="FANFAIL")
            # events.log to czarna skrzynka dla raportu dowodowego. Alarm wentylatorow
            # szedl dotad WYLACZNIE do guard.log, wiec raport - ktory sekcje krytyczna
            # buduje z events.log - twierdzil "nie wykryto alarmu chlodzenia", majac
            # osiem takich alarmow w tym samym dokumencie. Dokument przeczyl sam sobie.
            zapisz_zdarzenie("COOLING_ALARM", msg,
                             {"chip_c": round(soc_t, 1), "fans": list(fans)})
            notify(cfg, T("Fans stopped while the chip is hot"), msg, key="fan")


def zajmij_wylacznosc():
    """Tylko JEDEN demon na maszyne. Blokada trzymana przez caly czas zycia procesu.

    Dwie instancje to nie jest teoretyczny problem: kazda widzi te druga jako zwykly
    proces Pythona zzerajacy CPU i potrafi ja zapauzowac (zdarzylo sie 02.08.2026,
    gdy osierocony `python3 guard.py` z katalogu zrodel przezyl testy). Efekt: log
    pisany na dwa glosy i strażnik zamrozony przez samego siebie.

    Zwraca uchwyt pliku - trzeba go trzymac, zamkniecie zwalnia blokade.
    """
    import fcntl
    sciezka = os.path.join(BASE, "guard.lock")
    try:
        # "a+", nie "w": tryb "w" OBCINA plik zanim sprobuje flock, wiec kazde nieudane
        # uruchomienie kasowalo PID wlasciciela blokady - czyli jedyna diagnostyke
        # "kto ja trzyma". Zapis dopiero po zdobyciu blokady.
        f = open(sciezka, "a+")
    except OSError as e:
        # katalog zamiast pliku, brak prawa zapisu - bez tego demon padal tracebackiem
        # przy starcie, a launchd restartowal go w petli
        log("nie moge otworzyc %s (%s) - demon startuje BEZ wylacznosci" % (sciezka, e))
        return False
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    try:
        f.seek(0)
        f.truncate()
        f.write("%d\n" % os.getpid())
        f.flush()
    except OSError:
        pass
    return f


def main():
    ensure_dirs()
    # Wylacznosc obowiazuje TYLKO demona. `--once` i `status` to jednorazowe odczyty:
    # maja dzialac zawsze, takze gdy demon chodzi (tak sprawdza je czlowiek i testy).
    jednorazowo = ("--once" in sys.argv) or ("status" in sys.argv)
    _blokada = None if jednorazowo else zajmij_wylacznosc()
    # False = nie dalo sie otworzyc pliku blokady (katalog, brak praw). Startujemy mimo to:
    # brak wylacznosci jest zly, ale brak OCHRONY jest gorszy. None = ktos ja trzyma.
    if not jednorazowo and _blokada is None:
        print(T("another coffee-paladin daemon is already running - this one exits"),
              file=sys.stderr)
        return 1
    cfg = load_cfg()
    st = load_state()

    # `coffee-paladin status` bylo pulapka: konczylo sie kodem 0 bez slowa, co wyglada
    # na sukces. Teraz jest aliasem --once, a kazdy nieznany argument mowi, co umiemy (B6).
    znane = {"--once", "status"}
    obce = [a for a in sys.argv[1:] if a not in znane]
    if obce:
        print(T("unknown argument: %s") % " ".join(obce), file=sys.stderr)
        print(T("usage: coffee-paladin [--once | status]   (no arguments = run the daemon)"),
              file=sys.stderr)
        return 2

    if "--once" in sys.argv or "status" in sys.argv:
        (state, temp, speed, load, targets, lvl, why,
         soc, soc_t, ac, pct, _saferun_normal, _pokaz, _demote_only) = snapshot(cfg)
        fans = ",".join(str(x) for x in (soc.get("fans") if soc else [])) or "n/d"
        print(T("state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)") % (
            state, ("%.1f C" % soc_t) if soc_t else "n/d",
            ("%.1f C" % temp) if temp else "n/d", fans,
            (T("AC") if ac else T("battery %s%%") % (pct if pct is not None else "?")),
            speed, load, lvl, why or T("calm")))
        for pid, cpu, comm, _ in targets[:5]:
            print(T("  candidate: %-20s pid=%-7d %.0f%% CPU") % (comm, pid, cpu))
        return 0

    # Sprzatanie po poprzednim demonie robi WYLACZNIE demon. Kiedys ten blok stal
    # przed obsluga --once/status, wiec `coffee-paladin status` odmrazal wszystko,
    # co pauzowal DZIALAJACY demon, i czyscil mu state.json - a demon dalej myslal,
    # ze trzyma te procesy zamrozone (znalezione w bramce jakosci 02.08.2026).
    if st["paused"]:
        try:
            stan_mtime = os.path.getmtime(STATE_PATH)
        except Exception:
            stan_mtime = 0
        if stan_mtime >= boot_time():
            # ZANIM cokolwiek wznowimy - pomiar. Restart demona (aktualizacja, kickstart)
            # zdarza sie takze na goracej maszynie: wznowienie "na slepo" dawalo goracemu
            # zadaniu ~15 s pelnej pary przy chipie nad progiem, zanim pierwszy cykl petli
            # zdazyl je z powrotem zamrozic (runda 3 Codeksa, 05.08.2026). Ta sama bramka,
            # ktorej uzywa petla - nie kopia warunku.
            if bramka_wznowienia(cfg, st, battery_temp_c(), soc_temp_c(), thermal_state()):
                do_resume(cfg, st, T("guard startup - nothing is left frozen"))
            else:
                log("startup: machine still hot - %d paused entr(ies) stay frozen, "
                    "the loop will resume them after cooling" % len(st["paused"]))
        else:
            # stan sprzed rebootu: PID-y moga nalezec do zupelnie obcych procesow
            log("stale state from before boot - dropping %d paused entries without signaling"
                % len(st["paused"]))
            st["paused"] = {}
        save_state(st)

    stop = {"flag": False}

    def on_signal(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    # czarna skrzynka: czy poprzednia sesja skonczyla sie twardym zgasnieciem?
    pad = wykryj_twardy_pad()
    if pad:
        st["_ostatni_pad"] = pad
        notify(cfg, T("Mac shut down without warning"),
               T("Evidence from the moment of the crash was saved - menu bar > Export report"), key="pad")
    st["reczna_pauza"] = False
    # Nowa sesja demona = nowe liczniki sesji. Suma calkowita ("stats") zostaje nietknieta.
    st["stats_sesja"] = {"since": now()}
    try:
        if os.path.exists(CLEAN_STOP_PATH):
            os.remove(CLEAN_STOP_PATH)
    except Exception:
        pass

    # sprzet + kalibracja per Mac: raz przy starcie (system_profiler jest wolny)
    hw = {}
    kalibracja_odlozona = False   # musi istniec takze gdy kalibracja rzuci wyjatkiem
    try:
        hw = hardware_info()
        wynik_kalibracji = auto_calibrate(cfg, hw)
        # Czujnik potrafi wstac PO starcie demona (macmon zajety kompilacja paska
        # przy `install.sh`). Kalibracja idzie raz przy starcie, wiec bez tego Mac
        # bezwentylatorowy czekalby na swoje progi do nastepnego restartu demona,
        # a demon ma KeepAlive. Petla dokonczy robote, gdy czujnik wroci.
        kalibracja_odlozona = not hw.get("chip_sensor")
        cfg = load_cfg()          # kalibracja mogla dopisac progi
        if wynik_kalibracji == "watchonly" and cfg.get("dry_run"):
            notify(cfg, T("coffee-paladin: watch-only mode"),
                   T("Measuring and alerting only - nothing is paused. Enable protection in the menu bar (one click)."),
                   key="dryinfo")
    except Exception as e:
        log("CALIBRATION skipped: %r" % (e,))

    czujnik_chipa = T("yes") if soc_temp_c() is not None else T("NO (macmon missing - running on battery temperature only)")
    log(T("coffee-paladin start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s)"
          " | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery")
        % (cfg.get("soc_pause_c", 92), cfg.get("soc_resume_c", 80), cfg.get("soc_kill_c", 100),
           czujnik_chipa, cfg["batt_pause_c"], cfg["batt_kill_c"],
           cfg["pause_on_thermal_state"], cfg.get("batt_pct_pause", 10)))

    # Brak czujnika chipa to nie drobiazg: zostaje sama bateria, ktora reaguje
    # z kilkuminutowym opoznieniem. Dotad jedynym sladem byla jedna linia w logu,
    # ktorej nikt nie czyta - a `heat` i `fleet` dalej meldowaly, ze wszystko gra.
    _bez_czujnika = soc_temp_c() is None
    if _bez_czujnika:
        notify(cfg, T("Thermal guard: PROTECTION INCOMPLETE"),
               T("No chip temperature sensor (macmon missing). Only battery temperature "
                 "is watched, and it reacts minutes late. Fix: brew install macmon"),
               key="nosensor")

    crit_polls = 0
    cpu_hist = {}
    tick = 0

    obserwowane_cfg = None
    while not stop["flag"]:
        try:
            cfg = load_cfg()
            # kazda zmiana progow/zachowania zostawia slad stara -> nowa (B5);
            # pierwszy przebieg tylko zapamietuje stan, bez logowania
            obserwowane_cfg = loguj_zmiany_configu(obserwowane_cfg, cfg)
            reap_bg()
            (state, temp, speed, load, targets, lvl, why,
             soc, soc_t, ac, pct, saferun_normal, do_pokazania, demote_only) = snapshot(cfg)
            # Czujnik wrocil juz po starcie? Dokoncz odlozona kalibracje. Bez tego
            # Mac bezwentylatorowy siedzi na progach wentylatorowych do restartu demona.
            # Odczyt bierzemy z migawki (`soc`), zeby nie placic drugi raz za macmona;
            # reszta `hw` jest z systemu i sie nie zmienia miedzy taktami.
            if kalibracja_odlozona and soc:
                hw["fan_count"] = len(soc.get("fans") or [])
                hw["chip_sensor"] = True
                auto_calibrate(cfg, hw)
                cfg = load_cfg()
                kalibracja_odlozona = False

            fan_alarm(cfg, soc, soc_t, st)
            obsluz_rozkaz(cfg, st, targets)

            # dane pomocnicze dla paska (trend, zadania, licznik dnia)
            st["_trend_c_min"], st["_eta_min"] = trend_i_prognoza(cfg, soc_t)
            st["_dry"] = bool(cfg.get("dry_run"))
            st["_awake"] = keep_awake_update(cfg, targets, lvl, st)
            st["_prog_pauza"] = cfg.get("soc_pause_c")
            st["_prog_ubicie"] = cfg.get("soc_kill_c")
            if tick % 4 == 0:                      # rzadziej — to czytanie z dysku
                st["_zadania"] = zadania_saferun()
                st["_stat"] = statystyki_dnia()
                st["_top_cpu"], st["_top_ram"] = top_lists()
            # dysk zmienia sie wolno — odczyt raz na ~5 min wystarcza
            if tick % 20 == 0 or not st.get("_disk"):
                st["_disk"] = disk_usage()
            snap_dict = status_write(state, temp, soc, soc_t, ac, pct, speed, load, lvl, why,
                                     targets, st, st.get("_disk"), pokaz=do_pokazania)
            if tick % 4 == 0 and snap_dict:      # flota co ~1 min wystarczy
                fleet_write(cfg, snap_dict)

            # puls czarnej skrzynki — po twardym padzie zostanie tu ostatni znak zycia
            try:
                with open(HEARTBEAT_PATH, "w") as f:
                    # epoch przodem: strefa czasowa i DST wypadaja z rownania przy odczycie;
                    # tekst po spacji zostaje dla czlowieka (znalezisko Neo, 30.07)
                    f.write("%d %s" % (now(), ts()))
            except Exception:
                pass

            top = targets[0] if targets else None
            if tick % max(1, int(300 / cfg["poll_seconds"])) == 0 or lvl >= 2:
                fans = soc.get("fans") if soc else []
                hist_write([ts(), state,
                            "%.1f" % soc_t if soc_t else "",
                            "%.1f" % soc["gpu"] if soc and soc.get("gpu") else "",
                            "%.1f" % temp if temp else "",
                            max(fans) if fans else "",
                            "%.1f" % soc["watts"] if soc else "",
                            pct if pct is not None else "", 1 if ac else 0,
                            speed, "%.2f" % load, lvl,
                            top[2] if top else "", "%.0f" % top[1] if top else ""])

            # PONOWNY SIGSTOP dla wszystkiego, co uznajemy za wstrzymane. Powod: miedzy
            # zamrozeniem a zapisem state.json jest okno, w ktorym duty-limiter safe-run
            # (albo reczny kill -CONT) moze obudzic zadanie — a my dalej mielibysmy je
            # w pamieci jako "paused" i nigdy nie zamrozili ponownie. STOP na juz
            # zatrzymanym procesie nic nie kosztuje i nic nie psuje.
            if lvl >= 2 and not cfg["dry_run"]:
                for key, info in st["paused"].items():
                    pid = int(key)
                    if alive(pid):
                        sig(pid, info.get("pgid"), signal.SIGSTOP)

            # POTWIERDZENIE STANU SYSTEMOWEGO. Gdy jedynym powodem poziomu >=2 jest
            # `thermalState` (a prog chipu NIE jest przekroczony), wymagamy kilku
            # odczytow z rzedu. To druga polowa leku na migotanie z 10:46: minimalny
            # czas pauzy rozrzedzal oscylacje, ale to dopiero potwierdzanie wejscia
            # daje realna histereze na tym wyzwalaczu.
            prog_chipu = cfg.get("soc_pause_c", 95.0)
            sam_stan = (lvl >= 2 and (soc_t is None or soc_t < prog_chipu)
                        and (temp is None or temp < cfg["batt_pause_c"]))
            st["_state_polls"] = (st.get("_state_polls", 0) + 1) if sam_stan else 0
            if sam_stan and st["_state_polls"] < cfg.get("state_confirm_polls", 2):
                lvl = 1        # jeszcze nie ufamy pojedynczemu skokowi thermalState

            # ZATRZASK PER CZUJNIK. Czujnik moze BLOKOWAC wznowienie tylko wtedy, gdy sam
            # przekroczyl swoj prog pauzy i jeszcze nie zszedl do swojego progu wznowienia.
            # Wczesniej bramka byla nesymetryczna: pauze wywolywal DOWOLNY czujnik, ale
            # wznowienie blokowal KAZDY. Bateria stygnie kilka minut i przy dlugim kodowaniu
            # trzyma ~37 C, wiec przy progach chipa 95/87 pauza WYWOLANA CHIPEM nie konczyla
            # sie nigdy: chip schodzil do 71 C w 20 s, a bateria - trzy stopnie ponizej
            # WLASNEGO progu 40 C, ktorego nigdy nie przekroczyla - trzymala zadanie w stanie T
            # az do SIGTERM-a po 45 minutach. Log Pawla 04.08.2026: 15 pauz, ZERO wznowien,
            # dwa ubite zadania. Histereza czujnika ma chronic przed migotaniem JEGO progu,
            # a nie brac zakladnikow za cudzy prog.
            # Migawka realnie zatrzymanych procesow - JEDEN `ps` na cykl i tylko wtedy,
            # gdy w ogole cos mamy zamrozone. Uzywaja jej obie sciezki, ktore podejmuja
            # decyzje o cudzym zyciu: kasowanie nieaktualnych wpisow i SIGTERM po limicie.
            stoja = zatrzymane_teraz() if st["paused"] else (set(), set())
            if stoja is None and not st.get("_ps_cicho"):
                log("ps unavailable - postponing decisions about paused jobs")
            st["_ps_cicho"] = stoja is None

            # Zatrzaski aktualizowane w KAZDYM cyklu, takze gdy goraco - inaczej bateria,
            # ktora przekroczyla 40 C w trakcie pauzy, nie zapalilaby zatrzasku wcale.
            wolno_wznowic = bramka_wznowienia(cfg, st, temp, soc_t, state)

            if lvl >= 3:
                crit_polls += 1
                banner(cfg, T("Thermal guard: CRITICAL overheating"),
                       (T("The Mac is critically hot (%s). Watch-only mode - nothing is being stopped.")
                        if cfg.get("dry_run") else
                        T("The Mac is critically hot (%s). Heavy jobs are being stopped.")) % why)
                do_pause(cfg, st, targets, T("CRITICAL: ") + why, lvl_krytyczny=True)
                if crit_polls >= cfg["kill_after_polls"]:
                    do_terminate(cfg, st, why)
                    crit_polls = 0
            elif lvl == 2:
                crit_polls = 0
                do_pause(cfg, st, targets, why)
            else:
                crit_polls = 0
                cool = wolno_wznowic
                # po pauzie z powodu baterii wznawiamy dopiero na zasilaczu (albo po doladowaniu)
                powered = ac or pct is None or pct >= cfg.get("batt_pct_resume", 25)
                # MARTWE WPISY sprzatamy TU, niezaleznie od do_resume. Wczesniej jedynym
                # miejscem, ktore je usuwalo, bylo do_resume - a to ono jest zablokowane
                # flaga recznej pauzy. Powstawal stan absorbujacy: Pawel mrozi cos recznie,
                # ubija to z terminala, wpis zostaje na zawsze, `reczna_pauza` zostaje
                # na zawsze, i od tej chwili guard PAUZUJE, ale NIGDY nie wznawia -
                # kazde kolejne zadanie dostaje SIGTERM po limicie czasu.
                for _k in [k for k in list(st["paused"]) if not alive(int(k))]:
                    del st["paused"][_k]
                # WPISY OBUDZONE POZA GUARDEM. Maszyna jest chlodna, wiec ten proces i tak
                # ma prawo pracowac - a skoro juz pracuje (czlowiek dal `kill -CONT`, albo
                # obudzil go duty-limiter safe-run), to wpis jest tylko wyrokiem z odroczeniem:
                # zegar pauzy tyka dalej i po `max_pause_minutes` leci SIGTERM w zadanie
                # chodzace pelna para. Dokladnie tak zginal pomiar Pawla 04.08.2026 o 20:27,
                # 25 minut po recznym wznowieniu. Wpis kasujemy i mowimy o tym w logu.
                for _k in wpisy_nieaktualne(st["paused"], stoja):
                    log(T("dropping stale pause entry: %s (pid %s) is running again "
                          "- resumed outside the guard")
                        % (st["paused"][_k].get("comm", "?"), _k))
                    del st["paused"][_k]
                # flaga liczona z danych, a nie trzymana osobno - nie da sie rozjechac
                st["reczna_pauza"] = any(v.get("manual") for v in st["paused"].values())

                # MINIMALNY CZAS PAUZY. Bez tego wyzwalacz stanu systemowego (ktory
                # histerezy nie ma) daje oscylacje: pauza -> 15 s -> "warunki wrocily
                # do normy" -> pauza, w kolko, przy chipie dziesiec stopni ponizej
                # progu. Zadanie skacze, a nic sie nie chlodzi.
                min_p = max(0, cfg.get("min_pause_seconds", 60))
                # PER WPIS, nie wszystko-albo-nic: wczesniej brano najmlodsza pauze
                # z calej paczki, wiec swiezo zamrozony proces przytrzymywal ffmpeg
                # stojacy od godziny. Przy migotaniu stanu nowe kandydatury pojawiaja
                # sie cyklicznie i najstarsza pauza mogla czekac az do SIGTERM-a.
                # Reczne zamrozenie z paska ma pierwszenstwo - tych nie ruszamy.
                gotowe = [k for k, v in st["paused"].items()
                          if _wiek_pauzy(v) >= min_p and not v.get("manual")
                          and (powered or v.get("powod") != "bateria")]
                if gotowe and cool:
                    do_resume(cfg, st, T("conditions are back to normal"), only_keys=gotowe,
                              po_ostygnieciu=True)
                do_promote(cfg, st, cpu_hist, soc_t)
                # systemowe demony indeksowania dokladane TYLKO tutaj: degradacja tak,
                # pauza/ubicie nigdy (wariant A, patrz system_demote_patterns)
                do_demote(cfg, st, targets + demote_only, cpu_hist, soc_t, saferun_normal)

            # Nic nie moze wisiec w pauzie w nieskonczonosc — ALE czekanie na zasilacz
            # to nie awaria. Gdy chip i bateria sa chlodne, a jedynym powodem pauzy jest
            # niski poziom baterii, dajemy duzo wiecej czasu: obliczenie ma spokojnie
            # doczekac do momentu, az uzytkownik podepnie kabel, zamiast zginac po 45 minutach.
            tylko_bateria = (not ac and lvl >= 2
                             and (soc_t is None or soc_t < cfg.get("soc_pause_c", 88) - 10)
                             and (temp is None or temp < cfg["batt_pause_c"] - 3))
            limit_min = cfg.get("max_pause_minutes_batt", 240) if tylko_bateria else cfg["max_pause_minutes"]
            # Ile ta pauza trwa NAPRAWDE. Zegar scienny potrafi skoczyc (NTP, korekta
            # RTC, powrot z uspienia): skok o 3 h ubijal SIGTERM-em zadanie zapauzowane
            # minute wczesniej, a cofniecie zegara wylaczalo limit na dobre. monotonic()
            # nie przezywa restartu demona: nowy proces zaczyna liczyc od nowa (a pod
            # Apple'owym pythonem dokladnie od zera), wiec pomiar starego demona wyszedlby
            # ujemny i limit pauzy nigdy by nie zadzialal - zadanie zamrozone przed
            # restartem zostaloby w stanie T na zawsze. Dlatego wpis niesie znacznik
            # procesu, a cudzy pomiar wraca na zegar scienny, ktory jako jedyny znaczy
            # to samo po obu stronach restartu.
            # ...i ubijamy WYLACZNIE to, co naprawde stoi. Wpis to notatka guarda, nie stan
            # systemu: proces obudzony recznie albo przez limiter safe-run pracuje pelna para,
            # a jego wpis dalej postarzal sie w tle. SIGTERM po 45 minutach dostawalo wtedy
            # zdrowe zadanie w polowie roboty (Pawel, 04.08.2026, 20:27 - pomiar wznowiony
            # recznie o 20:02). Zegar liczy od PIERWSZEGO zatrzymania i tak ma byc:
            # od kary ratuje dowod, ze proces chodzi, a nie przewijanie stopera.
            przeterminowane = wpisy_przeterminowane(st["paused"], limit_min * 60, stoja)
            if przeterminowane:
                for k in przeterminowane:
                    log(T("PAUSE >%d min - terminating job %s (pid %s)")
                        % (limit_min, st["paused"][k].get("comm"), k), tag="KILL")
                do_terminate(cfg, st, T("paused for longer than %d min") % limit_min,
                             only_keys=przeterminowane)

            for _p in [p for p in _nie_da_sie if not alive(p)]:
                del _nie_da_sie[_p]
            _demote_nie_da_sie.difference_update(
                p for p in list(_demote_nie_da_sie) if not alive(p))
            # Lista dla paska i dla agentow odswiezana TU, nie tylko przy nowej pauzie.
            # Wczesniej `unpausable` niosl nazwe dawno martwego procesu az do nastepnej
            # proby pauzy, wiec agent AI w kolko meldowal niepelna ochrone.
            st["_unpausable"] = sorted(set(_nie_da_sie.values()))
            # Zegar degradacji przezywa pauzy: wpis znika dopiero ze SMIERCIA procesu,
            # nie z wypadnieciem z targets (SIGSTOP zeruje pcpu w <5 s i przy starym
            # przycinaniu najgoretszy job mial zegar kasowany co pauze - patrz B3).
            live = set(p[0] for p in targets)
            cpu_hist = dict((k, v) for k, v in cpu_hist.items()
                            if k in live or alive(k))
            st["demoted"] = [p for p in st["demoted"] if alive(p)]
            zywe_demoted = set(str(p) for p in st["demoted"])
            st["demoted_info"] = {k: v for k, v in st.get("demoted_info", {}).items()
                                  if k in zywe_demoted}
            save_state(st)
        except Exception as e:
            log(T("LOOP ERROR: %r") % (e,))
        tick += 1
        # drzemka przerywalna: rozkaz z paska (command) albo zmiana keep-awake
        # (awake.json) budzi petle NATYCHMIAST - reczne akcje reaguja w ~1 s,
        # a pelny cykl pomiarowy dalej chodzi rzadko. Koszt: dwa stat() co 0.5 s.
        def _mtime(p):
            try:
                return os.path.getmtime(p)
            except OSError:
                return None

        awake_przed = _mtime(AWAKE_PATH)
        # Zmiana configu TEZ budzi petle. Bez tego przelacznik ochrony z paska czekal
        # caly takt: `dry_run` idzie przez config.json, a nie przez plik `command`,
        # wiec jako jedyna reczna akcja nie mial sciezki na wybudzenie. Przy suwaku
        # interwalu na 30 s wygladalo to jak zawieszony przelacznik (Pawel, 03.08).
        cfg_przed = _mtime(CFG_PATH)
        for _ in range(int(cfg["poll_seconds"] * 2)):
            if stop["flag"]:
                break
            if os.path.exists(COMMAND_PATH):
                break
            if _mtime(AWAKE_PATH) != awake_przed:
                break
            if _mtime(CFG_PATH) != cfg_przed:
                break
            time.sleep(0.5)

    do_resume(cfg, st, T("guard is shutting down"))
    # Degradacja na rdzenie ekonomiczne przezywala zamkniecie demona: proces zostawal
    # przypiety do E-cores do konca zycia, niewidocznie, bo w temperaturze tego nie
    # widac - tylko w tempie pracy. Zdejmujemy ja tak samo jak pauze.
    for _pid in list(st.get("demoted_info") or {}):
        try:
            run(["taskpolicy", "-B", "-p", str(_pid)], timeout=5)
        except Exception:
            pass
    # `caffeinate -is` jest DZIECKIEM demona, ale przezywa go: po smierci straznika
    # przejmuje go launchd i Mac nigdy nie zasypia, bez zadnego sladu w interfejsie.
    try:
        _c = _caff.get("proc")
        if _c is not None and _c.poll() is None:
            _c.terminate()
            try:
                _c.communicate(timeout=3)
            except Exception:
                _c.kill()
    except Exception:
        pass
    save_state(st)
    # znacznik czystego zamkniecia — bez niego nastepny start uzna to za twardy pad
    try:
        with open(CLEAN_STOP_PATH, "w") as f:
            f.write(ts())
    except Exception:
        pass
    log("coffee-paladin stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
