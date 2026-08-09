#!/usr/bin/env python3
"""Verify E-core demotion and promotion hysteresis.

An overnight video queue exposed three defects in one mechanism:
  - the demotion timer reset after each SIGSTOP pause,
  - demotion was one-way and the process never returned to P-cores,
  - it demoted even on a cool Mac, making ffmpeg at 44 C run 11x slower.

These tests call the real do_demote/do_promote on a live `yes` process and verify
the system effect with `ps -o pri`, not just the guard's memory.

Run with:  python3 testy/test_demote_promote.py
"""
import os
import subprocess
import sys
import tempfile

KATALOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg_test_demote_")
sys.path.insert(0, KATALOG)
import guard  # noqa: E402  (TG_BASE must be in the environment before import.)

WYNIKI = []


def check(nazwa, warunek, szczegol=""):
    WYNIKI.append((nazwa, bool(warunek)))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           (" - " + szczegol) if (szczegol and not warunek) else ""))


def pri_z_ps(pid):
    """Return scheduling priority from ps.

    taskpolicy -b lowers it from ~31 to ~4; -B restores it. This intentionally does
    not use nice: once nice is raised, it cannot return without root, so demotion
    never touches nice.
    """
    out = subprocess.run(["ps", "-o", "pri=", "-p", str(pid)],
                         capture_output=True, text=True).stdout.strip()
    return int(out) if out else None


def swiezy_stan():
    return {"paused": {}, "demoted": [], "demoted_info": {}}


CFG = {
    "poll_seconds": 15,
    "demote_after_minutes": 1,      # limit = 60 s -> four 15 s cycles
    "demote_cpu_percent": 60.0,
    "demote_above_c": None,          # Derived value: soc_resume_c + 4 = 86.
    "soc_resume_c": 82.0,
    "dry_run": False,
    "notify": False,   # Keep tests silent; do not fire notifications on screen.
    "sound": False,
}


def main():
    proc = subprocess.Popen(["yes"], stdout=subprocess.DEVNULL)
    try:
        pid = proc.pid
        targets = [(pid, 99.0, "yes", None)]

        print("1) prog termiczny degradacji")
        check("demote_above_c=None -> soc_resume_c + 4",
              guard.prog_demote(CFG) == 86.0, str(guard.prog_demote(CFG)))
        check("demote_above_c jawny wygrywa z pochodna",
              guard.prog_demote(dict(CFG, demote_above_c=70)) == 70.0)

        print("2) zegar kumuluje, degradacja dopiero po limicie (maszyna GORACA)")
        st, hist = swiezy_stan(), {}
        pri_przed = pri_z_ps(pid)
        for cykl in range(3):
            guard.do_demote(CFG, st, targets, hist, soc_t=90.0)
        check("po 45 s skumulowanych: jeszcze nie zdegradowany",
              not st["demoted"], str(st["demoted"]))
        guard.do_demote(CFG, st, targets, hist, soc_t=90.0)
        check("po 60 s skumulowanych: zdegradowany", pid in st["demoted"])
        check("demoted_info niesie nazwe procesu",
              st["demoted_info"].get(str(pid), {}).get("comm") == "yes")
        import time; time.sleep(0.5)
        pri_po_demote = pri_z_ps(pid)
        check("taskpolicy -b naprawde poszedl w system (pri spadl)",
              pri_po_demote is not None and pri_po_demote < pri_przed,
              "pri %s -> %s" % (pri_przed, pri_po_demote))

        print("3) histereza: goraco trzyma na E-cores, ostygniecie oddaje P-cores")
        guard.do_promote(CFG, st, hist, soc_t=90.0)
        check("chip 90 C (> soc_resume_c): NIE promuje", pid in st["demoted"])
        guard.do_promote(CFG, st, hist, soc_t=None)
        check("brak odczytu chipu: NIE promuje (nie zgadujemy)", pid in st["demoted"])
        guard.do_promote(CFG, st, hist, soc_t=80.0)
        check("chip 80 C (<= soc_resume_c): promuje", pid not in st["demoted"])
        check("demoted_info wyczyszczone", str(pid) not in st["demoted_info"])
        import time; time.sleep(0.5)
        check("pri wrocil do wartosci sprzed degradacji", pri_z_ps(pid) == pri_przed,
              "pri=%s oczekiwane %s" % (pri_z_ps(pid), pri_przed))
        check("zegar wyzerowany - powrot to powrot, nie 15 s przerwy",
              hist.get(pid) == 0.0, str(hist.get(pid)))

        print("4) chlodna maszyna NIGDY nie degraduje (lekcja: ffmpeg 11x wolniej przy 44 C)")
        st2, hist2 = swiezy_stan(), {}
        for _ in range(10):
            guard.do_demote(CFG, st2, targets, hist2, soc_t=44.0)
        check("10 cykli przy 44 C: zero degradacji", not st2["demoted"])
        check("ale zegar CALY CZAS kumuluje (150 s)", hist2.get(pid) == 150.0,
              str(hist2.get(pid)))
        for _ in range(10):
            guard.do_demote(CFG, st2, targets, hist2, soc_t=None)
        check("brak odczytu chipu: zero degradacji", not st2["demoted"])

        print("5) sedno B3: wpis zegara przezywa pauze (kumulacja, nie czas od startu)")
        # Simulate pause: the process drops out of targets for any duration, leaving
        # hist unchanged. After "resume", accumulation continues from the same point.
        st3, hist3 = swiezy_stan(), {}
        guard.do_demote(CFG, st3, targets, hist3, soc_t=90.0)   # 15 s
        zebrane_przed_pauza = hist3[pid]
        guard.do_demote(CFG, st3, [], hist3, soc_t=90.0)         # Pause: absent from targets.
        check("pauza nie kasuje ani nie dolicza", hist3[pid] == zebrane_przed_pauza)
        for _ in range(3):
            guard.do_demote(CFG, st3, targets, hist3, soc_t=90.0)
        check("po pauzie dociera do limitu i degraduje", pid in st3["demoted"])

        print("6) safe-run --normal nie jest degradowany (B1.4)")
        st5, hist5 = swiezy_stan(), {}
        hist5[pid] = 999.0
        guard.do_demote(CFG, st5, targets, hist5, soc_t=90.0, saferun_normal={pid})
        check("pid z --normal poza degradacja mimo limitu i goraca", not st5["demoted"])
        check("zegar dla --normal w ogole nie tyka", hist5[pid] == 999.0)

        print("7) dry_run: obserwacja, zero dotykania procesow")
        st4, hist4 = swiezy_stan(), {}
        hist4[proc.pid] = 999.0
        guard.do_demote(dict(CFG, dry_run=True), st4, targets, hist4, soc_t=90.0)
        check("dry_run nie degraduje", not st4["demoted"])
    finally:
        proc.kill()
        proc.wait()

    padniete = [n for n, ok in WYNIKI if not ok]
    print("\nWYNIK: %d/%d" % (len(WYNIKI) - len(padniete), len(WYNIKI)))
    if padniete:
        sys.exit(1)


if __name__ == "__main__":
    main()
