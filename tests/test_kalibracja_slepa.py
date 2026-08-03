#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slepy czujnik nie moze zamrozic kalibracji na maszynie, ktora jej najbardziej potrzebuje.

Defekt zlapany na Neo 03.08.2026 przy pierwszej instalacji 2.2.2 (MacBook Air, bezwentylatorowy):
demon wystartowal zaraz po `install.sh`, ktory kompilowal pasek, wiec macmon nie wyrobil sie
z probkowaniem. `chip_sensor` wyszlo False, `fan_count` 0 — a warunek kalibracji wymaga OBU.
Skutek: Air dostal progi wentylatorowe 85/76/90 zamiast 78/70/88 i limit pauzy 45 min zamiast 120.
Minute pozniej `heat` pokazywal juz temperature chipa, wiec maszyna wygladala zdrowo.

Czego ten test pilnuje:
1. slepy czujnik NIE zapisuje `calibrated_for` (kalibracja ma sie powtorzyc przy nastepnym starcie),
2. po odzyskaniu czujnika Air DOSTAJE progi bezwentylatorowe,
3. slepy przebieg mowi o tym w logu (poprzednio pisal "thresholds defaults OK"),
4. przypadki PRZECIWNE: Mac z wentylatorami nietkniety, reczne progi uzytkownika swiete,
   maszyna raz skalibrowana nie kalibruje sie drugi raz.

Uruchomienie:  python3 tests/test_kalibracja_slepa.py
"""
import importlib.machinery
import json
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="kalibracja_slepa_")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

zaliczone = wszystkie = 0

AIR_SLEPY = {"model_id": "Mac14,2", "chip": "Apple M2", "model_name": "MacBook Air",
             "fan_count": 0, "chip_sensor": False}
AIR_WIDZI = {"model_id": "Mac14,2", "chip": "Apple M2", "model_name": "MacBook Air",
             "fan_count": 0, "chip_sensor": True}
PRO_WIDZI = {"model_id": "Mac16,8", "chip": "Apple M4 Pro", "model_name": "MacBook Pro",
             "fan_count": 2, "chip_sensor": True, "p_cores": 10, "e_cores": 4, "ram_gb": 48}


def test(nazwa, warunek, szczegol=""):
    global zaliczone, wszystkie
    wszystkie += 1
    if warunek:
        zaliczone += 1
        print("  [PASS] %s" % nazwa)
    else:
        print("  [FAIL] %s  -> %s" % (nazwa, szczegol))


def swiezy_config(**klucze):
    """Config jak po swiezej instalacji; `dry_run` jawny, zeby nie mieszac sie z migracja."""
    d = {"dry_run": False}
    d.update(klucze)
    with open(g.CFG_PATH, "w") as f:
        json.dump(d, f)


def z_dysku():
    with open(g.CFG_PATH) as f:
        return json.load(f)


def kalibruj(hw):
    """Tak, jak robi to demon przy starcie: DEFAULTS + to, co na dysku."""
    cfg = dict(g.DEFAULTS)
    cfg.update(z_dysku())
    wynik = g.auto_calibrate(cfg, hw)
    return wynik, z_dysku()


def log_ogon(n=1):
    try:
        with open(os.path.join(BASE, "guard.log")) as f:
            return f.read().strip().split("\n")[-n:]
    except Exception:
        return []


print("1. slepy czujnik: znacznik NIE moze zostac zapisany")
swiezy_config()
_, c = kalibruj(AIR_SLEPY)
test("calibrated_for nie zapisany przy chip_sensor=False",
     "calibrated_for" not in c, "w configu: %s" % c.get("calibrated_for"))
test("progi nietkniete (nie udajemy kalibracji)",
     "soc_pause_c" not in c, "soc_pause_c=%s" % c.get("soc_pause_c"))
test("log MOWI o odlozonej kalibracji, nie 'defaults OK'",
     any("CALIBRATION DEFERRED" in w for w in log_ogon(3)), log_ogon(1))
test("stary, mylacy komunikat nie pada przy slepym czujniku",
     not any("thresholds defaults OK" in w for w in log_ogon(3)), log_ogon(1))

print("\n2. czujnik wraca przy nastepnym starcie — Air dostaje swoje progi")
_, c = kalibruj(AIR_WIDZI)
test("soc_pause_c = 78", c.get("soc_pause_c") == 78.0, c.get("soc_pause_c"))
test("soc_resume_c = 70", c.get("soc_resume_c") == 70.0, c.get("soc_resume_c"))
test("soc_kill_c = 88", c.get("soc_kill_c") == 88.0, c.get("soc_kill_c"))
test("max_pause_minutes = 120", c.get("max_pause_minutes") == 120, c.get("max_pause_minutes"))
test("fan_check wylaczony (alarm wentylatorow na Airze jest zawsze falszywy)",
     c.get("fan_check") is False, c.get("fan_check"))
test("znacznik zapisany dopiero teraz, z sensor=True",
     c.get("calibrated_for", "").endswith("|sensor=True"), c.get("calibrated_for"))

print("\n3. przypadek przeciwny: raz skalibrowany Mac nie kalibruje sie drugi raz")
c_przed = z_dysku()
swiezy_config(**c_przed)                      # ten sam stan, kolejny start demona
_, c_po = kalibruj(AIR_WIDZI)
test("drugi przebieg nic nie zmienia", c_po == c_przed,
     "roznica: %s" % {k: (c_przed.get(k), c_po.get(k))
                      for k in set(c_przed) | set(c_po) if c_przed.get(k) != c_po.get(k)})

print("\n4. przypadek przeciwny: Mac z wentylatorami nie dostaje progow Aira")
swiezy_config()
_, c = kalibruj(PRO_WIDZI)
test("progi zostaja domyslne", "soc_pause_c" not in c, c.get("soc_pause_c"))
test("fan_check zostaje wlaczony", c.get("fan_check") is not False, c.get("fan_check"))
test("max_pause_minutes bez zmian", "max_pause_minutes" not in c, c.get("max_pause_minutes"))
test("znacznik zapisany (czujnik dziala)",
     c.get("calibrated_for", "").endswith("|fans=2|sensor=True"), c.get("calibrated_for"))

print("\n5. przypadek przeciwny: RECZNE progi uzytkownika sa swiete")
swiezy_config(soc_pause_c=92.0, soc_resume_c=84.0)
_, c = kalibruj(AIR_WIDZI)
test("reczny prog pauzy nietkniety", c.get("soc_pause_c") == 92.0, c.get("soc_pause_c"))
test("reczny prog wznowienia nietkniety", c.get("soc_resume_c") == 84.0, c.get("soc_resume_c"))
test("fan_check i tak wylaczony (to nie prog, to sens alarmu)",
     c.get("fan_check") is False, c.get("fan_check"))

print("\n6. slepy czujnik nie rozluznia praw config.json")
swiezy_config()
os.chmod(g.CFG_PATH, 0o600)
kalibruj(AIR_SLEPY)
test("prawa 0600 zachowane (w configu siedzi temat ntfy)",
     oct(os.stat(g.CFG_PATH).st_mode & 0o777) == "0o600",
     oct(os.stat(g.CFG_PATH).st_mode & 0o777))

print("\n7. migracja dry_run dziala TAKZE przy slepym czujniku")
with open(g.CFG_PATH, "w") as f:                       # config sprzed v1.3: bez dry_run
    json.dump({"lang": "pl"}, f)
wynik, c = kalibruj(AIR_SLEPY)
test("dry_run dopisany jawnie", c.get("dry_run") is True, c.get("dry_run"))
test("demon dostaje sygnal 'watchonly'", wynik == "watchonly", wynik)
test("ale znacznika nadal nie ma", "calibrated_for" not in c, c.get("calibrated_for"))

print("\n8. RECZNY prog ubicia przezywa kalibracje (zarzut Codeksa 03.08)")
swiezy_config()
kalibruj(AIR_SLEPY)                       # slepy start, znacznika brak
c = z_dysku()
c["soc_kill_c"] = 95.0                    # uzytkownik podnosi SAM prog ubicia
with open(g.CFG_PATH, "w") as f:
    json.dump(c, f)
_, c = kalibruj(AIR_WIDZI)                # czujnik wraca
test("soc_kill_c=95 nie zostal nadpisany przez 88", c.get("soc_kill_c") == 95.0,
     c.get("soc_kill_c"))
test("progi pauzy tez nietkniete, skoro user ruszyl komplet",
     c.get("soc_pause_c") is None or c.get("soc_pause_c") != 78.0, c.get("soc_pause_c"))
test("fan_check i tak wylaczony (to nie prog)", c.get("fan_check") is False, c.get("fan_check"))

print("\n9. migracja starego configu nie rozluznia praw (zarzut Codeksa 03.08)")
stara_umask = os.umask(0)                 # najgorszy przypadek: umask nic nie obcina
try:
    with open(g.CFG_PATH, "w") as f:
        json.dump({"lang": "pl"}, f)      # config sprzed v1.3: bez dry_run -> ZAPIS idzie
    os.chmod(g.CFG_PATH, 0o600)
    kalibruj(AIR_SLEPY)
    prawa = oct(os.stat(g.CFG_PATH).st_mode & 0o777)
    test("config.json zostaje 0600 (siedzi w nim temat ntfy)", prawa == "0o600", prawa)
finally:
    os.umask(stara_umask)

print("\n10. hardware_info: nieudany pierwszy odczyt macmona NIE przesadza")
# Zarzut Codeksa: sekcje 1-9 wolaja `auto_calibrate` z gotowym `hw`, wiec ponowienie
# odczytu w `hardware_info` nie bylo testowane WCALE. Mutacja `max_age=0` -> `max_age`
# domyslny przechodzila 22/22. Tu podstawiamy `run` i liczymy realne proby.
PROBA = {"n": 0}
PRAWDZIWY_RUN = g.run
MACMON_JSON = ('{"temp":{"cpu_temp_avg":55.0,"gpu_temp_avg":50.0},"fans":[],'
               '"memory":{"ram_usage":1,"ram_total":2,"swap_usage":0},"all_power":8.0}')


def run_atrapa(cmd, timeout=10):
    """macmon milczy przy pierwszych dwoch probach, potem odpowiada."""
    if cmd and "macmon" in str(cmd[0]):
        PROBA["n"] += 1
        return MACMON_JSON if PROBA["n"] >= 3 else ""
    if cmd[:1] == ["sysctl"]:
        return "8" if "cpu" in cmd[-1] else "17179869184"
    if cmd[:1] == ["system_profiler"]:
        return "Model Name: MacBook Air\nSerial Number (system): TEST123\n"
    if cmd[:1] == ["ioreg"]:
        return '"CycleCount" = 10\n"PermanentFailureStatus" = 0\n'
    if cmd[:1] == ["sw_vers"]:
        return "26.0"
    return ""


g.run = run_atrapa
g._soc_cache["t"] = None
g._soc_cache["val"] = None
try:
    hw = g.hardware_info()
    test("czujnik odzyskany mimo dwoch pustych odczytow", hw.get("chip_sensor") is True,
         "chip_sensor=%s po %d probach" % (hw.get("chip_sensor"), PROBA["n"]))
    test("macmon pytany WIECEJ niz raz (ponowienie realnie dziala)", PROBA["n"] >= 3,
         "prob: %d" % PROBA["n"])
    test("fan_count=0 przy pustej liscie wentylatorow", hw.get("fan_count") == 0,
         hw.get("fan_count"))

    # przypadek przeciwny: macmon milczy ZAWSZE - nie wolno kreccic w nieskonczonosc
    PROBA["n"] = 0
    g.run = lambda cmd, timeout=10: ("" if (cmd and "macmon" in str(cmd[0]))
                                     else run_atrapa(cmd, timeout))
    g._soc_cache["t"] = None
    g._soc_cache["val"] = None
    t0 = time.monotonic()
    hw2 = g.hardware_info()
    trwalo = time.monotonic() - t0
    test("trwale milczacy macmon konczy sie brakiem czujnika, nie zawieszeniem",
         hw2.get("chip_sensor") is False, hw2.get("chip_sensor"))
    test("ponowienia mieszcza sie w budzecie (<15 s)", trwalo < 15.0, "%.1f s" % trwalo)
finally:
    g.run = PRAWDZIWY_RUN
    g._soc_cache["t"] = None
    g._soc_cache["val"] = None

print("\nNIEPOKRYTE (uczciwie): dokonczenie kalibracji w PETLI demona, gdy czujnik wraca")
print("  juz po starcie. Sprawdzone rozumowaniem i recznie; nie da sie tego wymusic na")
print("  maszynie, na ktorej macmon dziala, bo demon nigdy nie wchodzi w stan slepy.")

shutil.rmtree(BASE, ignore_errors=True)
print("\n%d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
