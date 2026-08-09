#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mark uncertain shutdown evidence instead of discarding it.

Suspicious cases used to end with `return None`, meaning silence, the worst possible
black-box behavior. Three real paths can lose or falsify evidence:

  * drained RTC / NTP jump - the heartbeat lands more than 30 days before boot, so the
    30-day floor discarded it instead of marking it; evidence was lost permanently,
  * daemon killed by SIGKILL, `launchctl bootout`, or launchd timeout before a normal
    restart - heartbeat before boot and no clean_stop fabricated a hard shutdown on a
    day when the Mac worked correctly,
  * both looked just as certain in the document as a real hard shutdown.

None of these cases can be resolved locally and cheaply, so always record the evidence
with explicit `confidence`. A service human decides.

Run with:  python3 tests/test_pewnosc_padu.py
Does not touch the real ~/.coffee-paladin.
"""
import importlib.machinery
import io
import json
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-pewnosc-")
os.environ["TG_BASE"] = BASE
os.environ.setdefault("TG_LANG", "en")

g = importlib.machinery.SourceFileLoader("pw_guard", os.path.join(SRC, "guard.py")).load_module()
BOOT = g.boot_time()

wyniki = []


def test(nazwa, warunek, detal=""):
    wyniki.append(bool(warunek))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


def scena(puls, czyste=None, czysc_events=True):
    """Set up a data directory with a specific heartbeat and optional clean_stop.

    `czysc_events=False` leaves events.log in place for deduplication tests, because
    deduplication reads what has already been written.
    """
    pliki = [g.HEARTBEAT_PATH, g.CLEAN_STOP_PATH]
    if czysc_events:
        pliki.append(g.EVENTS_PATH)
    for p in pliki:
        if os.path.exists(p):
            os.remove(p)
    with io.open(g.HEARTBEAT_PATH, "w", encoding="utf-8") as f:
        f.write("%d %s" % (puls, g.ts(puls)))
    os.utime(g.HEARTBEAT_PATH, (puls, puls))
    with io.open(g.HIST_PATH, "w", encoding="utf-8") as f:
        f.write("time,thermal_state,chip_C\n%s,nominal,88.0\n" % g.ts(puls))
    if czyste is not None:
        io.open(g.CLEAN_STOP_PATH, "w").close()
        os.utime(g.CLEAN_STOP_PATH, (czyste, czyste))
    return g.detect_hard_shutdown()


def zapisane():
    """Return the last events.log entry, which is what the document actually receives."""
    try:
        linie = [l for l in io.open(g.EVENTS_PATH, encoding="utf-8").read().splitlines() if l.strip()]
        return json.loads(linie[-1]) if linie else None
    except Exception:
        return None


print("=== evidence must be MARKED, not discarded ===")

# 1. Plain hard shutdown, high confidence.
r = scena(BOOT - 600)
test("1. plain shutdown (10 min before boot) detected with high confidence",
     r and r.get("confidence") == "high", "got %s" % (r and r.get("confidence")))

# 2. Drained RTC / NTP jump: heartbeat more than 30 days before boot.
#    Previously: silence, `return None`, evidence lost permanently.
r = scena(BOOT - 45 * 86400)
w = zapisane()
test("2. heartbeat from 45 days ago: evidence WRITTEN (not silently discarded)", bool(r) and bool(w),
     "result=%s written=%s" % (bool(r), bool(w)))
test("3. ...and marked as unlikely",
     r and r.get("confidence") == "low"
     and w and w.get("context", {}).get("confidence") == "low",
     "confidence=%s" % (r and r.get("confidence")))
test("4. ...with a REASON for doubt",
     bool(w and w.get("context", {}).get("confidence_reason")),
     "reason: %r" % (w and w.get("context", {}).get("confidence_reason")))

# 3. Daemon killed long before normal restart, fabricating a shutdown.
r = scena(BOOT - 20 * 3600)
w = zapisane()
test("5. heartbeat 20 h before boot: written, but NOT as a certain hard shutdown",
     bool(r) and r.get("confidence") == "low",
     "confidence=%s" % (r and r.get("confidence")))
test("6. ...reason points to guard termination, not a Mac shutdown",
     bool(w) and "heartbeat" in (w.get("context", {}).get("confidence_reason") or "").lower(),
     "reason: %r" % (w and w.get("context", {}).get("confidence_reason")))

# 4. Boundary: 6 h before boot is still credible; the Mac could be off overnight.
r = scena(BOOT - 6 * 3600)
test("7. 6 h before boot still counts as a confident shutdown",
     r and r.get("confidence") == "high", "confidence=%s" % (r and r.get("confidence")))

# --- Countercases: silence where silence is correct ---
print("\n=== opposite case: when a shutdown must NOT be reported ===")

test("8. heartbeat from current session: silence", scena(BOOT + 60) is None)
test("9. clean stop before boot: silence", scena(BOOT - 600, czyste=BOOT - 600) is None)
test("10. clean_stop from current session does NOT silence a real shutdown",
     scena(BOOT - 600, czyste=time.time()) is not None)

# 11. Human-facing description carries a warning, not only a dry sentence.
r = scena(BOOT - 45 * 86400)
test("11. document description contains an explicit low-confidence warning",
     r and "LOW" in (r.get("description") or "").upper(),
     "description: %r" % (r and (r.get("description") or "")[:90]))

# 12. gap_to_boot_s lets a human assess the gap independently.
w = zapisane()
test("12. event carries measured heartbeat->boot gap",
     bool(w) and isinstance(w.get("context", {}).get("gap_to_boot_s"), (int, float)),
     "context=%s" % (w and list((w.get("context") or {}).keys())))

# --- item 4: the same shutdown may be described exactly once ---
print("\n=== one shutdown = one entry ===")


def ile_hard():
    try:
        linie = [l for l in io.open(g.EVENTS_PATH, encoding="utf-8").read().splitlines() if l.strip()]
        return sum(1 for l in linie if json.loads(l).get("type") == "HARD_SHUTDOWN")
    except Exception:
        return -1


# The daemon dies before touching heartbeat; each start sees the same old heartbeat.
os.remove(g.EVENTS_PATH) if os.path.exists(g.EVENTS_PATH) else None
scena(BOOT - 600)                      # Start 1: writes.
przed = ile_hard()
for _ in range(4):                     # Four more starts, heartbeat unchanged.
    g.detect_hard_shutdown()
test("13. five starts with the same heartbeat give ONE entry, not five",
     ile_hard() == 1, "entries: %d (after first start: %d)" % (ile_hard(), przed))

test("14. repeated detection returns None (no second notification)",
     g.detect_hard_shutdown() is None)

# Countercase: two different shutdowns produce two entries.
scena(BOOT - 4000, czysc_events=False)   # Different last heartbeat time = different failure.
test("15. second, DIFFERENT shutdown is written separately", ile_hard() == 2,
     "entries: %d" % ile_hard())

# Boundary: a difference below tolerance is still the same shutdown.
scena(BOOT - 4000 + 30, czysc_events=False)
test("16. heartbeat shifted by 30 s (mtime fallback) is still the SAME shutdown",
     ile_hard() == 2, "entries: %d" % ile_hard())

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(wyniki)
print("\nRESULT: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
