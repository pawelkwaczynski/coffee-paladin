#!/usr/bin/env python3
"""Regressions for safe-run process supervision with an isolated TG_BASE."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAFE_RUN = os.path.join(SRC, "safe-run")
passed = 0
total = 0


def check(name, ok, detail=""):
    global passed, total
    total += 1
    passed += bool(ok)
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                            "" if ok else " -> %s" % detail))


def setup():
    base = tempfile.mkdtemp(prefix="tg-real-tools-")
    binary = os.path.join(base, "bin")
    os.makedirs(binary)
    launch = os.path.join(binary, "launchctl")
    with open(launch, "w") as f:
        f.write("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$TG_BASE/launch.calls\"\nexit 0\n")
    os.chmod(launch, 0o755)
    with open(os.path.join(binary, "pgrep"), "w") as f:
        f.write("#!/bin/sh\nexit 3\n")
    os.chmod(os.path.join(binary, "pgrep"), 0o755)
    with open(os.path.join(base, "status.json"), "w") as f:
        json.dump({"level": 0, "chip_c": 45.0,
                   "thresholds": {"pause": 85.0, "resume": 76.0}}, f)
    env = dict(os.environ, TG_BASE=base, TG_LANG="en",
               PATH=binary + os.pathsep + os.environ.get("PATH", ""))
    env.pop("TG_SAFE_RUN_PGID", None)
    return base, binary, env


def run(env, args, **kwargs):
    return subprocess.run([sys.executable, SAFE_RUN, "--normal", "--allow-sleep"] + args,
                          env=env, capture_output=True, timeout=15, **kwargs)


# 21.10: A short command must not pay for a whole CPU-limit window.
# 22.10: the bound is 1.5 s, not 0.8 s: under a loaded test run 0.803 s failed it, and the
# regression it guards against (a blind sleep(2) before the first check) takes over 2 s.
FAST_EXIT_S = 1.5
base, binary, env = setup()
t0 = time.monotonic()
r = run(env, ["--", "/usr/bin/true"])
elapsed = time.monotonic() - t0
check("RT-1 prompt default exit", r.returncode == 0 and elapsed < FAST_EXIT_S,
      "rc=%s elapsed=%.3f stderr=%r" % (r.returncode, elapsed, r.stderr[-200:]))
with open(os.path.join(base, "config.json"), "w") as f:
    json.dump({"job_cpu_percent": 100}, f)
t0 = time.monotonic()
r = run(env, ["--", "/usr/bin/true"])
elapsed = time.monotonic() - t0
check("RT-1 prompt uncapped exit", r.returncode == 0 and elapsed < FAST_EXIT_S,
      "rc=%s elapsed=%.3f stderr=%r" % (r.returncode, elapsed, r.stderr[-200:]))
r = run(env, ["--", "/bin/sh", "-c", "exit 7"])
check("RT-1 exit code", r.returncode == 7, "rc=%s" % r.returncode)

# 21.10: ffmpeg's stderr-only error channel must stay empty for a clean job.
base, binary, env = setup()
env["SAFE_RUN_QUIET"] = "1"
r = run(env, ["--", "/bin/sh", "-c", "echo E >&2"])
log = os.path.join(base, "safe-run.log")
logged = open(log).read() if os.path.exists(log) else ""
check("RT-3 env quiet", r.returncode == 0 and r.stderr == b"E\n"
      and "exit code 0" in logged, "stderr=%r log=%r" % (r.stderr, logged[-200:]))
env.pop("SAFE_RUN_QUIET")
r = run(env, ["--quiet", "--", "/bin/sh", "-c", "echo E >&2"])
check("RT-3 flag quiet", r.returncode == 0 and r.stderr == b"E\n",
      "rc=%s stderr=%r" % (r.returncode, r.stderr))
r = run(env, ["--", "/bin/sh", "-c", "echo E >&2"])
check("RT-3 normal summary", b"exit code 0" in r.stderr,
      "stderr=%r" % r.stderr[-200:])

# 21.10: A closed fd 2 must not put wrapper text into the child's stdout.
base, binary, env = setup()
cmd = "exec %s %s --normal --allow-sleep -- /bin/sh -c 'printf OUT; exit 7' 2>&-" % (
    sys.executable, SAFE_RUN)
r = subprocess.run(["/bin/sh", "-c", cmd], env=env, capture_output=True, timeout=15)
check("RT-2 closed stderr", r.returncode == 7 and r.stdout == b"OUT",
      "rc=%s stdout=%r" % (r.returncode, r.stdout[-200:]))

# 21.10: HUP to the wrapper's session must also reach its separate job group.
base, binary, env = setup()
marker = os.path.join(base, "sleep.pid")
shell = 'echo $$ > "$1"; exec /bin/sleep 30'
p = subprocess.Popen([sys.executable, SAFE_RUN, "--normal", "--allow-sleep", "--",
                      "/bin/sh", "-c", shell, "sh", marker], env=env,
                     start_new_session=True, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE)
child = None
try:
    for _ in range(40):
        if os.path.exists(marker):
            child = int(open(marker).read())
            break
        time.sleep(0.05)
    if child:
        os.killpg(p.pid, signal.SIGHUP)
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    gone = False
    if child:
        for _ in range(40):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                gone = True
                break
            time.sleep(0.05)
    check("SIG-1 HUP forwarded", child is not None and gone,
          "wrapper_rc=%s child=%s gone=%s" % (p.poll(), child, gone))
finally:
    if child:
        try:
            os.killpg(child, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if p.poll() is None:
        os.killpg(p.pid, signal.SIGKILL)
    p.communicate(timeout=3)

# 21.10: A read-only managed directory must not orphan a launched job.
base, binary, env = setup()
managed = os.path.join(base, "managed")
os.makedirs(managed)
os.chmod(managed, 0o500)
pid_file = os.path.join(base, "registered_job.pid")
try:
    r = run(env, ["--", "/bin/sh", "-c", 'echo $$ > "$1"; exit 5',
                  "sh", pid_file])
finally:
    os.chmod(managed, 0o700)
warning = b"cannot register the job, it runs without the guard's registration"
gone = False
if os.path.exists(pid_file):
    try:
        os.kill(int(open(pid_file).read()), 0)
    except ProcessLookupError:
        gone = True
check("CC-1 registration failure", r.returncode == 5 and r.stdout == b""
      and gone and r.stderr.count(warning) == 1 and b"Traceback" not in r.stderr,
      "rc=%s gone=%s stderr=%r" % (r.returncode, gone, r.stderr[-400:]))

# 21.10: A failed process-list query cannot prove the guard is dead.
base, binary, env = setup()
r = run(env, ["--", "/usr/bin/true"])
calls = open(os.path.join(base, "launch.calls")).read() if os.path.exists(
    os.path.join(base, "launch.calls")) else ""
check("CC-2 fresh heartbeat", r.returncode == 0 and "kickstart" not in calls,
      "rc=%s calls=%r" % (r.returncode, calls))

# 21.10: Help must state the same default as SAFE_RUN_HOURS parsing.
base, binary, env = setup()
r = subprocess.run([sys.executable, SAFE_RUN, "--help"], env=env,
                   capture_output=True, timeout=15)
check("F13 help budget", r.returncode == 0 and b"20 h by default" in r.stdout,
      repr(r.stdout[:400]))

print("RESULT: %d/%d" % (passed, total))
sys.exit(0 if passed == total else 1)
