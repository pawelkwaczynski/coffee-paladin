# `detect_hard_shutdown()` Tests - Evidence Matrix

`test_wykryj_twardy_pad.py` covers 16 cases without starting the daemon and **without
touching** `~/.coffee-paladin`. Isolation is done by importing through `importlib` and
replacing every module `*_PATH`/`*_DIR` attribute with a temporary directory. Environment
`HOME` is not enough because `guard.py` computes these paths from `pwd`.

    T=$(mktemp -d) && python3 test_wykryj_twardy_pad.py "$T"; rm -rf "$T"

Scope: A) 8 logic cases: hard shutdown, clean stop, `[heartbeat-60, boot)` window,
30-day floor, restore without `-p`; B) 4 heartbeat format variants: new `epoch text`,
legacy text-only, junk, empty file; C) 4 time-zone scenarios, including
Kiritimati->Midway, 25 h delta, and legacy+zone, the only known FAIL; see note v4.

Result on `v1.7.4` (b5262eb): **A 8/8, B 4/4, C 3/4**.
