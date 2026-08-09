#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure a blind chip sensor does not freeze calibration on the Mac that needs it most.

On first install for a fanless MacBook Air, the daemon can start right after `install.sh`
while the menu bar is still compiling. macmon may not return a chip sample yet, so
`chip_sensor` becomes False and `fan_count` is 0, while calibration requires both. The
result was fan-cooled thresholds 85/76/90 instead of fanless 78/70/88, and a 45 min pause
limit instead of 120. A minute later `heat` could show chip temperature, making the Mac
look healthy.

This test verifies:
1. a blind sensor does not write `calibrated_for`, so calibration retries on next start,
2. once the sensor returns, Air receives fanless thresholds,
3. the blind pass logs the deferral instead of "thresholds defaults OK",
4. countercases: fan-cooled Macs stay untouched, manual user thresholds are sacred, and
   an already calibrated machine does not calibrate a second time.

Run with:  python3 tests/test_kalibracja_slepa.py
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
    """Write a fresh-install config with explicit `dry_run` to avoid migration noise."""
    d = {"dry_run": False}
    d.update(klucze)
    with open(g.CFG_PATH, "w") as f:
        json.dump(d, f)


def z_dysku():
    with open(g.CFG_PATH) as f:
        return json.load(f)


def kalibruj(hw):
    """Run calibration as the daemon does on startup: DEFAULTS plus disk config."""
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


print("1. blind sensor: marker must NOT be written")
swiezy_config()
_, c = kalibruj(AIR_SLEPY)
test("calibrated_for not written with chip_sensor=False",
     "calibrated_for" not in c, "in config: %s" % c.get("calibrated_for"))
test("thresholds untouched (do not pretend calibration happened)",
     "soc_pause_c" not in c, "soc_pause_c=%s" % c.get("soc_pause_c"))
test("log SAYS calibration was deferred, not 'defaults OK'",
     any("CALIBRATION DEFERRED" in w for w in log_ogon(3)), log_ogon(1))
test("old misleading message is not emitted with blind sensor",
     not any("thresholds defaults OK" in w for w in log_ogon(3)), log_ogon(1))

print("\n2. sensor returns on next start - Air gets its thresholds")
_, c = kalibruj(AIR_WIDZI)
test("soc_pause_c = 78", c.get("soc_pause_c") == 78.0, c.get("soc_pause_c"))
test("soc_resume_c = 70", c.get("soc_resume_c") == 70.0, c.get("soc_resume_c"))
test("soc_kill_c = 88", c.get("soc_kill_c") == 88.0, c.get("soc_kill_c"))
test("max_pause_minutes = 120", c.get("max_pause_minutes") == 120, c.get("max_pause_minutes"))
test("fan_check disabled (fan alarm on Air is always false)",
     c.get("fan_check") is False, c.get("fan_check"))
test("marker written only now, with sensor=True",
     c.get("calibrated_for", "").endswith("|sensor=True"), c.get("calibrated_for"))

print("\n3. opposite case: once-calibrated Mac does not calibrate twice")
c_przed = z_dysku()
swiezy_config(**c_przed)                      # same state, next daemon start
_, c_po = kalibruj(AIR_WIDZI)
test("second pass changes nothing", c_po == c_przed,
     "difference: %s" % {k: (c_przed.get(k), c_po.get(k))
                      for k in set(c_przed) | set(c_po) if c_przed.get(k) != c_po.get(k)})

print("\n4. opposite case: Mac with fans does not get Air thresholds")
swiezy_config()
_, c = kalibruj(PRO_WIDZI)
test("thresholds stay default", "soc_pause_c" not in c, c.get("soc_pause_c"))
test("fan_check stays enabled", c.get("fan_check") is not False, c.get("fan_check"))
test("max_pause_minutes unchanged", "max_pause_minutes" not in c, c.get("max_pause_minutes"))
test("marker written (sensor works)",
     c.get("calibrated_for", "").endswith("|fans=2|sensor=True"), c.get("calibrated_for"))

print("\n5. opposite case: user's MANUAL thresholds are sacred")
swiezy_config(soc_pause_c=92.0, soc_resume_c=84.0)
_, c = kalibruj(AIR_WIDZI)
test("manual pause threshold untouched", c.get("soc_pause_c") == 92.0, c.get("soc_pause_c"))
test("manual resume threshold untouched", c.get("soc_resume_c") == 84.0, c.get("soc_resume_c"))
test("fan_check disabled anyway (not a threshold, the alarm would make no sense)",
     c.get("fan_check") is False, c.get("fan_check"))

print("\n6. blind sensor does not loosen config.json permissions")
swiezy_config()
os.chmod(g.CFG_PATH, 0o600)
kalibruj(AIR_SLEPY)
test("0600 permissions preserved (config contains ntfy topic)",
     oct(os.stat(g.CFG_PATH).st_mode & 0o777) == "0o600",
     oct(os.stat(g.CFG_PATH).st_mode & 0o777))

print("\n7. dry_run migration also works with blind sensor")
with open(g.CFG_PATH, "w") as f:                       # Pre-v1.3 config, no dry_run.
    json.dump({"lang": "pl"}, f)
wynik, c = kalibruj(AIR_SLEPY)
test("dry_run added explicitly", c.get("dry_run") is True, c.get("dry_run"))
test("daemon gets 'watchonly' signal", wynik == "watchonly", wynik)
test("but marker is still absent", "calibrated_for" not in c, c.get("calibrated_for"))

print("\n8. MANUAL kill threshold survives calibration (review note 03.08)")
swiezy_config()
kalibruj(AIR_SLEPY)                       # Blind start, no marker.
c = z_dysku()
c["soc_kill_c"] = 95.0                    # User raises only the kill threshold.
with open(g.CFG_PATH, "w") as f:
    json.dump(c, f)
_, c = kalibruj(AIR_WIDZI)                # Sensor returns.
test("soc_kill_c=95 was not overwritten by 88", c.get("soc_kill_c") == 95.0,
     c.get("soc_kill_c"))
test("pause thresholds also untouched because user touched the full set",
     c.get("soc_pause_c") is None or c.get("soc_pause_c") != 78.0, c.get("soc_pause_c"))
test("fan_check disabled anyway (not a threshold)", c.get("fan_check") is False, c.get("fan_check"))

print("\n9. old config migration does not loosen permissions (review note 03.08)")
stara_umask = os.umask(0)                 # Worst case: umask does not trim anything.
try:
    with open(g.CFG_PATH, "w") as f:
        json.dump({"lang": "pl"}, f)      # Pre-v1.3 config: no dry_run means write path runs.
    os.chmod(g.CFG_PATH, 0o600)
    kalibruj(AIR_SLEPY)
    prawa = oct(os.stat(g.CFG_PATH).st_mode & 0o777)
    test("config.json stays 0600 (it contains ntfy topic)", prawa == "0o600", prawa)
finally:
    os.umask(stara_umask)

print("\n10. hardware_info: failed first macmon read is NOT decisive")
# Sections 1-9 call `auto_calibrate` with prepared `hw`, so retrying reads inside
# `hardware_info` was not tested at all. Stub `run` here and count real attempts.
PROBA = {"n": 0}
PRAWDZIWY_RUN = g.run
MACMON_JSON = ('{"temp":{"cpu_temp_avg":55.0,"gpu_temp_avg":50.0},"fans":[],'
               '"memory":{"ram_usage":1,"ram_total":2,"swap_usage":0},"all_power":8.0}')


def run_atrapa(cmd, timeout=10):
    """Return empty macmon output for two attempts, then return a sample."""
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
    test("sensor recovered despite two empty reads", hw.get("chip_sensor") is True,
         "chip_sensor=%s after %d attempts" % (hw.get("chip_sensor"), PROBA["n"]))
    test("macmon queried MORE than once (retry really works)", PROBA["n"] >= 3,
         "attempts: %d" % PROBA["n"])
    test("fan_count=0 with empty fan list", hw.get("fan_count") == 0,
         hw.get("fan_count"))

    # Countercase: if macmon is always silent, do not spin forever.
    PROBA["n"] = 0
    g.run = lambda cmd, timeout=10: ("" if (cmd and "macmon" in str(cmd[0]))
                                     else run_atrapa(cmd, timeout))
    g._soc_cache["t"] = None
    g._soc_cache["val"] = None
    t0 = time.monotonic()
    hw2 = g.hardware_info()
    trwalo = time.monotonic() - t0
    test("persistently silent macmon ends with missing sensor, not a hang",
         hw2.get("chip_sensor") is False, hw2.get("chip_sensor"))
    test("retries fit within the budget (<15 s)", trwalo < 15.0, "%.1f s" % trwalo)
finally:
    g.run = PRAWDZIWY_RUN
    g._soc_cache["t"] = None
    g._soc_cache["val"] = None

print("\nUNCOVERED (honestly): finishing calibration in the daemon LOOP when the sensor returns")
print("  after startup. Checked by reasoning and manually; it cannot be forced on")
print("  a machine where macmon works, because the daemon never enters blind mode.")

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (zaliczone, wszystkie))
sys.exit(0 if zaliczone == wszystkie else 1)
