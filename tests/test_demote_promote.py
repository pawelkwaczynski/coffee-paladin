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

        print("1) thermal demotion threshold")
        check("demote_above_c=None -> soc_resume_c + 4",
              guard.demote_threshold(CFG) == 86.0, str(guard.demote_threshold(CFG)))
        check("explicit demote_above_c beats derived value",
              guard.demote_threshold(dict(CFG, demote_above_c=70)) == 70.0)

        print("2) timer accumulates, demotion only after the limit (HOT machine)")
        st, hist = swiezy_stan(), {}
        pri_przed = pri_z_ps(pid)
        for cykl in range(3):
            guard.do_demote(CFG, st, targets, hist, soc_t=90.0)
        check("after 45 s accumulated: not demoted yet",
              not st["demoted"], str(st["demoted"]))
        guard.do_demote(CFG, st, targets, hist, soc_t=90.0)
        check("after 60 s accumulated: demoted", pid in st["demoted"])
        check("demoted_info carries process name",
              st["demoted_info"].get(str(pid), {}).get("comm") == "yes")
        import time; time.sleep(0.5)
        pri_po_demote = pri_z_ps(pid)
        check("taskpolicy -b really reached the system (priority dropped)",
              pri_po_demote is not None and pri_po_demote < pri_przed,
              "pri %s -> %s" % (pri_przed, pri_po_demote))

        print("3) hysteresis: hot keeps E-cores, cooling restores P-cores")
        guard.do_promote(CFG, st, hist, soc_t=90.0)
        check("chip 90 C (> soc_resume_c): does NOT promote", pid in st["demoted"])
        guard.do_promote(CFG, st, hist, soc_t=None)
        check("no chip reading: does NOT promote (we do not guess)", pid in st["demoted"])
        guard.do_promote(CFG, st, hist, soc_t=80.0)
        check("chip 80 C (<= soc_resume_c): promotes", pid not in st["demoted"])
        check("demoted_info cleared", str(pid) not in st["demoted_info"])
        import time; time.sleep(0.5)
        check("priority returned to the pre-demotion value", pri_z_ps(pid) == pri_przed,
              "pri=%s expected %s" % (pri_z_ps(pid), pri_przed))
        check("timer reset - return is return, not a 15 s gap",
              hist.get(pid) == 0.0, str(hist.get(pid)))

        print("4) cool machine NEVER demotes (lesson: ffmpeg 11x slower at 44 C)")
        st2, hist2 = swiezy_stan(), {}
        for _ in range(10):
            guard.do_demote(CFG, st2, targets, hist2, soc_t=44.0)
        check("10 cycles at 44 C: zero demotion", not st2["demoted"])
        check("but the timer keeps accumulating (150 s)", hist2.get(pid) == 150.0,
              str(hist2.get(pid)))
        for _ in range(10):
            guard.do_demote(CFG, st2, targets, hist2, soc_t=None)
        check("no chip reading: zero demotion", not st2["demoted"])

        print("5) B3 core: timer entry survives pause (accumulation, not time since start)")
        # Simulate pause: the process drops out of targets for any duration, leaving
        # hist unchanged. After "resume", accumulation continues from the same point.
        st3, hist3 = swiezy_stan(), {}
        guard.do_demote(CFG, st3, targets, hist3, soc_t=90.0)   # 15 s
        zebrane_przed_pauza = hist3[pid]
        guard.do_demote(CFG, st3, [], hist3, soc_t=90.0)         # Pause: absent from targets.
        check("pause neither clears nor adds time", hist3[pid] == zebrane_przed_pauza)
        for _ in range(3):
            guard.do_demote(CFG, st3, targets, hist3, soc_t=90.0)
        check("after pause it reaches the limit and demotes", pid in st3["demoted"])

        print("6) safe-run --normal is not demoted (B1.4)")
        st5, hist5 = swiezy_stan(), {}
        hist5[pid] = 999.0
        guard.do_demote(CFG, st5, targets, hist5, soc_t=90.0, saferun_normal={pid})
        check("pid with --normal stays out of demotion despite limit and heat", not st5["demoted"])
        check("--normal timer is not touched at all", hist5[pid] == 999.0)

        print("7) dry_run: observation, zero process changes")
        st4, hist4 = swiezy_stan(), {}
        hist4[proc.pid] = 999.0
        guard.do_demote(dict(CFG, dry_run=True), st4, targets, hist4, soc_t=90.0)
        check("dry_run does not demote", not st4["demoted"])
    finally:
        proc.kill()
        proc.wait()

    padniete = [n for n, ok in WYNIKI if not ok]
    print("\nRESULT: %d/%d" % (len(WYNIKI) - len(padniete), len(WYNIKI)))
    if padniete:
        sys.exit(1)


if __name__ == "__main__":
    main()
