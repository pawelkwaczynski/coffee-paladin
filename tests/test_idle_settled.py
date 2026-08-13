#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Settled-idle classification in `heat --profile`.

Field failure this guards against: a fanless Mac cools for many minutes after
work ends, so quiet-by-CPU samples taken during that cooldown are hot, and the
idle band came out absurd (field profile: idle median 81.3 °C, p90 92.7). The
resume-threshold rail leans on that band, so a poisoned band poisons advice.

Contract of settled_idle(): a quiet sample counts only when work ended at least
IDLE_SETTLE_AFTER_WORK_S earlier AND the last IDLE_STABLE_WINDOW_S of quiet
temperatures span no more than IDLE_STABLE_RANGE_C; everything else is counted
as skipped, and rows without timestamps are skipped, never trusted.

Run with:  python3 tests/test_idle_settled.py
Does not touch the real ~/.coffee-paladin.
"""
import importlib.machinery
import os
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp()
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
heat = importlib.machinery.SourceFileLoader("heat_idle_mod", os.path.join(SRC, "heat")).load_module()

ok = fail = 0


def check(name, condition, detail=""):
    global ok, fail
    if condition:
        ok += 1
        print("  [PASS] %s" % name)
    else:
        fail += 1
        print("  [FAIL] %s  -> %s" % (name, detail))


def row(minute, chip, watts=5.0, top_cpu=10, level=0, time_str=None):
    t = time_str if time_str is not None else "2026-08-01 %02d:%02d:00+0200" % (minute // 60, minute % 60)
    return {"time": t, "chip_C": "%.1f" % chip, "watts": "%.1f" % watts,
            "top_cpu": "%d" % top_cpu, "level": "%d" % level,
            "fan_rpm": "0", "cpu_limit": "100"}


def work(minute, chip=96.0):
    return row(minute, chip, watts=30.0, top_cpu=600)


print("=== the Neo scenario: hot cooldown must not enter the idle band ===")
rows = [work(m) for m in range(0, 10)]                       # 10 min of load at 96
rows += [row(10 + i, 90.0 - i * 2.5) for i in range(12)]     # cooling 90 -> 62.5 within settle window
rows += [row(25 + i, 55.0 + (0.1 * (i % 2))) for i in range(30)]  # truly settled at ~55
settled, skipped = heat.settled_idle(rows)
check("1. cooldown samples are skipped, not idle", skipped >= 12, "skipped=%d" % skipped)
check("2. settled band sits at the real idle temperature",
      settled and max(settled) < 60.0, "max=%s" % (max(settled) if settled else None))
check("3. the settled majority survives", len(settled) >= 15, "n=%d" % len(settled))

print("=== quiet-only history still yields an idle band ===")
rows = [row(i, 45.0 + 0.1 * (i % 3)) for i in range(60)]
settled, skipped = heat.settled_idle(rows)
check("4. no work in history -> idle still measured", len(settled) >= 50,
      "n=%d skipped=%d" % (len(settled), skipped))

print("=== temperature still moving = not settled ===")
rows = [row(i, 80.0 - i * 1.5) for i in range(20)]           # falling 1.5 C/min, no work rows
settled, skipped = heat.settled_idle(rows)
check("5. a drifting quiet series is skipped until stable",
      all(t <= 60.0 for t in settled), "settled=%s" % settled[:5])

print("=== rows without timestamps are never trusted ===")
rows = [row(0, 45.0, time_str="not-a-date") for _ in range(10)]
settled, skipped = heat.settled_idle(rows)
check("6. timestamp-less quiet rows are skipped", settled == [] and skipped == 10,
      "settled=%d skipped=%d" % (len(settled), skipped))

print("=== clock going backwards after work counts as 'just after work' ===")
rows = [work(30)]
rows += [row(5, 85.0)]                                        # earlier timestamp than the work row
settled, skipped = heat.settled_idle(rows)
check("7. negative gap to work is skipped", settled == [], "settled=%s" % settled)

print("=== level >= 2 breaks the idle claim even with low CPU ===")
rows = [row(i, 90.0, level=2) for i in range(5)]
rows += [row(5 + i, 88.0) for i in range(5)]                  # quiet but 5 min after level-2
settled, skipped = heat.settled_idle(rows)
check("8. guard-level-2 rows are treated as work", settled == [], "settled=%s" % settled)

print("=== the profile carries the skipped count for the honest printout ===")
rows = [work(m) for m in range(0, 10)]
rows += [row(10 + i, 88.0 - i) for i in range(5)]
prof = heat.thermal_profile(rows)
check("9. idle_not_settled present in the profile (and JSON)",
      prof.get("idle_not_settled", 0) >= 5, str(prof.get("idle_not_settled")))
check("10. contaminated-only history reports no idle median instead of a lie",
      prof.get("idle_median_c") is None, str(prof.get("idle_median_c")))

print("\nRESULT: %d/%d" % (ok, ok + fail))
sys.exit(0 if fail == 0 else 1)
