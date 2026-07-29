#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
thermal-guard - watches temperature and load on a Mac, without sudo.

Every N seconds it reads:
  * macOS thermal pressure (thermalstate: nominal/fair/serious/critical)
  * chip and GPU temperature, fan rpm and power draw (macmon -> IOReport)
  * battery temperature (ioreg AppleSmartBattery)
  * CPU throttling (pmset -g therm -> CPU_Speed_Limit)
  * load average and processes, with CPU rolled up across each process subtree (ps)

When it gets hot: SIGSTOP on heavy jobs. When it cools down: SIGCONT. In a critical state:
SIGCONT + SIGTERM so jobs can checkpoint, then SIGKILL after a grace period. The system,
Finder and interactive shells are never touched.

Measurement history: ~/.thermal-guard/history.csv   (evidence for "what happened at 3 a.m.")
Events:              ~/.thermal-guard/events.log    (hard shutdowns, cooling alarms)
Log:                 ~/.thermal-guard/guard.log
State (pauses):      ~/.thermal-guard/state.json    (restored on start -> nothing stays frozen)
Snapshot for the menu bar: ~/.thermal-guard/status.json

Usage:
  guard.py            # the loop (this is how the LaunchAgent starts it)
  guard.py --once     # a single pass, prints the reading (for testing)

Language of messages: TG_LANG=en|pl, or "lang" in config.json. Default: en.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, ".thermal-guard")
CFG_PATH = os.path.join(BASE, "config.json")
STATE_PATH = os.path.join(BASE, "state.json")
LOG_PATH = os.path.join(BASE, "guard.log")
HIST_PATH = os.path.join(BASE, "history.csv")
STATUS_PATH = os.path.join(BASE, "status.json")   # migawka dla paska menu
HEARTBEAT_PATH = os.path.join(BASE, "heartbeat")  # zywy puls — po twardym padzie zostaje ostatni
CLEAN_STOP_PATH = os.path.join(BASE, "clean_stop")
EVENTS_PATH = os.path.join(BASE, "events.log")    # czarna skrzynka: pady, alarmy
COMMAND_PATH = os.path.join(BASE, "command")      # rozkazy z paska menu
MANAGED_DIR = os.path.join(BASE, "managed")   # pliki <pid>.json od safe-run
MAX_LOG_BYTES = 5 * 1024 * 1024

LEVELS = {"nominal": 0, "fair": 1, "serious": 2, "critical": 3, "unknown": 1}

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
    "manage_unknown_heavy": True,
    "unknown_cpu_percent": 50.0,
    "unknown_min_seconds": 120,
    # czekanie na zasilacz to nie awaria — pauza z powodu baterii moze trwac duzo dluzej
    "max_pause_minutes_batt": 240,
    "fan_check": True,
    "fan_alert_temp_c": 70.0,   # powyzej tej temperatury chipa wentylatory MUSZA sie krecic
    "cpu_min_percent": 20.0,    # tylko procesy powyzej tego zuzycia sa ruszane
    "max_pause_minutes": 45,    # dluzej niz to w pauzie -> lagodne ubicie (jest checkpoint)
    "kill_after_polls": 4,      # tyle kolejnych odczytow krytycznych -> SIGTERM
    "demote_after_minutes": 5,  # ciezki proces dluzej niz to -> background QoS (E-cores) + nice
    "demote_cpu_percent": 60.0,
    "notify": True,
    "notify_min_gap_s": 300,
    # dzwieki systemowe przy zdarzeniach (afplay — dziala nawet gdy powiadomienia sa
    # wyciszone przez Skupienie). Rozne zdarzenia maja rozne dzwieki, zeby dalo sie
    # rozpoznac bez patrzenia: pauza=nisko, wznowienie=szklo, ubicie/pad=powaznie.
    "sound": True,
    # NIE USYPIAJ, GDY LICZY — jak Caffeine/Amphetamine, ale z bezpiecznikiem: czuwanie
    # trzymamy TYLKO gdy realnie dziala ciezkie zadanie i jest chlodno; przy pauzie/goracu
    # blokade zwalniamy (sen chlodzi najszybciej), po zakonczeniu zadania Mac normalnie
    # zasypia. Amphetamine trzymane bezwarunkowo to klasyczna droga do ugotowania laptopa
    # w plecaku — dlatego domyslnie wylaczone, wlacza sie swiadomie w Ustawieniach.
    "keep_awake_auto": False,
    # DOMYSLNIE TYLKO OBSERWACJA: swieza instalacja mierzy, loguje i ALARMUJE, ale nie
    # wstrzymuje niczyich procesow. Ochrone wlacza sie swiadomie — jednym kliknieciem w menu
    # paska albo "dry_run": false. Narzedzie, ktore od wejscia rusza cudza prace, traci
    # zaufanie przy pierwszym falszywym alarmie; narzedzie, ktore najpierw pokazuje, CO by
    # zrobilo, zdobywa je.
    "dry_run": True,
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
    # i sama nazwa procesu nic nie mowi
    "never_arg_patterns": ["thermal-guard", "thermal_guard", "guard.py", "safe-run"],
    # czego NIE wolno ruszac nigdy (nadrzedne wobec powyzszego)
    "never_patterns": [
        "kernel_task", "windowserver", "launchd", "loginwindow", "logd", "opendirectoryd",
        "backupd", "mds", "mdworker", "spotlight", "fileproviderd", "cloudd", "bird",
        "finder", "dock", "terminal", "ghostty", "iterm", "zsh", "bash", "sshd", "ssh",
        "guard.py", "thermal-guard", "safe-run", "code helper", "electron",
        # demony systemowe: potrafia dlugo zjadac rdzen, ale odrzucaja SIGSTOP albo psuja
        # sie po zamrozeniu — probowanie ich tylko zasmieca log i blokuje prawdziwe cele
        "duetexpertd", "suggestd", "photoanalysisd", "mediaanalysisd", "coreaudiod",
        "bluetoothd", "powerd", "syspolicyd", "xprotect", "trustd", "nsurlsessiond",
    ],
}


# ---------------------------------------------------------------- narzedzia

def now():
    return time.time()


def ts(t=None):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t if t else now()))


def ensure_dirs():
    for d in (BASE, MANAGED_DIR):
        if not os.path.isdir(d):
            os.makedirs(d, 0o755)


def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH) as f:
            user = json.load(f)
        if isinstance(user, dict):
            cfg.update(user)
    except Exception:
        pass
    return cfg


# ---------------------------------------------------------------- jezyk

def _lang():
    """Jezyk komunikatow: TG_LANG, potem "lang" w config.json, domyslnie angielski."""
    v = (os.environ.get("TG_LANG") or "").lower()[:2]
    if v in ("pl", "en"):
        return v
    try:
        with open(CFG_PATH) as f:
            v = (json.load(f).get("lang") or "").lower()[:2]
        if v in ("pl", "en"):
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
    "[DRY-RUN] would terminate %s (pid %d) - %s": "[DRY-RUN] ubicie %s (pid %d) - %s",
    "TERMINATED (SIGTERM) %s (pid %d) - %s": "STOP (SIGTERM) %s (pid %d) - %s",
    "SIGKILL %s (pid %d)": "SIGKILL %s (pid %d)",
    "[DRY-RUN] would demote %s (pid %d)": "[DRY-RUN] demote %s (pid %d)",
    "DEMOTED %s (pid %d) -> background QoS/E-cores + nice+10 (hot for >%d min)":
        "DEMOTE %s (pid %d) -> tlo/E-cores + nice+10 (mieli >%d min)",
    "Thermal guard: hot": "Thermal guard: goraco",
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
    "thermal-guard start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s)"
    " | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery":
        "thermal-guard start | chip: pauza>=%.0fC wznow<=%.0fC ubicie>=%.0fC (czujnik: %s)"
        " | bateria: pauza>=%.0fC ubicie>=%.0fC | stan>=%s | bramka baterii: <=%d%% bez zasilacza",
    "state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)":
        "stan=%s chip=%s bateria=%s wentylatory=%s zasilanie=%s CPU_limit=%d%% load1=%.2f poziom=%d (%s)",
    "  candidate: %-20s pid=%-7d %.0f%% CPU": "  kandydat: %-20s pid=%-7d %.0f%% CPU",
    "AC": "AC",
    "battery %s%%": "bateria %s%%",
    "calm": "spokoj",
}


def T(s):
    """Tlumaczy komunikat na polski, gdy LANG == pl. Angielski jest zrodlem prawdy."""
    return PL.get(s, s) if LANG == "pl" else s

def rotate(path):
    try:
        if os.path.getsize(path) > MAX_LOG_BYTES:
            os.replace(path, path + ".1")
    except Exception:
        pass


def log(msg):
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


def run(cmd, timeout=10):
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        out, _ = p.communicate(timeout=timeout)
        return out.decode("utf-8", "replace")
    except Exception:
        return ""


_last_notify = {}


SOUNDS = {
    "pause": "Basso",      # goraco — niski, powazny
    "resume": "Glass",     # ochlodzone — lekki
    "kill": "Sosumi",      # ubicie zadania
    "fan": "Basso",        # awaria chlodzenia
    "pad": "Basso",        # wykryty twardy pad
    "freeze": "Tink",      # reczne akcje z paska
}


def play_sound(cfg, key):
    if not cfg.get("sound", True):
        return
    name = SOUNDS.get(key, "Ping")
    path = "/System/Library/Sounds/%s.aiff" % name
    if os.path.exists(path):
        subprocess.Popen(["afplay", path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    subprocess.Popen(["osascript", "-e", script],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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


_soc_cache = {"t": 0.0, "val": None}


def soc_sensors(max_age=10.0):
    """Temperatura chipa, wentylatory i pobor mocy przez `macmon` (IOReport, bez sudo).

    Zwraca dict: {"cpu": C, "gpu": C, "fans": [rpm], "watts": W} albo None gdy macmon
    niedostepny. Wynik jest cache'owany, bo jedno probkowanie kosztuje ~1 s — a petla
    guarda chodzi co 15 s i pyta o to w kilku miejscach.

    UWAGA: na macOS 26 sensory przez IOHIDEventSystem sa juz zablokowane dla procesow
    bez uprawnien (dlatego wlasny czujnik Swift zwracal zero) — IOReport nadal dziala.
    """
    if time.time() - _soc_cache["t"] < max_age:
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
    _soc_cache["t"] = time.time()
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


def full_args(pid):
    out = run(["ps", "-o", "args=", "-p", str(pid)])
    return out.strip()


# ---------------------------------------------------------------- wybor procesow

def managed_pids_from_saferun():
    """PID-y zarejestrowane przez safe-run: {pid: pgid}."""
    res = {}
    try:
        for name in os.listdir(MANAGED_DIR):
            if not name.endswith(".json"):
                continue
            path = os.path.join(MANAGED_DIR, name)
            try:
                with open(path) as f:
                    d = json.load(f)
                pid = int(d["pid"])
                if alive(pid):
                    res[pid] = int(d.get("pgid", pid))
                else:
                    os.unlink(path)
            except Exception:
                try:
                    os.unlink(path)
                except Exception:
                    pass
    except Exception:
        pass
    return res


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        import errno
        return e.errno == errno.EPERM


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


def pick_targets(cfg, procs, saferun):
    """Procesy ktore wolno pauzowac, posortowane po CPU malejaco."""
    me = os.getpid()
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
            out.append((pid, cpu, comm, saferun[pid]))
            continue
        if any(n in low for n in never):
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
        args = full_args(pid).lower()
        if any(n.lower() in args for n in (cfg.get("never_arg_patterns") or [])):
            continue
        out.append((pid, cpu, comm, None))
    out.sort(key=lambda x: -x[1])
    return out


# ---------------------------------------------------------------- akcje

def load_state():
    try:
        with open(STATE_PATH) as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("paused", {})
            d.setdefault("demoted", [])
            return d
    except Exception:
        pass
    return {"paused": {}, "demoted": []}


def save_state(st):
    tmp = STATE_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(st, f, indent=1)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass


def sig(pid, pgid, s):
    """Wysyla sygnal do grupy procesow (gdy znana) albo do pojedynczego pid."""
    try:
        if pgid:
            os.killpg(pgid, s)
        else:
            os.kill(pid, s)
        return True
    except Exception:
        return False


def do_pause(cfg, st, targets, reason):
    changed = False
    for pid, cpu, comm, pgid in targets:
        key = str(pid)
        if key in st["paused"]:
            continue
        if cfg["dry_run"]:
            log(T("[DRY-RUN] would pause %s (pid %d, %.0f%% CPU) - %s") % (comm, pid, cpu, reason))
            notify(cfg, T("Thermal guard (watch-only): hot"),
                   T("Would pause %s - %s. Protection is off.") % (comm, reason), "pause")
            continue
        if sig(pid, pgid, signal.SIGSTOP):
            st["paused"][key] = {"since": now(), "comm": comm, "pgid": pgid, "cpu": cpu}
            changed = True
            log(T("PAUSED %s (pid %d, %.0f%% CPU) - %s") % (comm, pid, cpu, reason))
        else:
            # Cicha porazka byla grozna: pasek pokazywal "zamrozone", a proces biegl dalej.
            # Zwykle to demon systemowy, ktory odrzuca SIGSTOP — dopisujemy go do pominietych.
            log(T("FAILED to pause %s (pid %d) - not permitted to send the signal") % (comm, pid))
    if changed:
        names = ", ".join(sorted(set(v["comm"] for v in st["paused"].values())))
        notify(cfg, T("Thermal guard: hot"), T("Paused: %s (%s)") % (names, reason), "pause")
    return changed


def do_resume(cfg, st, reason):
    if not st["paused"]:
        return False
    for key, info in list(st["paused"].items()):
        pid = int(key)
        if alive(pid):
            sig(pid, info.get("pgid"), signal.SIGCONT)
            log(T("RESUMED %s (pid %d) - %s") % (info.get("comm", "?"), pid, reason))
        del st["paused"][key]
    notify(cfg, T("Thermal guard: cooled down"), T("Resumed paused jobs (%s)") % reason, "resume")
    return True


def do_terminate(cfg, st, reason):
    """SIGCONT + SIGTERM (proces w SIGSTOP nie obsluzy TERM), po 20 s SIGKILL."""
    victims = []
    for key, info in list(st["paused"].items()):
        pid = int(key)
        if not alive(pid):
            del st["paused"][key]
            continue
        if cfg["dry_run"]:
            log(T("[DRY-RUN] would terminate %s (pid %d) - %s") % (info.get("comm"), pid, reason))
            continue
        sig(pid, info.get("pgid"), signal.SIGCONT)
        sig(pid, info.get("pgid"), signal.SIGTERM)
        victims.append((pid, info))
        log(T("TERMINATED (SIGTERM) %s (pid %d) - %s") % (info.get("comm", "?"), pid, reason))
        del st["paused"][key]
    if victims:
        notify(cfg, T("Thermal guard: STOPPED"),
               T("Jobs terminated (%s). Resume from a checkpoint once the Mac has cooled down.")
               % reason, "kill")
        time.sleep(20)
        for pid, info in victims:
            if alive(pid):
                sig(pid, info.get("pgid"), signal.SIGKILL)
                log("SIGKILL %s (pid %d)" % (info.get("comm", "?"), pid))
    return bool(victims)


def do_demote(cfg, st, targets, cpu_hist):
    """Profilaktyka: dlugo mielacy proces -> background QoS (E-cores) + nice."""
    limit = cfg["demote_after_minutes"] * 60
    for pid, cpu, comm, pgid in targets:
        if cpu < cfg["demote_cpu_percent"]:
            continue
        first = cpu_hist.setdefault(pid, now())
        if now() - first < limit or pid in st["demoted"]:
            continue
        if cfg["dry_run"]:
            log(T("[DRY-RUN] would demote %s (pid %d)") % (comm, pid))
            continue
        subprocess.call(["taskpolicy", "-b", "-p", str(pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.call(["renice", "+10", "-p", str(pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st["demoted"].append(pid)
        log(T("DEMOTED %s (pid %d) -> background QoS/E-cores + nice+10 (hot for >%d min)")
            % (comm, pid, cfg["demote_after_minutes"]))


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
            lvl = max(lvl, 2); why.append("chip %.1f C" % soc)
        elif soc >= cfg.get("soc_pause_c", 92.0) - 7:
            lvl = max(lvl, 1); why.append("chip %.1f C" % soc)
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
            lvl = max(lvl, 2); why.append("bateria %.1f C" % temp)
        elif temp >= cfg["batt_pause_c"] - 3:
            lvl = max(lvl, 1); why.append("bateria %.1f C" % temp)
    if speed < cfg["speed_limit_pause"]:
        lvl = max(lvl, 2); why.append(T("CPU throttled to %d%%") % speed)
    return lvl, ", ".join(why)


def boot_time():
    """Moment ostatniego startu systemu (epoch)."""
    m = re.search(r"sec\s*=\s*(\d+)", run(["sysctl", "-n", "kern.boottime"]))
    return int(m.group(1)) if m else 0


def zapisz_zdarzenie(rodzaj, opis, kontekst=None):
    """Czarna skrzynka — zdarzenia, ktore maja przezyc restart i trafic do raportu."""
    try:
        with open(EVENTS_PATH, "a") as f:
            wpis = {"time": ts(), "type": rodzaj, "description": opis}
            if kontekst:
                wpis["context"] = kontekst
            f.write(json.dumps(wpis, ensure_ascii=False) + "\n")
    except Exception:
        pass


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
        puls = os.path.getmtime(HEARTBEAT_PATH)
        boot = boot_time()
        if not boot or puls >= boot:
            return None                       # puls z biezacej sesji — nic sie nie stalo
        czyste = os.path.getmtime(CLEAN_STOP_PATH) if os.path.exists(CLEAN_STOP_PATH) else 0
        if czyste >= puls - 60:
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
        opis = (T("Mac went down without a clean shutdown. Guard's last heartbeat: %s, "
                "system booted: %s.") % (ts(puls), ts(boot)))
        zapisz_zdarzenie("HARD_SHUTDOWN", opis, {"last_readings": ogon})
        log(T("!!! HARD SHUTDOWN DETECTED - ") + opis)
        return {"time": ts(puls), "description": opis, "readings": ogon}
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
    if rozkaz == "freeze":
        # flage stawiamy TYLKO gdy naprawde cos zamrozilismy — inaczej pasek klamie
        if targets and do_pause(cfg, st, targets, T("MANUAL FREEZE (from the menu bar)")):
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
        with open(LOG_PATH) as f:
            for line in f:
                if not line.startswith(dzis):
                    continue
                if "PAUZA " in line:
                    pauzy += 1
                elif "WZNOWIONE" in line:
                    wznowienia += 1
                elif "SIGTERM" in line or "koncze zadanie" in line:
                    ubicia += 1
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


def keep_awake_update(cfg, targets, lvl):
    """Utrzymuje/zwalnia blokade snu przez systemowy caffeinate.

    Warunek trzymania: opcja wlaczona ORAZ dziala ciezkie zadanie ORAZ poziom < 2 (chlodno).
    Kazde inne polaczenie = blokada w dol. To jest cala roznica wzgledem Caffeine:
    tam czlowiek musi pamietac o wylaczeniu, tu wylacza fizyka.
    """
    proc = _caff["proc"]
    zywy = proc is not None and proc.poll() is None
    chcemy = bool(cfg.get("keep_awake_auto")) and bool(targets) and lvl < 2
    if chcemy and not zywy:
        try:
            _caff["proc"] = subprocess.Popen(
                ["caffeinate", "-is"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log("KEEP-AWAKE start (heavy job running, machine cool)")
        except Exception:
            _caff["proc"] = None
    elif not chcemy and zywy:
        try:
            proc.terminate()
        except Exception:
            pass
        _caff["proc"] = None
        log("KEEP-AWAKE stop (job done, hot, or disabled)")
    return _caff["proc"] is not None and _caff["proc"].poll() is None


def fleet_write(cfg, status):
    """Migawka hosta do wspolnego folderu floty (jesli skonfigurowany)."""
    d = os.path.expanduser(cfg.get("fleet_dir") or "")
    if not d:
        return
    try:
        if not os.path.isdir(d):
            os.makedirs(d, 0o755)
        out = dict(status)
        out["host"] = hostname()
        out["guard_version"] = "1.4"
        tmp = os.path.join(d, ".%s.tmp" % hostname())
        with open(tmp, "w") as f:
            json.dump(out, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(d, "%s.json" % hostname()))
    except Exception:
        pass                      # flota jest dodatkiem — nie moze polozyc bezpiecznika


def status_write(state, temp, soc, soc_t, ac, pct, speed, load, lvl, why, targets, st, disk=None):
    """Migawka dla paska menu (`heatbar`). Pasek nic sam nie mierzy — czyta ten plik,
    wiec kosztuje zero CPU i zawsze pokazuje dokladnie to, co widzi guard."""
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
        "top_proc": top[2] if top else None,
        "top_cpu": round(top[1]) if top else None,
        "manual_pause": bool(st.get("reczna_pauza")),
        "dry_run": bool(st.get("_dry")),
        "keep_awake": bool(st.get("_awake")),
        "trend_c_min": st.get("_trend_c_min"),
        "eta_pause_min": st.get("_eta_min"),
        "jobs": st.get("_zadania", []),
        "stats": st.get("_stat", {}),
        "last_hard_shutdown": st.get("_ostatni_pad"),
        "thresholds": {"pause": st.get("_prog_pauza"), "kill": st.get("_prog_ubicie")},
    }
    tmp = STATUS_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, STATUS_PATH)   # podmiana atomowa — pasek nigdy nie zlapie polowy pliku
    except Exception:
        pass
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
    except Exception:
        pass
    new = not os.path.exists(HIST_PATH)
    try:
        with open(HIST_PATH, "a") as f:
            if new:
                f.write(HIST_HEADER)
            f.write(",".join(str(x) for x in row) + "\n")
    except Exception:
        pass


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
    saferun = managed_pids_from_saferun()
    targets = pick_targets(cfg, procs, saferun)
    lvl, why = severity(cfg, state, temp, speed, soc_t, ac, pct)
    return state, temp, speed, load, targets, lvl, why, soc, soc_t, ac, pct


def fan_alarm(cfg, soc, soc_t, st):
    """Chip goracy, a wentylatory stoja = awaria chlodzenia (zatarty wentylator,
    odlaczona tasma, zapchany uklad). Tylko krzyczy — pauzowanie zostawiamy termice,
    zeby blad odczytu nie zabijal obliczen."""
    if not cfg.get("fan_check", True) or not soc or soc_t is None:
        return
    fans = soc.get("fans") or []
    if not fans:
        return
    hot = soc_t >= cfg.get("fan_alert_temp_c", 75.0)
    dead = max(fans) == 0
    if hot and dead:
        if now() - st.get("fan_alarm_at", 0) > 600:
            st["fan_alarm_at"] = now()
            msg = (T("COOLING FAILURE? chip %.1f C while both fans report 0 rpm") % soc_t)
            log("!!! " + msg)
            notify(cfg, T("Fans stopped while the chip is hot"), msg, key="fan")


def main():
    ensure_dirs()
    cfg = load_cfg()
    st = load_state()

    if st["paused"]:
        do_resume(cfg, st, T("guard startup - nothing is left frozen"))
        save_state(st)

    if "--once" in sys.argv:
        state, temp, speed, load, targets, lvl, why, soc, soc_t, ac, pct = snapshot(cfg)
        fans = ",".join(str(x) for x in (soc.get("fans") if soc else [])) or "n/d"
        print(T("state=%s chip=%s battery=%s fans=%s power=%s CPU_limit=%d%% load1=%.2f level=%d (%s)") % (
            state, ("%.1f C" % soc_t) if soc_t else "n/d",
            ("%.1f C" % temp) if temp else "n/d", fans,
            (T("AC") if ac else T("battery %s%%") % (pct if pct is not None else "?")),
            speed, load, lvl, why or T("calm")))
        for pid, cpu, comm, _ in targets[:5]:
            print(T("  candidate: %-20s pid=%-7d %.0f%% CPU") % (comm, pid, cpu))
        return 0

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
    try:
        if os.path.exists(CLEAN_STOP_PATH):
            os.remove(CLEAN_STOP_PATH)
    except Exception:
        pass

    czujnik_chipa = T("yes") if soc_temp_c() is not None else T("NO (macmon missing - running on battery temperature only)")
    log(T("thermal-guard start | chip: pause>=%.0fC resume<=%.0fC kill>=%.0fC (sensor: %s)"
          " | battery: pause>=%.0fC kill>=%.0fC | state>=%s | battery gate: <=%d%% on battery")
        % (cfg.get("soc_pause_c", 92), cfg.get("soc_resume_c", 80), cfg.get("soc_kill_c", 100),
           czujnik_chipa, cfg["batt_pause_c"], cfg["batt_kill_c"],
           cfg["pause_on_thermal_state"], cfg.get("batt_pct_pause", 10)))

    crit_polls = 0
    cpu_hist = {}
    tick = 0

    while not stop["flag"]:
        try:
            cfg = load_cfg()
            state, temp, speed, load, targets, lvl, why, soc, soc_t, ac, pct = snapshot(cfg)
            fan_alarm(cfg, soc, soc_t, st)
            obsluz_rozkaz(cfg, st, targets)

            # dane pomocnicze dla paska (trend, zadania, licznik dnia)
            st["_trend_c_min"], st["_eta_min"] = trend_i_prognoza(cfg, soc_t)
            st["_dry"] = bool(cfg.get("dry_run"))
            st["_awake"] = keep_awake_update(cfg, targets, lvl)
            st["_prog_pauza"] = cfg.get("soc_pause_c")
            st["_prog_ubicie"] = cfg.get("soc_kill_c")
            if tick % 4 == 0:                      # rzadziej — to czytanie z dysku
                st["_zadania"] = zadania_saferun()
                st["_stat"] = statystyki_dnia()
            # dysk zmienia sie wolno — odczyt raz na ~5 min wystarcza
            if tick % 20 == 0 or not st.get("_disk"):
                st["_disk"] = disk_usage()
            snap_dict = status_write(state, temp, soc, soc_t, ac, pct, speed, load, lvl, why,
                                     targets, st, st.get("_disk"))
            if tick % 4 == 0 and snap_dict:      # flota co ~1 min wystarczy
                fleet_write(cfg, snap_dict)

            # puls czarnej skrzynki — po twardym padzie zostanie tu ostatni znak zycia
            try:
                with open(HEARTBEAT_PATH, "w") as f:
                    f.write(ts())
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

            if lvl >= 3:
                crit_polls += 1
                do_pause(cfg, st, targets, T("CRITICAL: ") + why)
                if crit_polls >= cfg["kill_after_polls"]:
                    do_terminate(cfg, st, why)
                    crit_polls = 0
            elif lvl == 2:
                crit_polls = 0
                do_pause(cfg, st, targets, why)
            else:
                crit_polls = 0
                cool = (temp is None or temp <= cfg["batt_resume_c"]) and LEVELS.get(state, 1) <= 1
                if soc_t is not None and soc_t > cfg.get("soc_resume_c", 80.0):
                    cool = False
                # po pauzie z powodu baterii wznawiamy dopiero na zasilaczu (albo po doladowaniu)
                powered = ac or pct is None or pct >= cfg.get("batt_pct_resume", 25)
                # reczne zamrozenie z paska ma pierwszenstwo — nie odmrazamy za plecami Pawla
                if st["paused"] and cool and powered and not st.get("reczna_pauza"):
                    do_resume(cfg, st, T("conditions are back to normal"))
                do_demote(cfg, st, targets, cpu_hist)

            # Nic nie moze wisiec w pauzie w nieskonczonosc — ALE czekanie na zasilacz
            # to nie awaria. Gdy chip i bateria sa chlodne, a jedynym powodem pauzy jest
            # niski poziom baterii, dajemy duzo wiecej czasu: obliczenie ma spokojnie
            # doczekac do momentu, az uzytkownik podepnie kabel, zamiast zginac po 45 minutach.
            tylko_bateria = (not ac and lvl >= 2
                             and (soc_t is None or soc_t < cfg.get("soc_pause_c", 88) - 10)
                             and (temp is None or temp < cfg["batt_pause_c"] - 3))
            limit_min = cfg.get("max_pause_minutes_batt", 240) if tylko_bateria else cfg["max_pause_minutes"]
            for key, info in list(st["paused"].items()):
                if now() - info["since"] > limit_min * 60:
                    log(T("PAUSE >%d min - terminating job %s (pid %s)")
                        % (limit_min, info.get("comm"), key))
                    do_terminate(cfg, st, T("paused for longer than %d min") % limit_min)
                    break

            live = set(p[0] for p in targets)
            cpu_hist = dict((k, v) for k, v in cpu_hist.items() if k in live)
            st["demoted"] = [p for p in st["demoted"] if alive(p)]
            save_state(st)
        except Exception as e:
            log(T("LOOP ERROR: %r") % (e,))
        tick += 1
        for _ in range(int(cfg["poll_seconds"] * 2)):
            if stop["flag"]:
                break
            time.sleep(0.5)

    do_resume(cfg, st, T("guard is shutting down"))
    save_state(st)
    # znacznik czystego zamkniecia — bez niego nastepny start uzna to za twardy pad
    try:
        with open(CLEAN_STOP_PATH, "w") as f:
            f.write(ts())
    except Exception:
        pass
    log("thermal-guard stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
