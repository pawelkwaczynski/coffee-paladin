#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wykrywanie padu ma OZNACZAC watpliwy dowod, nie wyrzucac go (pozycja 3 z listy).

Do 2.1.7 kazdy przypadek "podejrzany" konczyl sie `return None`, czyli CISZA - a to
najgorsze mozliwe zachowanie czarnej skrzynki. Trzy realne drogi do utraty albo
sfalszowania dowodu:

  * rozladowany RTC / skok NTP - puls wypadal ponad 30 dni przed bootem, wiec podloga
    30-dniowa WYRZUCALA go zamiast oznaczyc; dowod przepadal bezpowrotnie,
  * demon ubity (SIGKILL, `launchctl bootout`, timeout launchd) przed NORMALNYM
    restartem - puls sprzed bootu, brak clean_stop, wiec zdarzenie bylo FABRYKOWANE
    jako twardy pad w dniu, w ktorym Mac dzialal poprawnie,
  * jedno i drugie wygladalo w dokumencie tak samo pewnie jak prawdziwy pad.

Zadnego z tych przypadkow nie da sie rozstrzygnac lokalnie i tanio - dlatego dowod
zapisujemy ZAWSZE, ale z jawnym `confidence`. Rozstrzyga czlowiek w serwisie.

Uruchomienie:  python3 tests/test_pewnosc_padu.py
Nie dotyka prawdziwego ~/.coffee-paladin.
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


def scena(puls, czyste=None):
    """Czysty katalog danych z konkretnym pulsem (i opcjonalnym clean_stop)."""
    for p in (g.HEARTBEAT_PATH, g.CLEAN_STOP_PATH, g.EVENTS_PATH):
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
    return g.wykryj_twardy_pad()


def zapisane():
    """Ostatni wpis z events.log (to, co naprawde trafia do dokumentu)."""
    try:
        linie = [l for l in io.open(g.EVENTS_PATH, encoding="utf-8").read().splitlines() if l.strip()]
        return json.loads(linie[-1]) if linie else None
    except Exception:
        return None


print("=== dowod ma byc OZNACZONY, nie wyrzucony ===")

# 1. zwykly twardy pad - pelna pewnosc
r = scena(BOOT - 600)
test("1. zwykly pad (10 min przed bootem) wykryty z pewnoscia high",
     r and r.get("confidence") == "high", "dostalem %s" % (r and r.get("confidence")))

# 2. rozladowany RTC / skok NTP: puls ponad 30 dni przed bootem
#    WCZESNIEJ: cisza, `return None`, dowod przepadal bezpowrotnie
r = scena(BOOT - 45 * 86400)
w = zapisane()
test("2. puls sprzed 45 dni: dowod ZAPISANY (nie wyrzucony po cichu)", bool(r) and bool(w),
     "wynik=%s zapis=%s" % (bool(r), bool(w)))
test("3. ...i oznaczony jako maloprawdopodobny",
     r and r.get("confidence") == "low"
     and w and w.get("context", {}).get("confidence") == "low",
     "confidence=%s" % (r and r.get("confidence")))
test("4. ...z podanym POWODEM watpliwosci",
     bool(w and w.get("context", {}).get("confidence_reason")),
     "powod: %r" % (w and w.get("context", {}).get("confidence_reason")))

# 3. demon ubity dlugo przed normalnym restartem - fabrykacja padu
r = scena(BOOT - 20 * 3600)
w = zapisane()
test("5. puls 20 h przed bootem: zapisany, ale NIE jako pewny twardy pad",
     bool(r) and r.get("confidence") == "low",
     "confidence=%s" % (r and r.get("confidence")))
test("6. ...powod wskazuje na ubicie bezpiecznika, nie na pad Maca",
     bool(w) and "heartbeat" in (w.get("context", {}).get("confidence_reason") or "").lower(),
     "powod: %r" % (w and w.get("context", {}).get("confidence_reason")))

# 4. granica: 6 h przed bootem to nadal wiarygodny pad (Mac lezal wylaczony na noc)
r = scena(BOOT - 6 * 3600)
test("7. 6 h przed bootem nadal liczy sie jako pewny pad",
     r and r.get("confidence") == "high", "confidence=%s" % (r and r.get("confidence")))

# --- PRZYPADKI PRZECIWNE: cisza tam, gdzie cisza jest poprawna ---
print("\n=== przypadek przeciwny: kiedy NIE wolno meldowac padu ===")

test("8. puls z biezacej sesji: cisza", scena(BOOT + 60) is None)
test("9. czysty stop sprzed bootu: cisza", scena(BOOT - 600, czyste=BOOT - 600) is None)
test("10. clean_stop z biezacej sesji NIE wycisza prawdziwego padu",
     scena(BOOT - 600, czyste=time.time()) is not None)

# 11. opis dla czlowieka niesie ostrzezenie, nie samo suche zdanie
r = scena(BOOT - 45 * 86400)
test("11. opis w dokumencie zawiera jawne ostrzezenie o niskiej wiarygodnosci",
     r and "LOW" in (r.get("description") or "").upper(),
     "opis: %r" % (r and (r.get("description") or "")[:90]))

# 12. pole gap_to_boot_s pozwala czlowiekowi ocenic samodzielnie
w = zapisane()
test("12. zdarzenie niesie zmierzona luke puls->boot",
     bool(w) and isinstance(w.get("context", {}).get("gap_to_boot_s"), (int, float)),
     "context=%s" % (w and list((w.get("context") or {}).keys())))

shutil.rmtree(BASE, ignore_errors=True)
ok = sum(wyniki)
print("\nWYNIK: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
