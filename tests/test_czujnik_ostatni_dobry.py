#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A single failed macmon sample must not blind the guard.

Under full load one `macmon pipe` sample can fail. Until now the miss was cached as
"no chip sensor" for the next 10 seconds, and that has teeth:

* the daemon fell back to battery temperature alone, which reacts minutes late;
* `resume_gate` reads an unknown chip as a chip that is not holding, so a machine
  could resume frozen jobs during the very moment it was too busy to answer.

The fix keeps the last good reading for SOC_STALE_GRACE_S and marks it "stale". This
test pins the behaviour that matters: stale may TIGHTEN protection, never invent a
sensor, and never outlive its grace window.

Run with:  python3 tests/test_czujnik_ostatni_dobry.py
"""
import importlib.machinery
import os
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
g = importlib.machinery.SourceFileLoader("g", os.path.join(SRC, "guard.py")).load_module()

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s  -> %s" % (name, detail))


SAMPLE = ('{"temp":{"cpu_temp_avg":%s,"gpu_temp_avg":40.0},'
          '"fans":[{"rpm":2000}],"all_power":30.0,'
          '"memory":{"ram_usage":1073741824,"ram_total":2147483648,"swap_usage":0}}')

_answer = {"ok": True, "cpu": 92.0}
_clock = {"now": 1000.0}


def fake_run(cmd, timeout=None):
    if cmd and "macmon" in cmd[0]:
        return SAMPLE % _answer["cpu"] if _answer["ok"] else ""
    return ""


def fake_monotonic():
    return _clock["now"]


g.run = fake_run
g.time.monotonic = fake_monotonic


def _soc_good_t():
    """When the last good reading was taken, on the fake clock."""
    return g._soc_cache["good_t"]


def reset_cache():
    g._soc_cache.update({"t": None, "val": None, "good": None,
                         "good_t": None, "stale_logged": False})


print("1. A good reading is a good reading")
reset_cache()
_answer.update({"ok": True, "cpu": 92.0})
s = g.soc_sensors()
test("chip read", s is not None and s["cpu"] == 92.0, repr(s))
test("not marked stale", s is not None and not s.get("stale"), repr(s))
test("hottest point returned", g.soc_temp_c(fresh_only=True) == 92.0)

print("2. A failed sample falls back to the last good one")
_answer["ok"] = False
_clock["now"] += 20.0                      # past the 10 s cache, inside the 45 s grace
s = g.soc_sensors()
test("still has a temperature", s is not None and s["cpu"] == 92.0, repr(s))
test("marked stale", s is not None and s.get("stale") is True, repr(s))
test("age reported", s is not None and 19.0 <= s.get("stale_age_s", 0) <= 21.0, repr(s))

print("3. Stale still holds a resume back (the point of the whole thing)")
cfg = {"soc_resume_c": 76.0, "batt_pause_c": 40.0, "batt_resume_c": 36.0}
st = {}
test("hot stale chip blocks resume",
     g.resume_gate(cfg, st, 30.0, g.soc_temp_c(), "nominal") is False)

print("4. Callers that must not guess can refuse stale")
test("allow_stale=False returns nothing", g.soc_sensors(max_age=0, allow_stale=False) is None)
test("fresh_only returns nothing", g.soc_temp_c(fresh_only=True) is None)
test("cached stale is refused too", g.soc_sensors(allow_stale=False) is None)

print("5. The grace window really ends")
# Relative to the constant, not to a hardcoded number: the window was widened once already
# (a hung read costs more than the poll interval) and this test must not need editing again.
_clock["now"] += g.SOC_STALE_GRACE_S + 5.0
s = g.soc_sensors(max_age=0)
test("no reading after the grace", s is None, repr(s))
test("unknown chip again", g.soc_temp_c() is None)

print("6. Recovery restores a fresh reading")
_answer.update({"ok": True, "cpu": 70.0})
_clock["now"] += 1.0
s = g.soc_sensors(max_age=0)
test("fresh value after recovery", s is not None and s["cpu"] == 70.0, repr(s))
test("stale flag cleared", s is not None and not s.get("stale"), repr(s))

print("7. Nothing is invented when there was never a reading")
reset_cache()
_answer["ok"] = False
_clock["now"] += 5.0
test("no sensor stays no sensor", g.soc_sensors(max_age=0) is None)
test("no phantom temperature", g.soc_temp_c() is None)

print("8. A read that HANGS still lands inside the grace window")
# The first version of this test only simulated an instant empty answer, so it never
# measured the thing that actually expires the window: a failing read costs up to
# SOC_READ_TIMEOUT_S per macmon path, two paths, on top of the 15 s poll interval.
reset_cache()
_answer.update({"ok": True, "cpu": 93.0})
g.soc_sensors(max_age=0)


def slow_failing_run(cmd, timeout=None):
    if cmd and "macmon" in cmd[0]:
        _clock["now"] += g.SOC_READ_TIMEOUT_S      # the path hangs to its full budget
        return ""
    return ""


g.run = slow_failing_run
_clock["now"] += 15.0                              # next poll
s = g.soc_sensors(max_age=0)                       # burns 2 x timeout inside the call
worst_case_age = _clock["now"] - _soc_good_t()
test("worst cycle costs less than the grace window",
     worst_case_age < g.SOC_STALE_GRACE_S,
     "age %.0f s vs grace %.0f s" % (worst_case_age, g.SOC_STALE_GRACE_S))
test("hung sensor still yields the last good reading",
     s is not None and s.get("stale") is True, repr(s))
g.run = fake_run

print("9. Promotion never runs on a remembered reading")
# do_promote is the one decision that RELAXES protection. Before last-known-good, an
# unknown chip blocked it; a cool memory must not unblock it.
reset_cache()
_answer.update({"ok": True, "cpu": 50.0})          # cool: promotion would be allowed
g.soc_sensors(max_age=0)
_answer["ok"] = False
_clock["now"] += 20.0
test("stale cool reading is visible to tightening paths", g.soc_temp_c() == 50.0)
test("but promotion sees nothing", g.soc_temp_c(fresh_only=True) is None)

promoted = []
cfg_p = {"dry_run": False, "soc_resume_c": 76.0}
st_p = {"demoted": [999999], "demoted_info": {}}
g.do_promote(cfg_p, st_p, {}, g.soc_temp_c(fresh_only=True))
test("nothing promoted while the sensor is silent", st_p["demoted"] == [999999])

print("10. A remembered reading pauses, but never kills")
# The escalation path is: level 3 for kill_after_polls consecutive polls, then SIGTERM.
# A chip that measured 89 C can be at 60 C nineteen seconds later, so a remembered number
# must be able to freeze work and must NOT be able to end it.
cfg_k = {"soc_kill_c": 88.0, "soc_pause_c": 78.0, "batt_kill_c": 45.0,
         "batt_pause_c": 40.0, "speed_limit_pause": 60, "pause_on_thermal_state": "serious"}
fresh_lvl, _ = g.severity(cfg_k, "nominal", 30.0, 100, 89.0, True, 100, soc_stale=False)
stale_lvl, stale_why = g.severity(cfg_k, "nominal", 30.0, 100, 89.0, True, 100, soc_stale=True)
test("fresh critical chip still reaches level 3", fresh_lvl == 3, str(fresh_lvl))
test("remembered critical chip stops at level 2 (pause)", stale_lvl == 2, str(stale_lvl))
test("and says so in the reason", "remember" in stale_why or "zapamie" in stale_why, stale_why)

crit_polls = 0
for poll in range(4):                       # four hung polls inside the grace window
    lvl, _ = g.severity(cfg_k, "nominal", 30.0, 100, 89.0, True, 100, soc_stale=True)
    crit_polls = crit_polls + 1 if lvl >= 3 else 0
test("four remembered polls never arm the kill counter", crit_polls == 0, str(crit_polls))

print("11. A remembered reading never accuses the hardware of cooling failure")
# fan_alarm writes COOLING_ALARM into events.log, which later appears in the repair-shop
# report. Three remembered polls of "hot chip, fans at zero" must not build that case.
alarms = []
g.record_event = lambda kind, *a, **k: alarms.append(kind)
g.notify = lambda *a, **k: None
cfg_f = {"fan_check": True, "fan_alert_temp_c": 70.0}
g._fan_zero["n"] = 0
stale_soc = {"cpu": 95.0, "gpu": 60.0, "fans": [0], "watts": 30.0, "stale": True}
for _ in range(4):
    g.fan_alarm(cfg_f, stale_soc, 95.0, {})
test("no cooling alarm from remembered readings", alarms == [], repr(alarms))
test("and the counter stays at zero", g._fan_zero["n"] == 0, str(g._fan_zero["n"]))

print("12. The evidence file records measurements, not memories")
# Calls the same builder the daemon loop calls, so this cannot pass against broken
# production logic the way a copied expression would.
fresh_soc = {"cpu": 88.0, "gpu": 61.0, "fans": [3000], "watts": 33.0}
row_fresh = g.hist_row("nominal", fresh_soc, 88.0, 31.0, [3000], 90, True, 100, 4.0, 2, None)
row_stale = g.hist_row("nominal", stale_soc, 95.0, 31.0, [0], 90, True, 100, 4.0, 2, None)
test("a measured chip value is written", row_fresh[2] == "88.0", repr(row_fresh[:7]))
test("a measured GPU and fan value too",
     row_fresh[3] == "61.0" and row_fresh[5] == 3000, repr(row_fresh[:7]))
test("a remembered chip leaves the column empty", row_stale[2] == "", repr(row_stale[:7]))
test("and takes GPU, fans and watts with it",
     row_stale[3] == "" and row_stale[5] == "" and row_stale[6] == "", repr(row_stale[:7]))
test("battery temperature is its own sensor and stays", row_stale[4] == "31.0", repr(row_stale[:7]))

print("13. Every reader gets the qualifier with the number")
# The contract is "chip_stale travels with chip_c". These are the files other tools and
# the menu bar read; a number arriving without its qualifier is the whole failure mode.
act = g.agent_activity([], chip_c=95.0, level=2, chip_stale=True)
test("agent activity carries chip_stale", act.get("chip_stale") is True, repr(act.get("chip_stale")))
act_fresh = g.agent_activity([], chip_c=88.0, level=2)
test("and defaults to False for a measured one", act_fresh.get("chip_stale") is False)

print("14. The mutation test: remove the fallback and case 2 must fail")
reset_cache()
_answer.update({"ok": True, "cpu": 95.0})
g.soc_sensors(max_age=0)
grace, g.SOC_STALE_GRACE_S = g.SOC_STALE_GRACE_S, 0.0
_answer["ok"] = False
_clock["now"] += 1.0
test("grace 0 means no fallback", g.soc_sensors(max_age=0) is None)
g.SOC_STALE_GRACE_S = grace

print("\n%d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
