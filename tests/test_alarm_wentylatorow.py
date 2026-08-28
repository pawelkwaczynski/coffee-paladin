#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that the cooling alarm accuses the hardware on TIME, not on a poll count.

Every COOLING_ALARM entry in events.log so far (seven of them) was false. Each one was
followed in history.csv by fans at 2500-4800 rpm between 14 s and 3 min later, so the
machine was cooling itself normally the whole time. Apple silicon parks the fans at 0 rpm
and ramps them with a delay; "hot chip and 0 rpm" is what the beginning of a ramp looks
like. The old rule fired after `fan_alert_polls` readings, and with poll_seconds at 5 s
that was fifteen seconds, deep inside the ramp. The alarm lands in events.log and from
there in the repair-shop report, so a false one is expensive.

The rule now has two gates that must not be confused:
  - the COUNTER (`fan_alert_polls`) still opens the emergency net at the old speed;
  - the ACCUSATION (notification plus COOLING_ALARM record) also needs `fan_alert_seconds`
    of continuous wall time, and a gap in the polls breaks that continuity.

Run with:  python3 tests/test_alarm_wentylatorow.py
Does not touch the real ~/.coffee-paladin.
"""
import importlib.machinery
import json
import os
import shutil
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


# Sensor frames straight from the false alarms: a hot chip with the fans still parked,
# and the same chip once the ramp has finished.
HOT_STOPPED = {"cpu": 80.0, "fans": [0, 0]}
HOT_SPINNING = {"cpu": 80.0, "fans": [2500, 4800]}
CHIP_C = 80.0

clock = {"t": 1700000000.0}
events = []
notes = []
g.now = lambda: clock["t"]
g.record_event = lambda kind, description, context=None, **kw: \
    events.append((kind, description, context))
g.notify = lambda *a, **kw: notes.append(a)
g.log = lambda *a, **kw: None

BASE_CFG = {"fan_check": True, "fan_alert_temp_c": 70.0, "fan_alert_polls": 3,
            "fan_alert_seconds": 300, "poll_seconds": 5}


def scenario(**overrides):
    """Start a clean run: no streak, no recorded events, clock back at the fixed epoch.

    The streak is cleared by writing the dict directly rather than by calling the
    production reset, so a reset that stopped working cannot quietly fix the setup.
    """
    g._fan_zero["n"] = 0
    g._fan_zero["since"] = 0.0
    g._fan_zero["last"] = 0.0
    del events[:]
    del notes[:]
    clock["t"] = 1700000000.0
    cfg = dict(BASE_CFG)
    cfg.update(overrides)
    return cfg, {}


def poll(cfg, st, soc, step=None):
    """One daemon tick: the wall clock moves by one interval, then the sensors are read."""
    clock["t"] += cfg["poll_seconds"] if step is None else step
    g.fan_alarm(cfg, soc, CHIP_C, st)


def held_now():
    return clock["t"] - g._fan_zero["since"] if g._fan_zero["n"] else 0.0


print("1. the window, not the counter, decides whether to accuse the hardware")
cfg, st = scenario()
for _ in range(3):
    poll(cfg, st, HOT_STOPPED)
test("three readings 5 s apart stay silent (this is what fired all seven false alarms)",
     not events, "events: %r" % (events,))
test("the emergency counter is nevertheless already at fan_alert_polls",
     g._fan_zero["n"] >= cfg["fan_alert_polls"], "counter: %s" % g._fan_zero["n"])

guard_ticks = 0
while held_now() < cfg["fan_alert_seconds"] - cfg["poll_seconds"] and guard_ticks < 500:
    poll(cfg, st, HOT_STOPPED)
    guard_ticks += 1
test("still silent one interval before the window closes",
     not events, "held=%.0f s, events: %r" % (held_now(), events))
poll(cfg, st, HOT_STOPPED)
test("alarms once the condition has held for the whole window",
     len(events) == 1 and events[0][0] == "COOLING_ALARM",
     "held=%.0f s, events: %r" % (held_now(), events))
test("and the person gets a notification too", len(notes) == 1, "notes: %r" % (notes,))

print("\n2. the record carries the evidence the next audit needs")
ctx = events[0][2] if events else {}
test("context is a dict with the measurement", isinstance(ctx, dict), repr(ctx))
test("context carries held_s", isinstance(ctx.get("held_s"), (int, float)), repr(ctx))
test("held_s is at least the configured window",
     (ctx.get("held_s") or 0) >= cfg["fan_alert_seconds"], repr(ctx.get("held_s")))
test("context carries the poll count", ctx.get("polls") == g._fan_zero["n"],
     "%r vs %r" % (ctx.get("polls"), g._fan_zero["n"]))
test("the reported duration also reaches the message text",
     "%d s" % int(ctx.get("held_s") or 0) in (events[0][1] or ""), repr(events[0][1]))
test("the record still carries chip and fans", ctx.get("chip_c") == 80.0
     and ctx.get("fans") == [0, 0], repr(ctx))
test("it survives json, which is how events.log stores it",
     json.loads(json.dumps(ctx))["held_s"] == ctx["held_s"], repr(ctx))

print("\n3. a fan that finally spins up ends the streak")
cfg, st = scenario()
for _ in range(30):                              # 150 s of hot chip with parked fans
    poll(cfg, st, HOT_STOPPED)
test("half a window built up", 140 <= held_now() <= 160, "held=%.0f s" % held_now())
poll(cfg, st, HOT_SPINNING)                      # the ramp arrives, as in all seven cases
test("the streak is cleared", g._fan_zero["n"] == 0, "counter: %s" % g._fan_zero["n"])
test("and so is its start time", g._fan_zero["since"] == 0.0,
     "since: %r" % g._fan_zero["since"])
for _ in range(30):                              # another 150 s of the same condition
    poll(cfg, st, HOT_STOPPED)
test("two half windows on either side of a spin-up do not add up to an alarm",
     not events, "held=%.0f s, events: %r" % (held_now(), events))

print("\n4. wall time that nobody measured does not count")
cfg, st = scenario(poll_seconds=15)              # gap limit: 3 * 15 + 60 = 105 s
for _ in range(3):
    poll(cfg, st, HOT_STOPPED)
test("a slow poll inside the limit keeps the streak", g._fan_zero["n"] == 3,
     "counter: %s" % g._fan_zero["n"])
poll(cfg, st, HOT_STOPPED, step=100)             # late, but still a measured reading
test("100 s between readings is late, not a hole", g._fan_zero["n"] == 4,
     "counter: %s" % g._fan_zero["n"])
poll(cfg, st, HOT_STOPPED, step=3600)            # lid closed for an hour
test("an hour without polls breaks the streak", g._fan_zero["n"] == 1,
     "counter: %s" % g._fan_zero["n"])
test("the window restarts at the first reading after the gap", held_now() == 0.0,
     "held=%.1f s" % held_now())
test("an hour of unmeasured wall time raises no alarm", not events,
     "events: %r" % (events,))

print("\n5. fan_alert_seconds=0 gives back the old poll-only rule")
cfg, st = scenario(fan_alert_seconds=0)
poll(cfg, st, HOT_STOPPED)
test("first reading is silent", not events, "events: %r" % (events,))
poll(cfg, st, HOT_STOPPED)
test("second reading is silent", not events, "events: %r" % (events,))
poll(cfg, st, HOT_STOPPED)
test("third reading alarms, exactly as before the change", len(events) == 1,
     "events: %r" % (events,))

print("\n6. the daemon ships with a window that covers fan spin-up")
g.now = g.time.time                              # config code stamps real timestamps
test("fan_alert_seconds is a default", "fan_alert_seconds" in g.DEFAULTS,
     repr(sorted(k for k in g.DEFAULTS if k.startswith("fan_"))))
test("its default is longer than the longest measured spin-up lag (3 min)",
     g.DEFAULTS.get("fan_alert_seconds", 0) >= 180,
     repr(g.DEFAULTS.get("fan_alert_seconds")))
test("fan_alert_polls is untouched", g.DEFAULTS.get("fan_alert_polls") == 3,
     repr(g.DEFAULTS.get("fan_alert_polls")))

json.dump({"fan_alert_seconds": 99999}, open(os.path.join(BASE, "config.json"), "w"))
loaded = g.load_cfg()
test("an absurd window is clamped, not obeyed", loaded.get("fan_alert_seconds") == 3600,
     repr(loaded.get("fan_alert_seconds")))
json.dump({"fan_alert_seconds": -5}, open(os.path.join(BASE, "config.json"), "w"))
loaded = g.load_cfg()
test("a negative window is clamped to the legacy 0", loaded.get("fan_alert_seconds") == 0,
     repr(loaded.get("fan_alert_seconds")))

shutil.rmtree(BASE, ignore_errors=True)
print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
