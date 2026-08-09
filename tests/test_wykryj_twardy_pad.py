import importlib.util, os, shutil, sys, tempfile, time

# --- ISOLATION GATE --------------------------------------------------------------
# This test deletes heartbeat, clean_stop, and events.log under <HOME>/.coffee-paladin,
# the black box used for warranty reports. HOME used to come straight from sys.argv[1]
# without validation, so `python3 tests/test_wykryj_twardy_pad.py ~` destroyed real
# evidence. The argument is now optional; without it the test creates its own sandbox.
MARKER = ".piaskownica-testu"


def refuse(reason):
    print("REFUSAL: %s" % reason, file=sys.stderr)
    print("This test deletes heartbeat/clean_stop/events.log. Run without an argument "
          "or provide an empty directory, for example $(mktemp -d).", file=sys.stderr)
    sys.exit(2)


should_clean = len(sys.argv) < 2
home = (tempfile.mkdtemp(prefix="paladin_pad_") if should_clean
        else os.path.abspath(os.path.expanduser(sys.argv[1])))
real_home = os.path.realpath(os.path.expanduser("~"))
if os.path.realpath(home) == real_home:
    refuse("specified directory is the real home directory (%s)" % real_home)
if real_home.startswith(os.path.realpath(home).rstrip("/") + "/"):
    refuse("real home directory is inside %s" % home)

base = os.path.join(home, ".coffee-paladin")
# Marker distinguishes this sandbox from foreign data and allows repeated runs.
if os.path.exists(base) and not os.path.exists(os.path.join(base, MARKER)):
    refuse("%s already exists and is not this test's sandbox" % base)
os.makedirs(base, exist_ok=True)
open(os.path.join(base, MARKER), "w").close()
# ---------------------------------------------------------------------------------
spec = importlib.util.spec_from_file_location("g", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guard.py"))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
g.HOME, g.BASE = home, base
for n in [n for n in dir(g) if n.endswith(("_PATH", "_DIR"))]:
    setattr(g, n, os.path.join(base, os.path.basename(getattr(g, n))))
assert g.EVENTS_PATH.startswith(base), "isolation did not work"
boot = g.boot_time()

def setup(heartbeat_time, clean_run=None, content=None, mtime=None):
    for p in (g.HEARTBEAT_PATH, g.CLEAN_STOP_PATH, g.EVENTS_PATH):
        if os.path.exists(p): os.remove(p)
    with open(g.HEARTBEAT_PATH, "w") as f:
        f.write(content if content is not None else "%d %s" % (heartbeat_time, g.ts(heartbeat_time)))   # New format.
    m = mtime if mtime is not None else heartbeat_time
    os.utime(g.HEARTBEAT_PATH, (m, m))
    with open(g.HIST_PATH, "w") as f:
        f.write("time,thermal_state,chip_C\n2026-07-30 09:00:00,nominal,40.0\n")
    if clean_run is not None:
        open(g.CLEAN_STOP_PATH, "w").close(); os.utime(g.CLEAN_STOP_PATH, (clean_run, clean_run))

def run(name, expected, **kw):
    setup(**kw); r = g.detect_hard_shutdown()
    got = "SHUTDOWN" if r else "silent"
    ok = got == expected
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {got}" + (f" ({r['time']})" if r else ""))
    return ok

print(f"=== A. matrix of 8 cases, NEW format (boot={g.ts(boot)}) ===")
A = [run("1. hard shutdown, no clean_stop", "SHUTDOWN", heartbeat_time=boot-600),
     run("2. clean stop before boot", "silent", heartbeat_time=boot-600, clean_run=boot-600),
     run("3. clean_stop from current session does not silence", "SHUTDOWN", heartbeat_time=boot-600, clean_run=time.time()),
     run("4. clean_stop from the future does not silence", "SHUTDOWN", heartbeat_time=boot-600, clean_run=time.time()+86400),
     run("5. old clean_stop (3 days) does not silence", "SHUTDOWN", heartbeat_time=boot-600, clean_run=boot-3*86400),
     run("6. heartbeat from current session", "silent", heartbeat_time=boot+60),
     # Decision change: the 30-day floor used to discard evidence instead of marking it,
     # making the black box silent exactly when the clock was broken: drained RTC or NTP
     # jump. The event is now written with `confidence: low` and a reason; service staff
     # make the final assessment. Details and countercases: tests/test_pewnosc_padu.py.
     run("7. 1970 phantom: written, but with low confidence", "SHUTDOWN", heartbeat_time=833377),
     run("8. restore without -p: mtime=now, epoch real", "SHUTDOWN", heartbeat_time=boot-600, mtime=time.time())]

print("\n=== B. file format variants ===")
B = [run("legacy (text only, no epoch)", "SHUTDOWN", heartbeat_time=boot-600, content=g.ts(boot-600)),
     run("junk in content -> fallback to mtime", "SHUTDOWN", heartbeat_time=boot-600, content="xyzzy"),
     run("empty file -> fallback to mtime", "SHUTDOWN", heartbeat_time=boot-600, content=""),
     run("new format + junk tail", "SHUTDOWN", heartbeat_time=boot-600, content="%d cokolwiek" % (boot-600))]

print("\n=== C. time zones (real shutdown 10 min before boot) ===")
def tz(shutdown_tz, boot_tz, legacy=False):
    os.environ["TZ"] = shutdown_tz; time.tzset()
    heartbeat_time = boot - 600
    content = g.ts(heartbeat_time) if legacy else "%d %s" % (heartbeat_time, g.ts(heartbeat_time))
    setup(heartbeat_time, content=content)
    os.environ["TZ"] = boot_tz; time.tzset()
    r = g.detect_hard_shutdown()
    print(f"  [{'PASS' if r else 'FAIL'}] {'legacy' if legacy else 'new'}: shutdown in {shutdown_tz} "
          f"-> boot in {boot_tz}: {'SHUTDOWN detected' if r else 'SILENT - evidence lost'}")
    return bool(r)
C = [tz("Europe/Warsaw", "Europe/Warsaw"),
     tz("Europe/Warsaw", "America/New_York"),
     tz("Pacific/Kiritimati", "Pacific/Midway"),
     tz("Europe/Warsaw", "America/New_York", legacy=True)]
os.environ["TZ"] = "Europe/Warsaw"; time.tzset()
if should_clean:
    shutil.rmtree(home, ignore_errors=True)
passed, total = sum(A) + sum(B) + sum(C), len(A) + len(B) + len(C)
print(f"\nRESULT: A {sum(A)}/{len(A)}   B {sum(B)}/{len(B)}   C {sum(C)}/{len(C)}"
      f"   TOTAL {passed}/{total}")
# Without this, the file never exited with an error code; it was "green" only because
# nobody checked the exit code, even though it is the first command in AGENTS.md.
sys.exit(0 if passed == total else 1)
