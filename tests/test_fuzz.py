#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy losowe (fuzzing / property-based) czystych funkcji coffee-paladin.

Uruchomienie:   python3 tests/test_fuzz.py
                python3 tests/test_fuzz.py --seed 12345   (inne ziarno)
                python3 tests/test_fuzz.py --n 1000       (wiecej przebiegow)

Zasada: NIE czytamy kodu w poszukiwaniu bledow - generujemy wejscia i patrzymy,
co sie wysypie. Kazdy wyjatek, ktory wychodzi z funkcji na zewnatrz, jest
znaleziskiem. Osobno sprawdzamy wlasnosci wyniku (oracle): funkcja moze nie
rzucic wyjatkiem, a i tak zwrocic bzdure (np. prog NaN, ktory nigdy nie zadziala).

Wszystko dzieje sie w katalogu tymczasowym (TG_BASE), zaden proces nie jest
uruchamiany (subprocess jest podmieniony na atrapy), zero obciazenia maszyny.
"""

import argparse
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
import time
import traceback
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT_SEKUND = 60.0          # twardy limit na jedna funkcje (maszyna moze byc goraca)

# ---------------------------------------------------------------- srodowisko

TMP = tempfile.mkdtemp(prefix="tg-fuzz-")
os.environ["TG_BASE"] = TMP
os.environ.setdefault("TG_LANG", "en")
os.makedirs(os.path.join(TMP, "managed"), exist_ok=True)


def zaladuj(nazwa, plik):
    return SourceFileLoader(nazwa, os.path.join(REPO, plik)).load_module()


guard = zaladuj("tgfuzz_guard", "guard.py")
heat = zaladuj("tgfuzz_heat", "heat")
saferun = zaladuj("tgfuzz_saferun", "safe-run")
treport = zaladuj("tgfuzz_treport", "thermal-report")

# zadnych procesow: kazde wyjscie z `ps`/`sysctl` jest atrapa
guard.run = lambda cmd, timeout=10: ""
heat.sh = lambda cmd, timeout=15: ""
saferun.sh = lambda cmd, timeout=15: ""
treport.sh = lambda cmd, timeout=30: ""

# ---------------------------------------------------------------- raport

ZNALEZISKA = {}          # (funkcja, klucz) -> {opis, wejscie, powaga, ile}
PRZEBIEGI = {}
OK_FUNKCJE = []


def znalezisko(funkcja, klucz, wejscie, opis, powaga):
    k = (funkcja, klucz)
    if k in ZNALEZISKA:
        ZNALEZISKA[k]["ile"] += 1
        return
    ZNALEZISKA[k] = {"funkcja": funkcja, "klucz": klucz, "wejscie": skroc(wejscie),
                     "opis": opis, "powaga": powaga, "ile": 1}


def skroc(x, n=300):
    s = repr(x)
    return s if len(s) <= n else s[:n] + "...<%d znakow>" % len(s)


def klucz_bledu(exc):
    return "EXC:" + type(exc).__name__


def skonczona(w):
    """math.isfinite bez wysadzania sie na 400-cyfrowym intcie."""
    if isinstance(w, bool):
        return True
    if isinstance(w, int):
        return True
    try:
        return math.isfinite(w)
    except Exception:
        return False


class Sesja(object):
    """Jedna funkcja pod ostrzalem: liczy przebiegi, pilnuje limitu czasu,
    deduplikuje te same bledy (zapisujac PIERWSZE wejscie, na ktorym peklo)."""

    def __init__(self, nazwa, seed):
        self.nazwa = nazwa
        self.seed = seed
        self.rng = random.Random("%s|%s" % (seed, nazwa))
        self.start = time.time()
        self.n = 0
        self.bledy = 0
        self.bzdury = 0

    def czas_minal(self):
        return time.time() - self.start > LIMIT_SEKUND

    def blad(self, wejscie, exc, powaga="WYSOKA"):
        self.bledy += 1
        znalezisko(self.nazwa, klucz_bledu(exc), wejscie,
                   "wyjatek wychodzi z funkcji: %s: %s" % (type(exc).__name__, exc), powaga)

    def bzdura(self, wejscie, opis, powaga="SREDNIA", klucz=None):
        self.bzdury += 1
        znalezisko(self.nazwa, klucz or opis[:60], wejscie, opis, powaga)

    def koniec(self):
        PRZEBIEGI[self.nazwa] = {
            "przebiegi": self.n,
            "sekundy": round(time.time() - self.start, 2),
            "bledy": self.bledy,
            "bzdury": self.bzdury,
        }
        if not self.bledy and not self.bzdury:
            OK_FUNKCJE.append(self.nazwa)


# ---------------------------------------------------------------- generatory

EMOJI = "\U0001F525\U0001F9CA☕\U0001F4BB"
STEROWNE = "".join(chr(c) for c in range(1, 32))

DZIWNE_STRINGI = [
    "", " ", "\x00", "a\x00b", STEROWNE, EMOJI, "ff" + EMOJI + "mpeg",
    "\u202e\u200b bidi", "\\", "/", "../../etc/passwd", "%s %d %.1f",
    "python" * 2000, "A" * 10000, "中文名称", "йцу",
    "NaN", "Infinity", "-0", "1e400", "0x41", "  41  ", "41,5",
    "\n\r\t", "'; DROP TABLE --", "\ud83d".encode("utf-16", "surrogatepass").decode("utf-16", "replace"),
]

DZIWNE_LICZBY = [
    0, 1, -1, 2 ** 31, 2 ** 63, -2 ** 63, 10 ** 400, -10 ** 400,
    0.0, -0.0, 1e-323, 1e308, -1e308, float("inf"), float("-inf"), float("nan"),
    1e9, -1e9, 0.1 + 0.2, 90.0, 85.5, 40.0, -273.15,
]


def losowy_string(rng):
    r = rng.random()
    if r < 0.4:
        return rng.choice(DZIWNE_STRINGI)
    if r < 0.6:
        return "".join(rng.choice("abcXYZ012 ./-_\x00" + EMOJI) for _ in range(rng.randint(0, 40)))
    if r < 0.7:
        return "A" * rng.choice([1000, 10000])
    return rng.choice(["ffmpeg", "python3", "node", "claude", "kernel_task", "x265", "Python"])


def losowa_liczba(rng):
    if rng.random() < 0.5:
        return rng.choice(DZIWNE_LICZBY)
    if rng.random() < 0.5:
        return rng.uniform(-1e6, 1e6)
    return rng.randint(-10 ** 6, 10 ** 6)


def losowa_wartosc(rng, glebokosc=0):
    r = rng.random()
    if glebokosc < 3 and r < 0.10:
        return [losowa_wartosc(rng, glebokosc + 1) for _ in range(rng.randint(0, 5))]
    if glebokosc < 3 and r < 0.16:
        return {losowy_string(rng): losowa_wartosc(rng, glebokosc + 1)
                for _ in range(rng.randint(0, 4))}
    if r < 0.30:
        return losowy_string(rng)
    if r < 0.75:
        return losowa_liczba(rng)
    if r < 0.85:
        return rng.choice([True, False])
    if r < 0.92:
        return None
    return rng.choice([[], {}, [1, 2, 3], ["ffmpeg", ""], [""], [None], {"a": 1}])


# ---------------------------------------------------------------- 1. load_cfg

CFG = os.path.join(TMP, "config.json")

SUROWE_CONFIGI = [
    "",                                   # plik pusty
    "null",
    "true",
    "[]",
    '"tekst"',
    "{",                                  # obciety
    '{"soc_pause_c": 85.0',               # obciety w polowie
    "\x00\x01\x02\xff\xfe",               # smieci binarne
    '{"poll_seconds": 1e400}',            # nieskonczonosc w kluczu calkowitym
    '{"batt_pause_c": 1e400}',            # nieskonczonosc w kluczu zmiennoprzecinkowym
    '{"batt_pause_c": %s}' % ("9" * 400),  # 400-cyfrowa liczba calkowita
    '{"poll_seconds": %s}' % ("9" * 400),
    '{"soc_pause_c": NaN, "soc_kill_c": NaN, "soc_resume_c": NaN}',
    '{"cpu_min_percent": NaN}',
    '{"soc_pause_c": Infinity, "soc_kill_c": Infinity}',
    '{"soc_pause_c": -Infinity}',
    '{"never_patterns": [""], "managed_patterns": [""]}',
    '{"soc_kill_c": 10, "soc_pause_c": 90, "soc_resume_c": 95}',   # progi na opak
    '{"lang": "\\u0000"}',
    '{"never_extra": [null, 1, {}, [], "\\u0000"]}',
    "{" + ",".join('"k%d": %d' % (i, i) for i in range(20000)) + "}",   # config-olbrzym
]


def wpisz_cfg(tekst):
    with open(CFG, "w") as f:
        f.write(tekst)


def sprawdz_cfg(s, wejscie, cfg):
    """Oracle configu: komplet kluczy, wlasciwe typy, liczby skonczone, progi rosnace."""
    for k, wzor in guard.DEFAULTS.items():
        if k not in cfg:
            s.bzdura(wejscie, "load_cfg gubi klucz %s" % k, "WYSOKA", klucz="brak-klucza")
            continue
        w = cfg[k]
        if isinstance(wzor, bool) and not isinstance(w, bool):
            s.bzdura(wejscie, "klucz %s ma typ %s zamiast bool" % (k, type(w).__name__),
                     "WYSOKA", klucz="bool-zly-typ")
        elif isinstance(wzor, (int, float)) and not isinstance(wzor, bool):
            if isinstance(w, bool) or not isinstance(w, (int, float)):
                s.bzdura(wejscie,
                         "klucz liczbowy %s dostal wartosc %r (typ %s) i PRZESZEDL walidacje typow "
                         "- bool omija cala kontrole, wiec np. {\"poll_seconds\": true} = petla co 1 s, "
                         "a {\"soc_pause_c\": true} = prog pauzy 1 C" % (k, w, type(w).__name__),
                         "WYSOKA", klucz="bool-zamiast-liczby")
            elif not skonczona(w):
                s.bzdura(wejscie,
                         "prog %s = %r (NaN/inf) przechodzi walidacje - kazde porownanie "
                         "z nim jest falszywe, bezpiecznik oslepa bez ostrzezenia" % (k, w),
                         "WYSOKA", klucz="nieskonczony-prog")
        elif isinstance(wzor, list) and not isinstance(w, list):
            s.bzdura(wejscie, "klucz %s nie jest lista" % k, "WYSOKA", klucz="nie-lista")
        elif isinstance(wzor, str) and not isinstance(w, str):
            s.bzdura(wejscie, "klucz %s nie jest stringiem" % k, "SREDNIA", klucz="nie-str")
    try:
        if skonczona(cfg["soc_resume_c"]) and skonczona(cfg["soc_pause_c"]):
            if cfg["soc_resume_c"] >= cfg["soc_pause_c"]:
                s.bzdura(wejscie, "soc_resume_c >= soc_pause_c po walidacji (mlynek pauza/wznowienie)",
                         "WYSOKA", klucz="progi-resume")
        if skonczona(cfg["soc_pause_c"]) and skonczona(cfg["soc_kill_c"]):
            if cfg["soc_pause_c"] >= cfg["soc_kill_c"]:
                s.bzdura(wejscie, "soc_pause_c >= soc_kill_c po walidacji (SIGTERM przy progu pauzy)",
                         "WYSOKA", klucz="progi-kill")
    except Exception:
        pass
    for k in ("never_patterns", "never_arg_patterns"):
        for nazwa in guard.WLASNE_NAZWY:
            if nazwa not in cfg.get(k, []):
                s.bzdura(wejscie, "%s nie zawiera wlasnej nazwy %r - guard moze zapauzowac sam siebie"
                         % (k, nazwa), "WYSOKA", klucz="brak-wlasnej-nazwy")
    for w in cfg.get("never_patterns", []):
        if not isinstance(w, str) or not w.strip():
            s.bzdura(wejscie, "pusty/nie-tekstowy wzorzec w never_patterns: %r" % (w,),
                     "WYSOKA", klucz="pusty-wzorzec")


def fuzz_load_cfg(seed, n):
    s = Sesja("guard.load_cfg", seed)
    klucze = list(guard.DEFAULTS)
    for i in range(n):
        if s.czas_minal():
            break
        s.n += 1
        if i < len(SUROWE_CONFIGI):
            tekst = SUROWE_CONFIGI[i]
        elif i == len(SUROWE_CONFIGI):
            tekst = json.dumps({"never_extra": ["x" * 1000] * 10000})     # ~10 MB
        else:
            d = {}
            for k in s.rng.sample(klucze, s.rng.randint(1, min(12, len(klucze)))):
                d[k] = losowa_wartosc(s.rng)
            for _ in range(s.rng.randint(0, 3)):
                d[losowy_string(s.rng)] = losowa_wartosc(s.rng)
            try:
                tekst = json.dumps(d, allow_nan=True)
            except Exception:
                continue
        wpisz_cfg(tekst)
        del guard._zle_typy[:]
        try:
            cfg = guard.load_cfg()
        except Exception as e:
            s.blad(tekst, e)
            continue
        if not isinstance(cfg, dict):
            s.bzdura(tekst, "load_cfg zwrocil %s zamiast dict" % type(cfg).__name__, "WYSOKA")
            continue
        sprawdz_cfg(s, tekst, cfg)
    wpisz_cfg("{}")
    s.koniec()


# ---------------------------------------------------------------- 2. severity

def losowa_temp(rng, wrogo):
    if not wrogo:
        return rng.choice([None, -273.15, 0.0, 40.0, 85.0, 90.5, 1e9, -1e9,
                           float("nan"), float("inf"), rng.uniform(-100, 200)])
    return losowa_wartosc(rng)


def fuzz_severity(seed, n, wrogo=False):
    nazwa = "guard.severity" + ("[wrogie typy]" if wrogo else "")
    s = Sesja(nazwa, seed)
    wpisz_cfg("{}")
    cfg_bazowy = guard.load_cfg()
    stany = list(guard.LEVELS) + ["", None, "SERIOUS", 3, "\x00"]
    for _ in range(n):
        if s.czas_minal():
            break
        s.n += 1
        cfg = dict(cfg_bazowy)
        if s.rng.random() < 0.3:
            for k in ("soc_pause_c", "soc_kill_c", "batt_pause_c", "batt_kill_c",
                      "speed_limit_pause", "batt_pct_pause"):
                if s.rng.random() < 0.4:
                    cfg[k] = losowa_liczba(s.rng)
        arg = {
            "state": s.rng.choice(stany) if wrogo else s.rng.choice(list(guard.LEVELS)),
            "temp": losowa_temp(s.rng, wrogo),
            "speed": s.rng.choice([100, 0, -5, 1e9, 60]) if not wrogo else losowa_wartosc(s.rng),
            "soc": losowa_temp(s.rng, wrogo),
            "ac": s.rng.choice([True, False]) if not wrogo else losowa_wartosc(s.rng),
            "pct": s.rng.choice([None, 0, 5, 50, 100, -1, 10 ** 9]) if not wrogo
                   else losowa_wartosc(s.rng),
        }
        try:
            lvl, why = guard.severity(cfg, arg["state"], arg["temp"], arg["speed"],
                                      soc=arg["soc"], ac=arg["ac"], pct=arg["pct"])
        except Exception as e:
            s.blad({"cfg_progi": {k: cfg[k] for k in ("soc_pause_c", "soc_kill_c")}, "arg": arg},
                   e, "WYSOKA" if not wrogo else "NISKA")
            continue
        if not isinstance(lvl, int) or lvl not in (0, 1, 2, 3):
            s.bzdura(arg, "severity zwrocil poziom %r (poza 0..3)" % (lvl,), "WYSOKA",
                     klucz="poziom-poza-zakresem")
        if not isinstance(why, str):
            s.bzdura(arg, "powod nie jest tekstem: %r" % (why,), "SREDNIA", klucz="powod-nie-str")
        soc = arg["soc"]
        if isinstance(soc, float) and math.isfinite(soc) and skonczona(cfg["soc_kill_c"]):
            if soc >= cfg["soc_kill_c"] and lvl != 3:
                s.bzdura(arg, "chip %.1f C >= progu ubicia %.1f C, a poziom = %s"
                         % (soc, cfg["soc_kill_c"], lvl), "WYSOKA", klucz="kill-nie-zadzialal")
        if isinstance(soc, float) and math.isnan(soc) and lvl == 0:
            s.bzdura(arg, "chip = NaN traktowany jak zimny (poziom 0, zero ostrzezenia)",
                     "SREDNIA", klucz="nan-jak-zimny")
    s.koniec()


# ---------------------------------------------------------------- 3. normalize_batt_temp

def fuzz_normalize(seed, n, modul, nazwa):
    s = Sesja(nazwa, seed)
    stale = DZIWNE_LICZBY + DZIWNE_STRINGI + [None, True, False, [], {}, b"41", b"", (1,),
                                              "41", "3081", "444", "0", "-5", "1e400"]
    for i in range(n):
        if s.czas_minal():
            break
        s.n += 1
        if i < len(stale):
            raw = stale[i]
        elif s.rng.random() < 0.5:
            raw = s.rng.uniform(-1e9, 1e9)
        else:
            raw = losowa_wartosc(s.rng)
        try:
            v = modul.normalize_batt_temp(raw)
        except Exception as e:
            # realni wywolujacy podaja string z ioreg albo None - reszta to badanie granic
            s.blad(raw, e, "WYSOKA" if isinstance(raw, (str, bytes, type(None))) else "SREDNIA")
            continue
        if v is None:
            continue
        if not isinstance(v, float) or not math.isfinite(v):
            s.bzdura(raw, "zwrocono %r (nie-skonczona liczba)" % (v,), "WYSOKA", klucz="niesk")
        elif not (5.0 < v <= 100.0):
            s.bzdura(raw, "zwrocono %r - poza deklarowanym zakresem 5..100 C" % (v,),
                     "WYSOKA", klucz="poza-zakresem")
    s.koniec()


# ---------------------------------------------------------------- 4. cpu_z_dziecmi

def losowe_procesy(rng, wrogo=False):
    ile = rng.choice([0, 1, 2, 5, 30, 200])
    procs = []
    for _ in range(ile):
        pid = rng.choice([rng.randint(-10, 5000), 0, 1, -1, 2 ** 63, rng.randint(1, 50)])
        ppid = rng.choice([rng.randint(-10, 5000), 0, 1, pid, rng.randint(1, 50)])
        cpu = rng.choice([0.0, 1.0, 99.9, -5.0, 1e9, float("nan"), float("inf"),
                          rng.uniform(0, 100)])
        comm = losowy_string(rng)
        if wrogo and rng.random() < 0.2:
            comm = rng.choice([None, 123, [], b"ffmpeg"])
        procs.append((pid, ppid, cpu, comm))
    if ile and rng.random() < 0.3:      # cykl rodzic<->dziecko
        a, b = procs[0][0], procs[-1][0]
        procs[0] = (a, b, procs[0][2], procs[0][3])
        procs[-1] = (b, a, procs[-1][2], procs[-1][3])
    if ile and rng.random() < 0.2:      # dlugi lancuch (test glebokosci rekursji)
        procs = [(i, i - 1, 1.0, "chain") for i in range(1, min(ile, 200) + 1)]
    return procs


def fuzz_cpu_z_dziecmi(seed, n):
    s = Sesja("guard.cpu_z_dziecmi", seed)
    for _ in range(n):
        if s.czas_minal():
            break
        s.n += 1
        procs = losowe_procesy(s.rng, wrogo=s.rng.random() < 0.2)
        try:
            suma = guard.cpu_z_dziecmi(procs)
        except Exception as e:
            s.blad(procs[:6], e)
            continue
        if not isinstance(suma, dict):
            s.bzdura(procs[:6], "zwrocono %s zamiast dict" % type(suma).__name__, "WYSOKA",
                     klucz="zly-typ-wyniku")
            continue
        # ujemne/nieskonczone CPU nie wychodzi z `ps` - przy takich wejsciach suma
        # poddrzewa moze byc mniejsza od wlasnego CPU i nie jest to blad funkcji
        if any(not isinstance(c, (int, float)) or isinstance(c, bool)
               or not skonczona(c) or c < 0 for _p, _pp, c, _c in procs):
            continue
        # porownujemy do mapy "ostatni wpis wygrywa" - tak samo, jak robi to sama funkcja
        wlasne = {}
        for pid, ppid, cpu, comm in procs:
            try:
                wlasne[pid] = cpu
            except TypeError:
                pass
        for pid, cpu in wlasne.items():
            if isinstance(cpu, float) and math.isfinite(cpu) and cpu >= 0:
                w = suma.get(pid)
                if isinstance(w, float) and math.isfinite(w) and w + 1e-6 < cpu:
                    s.bzdura((pid, cpu, w),
                             "suma poddrzewa (%r) mniejsza niz wlasne CPU procesu (%r)" % (w, cpu),
                             "SREDNIA", klucz="suma-mniejsza")
    s.koniec()


# ---------------------------------------------------------------- 5. pick_targets

def fuzz_pick_targets(seed, n):
    s = Sesja("guard.pick_targets", seed)
    wpisz_cfg("{}")
    cfg_bazowy = guard.load_cfg()
    stare = (guard.proc_age_seconds, guard.pierwszoplanowy_na_tty, guard.full_args)
    guard.proc_age_seconds = lambda pid: s.rng.choice([0, 5, 130, 10 ** 6])
    guard.pierwszoplanowy_na_tty = lambda pid: s.rng.random() < 0.3
    guard.full_args = lambda pid: losowy_string(s.rng)
    try:
        for _ in range(n):
            if s.czas_minal():
                break
            s.n += 1
            cfg = dict(cfg_bazowy)
            if s.rng.random() < 0.3:
                cfg["cpu_min_percent"] = losowa_liczba(s.rng)
            if s.rng.random() < 0.2:
                cfg["count_children"] = s.rng.choice([True, False, None, "tak"])
            if s.rng.random() < 0.2:
                cfg["managed_patterns"] = [losowy_string(s.rng) for _ in range(s.rng.randint(0, 3))]
            procs = losowe_procesy(s.rng, wrogo=s.rng.random() < 0.15)
            saferun_map = {}
            for p in procs:
                if s.rng.random() < 0.1:
                    saferun_map[p[0]] = s.rng.choice([p[0], -1, 0, None])
            # list_procs zawsze daje (int, int, float, str); wejscia lamiace ten
            # kontrakt sa oznaczane jako NISKIE, bo nie da sie ich dostac z `ps`
            wg_kontraktu = all(isinstance(p[0], int) and isinstance(p[1], int)
                               and isinstance(p[2], float) and isinstance(p[3], str)
                               for p in procs)
            try:
                out = guard.pick_targets(cfg, procs, saferun_map)
            except Exception as e:
                s.blad({"procs": procs[:4], "cpu_min": cfg["cpu_min_percent"],
                        "saferun": dict(list(saferun_map.items())[:3])}, e,
                       "WYSOKA" if wg_kontraktu else "NISKA")
                continue
            if not isinstance(out, list):
                s.bzdura(procs[:4], "zwrocono %s zamiast listy" % type(out).__name__, "WYSOKA",
                         klucz="zly-typ-wyniku")
                continue
            for t in out:
                if not (isinstance(t, tuple) and len(t) == 4):
                    s.bzdura(t, "element wyniku nie jest 4-krotka", "WYSOKA", klucz="nie-4-krotka")
                    continue
                pid, cpu, comm, pgid = t
                if isinstance(pid, int) and pid <= 1:
                    s.bzdura(t, "na liscie celow PID <= 1 (%r) - kandydat do sygnalu w init/jadro"
                             % (pid,), "WYSOKA", klucz="pid<=1")
                if isinstance(cpu, float) and math.isnan(cpu) and pid not in saferun_map:
                    s.bzdura(t, "proces z CPU = NaN przeszedl prog cpu_min_percent i trafil "
                                "na liste do zapauzowania", "SREDNIA", klucz="nan-przechodzi-prog")
            cpu_list = [t[1] for t in out if isinstance(t[1], (int, float))
                        and not (isinstance(t[1], float) and math.isnan(t[1]))]
            if cpu_list != sorted(cpu_list, reverse=True):
                s.bzdura(cpu_list[:8], "wynik nie jest posortowany malejaco po CPU (NaN w CPU "
                                       "rozbija sortowanie - najgoretszy proces przestaje byc pierwszy)",
                         "NISKA", klucz="brak-sortowania")
    finally:
        guard.proc_age_seconds, guard.pierwszoplanowy_na_tty, guard.full_args = stare
    s.koniec()


# ---------------------------------------------------------------- 6. args_bez_sciezek

def fuzz_args_bez_sciezek(seed, n):
    s = Sesja("guard.args_bez_sciezek", seed)
    stary = guard.full_args
    proby = [
        "", "   ", "\x00", "ffmpeg -i /Users/x/wideo/rec.mkv -c:v libx265 out.mkv",
        "node /Users/x/.vscode/extensions/server.js", "/bin/sleep 10",
        "A" * 100000, EMOJI * 100, STEROWNE, "python3 " + "../" * 5000 + "a.mp4",
    ]
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            wej = proby[i] if i < len(proby) else losowy_string(s.rng)
            guard.full_args = lambda pid, _w=wej: _w
            try:
                out = guard.args_bez_sciezek(s.rng.randint(-5, 99999))
            except Exception as e:
                s.blad(wej, e)
                continue
            if not isinstance(out, str):
                s.bzdura(wej, "zwrocono %s zamiast str" % type(out).__name__, "WYSOKA",
                         klucz="zly-typ-wyniku")
            elif out != out.lower():
                s.bzdura(wej, "wynik nie jest w calosci malymi literami", "NISKA", klucz="wielkosc-liter")
    finally:
        guard.full_args = stary
    s.koniec()


# ---------------------------------------------------------------- 7. wykryj_twardy_pad

HB = os.path.join(TMP, "heartbeat")
CLEAN = os.path.join(TMP, "clean_stop")
HIST = os.path.join(TMP, "history.csv")
EVENTS = os.path.join(TMP, "events.log")
BOOT = int(time.time()) - 3600      # system wstal godzine temu


def fuzz_wykryj_twardy_pad(seed, n):
    s = Sesja("guard.wykryj_twardy_pad", seed)
    stary_boot, stary_log = guard.boot_time, guard.log
    guard.boot_time = lambda: BOOT
    guard.log = lambda msg: None
    warianty = [
        None,                                        # brak pliku
        "",                                          # pusty
        "   \n",
        str(BOOT - 600),                             # klasyczny twardy pad
        "%d %s" % (BOOT - 600, time.strftime("%Y-%m-%d %H:%M:%S")),
        str(BOOT + 600),                             # puls z przyszlosci
        "0",                                         # sprzed 1970
        "-1e18",
        "nan",
        "inf",
        "-inf",
        "1e400",
        "9" * 400,
        "\x00\x01\xff\xfe",
        "smieci bez liczby",
        "2026-08-01 12:00:00",                       # stary format tekstowy
        "1970-01-01 00:00:00",
        "9999-12-31 23:59:59",
        "%d" % (BOOT - 40 * 86400),                  # implausibly old
        "%d obciete" % (BOOT - 600),
    ]
    hist_warianty = [
        None,
        "",
        "time,thermal_state,chip_C\n",
        "time,thermal_state,chip_C\n2026-08-01 10:00:00,nominal,55.0\n",
        "\x00\xff" * 100,
        "a,b\n" + "x" * 100000 + "\n",
        ",,,\n,,,\n",
        "time,\n" + "\n".join("," * i for i in range(50)),
    ]
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            hb = warianty[i] if i < len(warianty) else (
                losowy_string(s.rng) if s.rng.random() < 0.5
                else str(s.rng.choice([BOOT - 600, BOOT + 1, 0, -1, 1e18])))
            czysty = s.rng.random() < 0.3
            hv = s.rng.choice(hist_warianty)
            # EVENTS tez: kazdy przypadek fuzzera ma byc NIEZALEZNY. Bez tego drugi
            # przypadek z tym samym pulsem trafia w deduplikacje twardego padu
            # (guard.pad_juz_zapisany, od 2.1.9) i oracle bledy odczytuje to jako
            # "pad przeoczony" - a to jest dokladnie zamierzone zachowanie.
            for p in (HB, CLEAN, HIST, EVENTS):
                if os.path.exists(p):
                    os.unlink(p)
            if hb is not None:
                with open(HB, "wb") as f:
                    f.write(hb.encode("utf-8", "surrogateescape"))
            if czysty:
                with open(CLEAN, "w") as f:
                    f.write("x")
                os.utime(CLEAN, (BOOT - 500, BOOT - 500))
            if hv is not None:
                with open(HIST, "wb") as f:
                    f.write(hv.encode("utf-8", "surrogateescape"))
            wej = {"heartbeat": hb, "clean_stop": czysty, "history": skroc(hv, 60)}
            try:
                r = guard.wykryj_twardy_pad()
            except Exception as e:
                s.blad(wej, e)
                continue
            if r is not None and not isinstance(r, dict):
                s.bzdura(wej, "zwrocono %s zamiast dict/None" % type(r).__name__, "WYSOKA",
                         klucz="zly-typ-wyniku")
            # oracle: jednoznaczny twardy pad MUSI zostac wykryty
            if hb is not None and not czysty:
                try:
                    epoch = float(hb.split()[0])
                except Exception:
                    epoch = None
                if (epoch is not None and math.isfinite(epoch)
                        and BOOT - 30 * 86400 < epoch < BOOT and r is None):
                    s.bzdura(wej, "puls %r jest sprzed bootu i nie ma clean_stop, a twardy pad "
                                  "NIE zostal zaraportowany" % (hb,), "WYSOKA", klucz="pad-przeoczony")
                if (epoch is not None and not math.isfinite(epoch) and r is None
                        and hb.strip().lower().startswith("nan")):
                    s.bzdura(wej, "puls 'nan' cicho unieszkodliwia detekcje padu "
                                  "(funkcja wychodzi przez wlasny except)", "NISKA", klucz="nan-puls")
    finally:
        guard.boot_time, guard.log = stary_boot, stary_log
        for p in (HB, CLEAN, HIST, EVENTS):
            if os.path.exists(p):
                os.unlink(p)
    s.koniec()


# ---------------------------------------------------------------- 8. statystyki_dnia

LOG = os.path.join(TMP, "guard.log")

# Wpisy budujemy Z TYCH SAMYCH SLOWNIKOW, ktorych uzywa guard - dzieki temu test
# nie zestarzeje sie przy poprawce tlumaczen.
K_PAUZA = "PAUSED %s (pid %d, %.0f%% CPU) - %s"
K_WZNOW = "RESUMED %s (pid %d) - %s"
K_UBICIE = "TERMINATED (SIGTERM) %s (pid %d) - %s"
K_ZAPOWIEDZ = "PAUSE >%d min - terminating job %s (pid %s)"


def _wpis(lang, klucz, args):
    return (guard.DICTS.get(lang, {}).get(klucz, klucz)) % args


WPISY = {}
for _l in ("en", "pl", "ru", "zh", "es"):
    WPISY[_l] = {
        "pauza": _wpis(_l, K_PAUZA, ("ffmpeg", 1, 99, "chip 90 C")),
        "wznow": _wpis(_l, K_WZNOW, ("ffmpeg", 1, "cooled down")),
        "ubicie": _wpis(_l, K_UBICIE, ("ffmpeg", 1, "chip 95 C")),
        "zapowiedz": _wpis(_l, K_ZAPOWIEDZ, (45, "ffmpeg", 1)),
    }


TRIGGERY = ("PAUZA ", "PAUSED ", "WZNOWIONE", "RESUMED", "SIGTERM",
            "koncze zadanie", "terminating job")


def fuzz_statystyki_dnia(seed, n):
    s = Sesja("guard.statystyki_dnia", seed)
    dzis = time.strftime("%Y-%m-%d")
    smieci = [
        "", "\n", "\x00\xff smieci", "linia bez daty", "2020-01-01 PAUSED x",
        dzis + " " * 5000 + "PAUSED", "A" * 1000000, dzis + " PAUSED  RESUMED  SIGTERM",
    ]
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            linie = []
            oczek = {"pauses": 0, "resumes": 0, "kills": 0}
            zapowiedzi = 0
            zatrute = False        # smieci, ktore SAME zawieraja slowo-klucz
            lang = list(WPISY)[i % 5] if i < 40 else s.rng.choice(list(WPISY))
            for _ in range(s.rng.randint(0, 20)):
                r = s.rng.random()
                if r < 0.35:
                    linie.append("%s 10:00:00  %s" % (dzis, WPISY[lang]["pauza"]))
                    oczek["pauses"] += 1
                elif r < 0.55:
                    linie.append("%s 10:00:00  %s" % (dzis, WPISY[lang]["wznow"]))
                    oczek["resumes"] += 1
                elif r < 0.70:
                    linie.append("%s 10:00:00  %s" % (dzis, WPISY[lang]["ubicie"]))
                    oczek["kills"] += 1
                elif r < 0.78:
                    linie.append("%s 10:00:00  %s" % (dzis, WPISY[lang]["zapowiedz"]))
                    zapowiedzi += 1
                else:
                    x = s.rng.choice(smieci)
                    linie.append(x)
                    zatrute = zatrute or any(w in x for w in TRIGGERY)
            if i < len(smieci):
                linie.append(smieci[i])
                zatrute = zatrute or any(w in smieci[i] for w in TRIGGERY)
            tresc = "\n".join(linie) + "\n"
            with open(LOG, "wb") as f:
                f.write(tresc.encode("utf-8", "surrogateescape"))
            try:
                st = guard.statystyki_dnia()
            except Exception as e:
                s.blad(skroc(tresc, 200), e)
                continue
            if not isinstance(st, dict) or set(st) != {"pauses", "resumes", "kills"}:
                s.bzdura(skroc(tresc, 200), "zwrocono %r" % (st,), "WYSOKA", klucz="zly-typ-wyniku")
                continue
            wej = {"jezyk_logu": lang, "log": skroc(tresc, 160)}
            if st["pauses"] < oczek["pauses"]:
                s.bzdura(wej,
                         "jezyk %s: policzono %d pauz zamiast %d - funkcja szuka tylko "
                         "'PAUZA '/'PAUSED ', wiec w ru/zh/es statystyki dnia w pasku sa ZEROWE"
                         % (lang, st["pauses"], oczek["pauses"]), "SREDNIA", klucz="pauzy-jezyki")
            if st["resumes"] < oczek["resumes"]:
                s.bzdura(wej,
                         "jezyk %s: policzono %d wznowien zamiast %d (szukane sa tylko "
                         "'WZNOWIONE'/'RESUMED')" % (lang, st["resumes"], oczek["resumes"]),
                         "SREDNIA", klucz="wznowienia-jezyki")
            if st["kills"] < oczek["kills"]:
                s.bzdura(wej, "jezyk %s: policzono %d ubic zamiast %d"
                         % (lang, st["kills"], oczek["kills"]), "SREDNIA", klucz="ubicia-jezyki")
            if zapowiedzi and not zatrute and st["pauses"] > oczek["pauses"]:
                s.bzdura(wej,
                         "jezyk %s: zapowiedz ubicia ('PAUZA >45 min - koncze zadanie') zostala "
                         "policzona jako PAUZA (%d zamiast %d) - kolejnosc elif sprawia, ze wpis "
                         "o ubiciu nigdy nie trafia do licznika kills"
                         % (lang, st["pauses"], oczek["pauses"]), "SREDNIA",
                         klucz="zapowiedz-jako-pauza")
    finally:
        if os.path.exists(LOG):
            os.unlink(LOG)
    s.koniec()


# ---------------------------------------------------------------- 9. _loguj_awake

def fuzz_loguj_awake(seed, n):
    s = Sesja("guard._loguj_awake", seed)
    stary_log = guard.log
    guard.log = lambda msg: None
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            guard._awake_log.update({"ostatni": "", "kiedy": 0.0, "pominiete": 0}
                                    if s.rng.random() < 0.2 else {})
            msg = losowa_wartosc(s.rng) if s.rng.random() < 0.3 else losowy_string(s.rng)
            try:
                guard._loguj_awake(msg)
            except Exception as e:
                s.blad(msg, e, "NISKA")
    finally:
        guard.log = stary_log
    s.koniec()


# ---------------------------------------------------------------- 10. heat.stuck

def fuzz_heat_stuck(seed, n):
    s = Sesja("heat.stuck", seed)
    stary = heat.sh
    wyjscia_ps = [
        "",
        "123 T   01:00 ffmpeg",
        "123 T\n",                                    # za malo pol
        "  1 TXs  10-01:02:03 kernel_task\n2 S 00:01 launchd\n",
        "-1 T 00:01 " + EMOJI + "\n",
        "abc T 00:01 x\n",
        "999999999999999999999 T 00:01 " + "A" * 5000 + "\n",
        "\x00\xff T 00:01 x\n",
        "\n".join("%d T 00:%02d proc%d" % (i, i % 60, i) for i in range(2000)),
    ]
    stany = [
        None, "", "null", "[]", "\"abc\"", "{}", '{"paused": {}}',
        '{"paused": {"123": {"comm": "ffmpeg"}}}',
        '{"paused": [{"pid": 123}]}',
        '{"paused": ["123"]}',
        '{"paused": 5}',
        '{"paused": [1,2,3]}',
        '{"paused": null}',
        "{obciete",
        "\x00\xff",
    ]
    try:
        for i in range(n):
            if s.czas_minal():
                break
            s.n += 1
            ps = wyjscia_ps[i] if i < len(wyjscia_ps) else s.rng.choice(wyjscia_ps)
            heat.sh = lambda cmd, timeout=15, _o=ps: _o
            st_json = stany[i % len(stany)] if i < 40 else s.rng.choice(stany)
            for plik in ("state.json", "status.json"):
                p = os.path.join(TMP, plik)
                if st_json is None:
                    if os.path.exists(p):
                        os.unlink(p)
                else:
                    with open(p, "wb") as f:
                        f.write(st_json.encode("utf-8", "surrogateescape"))
            wej = {"ps": skroc(ps, 80), "state.json": st_json}
            try:
                with redirect_stdout(io.StringIO()):
                    rc = heat.stuck()
            except Exception as e:
                s.blad(wej, e)
                continue
            if rc != 0:
                s.bzdura(wej, "zwrocono kod %r zamiast 0" % (rc,), "NISKA", klucz="zly-kod")
    finally:
        heat.sh = stary
        for plik in ("state.json", "status.json"):
            p = os.path.join(TMP, plik)
            if os.path.exists(p):
                os.unlink(p)
    s.koniec()


# ---------------------------------------------------------------- 11. chip_juz_goracy

STATUS = os.path.join(TMP, "status.json")

STATUSY = [
    None,                                    # brak pliku
    "",
    "null",
    "[]",
    "[1, 2, 3]",
    '"goraco"',
    "true",
    "123",
    "{",
    "{}",
    '{"level": 0}',
    '{"level": 3}',
    '{"level": "3"}',
    '{"level": null}',
    '{"level": [2]}',
    '{"level": 1, "chip_c": 90}',
    '{"level": 1, "chip_c": "90"}',
    '{"level": 1, "chip_c": NaN}',
    '{"level": 1, "chip_c": Infinity}',
    '{"level": 1, "chip_c": 90, "thresholds": {"pause": 85}}',
    '{"level": 1, "chip_c": 90, "thresholds": []}',
    '{"level": 1, "chip_c": 90, "thresholds": [1]}',
    '{"level": 1, "chip_c": 90, "thresholds": "85"}',
    '{"level": 1, "chip_c": 90, "thresholds": {"pause": null}}',
    '{"level": 1, "chip_c": 90, "thresholds": {"pause": "goraco"}}',
    '{"level": 1, "chip_c": 90, "thresholds": {"pause": 0}}',
    '{"level": 1, "chip_c": 1e400}',
    "\x00\xff\xfe",
]


def fuzz_chip_juz_goracy(seed, n):
    s = Sesja("safe-run.chip_juz_goracy", seed)
    for i in range(n):
        if s.czas_minal():
            break
        s.n += 1
        if i < len(STATUSY):
            tresc = STATUSY[i]
        else:
            d = {}
            for k in ("level", "chip_c", "thresholds"):
                if s.rng.random() < 0.8:
                    d[k] = losowa_wartosc(s.rng)
            try:
                tresc = json.dumps(d, allow_nan=True)
            except Exception:
                continue
        if os.path.exists(STATUS):
            os.unlink(STATUS)
        if tresc is not None:
            with open(STATUS, "wb") as f:
                f.write(tresc.encode("utf-8", "surrogateescape"))
        try:
            r = saferun.chip_juz_goracy()
        except Exception as e:
            # status.json guard zapisuje atomowo (tmp + os.replace) i zawsze jako dict,
            # wiec takie tresci biora sie z recznej edycji, uszkodzenia FS albo obcego
            # narzedzia - stad SREDNIA, mimo ze skutek (traceback w safe-run) jest ciezki
            s.blad(tresc, e, "SREDNIA")
            continue
        if not (isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], bool)
                and isinstance(r[1], str)):
            s.bzdura(tresc, "zwrocono %r zamiast (bool, str)" % (r,), "SREDNIA", klucz="zly-typ-wyniku")
    if os.path.exists(STATUS):
        os.unlink(STATUS)
    s.koniec()


# ---------------------------------------------------------------- 12. max_temp_since / czas_z

def fuzz_max_temp_since(seed, n):
    s = Sesja("safe-run.max_temp_since", seed)
    naglowek = "time,thermal_state,chip_C,gpu_C,battery_C\n"
    warianty = [
        "", naglowek, naglowek + "2026-08-01 10:00:00,nominal,80.5,,\n",
        naglowek + "2026-08-01 10:00:00,nominal,nan,,\n",
        naglowek + "2026-08-01 10:00:00,nominal,inf,,\n",
        naglowek + "2026-08-01 10:00:00,nominal,1e400,,\n",
        naglowek + ",,,\n",
        naglowek + "zla data,nominal,80,,\n",
        naglowek + "2026-08-01 10:00:00,nominal," + "9" * 100000 + ",,\n",
        "\x00\xff" * 500,
        naglowek + "\n".join("2026-08-01 10:00:%02d,nominal,%d,," % (i % 60, i) for i in range(500)),
    ]
    for i in range(n):
        if s.czas_minal():
            break
        s.n += 1
        tresc = warianty[i] if i < len(warianty) else s.rng.choice(warianty)
        with open(HIST, "wb") as f:
            f.write(tresc.encode("utf-8", "surrogateescape"))
        t0 = s.rng.choice([0, time.time(), time.time() - 10 ** 9, -1, float("nan")])
        try:
            v = saferun.max_temp_since(t0)
        except Exception as e:
            s.blad({"csv": skroc(tresc, 80), "t0": t0}, e)
            continue
        if v is not None and (not isinstance(v, float) or not math.isfinite(v)):
            s.bzdura({"csv": skroc(tresc, 80), "t0": t0},
                     "zwrocono %r (nie-skonczona temperatura trafia do komunikatu)" % (v,),
                     "SREDNIA", klucz="niesk")
    if os.path.exists(HIST):
        os.unlink(HIST)
    s.koniec()


def fuzz_czas_z(seed, n):
    s = Sesja("thermal-report.czas_z", seed)
    stale = ["", "2026-08-01 10:00:00", "2026-13-45 99:99:99", "0000-00-00 00:00:00",
             "9999-12-31 23:59:59", "1969-12-31 23:59:59", "\x00", "A" * 100000,
             None, 123, [], {}, b"2026-08-01 10:00:00", EMOJI]
    for i in range(n):
        if s.czas_minal():
            break
        s.n += 1
        x = stale[i] if i < len(stale) else losowa_wartosc(s.rng)
        try:
            v = treport.czas_z(x)
        except Exception as e:
            s.blad(x, e)
            continue
        if not isinstance(v, (int, float)):
            s.bzdura(x, "zwrocono %r zamiast liczby" % (v,), "SREDNIA", klucz="zly-typ-wyniku")
    s.koniec()


# ---------------------------------------------------------------- raport koncowy

def wypisz_raport(seed, n):
    print("=" * 78)
    print("FUZZING coffee-paladin - ziarno %s, %d losowych wejsc na funkcje" % (seed, n))
    print("katalog roboczy (TG_BASE): %s" % TMP)
    print("=" * 78)
    print("\n%-34s %8s %8s %8s %8s" % ("funkcja", "przebieg", "sek", "wyjatki", "bzdury"))
    print("-" * 78)
    for nazwa, d in PRZEBIEGI.items():
        print("%-34s %8d %8.2f %8d %8d"
              % (nazwa, d["przebiegi"], d["sekundy"], d["bledy"], d["bzdury"]))

    print("\n" + "=" * 78)
    lista = list(ZNALEZISKA.values())
    if not lista:
        print("ZNALEZISKA: brak - wszystkie funkcje przetrwaly ostrzal.")
    else:
        print("ZNALEZISKA (%d roznych; liczba w nawiasie = ile wejsc je wywolalo):" % len(lista))
        kolejnosc = {"WYSOKA": 0, "SREDNIA": 1, "NISKA": 2}
        for i, z in enumerate(sorted(lista, key=lambda x: (kolejnosc.get(x["powaga"], 9),
                                                           x["funkcja"])), 1):
            print("\n%d. [%s] %s  (x%d)" % (i, z["powaga"], z["funkcja"], z["ile"]))
            print("   co: %s" % z["opis"])
            print("   wejscie: %s" % z["wejscie"])
    print("\n" + "=" * 78)
    czyste = [n_ for n_ in PRZEBIEGI if n_ in OK_FUNKCJE]
    print("BEZ ZARZUTU (%d): %s" % (len(czyste), ", ".join(czyste) if czyste else "-"))
    print("=" * 78)
    return 1 if any(z["powaga"] == "WYSOKA" for z in lista) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260802)
    ap.add_argument("--n", type=int, default=250)
    a = ap.parse_args()
    seed, n = a.seed, a.n
    random.seed(seed)

    try:
        fuzz_load_cfg(seed, n)
        fuzz_severity(seed, n, wrogo=False)
        fuzz_severity(seed, n, wrogo=True)
        fuzz_normalize(seed, max(n, 300), guard, "guard.normalize_batt_temp")
        fuzz_normalize(seed, max(n, 300), heat, "heat.normalize_batt_temp")
        fuzz_cpu_z_dziecmi(seed, n)
        fuzz_pick_targets(seed, n)
        fuzz_args_bez_sciezek(seed, n)
        fuzz_wykryj_twardy_pad(seed, n)
        fuzz_statystyki_dnia(seed, n)
        fuzz_loguj_awake(seed, n)
        fuzz_heat_stuck(seed, n)
        fuzz_chip_juz_goracy(seed, n)
        fuzz_max_temp_since(seed, n)
        fuzz_czas_z(seed, n)
        rc = wypisz_raport(seed, n)
    except Exception:
        traceback.print_exc()
        rc = 2
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
