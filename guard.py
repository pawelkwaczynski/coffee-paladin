#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
thermal-guard — pilnuje temperatury i obciazenia Maca (bez sudo).

Co N sekund czyta:
  * stan termiczny macOS  (thermalstate: nominal/fair/serious/critical)
  * temperature baterii   (ioreg AppleSmartBattery -> "Temperature", setne stopnia)
  * throttling CPU        (pmset -g therm -> CPU_Speed_Limit)
  * load average + procesy (ps)

Gdy goraco: SIGSTOP na ciezkie zadania obliczeniowe (ffmpeg, python, julia, ollama...).
Gdy ostygnie: SIGCONT. Przy stanie krytycznym: SIGCONT + SIGTERM (zadania maja checkpointy),
po grace SIGKILL. Systemu, Findera ani sesji Claude/Hermes NIE rusza.

Historia pomiarow: ~/.thermal-guard/history.csv     (do dowodow "co sie dzialo o 3 w nocy")
Zdarzenia:         ~/.thermal-guard/guard.log
Stan (pauzy):      ~/.thermal-guard/state.json      (odtwarzany po restarcie -> nic nie zostaje zamrozone)

Uzycie:
  guard.py            # petla (tak odpala LaunchAgent)
  guard.py --once     # jeden przebieg, wypisuje odczyt (do testow)
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
    # Progi ustalone z Pawlem 29.07.2026 — sufit 90 C to jego decyzja. Sa ostrzejsze niz
    # fabryczne dlawienie macOS (~100-108 C), bo MBP jest podejrzany o wade zasilania.
    # Pauza chlodzi chip w kilkanascie sekund (89 -> 60 C zmierzone), wiec do ubicia
    # w praktyce nie dochodzi — a SIGSTOP niczego nie niszczy.
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
    "dry_run": False,
    # co wolno pauzowac (dopasowanie po nazwie procesu, case-insensitive)
    "managed_patterns": [
        "ffmpeg", "ffprobe", "handbrake", "x265", "x264", "compressor",
        "python", "python3", "uv", "julia", "z3", "geng", "nauty", "lean", "lake",
        "ollama", "llama", "mlx", "whisper", "node", "java", "rustc", "cargo",
        "blender", "rclone", "7z", "zstd", "xz", "tar", "bsdtar", "make", "cc1plus", "clang",
    ],
    # czego NIE wolno ruszac nigdy (nadrzedne wobec powyzszego)
    "never_patterns": [
        "kernel_task", "windowserver", "launchd", "loginwindow", "logd", "opendirectoryd",
        "backupd", "mds", "mdworker", "spotlight", "fileproviderd", "cloudd", "bird",
        "finder", "dock", "terminal", "ghostty", "iterm", "zsh", "bash", "sshd", "ssh",
        "claude", "hermes", "guard.py", "thermal-guard", "safe-run", "code helper", "electron",
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


def notify(cfg, title, text, key="default"):
    if not cfg["notify"]:
        return
    t = now()
    if t - _last_notify.get(key, 0) < cfg["notify_min_gap_s"]:
        return
    _last_notify[key] = t
    script = 'display notification %s with title %s sound name "Submarine"' % (
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


def battery_temp_c():
    """Temperatura pakietu baterii w C (None gdy brak baterii)."""
    out = run(["ioreg", "-r", "-c", "AppleSmartBattery", "-d", "1", "-w", "0"], timeout=15)
    best = None
    for key in ('"Temperature"', '"VirtualTemperature"'):
        m = re.search(re.escape(key) + r"\s*=\s*(\d+)", out)
        if m:
            v = int(m.group(1)) / 100.0
            if 5.0 < v < 90.0 and (best is None or v > best):
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

        val = {
            "cpu": sane(cpu),
            "gpu": sane(gpu),
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
    never = [p.lower() for p in cfg["never_patterns"]]
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
        if any(n in args for n in ("thermal-guard", "thermal_guard", "guard.py", "safe-run")):
            continue
        if "claude" in args and "python" not in low:
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
            log("[DRY-RUN] pauza %s (pid %d, %.0f%% CPU) — %s" % (comm, pid, cpu, reason))
            continue
        if sig(pid, pgid, signal.SIGSTOP):
            st["paused"][key] = {"since": now(), "comm": comm, "pgid": pgid, "cpu": cpu}
            changed = True
            log("PAUZA  %s (pid %d, %.0f%% CPU) — %s" % (comm, pid, cpu, reason))
        else:
            # Cicha porazka byla grozna: pasek pokazywal "zamrozone", a proces biegl dalej.
            # Zwykle to demon systemowy, ktory odrzuca SIGSTOP — dopisujemy go do pominietych.
            log("NIE UDALO SIE wstrzymac %s (pid %d) — brak uprawnien do sygnalu" % (comm, pid))
    if changed:
        names = ", ".join(sorted(set(v["comm"] for v in st["paused"].values())))
        notify(cfg, "Thermal guard: gorąco", "Wstrzymano: %s (%s)" % (names, reason), "pause")
    return changed


def do_resume(cfg, st, reason):
    if not st["paused"]:
        return False
    for key, info in list(st["paused"].items()):
        pid = int(key)
        if alive(pid):
            sig(pid, info.get("pgid"), signal.SIGCONT)
            log("WZNOWIONE %s (pid %d) — %s" % (info.get("comm", "?"), pid, reason))
        del st["paused"][key]
    notify(cfg, "Thermal guard: ochłodzone", "Wznowiono wstrzymane zadania (%s)" % reason, "resume")
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
            log("[DRY-RUN] ubicie %s (pid %d) — %s" % (info.get("comm"), pid, reason))
            continue
        sig(pid, info.get("pgid"), signal.SIGCONT)
        sig(pid, info.get("pgid"), signal.SIGTERM)
        victims.append((pid, info))
        log("STOP (SIGTERM) %s (pid %d) — %s" % (info.get("comm", "?"), pid, reason))
        del st["paused"][key]
    if victims:
        notify(cfg, "Thermal guard: ZATRZYMANE",
               "Ubito zadania (%s). Wznow z checkpointu, gdy Mac ostygnie." % reason, "kill")
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
            log("[DRY-RUN] demote %s (pid %d)" % (comm, pid))
            continue
        subprocess.call(["taskpolicy", "-b", "-p", str(pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.call(["renice", "+10", "-p", str(pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st["demoted"].append(pid)
        log("DEMOTE %s (pid %d) -> tlo/E-cores + nice+10 (mieli >%d min)"
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
            lvl = max(lvl, 3); why.append("chip %.1f C" % soc)
        elif soc >= cfg.get("soc_pause_c", 92.0):
            lvl = max(lvl, 2); why.append("chip %.1f C" % soc)
        elif soc >= cfg.get("soc_pause_c", 92.0) - 7:
            lvl = max(lvl, 1); why.append("chip %.1f C" % soc)
    # bramka na baterie: na zasilaniu bateryjnym ponizej progu pauzujemy, zeby dlugie
    # obliczenie nie zgaslo razem z laptopem w polowie bloku (czekamy na zasilacz)
    if not ac and pct is not None and pct <= cfg.get("batt_pct_pause", 10):
        lvl = max(lvl, 2); why.append("bateria %d%% bez zasilacza" % pct)
    s = LEVELS.get(state, 1)
    if s >= 3:
        lvl = max(lvl, 3); why.append("stan termiczny=critical")
    elif s >= LEVELS.get(cfg["pause_on_thermal_state"], 2):
        lvl = max(lvl, 2); why.append("stan termiczny=%s" % state)
    elif s == 1:
        lvl = max(lvl, 1); why.append("stan termiczny=fair")
    if temp is not None:
        if temp >= cfg["batt_kill_c"]:
            lvl = max(lvl, 3); why.append("bateria %.1f C" % temp)
        elif temp >= cfg["batt_pause_c"]:
            lvl = max(lvl, 2); why.append("bateria %.1f C" % temp)
        elif temp >= cfg["batt_pause_c"] - 3:
            lvl = max(lvl, 1); why.append("bateria %.1f C" % temp)
    if speed < cfg["speed_limit_pause"]:
        lvl = max(lvl, 2); why.append("CPU dławione do %d%%" % speed)
    return lvl, ", ".join(why)


def boot_time():
    """Moment ostatniego startu systemu (epoch)."""
    m = re.search(r"sec\s*=\s*(\d+)", run(["sysctl", "-n", "kern.boottime"]))
    return int(m.group(1)) if m else 0


def zapisz_zdarzenie(rodzaj, opis, kontekst=None):
    """Czarna skrzynka — zdarzenia, ktore maja przezyc restart i trafic do raportu."""
    try:
        with open(EVENTS_PATH, "a") as f:
            wpis = {"czas": ts(), "rodzaj": rodzaj, "opis": opis}
            if kontekst:
                wpis["kontekst"] = kontekst
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
                if w.strip() and not w.startswith("czas,"):
                    ogon.append(dict(zip(naglowek, w.strip().split(","))))
        except Exception:
            pass
        opis = ("Mac zgasl bez czystego zamkniecia. Ostatni puls guarda: %s, "
                "system wstal: %s." % (ts(puls), ts(boot)))
        zapisz_zdarzenie("TWARDY_PAD", opis, {"ostatnie_pomiary": ogon})
        log("!!! WYKRYTO TWARDY PAD — " + opis)
        return {"czas": ts(puls), "opis": opis, "pomiary": ogon}
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
        if targets and do_pause(cfg, st, targets, "ZAMROZENIE RECZNE (z paska menu)"):
            st["reczna_pauza"] = True
        else:
            log("reczne zamrozenie: nie bylo czego zamrozic")
            notify(cfg, "Nie ma czego zamrozic",
                   "Zadne ciezkie zadanie nie spelnia warunkow", key="freeze")
    elif rozkaz == "resume":
        st["reczna_pauza"] = False
        do_resume(cfg, st, "wznowienie reczne (z paska menu)")


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
    return {"pauzy": pauzy, "wznowienia": wznowienia, "ubicia": ubicia}


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
                out.append({"nazwa": d.get("name") or d.get("comm") or "?",
                            "pid": pid,
                            "minuty": round(proc_age_seconds(pid) / 60.0)})
    except Exception:
        pass
    return out


def status_write(state, temp, soc, soc_t, ac, pct, speed, load, lvl, why, targets, st):
    """Migawka dla paska menu (`heatbar`). Pasek nic sam nie mierzy — czyta ten plik,
    wiec kosztuje zero CPU i zawsze pokazuje dokladnie to, co widzi guard."""
    top = targets[0] if targets else None
    data = {
        "czas": ts(), "stan": state, "poziom": lvl, "powod": why,
        "chip_c": round(soc_t, 1) if soc_t else None,
        "gpu_c": round(soc["gpu"], 1) if soc and soc.get("gpu") else None,
        "bateria_c": round(temp, 1) if temp else None,
        "wentylatory": (soc.get("fans") if soc else []) or [],
        "waty": round(soc["watts"], 1) if soc else None,
        "bateria_pct": pct, "na_zasilaczu": bool(ac),
        "cpu_limit": speed, "load1": round(load, 2),
        "wstrzymane": [v.get("comm") for v in st.get("paused", {}).values()],
        "top_proc": top[2] if top else None,
        "top_cpu": round(top[1]) if top else None,
        "reczna_pauza": bool(st.get("reczna_pauza")),
        "trend_c_min": st.get("_trend_c_min"),
        "eta_pauza_min": st.get("_eta_min"),
        "zadania": st.get("_zadania", []),
        "statystyki": st.get("_stat", {}),
        "ostatni_pad": st.get("_ostatni_pad"),
        "progi": {"pauza": st.get("_prog_pauza"), "ubicie": st.get("_prog_ubicie")},
    }
    tmp = STATUS_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, STATUS_PATH)   # podmiana atomowa — pasek nigdy nie zlapie polowy pliku
    except Exception:
        pass


HIST_HEADER = ("czas,stan,chip_C,gpu_C,bateria_C,wentylator_rpm,waty,"
               "bateria_pct,na_zasilaczu,cpu_limit,load1,poziom,top_proc,top_cpu\n")


def hist_write(row):
    rotate(HIST_PATH)
    # przy zmianie zestawu kolumn odkladamy stary plik zamiast mieszac formaty
    try:
        if os.path.exists(HIST_PATH):
            with open(HIST_PATH) as f:
                if f.readline() != HIST_HEADER:
                    os.rename(HIST_PATH, HIST_PATH.replace(".csv", "_stary.csv"))
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
            msg = ("AWARIA CHLODZENIA? chip %.1f C, a oba wentylatory 0 obr/min" % soc_t)
            log("!!! " + msg)
            notify(cfg, "Wentylatory stoja przy goracym chipie", msg, key="fan")


def main():
    ensure_dirs()
    cfg = load_cfg()
    st = load_state()

    if st["paused"]:
        do_resume(cfg, st, "start guarda — nic nie zostaje zamrozone")
        save_state(st)

    if "--once" in sys.argv:
        state, temp, speed, load, targets, lvl, why, soc, soc_t, ac, pct = snapshot(cfg)
        fans = ",".join(str(x) for x in (soc.get("fans") if soc else [])) or "n/d"
        print("stan=%s chip=%s bateria=%s wentylatory=%s zasilanie=%s CPU_limit=%d%% load1=%.2f poziom=%d (%s)" % (
            state, ("%.1f C" % soc_t) if soc_t else "n/d",
            ("%.1f C" % temp) if temp else "n/d", fans,
            ("AC" if ac else "bateria %s%%" % (pct if pct is not None else "?")),
            speed, load, lvl, why or "spokoj"))
        for pid, cpu, comm, _ in targets[:5]:
            print("  kandydat: %-20s pid=%-7d %.0f%% CPU" % (comm, pid, cpu))
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
        notify(cfg, "Mac zgasl bez ostrzezenia",
               "Zapisalem dowody z chwili padu — menu paska > Eksportuj raport", key="pad")
    st["reczna_pauza"] = False
    try:
        if os.path.exists(CLEAN_STOP_PATH):
            os.remove(CLEAN_STOP_PATH)
    except Exception:
        pass

    czujnik_chipa = "tak" if soc_temp_c() is not None else "NIE (brak macmon — lecimy na samej baterii)"
    log("thermal-guard start | chip: pauza>=%.0fC wznow<=%.0fC ubicie>=%.0fC (czujnik: %s)"
        " | bateria: pauza>=%.0fC ubicie>=%.0fC | stan>=%s | bramka baterii: <=%d%% bez zasilacza"
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
            st["_prog_pauza"] = cfg.get("soc_pause_c")
            st["_prog_ubicie"] = cfg.get("soc_kill_c")
            if tick % 4 == 0:                      # rzadziej — to czytanie z dysku
                st["_zadania"] = zadania_saferun()
                st["_stat"] = statystyki_dnia()
            status_write(state, temp, soc, soc_t, ac, pct, speed, load, lvl, why, targets, st)

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
                do_pause(cfg, st, targets, "KRYTYCZNIE: " + why)
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
                    do_resume(cfg, st, "warunki wrocily do normy")
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
                    log("PAUZA >%d min — koncze zadanie %s (pid %s)"
                        % (limit_min, info.get("comm"), key))
                    do_terminate(cfg, st, "pauza dluzsza niz %d min" % limit_min)
                    break

            live = set(p[0] for p in targets)
            cpu_hist = dict((k, v) for k, v in cpu_hist.items() if k in live)
            st["demoted"] = [p for p in st["demoted"] if alive(p)]
            save_state(st)
        except Exception as e:
            log("BLAD petli: %r" % (e,))
        tick += 1
        for _ in range(int(cfg["poll_seconds"] * 2)):
            if stop["flag"]:
                break
            time.sleep(0.5)

    do_resume(cfg, st, "guard konczy prace")
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
