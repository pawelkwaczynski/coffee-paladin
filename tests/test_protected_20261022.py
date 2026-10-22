#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Protected apps, second round (22.10), each against the real code.

1. safe-run: the CPU limiter never freezes a protected app (alone or inside the job's group, also
   while the guard reports level 2), a protected command gets no efficiency-core wrapper, and the
   list comes from config.json the way the guard resolves it. The notice respects --quiet.
2. FaceTime's call engines and the screen-capture daemons run outside any .app bundle; they are
   never pause targets, even in an emergency.
3. A protected app below the unknown-heavy gates (CPU and age) is not listed or logged as heating
   the Mac; it is still never a target.
4. Executables anywhere inside a protected bundle (Contents/Helpers, Library/LaunchAgents,
   framework helpers) are protected.
5. ' OBS', 'OBS.app' and 'obs.APP ' in config mean OBS; user entries that match no installed
   bundle are logged once, not every cycle.

Run with:  python3 tests/test_protected_20261022.py
Isolated TG_BASE and a no-op launchctl; the only processes signalled are the ones this test
starts (symlinks to /bin/sleep).
"""
import atexit
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="tg-protected2-")
os.environ["TG_BASE"] = BASE
os.environ["TG_LANG"] = "en"
os.environ.pop("SAFE_RUN_QUIET", None)
os.environ.pop("TG_SAFE_RUN_PGID", None)
sys.path.insert(0, os.path.join(SRC, "tests"))
from _load import load_source  # noqa: E402

g = load_source("guard_protected2", os.path.join(SRC, "guard.py"))
sr = load_source("saferun_protected2", os.path.join(SRC, "safe-run"))
SAFE_RUN = os.path.join(SRC, "safe-run")
STATUS = os.path.join(BASE, "status.json")

passed = total = 0


def test(name, condition, detail=""):
    global passed, total
    total += 1
    passed += bool(condition)
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "  -> %r" % (detail,)))


def stat(pid):
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()


def write_status(level):
    with open(STATUS, "w") as f:
        json.dump({"level": level, "chip_c": 45.0, "thresholds": {"pause": 85.0, "resume": 76.0}}, f)


root = tempfile.mkdtemp(prefix="tg-protected2-bin-")
obs = os.path.join(root, "OBS.app", "Contents", "MacOS", "OBS")
job = os.path.join(root, "jobrunner")
os.makedirs(os.path.dirname(obs))
os.symlink("/bin/sleep", obs)
os.symlink("/bin/sleep", job)
spawned = []


def spawn(argv):
    p = subprocess.Popen(argv, start_new_session=True)
    spawned.append(p)
    return p


def cleanup(p):
    # Only while the leader is unreaped: then its pid and group number are still ours.
    if p.poll() is not None:
        return
    try:
        os.killpg(p.pid, signal.SIGCONT)
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        p.wait(timeout=5)
    except Exception:
        pass


# Whatever happens below, every process this test started is resumed and killed on exit.
atexit.register(lambda: [cleanup(p) for p in spawned])


def limiter_run(leader, watch, seconds, opt=None):
    """Run sr.limited_wait on `leader` at 95%; sample `watch` pids; return (states, stderr text)."""
    states = {pid: [] for pid in watch}
    err = io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        if opt is None:
            th = threading.Thread(target=lambda: sr.limited_wait(leader, 95.0, time.time() + seconds))
        else:
            th = threading.Thread(target=lambda: sr.limited_wait(leader, 95.0, time.time() + seconds, opt))
        th.start()
        t0 = time.time()
        while time.time() - t0 < seconds + 0.3:
            for pid in watch:
                states[pid].append(stat(pid)[:1])
            time.sleep(0.02)
        th.join()
    finally:
        sys.stderr = old
    return states, err.getvalue()


print("1. safe-run and protected apps")
names = getattr(sr, "protected_names", lambda conf: frozenset())
test("safe-run's default list is the guard's default list",
     getattr(sr, "PROTECTED_APPS", None) == g.DEFAULTS["protected_apps"])
test("no config: the defaults apply", {"zoom.us", "obs"} <= names({}), sorted(names({}))[:5])
test("protected_apps replaces the defaults", names({"protected_apps": ["Foo"]}) == {"foo"},
     names({"protected_apps": ["Foo"]}))
test("protected_apps_extra adds, with ' Bar.app' meaning Bar",
     {"zoom.us", "bar"} <= names({"protected_apps_extra": [" Bar.app"]}))
test("a protected_apps of the wrong type falls back to the defaults like the guard",
     "zoom.us" in names({"protected_apps": "OBS"}))

write_status(2)
try:
    p = spawn([obs, "300"])
    time.sleep(0.3)
    states, err = limiter_run(p, [p.pid], 4.0)
    test("level 2: the protected job is never stopped by the limiter", states[p.pid].count("T") == 0,
         "T in %d of %d samples" % (states[p.pid].count("T"), len(states[p.pid])))
    test("one notice on stderr names the protected app",
         err.count("protected app") == 1 and "OBS" in err, err)
finally:
    cleanup(p)
try:
    p = spawn([job, "300"])
    time.sleep(0.3)
    states, _ = limiter_run(p, [p.pid], 3.0)
    test("control: an ordinary job IS stopped at level 2 (the sampler sees T)", states[p.pid].count("T") > 0,
         len(states[p.pid]))
finally:
    cleanup(p)
try:
    leader = spawn(["/bin/sh", "-c", '"$1" 301 & exec "$2" 300', "sh", obs, job])
    time.sleep(0.6)
    members = subprocess.run(["pgrep", "-g", str(leader.pid)], capture_output=True, text=True).stdout.split()
    obs_pid = next((int(m) for m in members if g.exe_path(int(m)) == obs), None)
    test("the fake OBS is in the job group", obs_pid is not None, members)
    with open(os.path.join(BASE, "safe-run.log"), "w"):
        pass
    states, err = limiter_run(leader, [leader.pid, obs_pid or leader.pid], 4.0,
                              {"quiet": True, "normal": False})
    test("level 2: OBS inside the job group is never stopped", obs_pid and states[obs_pid].count("T") == 0,
         states.get(obs_pid, [])[:40])
    test("level 2: the rest of the group still gets the limiter", states[leader.pid].count("T") > 0,
         states[leader.pid][:40])
    with open(os.path.join(BASE, "safe-run.log")) as f:
        logged = f.read()
    test("--quiet: the notice goes to safe-run.log, not stderr",
         "protected app" not in err and logged.count("protected app") == 1 and "efficiency cores" in logged,
         (err, logged))
finally:
    cleanup(leader)

FAKE_BIN = os.path.join(BASE, "bin")
os.makedirs(FAKE_BIN)
with open(os.path.join(FAKE_BIN, "launchctl"), "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(os.path.join(FAKE_BIN, "launchctl"), 0o755)
ENV = dict(os.environ, TG_BASE=BASE, TG_LANG="en", PATH=FAKE_BIN + os.pathsep + os.environ.get("PATH", ""))
write_status(0)
base_nice = os.nice(0)


def run_saferun(command, extra=(), probe=True, path=""):
    """Start safe-run on `command`, read the job's nice and priority, return (rc, stderr, nice, pri)."""
    env = dict(ENV, PATH=path + os.pathsep + ENV["PATH"]) if path else ENV
    p = subprocess.Popen([sys.executable, SAFE_RUN, "--allow-sleep"] + list(extra) + ["--", command, "3"],
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    spawned.append(p)
    nice = pri = None
    t0 = time.time()
    while probe and time.time() - t0 < 8 and nice is None:
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,pri=,nice=,comm="], capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.split(None, 4)
            if len(parts) == 5 and parts[1] == str(p.pid) and parts[4] == command:
                pri, nice = int(parts[2]), int(parts[3])
        time.sleep(0.1)
    _out, err = p.communicate(timeout=30)
    return p.returncode, err.decode("utf-8", "replace"), nice, pri


rc, err, nice, pri = run_saferun(obs)
test("safe-run -- OBS: the job runs without nice", rc == 0 and nice == base_nice, (rc, nice, base_nice))
test("safe-run -- OBS: the job is not on background QoS (priority not 4)", pri is not None and pri != 4, pri)
test("safe-run -- OBS: one line says why, and the summary shows all cores and no limit",
     err.count("OBS is a protected app") == 1 and "cores=all, CPU limit=100%" in err, err)
rc, err, nice, pri = run_saferun(job)
test("control: an ordinary job gets nice 10 and background QoS",
     rc == 0 and nice == min(base_nice + 10, 20) and pri == 4, (rc, nice, pri, err))
with open(os.path.join(BASE, "safe-run.log"), "w"):
    pass
rc, err, nice, pri = run_saferun(obs, ["--quiet"])
with open(os.path.join(BASE, "safe-run.log")) as f:
    logged = f.read()
test("--quiet: the launch notice goes to safe-run.log only",
     rc == 0 and "protected app" not in err and "OBS is a protected app" in logged, (err, logged))
# A command in PATH that is a symlink to a protected bundle's executable. The executable is a
# script here: a copied system binary is killed by code signing, and a symlink to /bin/sleep
# would resolve out of the bundle.
loom = os.path.join(root, "Loom.app", "Contents", "MacOS", "Loom")
os.makedirs(os.path.dirname(loom))
with open(loom, "w") as f:
    f.write('#!/bin/sh\nexec /bin/sleep "$@"\n')
os.chmod(loom, 0o755)
link_dir = os.path.join(root, "linkbin")
os.makedirs(link_dir)
os.symlink(loom, os.path.join(link_dir, "loom"))
rc, err, _nice, _pri = run_saferun("loom", probe=False, path=link_dir)
test("a command in PATH linked into a protected bundle counts too",
     rc == 0 and "Loom is a protected app" in err and "cores=all, CPU limit=100%" in err, err)

for p in spawned:
    cleanup(p)
time.sleep(0.2)
left = subprocess.run(["pgrep", "-f", root], capture_output=True, text=True).stdout.split()
test("no test process left behind", not left, left)

# Routing tests below mock every process action: nothing is signalled.
logs = []
g.log = lambda *a, **k: logs.append(a[0])
g.notify = lambda *a, **k: None
g.args_without_paths = lambda pid: ""
g.foreground_on_tty = lambda pid: False
cfg = dict(g.DEFAULTS, managed_patterns=[], count_children=False, cpu_min_percent=20,
           unknown_cpu_percent=50, unknown_min_seconds=120, dry_run=False)

print("2. call and screen-capture daemons")
daemons = {
    99401: "/usr/libexec/avconferenced",
    99402: "/System/Library/PrivateFrameworks/TelephonyUtilities.framework/callservicesd",
    99403: ("/System/Library/PrivateFrameworks/TelephonyUtilities.framework/XPCServices/"
          "com.apple.FaceTime.FTConversationService.xpc/Contents/MacOS/com.apple.FaceTime.FTConversationService"),
    99404: "/usr/libexec/replayd",
    99405: "/System/Library/CoreServices/screencaptureui.app/Contents/MacOS/screencaptureui",
    99406: "/usr/libexec/someotherd",
}
procs = [(pid, 1, 90.0, os.path.basename(path)) for pid, path in daemons.items()]
with patch.object(g, "exe_path", side_effect=lambda pid: daemons.get(pid, "")), \
        patch.object(g, "proc_age_seconds", return_value=900):
    g._EMERGENCY["on"] = True
    targets = {t[0] for t in g.pick_targets(cfg, procs, {})}
    test("emergency: none of the five daemons is a pause target", not targets & {99401, 99402, 99403, 99404, 99405},
         sorted(targets))
    test("emergency: an ordinary macOS service still is (control)", 99406 in targets, sorted(targets))
    g._EMERGENCY["on"] = False
    g.pick_targets(cfg, procs, {})
    test("no emergency: the daemons are named as macOS services, not as desktop apps",
         {99401, 99402, 99403, 99404, 99405} <= {t[0] for t in g._SYSTEM_HOT} and not {t[0] for t in g._GUI_HOT},
         (g._SYSTEM_HOT, g._GUI_HOT))
    g._EMERGENCY["on"] = True
    targets = {t[0] for t in g.pick_targets(dict(cfg, protected_daemons=[]), procs, {})}
    test("protected_daemons: [] turns the protection off", {99401, 99404} <= targets, sorted(targets))
    sent = []
    with patch.object(g, "sig", side_effect=lambda *a: sent.append(a) or 0), \
            patch.object(g.subprocess, "call", side_effect=lambda *a, **k: sent.append(a) or 0):
        st = {"paused": {}, "demoted": [], "demoted_info": {}}
        g.do_pause(cfg, st, [(99401, 90.0, "avconferenced", None)], "test")
        demoted = g.demote_pid(cfg, st, 99404, "replayd", None, 90.0, 90.0, "test")
    test("do_pause and demotion refuse a protected daemon", not sent and not st["paused"] and not demoted,
         (sent, st["paused"], demoted))
    g._EMERGENCY["on"] = False

print("3. protected app below the unknown-heavy gates")
apps = {99501: "/Applications/zoom.us.app/Contents/MacOS/zoom.us", 99502: "/Applications/Foo.app/Contents/MacOS/Foo"}
for cpu, age, listed in ((25.0, 10, False), (91.0, 10, False), (25.0, 900, False), (91.0, 900, True)):
    procs = [(99501, 1, cpu, "zoom.us"), (99502, 1, cpu, "Foo")]
    with patch.object(g, "exe_path", side_effect=lambda pid: apps.get(pid, "")), \
            patch.object(g, "proc_age_seconds", return_value=age):
        for emergency in (False, True):
            g._EMERGENCY["on"] = emergency
            targets = {t[0] for t in g.pick_targets(cfg, procs, {})}
            test("zoom.us at %.0f%% for %d s is never a target (emergency=%s)" % (cpu, age, emergency),
                 99501 not in targets, sorted(targets))
        g._EMERGENCY["on"] = False
        g.pick_targets(cfg, procs, {})
    del logs[:]
    g._HOT_APP_SAID.clear()
    g.say_hot_apps(cfg, {}, g._GUI_HOT, g._SYSTEM_HOT, gap_s=0)
    said = [x for x in logs if "zoom.us" in x]
    test("zoom.us at %.0f%% for %d s: %s" % (cpu, age, "listed and logged once" if listed else "not listed, no log line"),
         ((99501 in {t[0] for t in g._GUI_HOT}) == listed) and len(said) == (1 if listed else 0), (g._GUI_HOT, said))

print("4. executables outside Contents/MacOS")
names = g.protected_names(cfg)
for path in ("/Applications/Microsoft Teams.app/Contents/Helpers/com.microsoft.teams2.respawn",
             "/Applications/Microsoft Teams.app/Contents/Library/LaunchAgents/com.microsoft.teams2.agent",
             "/Applications/Discord.app/Contents/Frameworks/Squirrel.framework/Resources/ShipIt",
             "/Applications/zoom.us.app/Contents/Frameworks/Transcode.app/Contents/MacOS/Transcode"):
    test("protected: %s" % path.split("/Contents/")[-1], g.bundle_protected(path, names), path)
test("an ordinary bundle's helper is not protected",
     not g.bundle_protected("/Applications/Foo.app/Contents/Helpers/foo-agent", names))
test("app_kind is unchanged for an ordinary helper outside Contents/MacOS",
     g.app_kind("/Applications/Foo.app/Contents/Helpers/foo-agent") is None)
helpers = {99601: "/Applications/Microsoft Teams.app/Contents/Helpers/com.microsoft.teams2.respawn",
           99602: "/Applications/Foo.app/Contents/Helpers/foo-agent"}
procs = [(99601, 1, 90.0, "com.microsoft.teams2.respawn"), (99602, 1, 90.0, "foo-agent")]
with patch.object(g, "exe_path", side_effect=lambda pid: helpers.get(pid, "")), \
        patch.object(g, "proc_age_seconds", return_value=900):
    g._EMERGENCY["on"] = False
    targets = {t[0] for t in g.pick_targets(cfg, procs, {})}
test("Teams' respawn helper is not a pause target", 99601 not in targets, sorted(targets))
test("an ordinary helper outside Contents/MacOS is still a target (control)", 99602 in targets, sorted(targets))

print("5. natural spellings in config")
CFG = os.path.join(BASE, "config.json")
installed = next((n for n, d in (("Calculator", "/System/Applications"), ("Safari", "/Applications"))
                  if os.path.isdir(os.path.join(d, n + ".app"))), None)
missing = "Zzqx Missing Recorder"
with open(CFG, "w") as f:
    json.dump({"protected_apps": [" OBS", "OBS.app", "obs.APP ", "OBS Studio", "zoom.us", "  ", ".app"],
               "protected_apps_extra": ["Foo.app ", missing] + ([installed + ".app"] if installed else [])}, f)
del logs[:]
loaded = g.load_cfg()
test("protected_apps: whitespace and a trailing .app are stripped",
     loaded["protected_apps"] == ["OBS", "OBS", "obs", "OBS Studio", "zoom.us"], loaded["protected_apps"])
test("protected_apps_extra: the same", loaded["protected_apps_extra"][:2] == ["Foo", missing],
     loaded["protected_apps_extra"])
test("' OBS' now protects OBS.app", g.bundle_protected(obs, g.protected_names(loaded)))
test("no alias guessing: 'OBS Studio' alone does not protect OBS.app",
     not g.bundle_protected(obs, g.protected_names(dict(loaded, protected_apps=["OBS Studio"],
                                                         protected_apps_extra=[]))))
said = [x for x in logs if missing in x]
test("one line names the entries that match no installed bundle", len(said) == 1 and "OBS Studio" in said[0]
     and "Foo" in said[0], said)
test("an installed app and a default name are not reported",
     said and (installed is None or installed not in said[0]) and "zoom.us" not in said[0], said)
g.load_cfg()
g.load_cfg()
test("the same config loaded again: no new line", len([x for x in logs if missing in x]) == 1, logs)
with open(CFG, "w") as f:
    json.dump({"protected_apps_extra": [missing]}, f)
del logs[:]
g.load_cfg()
said = [x for x in logs if missing in x]
not_installed_defaults = [n for n in g.DEFAULTS["protected_apps"]
                          if not any(os.path.isdir(os.path.join(d, n + ".app"))
                                     for d in ("/Applications", "/System/Applications"))]
test("a changed config is reported again, defaults stay out of it",
     len(said) == 1 and not any('"%s"' % n in said[0] for n in not_installed_defaults), said)

print("6. the limiter releases its own stops (follow-up review, 22.10)")


def kill_member(pid, pgid):
    """Resume and kill a process this test started, only while it is still in its group."""
    try:
        if pid and os.getpgid(pid) == pgid:
            os.kill(pid, signal.SIGCONT)
            os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def wait_for(pred, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if pred():
            return True
        time.sleep(0.02)
    return False


def others_in_group(pgid, but):
    out = subprocess.run(["pgrep", "-g", str(pgid)], capture_output=True, text=True).stdout.split()
    return [int(x) for x in out if int(x) != but]


g.log = lambda *a, **k: logs.append(a[0])
write_status(2)
leader = spawn(["/bin/sh", "-c", '"$1" 301 & exec "$1" 300', "sh", job])
child = None
try:
    time.sleep(0.5)
    child = (others_in_group(leader.pid, leader.pid) or [None])[0]
    th = threading.Thread(target=lambda: sr.limited_wait(leader, 95.0, time.time() + 10))
    th.start()
    stopped = wait_for(lambda: stat(leader.pid).startswith("T"), 5)
    os.kill(leader.pid, signal.SIGKILL)        # the leader dies while the guard reports level 2
    th.join(timeout=8)
    time.sleep(0.2)
    test("level 2, leader killed while stopped: the limiter's stop on the rest of the group is released",
         stopped and child and not stat(child).startswith("T"), (stopped, child, stat(child) if child else None))
finally:
    kill_member(child, leader.pid)
    cleanup(leader)

# A job that catches SIGTERM (a plain sleep dies of a default TERM even while stopped on macOS):
# its handler cannot run while the limiter holds it stopped.
trapjob = os.path.join(root, "trapjob.sh")
with open(trapjob, "w") as f:
    f.write("trap 'exit 3' TERM\nwhile :; do /bin/sleep 0.2; done\n")
write_status(0)
p = subprocess.Popen([sys.executable, SAFE_RUN, "--allow-sleep", "--normal", "--", "/bin/sh", trapjob], env=ENV,
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
spawned.append(p)
jpid = None
try:
    def find_job():
        global jpid
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and parts[1] == str(p.pid) and trapjob in parts[2]:
                jpid = int(parts[0])
        return jpid is not None
    found = wait_for(find_job, 8)
    write_status(2)
    held = found and wait_for(lambda: stat(jpid).startswith("T"), 6)
    os.kill(p.pid, signal.SIGTERM)
    try:
        p.wait(timeout=6)
    except subprocess.TimeoutExpired:
        pass
    test("level 2: SIGTERM to safe-run reaches the stopped job's handler and safe-run exits",
         held and p.returncode == 3 and not stat(jpid), (found, held, p.returncode, stat(jpid) if jpid else None))
finally:
    if jpid:
        for m in others_in_group(jpid, 0):
            kill_member(m, jpid)
    cleanup(p)

real_killpg = os.killpg


def killpg_cont_fails(pgid, s):
    if s == signal.SIGCONT:
        raise PermissionError(1, "Operation not permitted")
    return real_killpg(pgid, s)


leader = spawn(["/bin/sh", "-c", '"$1" 301 & exec "$2" 300', "sh", obs, job])
try:
    time.sleep(0.6)
    with patch.object(sr.os, "killpg", side_effect=killpg_cont_fails):
        states, _ = limiter_run(leader, [leader.pid], 4.0)
    final = stat(leader.pid)
    test("group SIGCONT fails: members stopped one by one are resumed one by one",
         states[leader.pid].count("T") > 0 and not final.startswith("T"), (states[leader.pid].count("T"), final))
finally:
    cleanup(leader)

leader = spawn(["/bin/sh", "-c", '"$1" 301 & exec "$2" 300', "sh", obs, job])
foreign = spawn([job, "302"])          # own session: stands in for a pid reused by an unrelated process
try:
    time.sleep(0.6)
    g._PROTECTED_NAMES["names"] = g.protected_names(dict(g.DEFAULTS))
    listed = g.group_members(leader.pid)
    with patch.object(g, "group_members", return_value=listed + [foreign.pid]):
        g.sig(leader.pid, leader.pid, signal.SIGSTOP)
    time.sleep(0.2)
    test("guard sig(): a listed pid that is no longer in the group is not signalled",
         stat(leader.pid).startswith("T") and not stat(foreign.pid).startswith("T"),
         (stat(leader.pid), stat(foreign.pid)))
    g.sig(leader.pid, leader.pid, signal.SIGCONT)
finally:
    cleanup(foreign)
    cleanup(leader)

real_group_paths = sr.group_paths
calls = []


def listing_fails_after_first(pgid):
    calls.append(pgid)
    return real_group_paths(pgid) if len(calls) == 1 else {}


leader = spawn(["/bin/sh", "-c", '"$1" 301 & exec "$2" 300', "sh", obs, job])
try:
    time.sleep(0.6)
    obs_pid = next((m for m in others_in_group(leader.pid, leader.pid) if g.exe_path(m) == obs), None)
    with patch.object(sr, "group_paths", side_effect=listing_fails_after_first):
        states, _ = limiter_run(leader, [obs_pid or leader.pid], 6.5)
    test("ps fails after OBS was seen: the fallback does not stop OBS",
         obs_pid and len(calls) >= 2 and states[obs_pid].count("T") == 0,
         (obs_pid, len(calls), states.get(obs_pid, [])[:60]))
finally:
    cleanup(leader)

p = spawn([job, "300"])
try:
    time.sleep(0.3)
    with patch.object(sr, "group_paths", return_value={}):
        states, _ = limiter_run(p, [p.pid], 3.0)
    test("control: ps blocked and no protected app ever seen: killpg still limits the job",
         states[p.pid].count("T") > 0, len(states[p.pid]))
finally:
    cleanup(p)
time.sleep(0.2)
left = subprocess.run(["pgrep", "-f", root], capture_output=True, text=True).stdout.split()
test("no test process left behind (section 6)", not left, left)

print("\nRESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
