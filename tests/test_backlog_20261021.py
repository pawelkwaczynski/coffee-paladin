#!/usr/bin/env python3
"""Regression cases for pause identity, pressure observation, and CPU tier naming."""
import ctypes
import contextlib
import io
import json
import os
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from _load import load_source

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.TemporaryDirectory(prefix="thermal_backlog_")
os.environ["TG_BASE"] = BASE.name
os.environ["TG_LANG"] = "en"
g = load_source("guard_backlog", os.path.join(SRC, "guard.py"))
h = load_source("heat_backlog", os.path.join(SRC, "heat"))


class BacklogTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(g.DEFAULTS, notify=False, dry_run=False)

    def test_pid_reuse_resume_reassert_and_legacy(self):
        child = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: child.wait(timeout=2) if child.poll() is not None else (child.kill(), child.wait(timeout=2)))
        born, comm, boot = 1700000000, "sleep", "test-boot"
        calls = []
        def fake_sig(pid, pgid, sig):
            calls.append(sig)
            return 0
        def entry(**extra):
            return {"paused": {str(child.pid): dict(comm=comm, pgid=None, since=g.now(),
                          born=born, boot_session=boot, **extra)}}
        with patch.object(g, "sig", fake_sig), patch.object(g, "notify"), patch.object(g, "log") as logged, patch.object(g, "event_jsonl") as event, patch.object(g, "process_identity", return_value=(born, comm, 0)), patch.object(g, "boot_session_id", return_value=boot):
            st = entry()
            st["paused"][str(child.pid)]["born"] = born - 100
            g.do_resume(self.cfg, st, "test")
            self.assertEqual(calls, [])
            self.assertFalse(st["paused"])
            self.assertIn("entry dropped, no signal", logged.call_args_list[0].args[0])
            self.assertEqual(event.call_args_list[0].args[0], "pause_entry_dropped")
            self.assertEqual(event.call_args_list[0].kwargs["reason"], "pid_reused")
            st = entry()
            st["paused"][str(child.pid)]["born"] = born - 100
            g.reassert_paused(self.cfg, st)
            self.assertEqual(calls, [])
            self.assertFalse(st["paused"])
            st = entry()
            g.reassert_paused(self.cfg, st)
            self.assertEqual(calls, [signal.SIGSTOP])
            calls.clear()
            g.do_resume(self.cfg, st, "test")
            self.assertEqual(calls, [signal.SIGCONT])
            st = entry()
            del st["paused"][str(child.pid)]["born"]
            g.reassert_paused(self.cfg, st)
            self.assertEqual(calls[-1], signal.SIGSTOP)
            calls.clear()
            g.do_resume(self.cfg, st, "test")
            self.assertEqual(calls, [signal.SIGCONT])

    def test_live_identity_or_skip(self):
        child = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: child.wait(timeout=2) if child.poll() is not None else (child.kill(), child.wait(timeout=2)))
        identity = g.process_identity(child.pid)
        if identity is None or not g.boot_session_id():
            self.skipTest("ps or sysctl denied by sandbox")
        self.assertEqual(identity[1], "sleep")
        self.assertGreater(identity[0], 0)

    def test_lstart_parse_and_pause_capture(self):
        with patch.object(g, "run", return_value="Wed Oct 21 12:34:56 2026 1234 /bin/sleep\n"):
            identity = g.process_identity(1234)
        self.assertEqual(identity[1:], ("sleep", 1234))
        self.assertGreater(identity[0], 0)
        st = {"paused": {}}
        with patch.object(g, "process_identity", return_value=(identity[0], "sleep", 1234)), patch.object(g, "boot_session_id", return_value="boot"), patch.object(g, "sig", return_value=0) as sent, patch.object(g, "notify"), patch.object(g, "log"), patch.object(g, "event_jsonl"):
            cfg = dict(self.cfg, demote_at_pause=False)
            g.do_pause(cfg, st, [(1234, 50, "sleep", 1234)], "test")
        self.assertEqual(st["paused"]["1234"]["born"], identity[0])
        self.assertEqual(st["paused"]["1234"]["boot_session"], "boot")
        sent.assert_called_once_with(1234, 1234, signal.SIGSTOP)

    def test_terminate_checks_identity_before_cont_term_and_kill(self):
        key = "1234"
        info = {"comm": "sleep", "pgid": 1234, "since": g.now()-5000,
                "born": 1700000000, "boot_session": "boot"}
        st = {"paused": {key: dict(info)}}
        calls = []
        with patch.object(g, "alive", return_value=True), patch.object(g, "stopped_now", return_value=({1234}, {1234})), patch.object(g, "process_identity", return_value=(1700000100, "sleep", 1234)), patch.object(g, "boot_session_id", return_value="boot"), patch.object(g, "sig", side_effect=lambda p, pg, s: calls.append(s) or 0), patch.object(g, "log"), patch.object(g, "event_jsonl"):
            g.do_terminate(self.cfg, st, "test")
        self.assertEqual(calls, [])
        self.assertFalse(st["paused"])
        st = {"paused": {key: dict(info)}}
        identities = [(1700000000, "sleep", 1234), (1700000000, "sleep", 1234),
                      (1700000100, "sleep", 1234)]
        with patch.object(g, "alive", return_value=True), patch.object(g, "stopped_now", return_value=({1234}, {1234})), patch.object(g, "process_identity", side_effect=identities), patch.object(g, "boot_session_id", return_value="boot"), patch.object(g, "sig", side_effect=lambda p, pg, s: calls.append(s) or 0), patch.object(g.time, "sleep"), patch.object(g, "notify"), patch.object(g, "log"), patch.object(g, "event_jsonl"):
            g.do_terminate(self.cfg, st, "test")
        self.assertEqual(calls, [signal.SIGCONT, signal.SIGTERM])

    def test_identity_read_does_not_depend_on_locale(self):
        # 21.10: under pl_PL ps prints "śr. 21 paź" and the parser saw no identity at all.
        seen = []
        with patch.object(g, "run", side_effect=lambda cmd, timeout=10: seen.append(cmd) or ""):
            g.process_identity(1234)
        self.assertIn("LC_ALL=C", seen[0])
        child = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: (child.kill(), child.wait(timeout=2)) if child.poll() is None else None)
        with patch.dict(os.environ, {"LC_ALL": "pl_PL.UTF-8", "LANG": "pl_PL.UTF-8"}):
            identity = g.process_identity(child.pid)
        if identity is None and g.run(["ps", "-o", "pid=", "-p", str(child.pid)]).strip() == "":
            self.skipTest("ps denied by sandbox")
        self.assertIsNotNone(identity)
        self.assertEqual(identity[1], "sleep")

    def test_unreadable_identity_keeps_entry_and_only_resume_goes_ahead(self):
        # 21.10: a momentary ps failure must not drop the entry, or the job stays frozen forever.
        key = "1234"
        info = {"comm": "sleep", "pgid": 1234, "since": g.now() - 5000,
                "born": 1700000000, "boot_session": "boot"}
        calls = []
        common = dict(sig=lambda p, pg, s: calls.append(s) or 0)
        with patch.object(g, "alive", return_value=True), patch.object(g, "process_identity", return_value=None), patch.object(g, "boot_session_id", return_value="boot"), patch.object(g, "sig", common["sig"]), patch.object(g, "stopped_now", return_value=({1234}, {1234})), patch.object(g, "notify"), patch.object(g, "log"), patch.object(g, "event_jsonl"), patch.object(g, "run", return_value="S"):
            st = {"paused": {key: dict(info)}}
            g.reassert_paused(self.cfg, st)
            self.assertEqual(calls, [])
            self.assertIn(key, st["paused"])
            g.do_terminate(self.cfg, st, "test")
            self.assertEqual(calls, [])
            self.assertIn(key, st["paused"])
            g.do_resume(self.cfg, st, "test")
            self.assertEqual(calls, [signal.SIGCONT])

    def test_pause_goes_ahead_without_identity_but_not_for_another_command(self):
        sent = []
        with patch.object(g, "sig", side_effect=lambda p, pg, s: sent.append(s) or 0), patch.object(g, "notify"), patch.object(g, "log"), patch.object(g, "event_jsonl"), patch.object(g, "boot_session_id", return_value="boot"):
            cfg = dict(self.cfg, demote_at_pause=False)
            st = {"paused": {}}
            with patch.object(g, "process_identity", return_value=None):
                g.do_pause(cfg, st, [(1234, 50, "ffmpeg", 1234)], "test")
            self.assertEqual(sent, [signal.SIGSTOP])
            self.assertIsNone(st["paused"]["1234"]["born"])
            sent.clear()
            st = {"paused": {}}
            with patch.object(g, "process_identity", return_value=(1700000000, "Safari", 1234)):
                g.do_pause(cfg, st, [(1234, 50, "ffmpeg", 1234)], "test")
            self.assertEqual(sent, [])
            self.assertFalse(st["paused"])

    def test_pressure_status_change_log_and_unknown_speed(self):
        class Lib:
            def notify_register_check(self, name, token):
                token._obj.value = 7
                return 0
            def notify_get_state(self, token, state):
                state._obj.value = 2
                return 0
            def notify_cancel(self, token):
                return 0
        logs = []
        with patch.object(ctypes, "CDLL", return_value=Lib()), patch.object(g, "log", logs.append):
            g._ostatnio_odrzucone["v"] = []
            self.assertEqual(g.thermal_pressure(), (2, "heavy"))
            st = {"paused": {}}
            args = ("fair", None, None, None, True, 80, None, 0.0, 1, "", [], st)
            first = g.status_write(*args)
            second = g.status_write(*args)
            self.assertEqual(first["thermal_pressure"], {"level": 2, "name": "heavy"})
            self.assertEqual(second["thermal_pressure"], first["thermal_pressure"])
            self.assertEqual(sum("thermal pressure" in x for x in logs), 1)
        with patch.object(g, "run", return_value="No CPU power status has been recorded"):
            self.assertIsNone(g.cpu_speed_limit())
        self.assertIsInstance(g.severity(self.cfg, "nominal", None, None), tuple)
        def fake_heat_sh(cmd, timeout=15):
            return "8" if cmd[-1] == "hw.ncpu" else "No CPU power status has been recorded"
        with patch.object(h, "sh", fake_heat_sh), patch.object(h, "guard_alive", return_value=False), patch.object(h.sys, "argv", ["heat", "--json"]), contextlib.redirect_stdout(io.StringIO()) as out:
            h.main()
        self.assertIsNone(json.loads(out.getvalue())["measured"]["cpu_limit"])

    def test_real_pressure_or_skip(self):
        pressure = g.thermal_pressure()
        if pressure is None:
            self.skipTest("thermal notification unavailable in sandbox")
        self.assertIn(pressure[0], range(5))

    def test_named_cpu_tiers_and_fallback(self):
        for values, expected in (
            ({"hw.nperflevels": "2", "hw.perflevel0.name": "Performance", "hw.perflevel0.physicalcpu": "10", "hw.perflevel1.name": "Efficiency", "hw.perflevel1.physicalcpu": "4"}, (10, 4)),
            ({"hw.nperflevels": "2", "hw.perflevel0.name": "Super", "hw.perflevel0.physicalcpu": "6", "hw.perflevel1.name": "Performance", "hw.perflevel1.physicalcpu": "12"}, (18, 0)),
            ({"hw.nperflevels": "3", "hw.perflevel0.name": "Super", "hw.perflevel0.physicalcpu": "6", "hw.perflevel1.name": "Performance", "hw.perflevel1.physicalcpu": "12", "hw.perflevel2.name": "Efficiency", "hw.perflevel2.physicalcpu": "4"}, (18, 4)),
            ({"hw.perflevel0.physicalcpu": "10", "hw.perflevel1.physicalcpu": "4"}, (10, 4)),
        ):
            def fake_run(cmd, timeout=10):
                return values.get(cmd[-1], "") if cmd[0] == "sysctl" else ""
            with patch.object(g, "run", fake_run), patch.object(g, "soc_sensors", return_value={"fans": [1]}):
                hw = g.hardware_info()
            self.assertEqual((hw["p_cores"], hw["e_cores"]), expected)
            if values.get("hw.nperflevels"):
                self.assertEqual(len(hw["cpu_tiers"]), int(values["hw.nperflevels"]))


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        BASE.cleanup()
