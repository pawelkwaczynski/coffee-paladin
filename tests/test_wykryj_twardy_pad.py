import importlib.util, os, sys, time
home = sys.argv[1]; base = os.path.join(home, ".thermal-guard"); os.makedirs(base, exist_ok=True)
spec = importlib.util.spec_from_file_location("g", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guard.py"))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
g.HOME, g.BASE = home, base
for n in [n for n in dir(g) if n.endswith(("_PATH", "_DIR"))]:
    setattr(g, n, os.path.join(base, os.path.basename(getattr(g, n))))
assert g.EVENTS_PATH.startswith(base), "izolacja nie zadzialala"
boot = g.boot_time()

def setup(puls, czyste=None, tresc=None, mtime=None):
    for p in (g.HEARTBEAT_PATH, g.CLEAN_STOP_PATH, g.EVENTS_PATH):
        if os.path.exists(p): os.remove(p)
    with open(g.HEARTBEAT_PATH, "w") as f:
        f.write(tresc if tresc is not None else "%d %s" % (puls, g.ts(puls)))   # NOWY format
    m = mtime if mtime is not None else puls
    os.utime(g.HEARTBEAT_PATH, (m, m))
    with open(g.HIST_PATH, "w") as f:
        f.write("time,thermal_state,chip_C\n2026-07-30 09:00:00,nominal,40.0\n")
    if czyste is not None:
        open(g.CLEAN_STOP_PATH, "w").close(); os.utime(g.CLEAN_STOP_PATH, (czyste, czyste))

def run(nazwa, oczekiwane, **kw):
    setup(**kw); r = g.wykryj_twardy_pad()
    got = "PAD" if r else "cicho"
    ok = got == oczekiwane
    print(f"  [{'PASS' if ok else 'FAIL'}] {nazwa}: {got}" + (f" ({r['time']})" if r else ""))
    return ok

print(f"=== A. matryca 8 przypadków, NOWY format (boot={g.ts(boot)}) ===")
A = [run("1. twardy pad, brak clean_stop", "PAD", puls=boot-600),
     run("2. czysty stop sprzed bootu", "cicho", puls=boot-600, czyste=boot-600),
     run("3. clean_stop z bieżącej sesji nie wycisza [Codex]", "PAD", puls=boot-600, czyste=time.time()),
     run("4. clean_stop z przyszłości nie wycisza", "PAD", puls=boot-600, czyste=time.time()+86400),
     run("5. stary clean_stop (3 dni) nie wycisza", "PAD", puls=boot-600, czyste=boot-3*86400),
     run("6. puls z bieżącej sesji", "cicho", puls=boot+60),
     run("7. fantom 1970 (podłoga 30 dni)", "cicho", puls=833377),
     run("8. restore bez -p: mtime=teraz, epoch prawdziwy", "PAD", puls=boot-600, mtime=time.time())]

print("\n=== B. warianty formatu pliku ===")
B = [run("legacy (sam tekst, bez epoch)", "PAD", puls=boot-600, tresc=g.ts(boot-600)),
     run("śmieci w treści → fallback na mtime", "PAD", puls=boot-600, tresc="xyzzy"),
     run("pusty plik → fallback na mtime", "PAD", puls=boot-600, tresc=""),
     run("nowy format + śmieciowy ogon", "PAD", puls=boot-600, tresc="%d cokolwiek" % (boot-600))]

print("\n=== C. strefy czasowe (prawdziwy pad 10 min przed bootem) ===")
def tz(tz_pad, tz_boot, legacy=False):
    os.environ["TZ"] = tz_pad; time.tzset()
    puls = boot - 600
    tresc = g.ts(puls) if legacy else "%d %s" % (puls, g.ts(puls))
    setup(puls, tresc=tresc)
    os.environ["TZ"] = tz_boot; time.tzset()
    r = g.wykryj_twardy_pad()
    print(f"  [{'PASS' if r else 'FAIL'}] {'legacy' if legacy else 'nowy'}: pad w {tz_pad} → boot w {tz_boot}: "
          f"{'PAD wykryty' if r else 'CICHO — dowód utracony'}")
    return bool(r)
C = [tz("Europe/Warsaw", "Europe/Warsaw"),
     tz("Europe/Warsaw", "America/New_York"),
     tz("Pacific/Kiritimati", "Pacific/Midway"),
     tz("Europe/Warsaw", "America/New_York", legacy=True)]
os.environ["TZ"] = "Europe/Warsaw"; time.tzset()
print(f"\nWYNIK: A {sum(A)}/{len(A)}   B {sum(B)}/{len(B)}   C {sum(C)}/{len(C)}")
