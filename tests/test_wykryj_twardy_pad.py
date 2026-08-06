import importlib.util, os, shutil, sys, tempfile, time

# --- BRAMKA IZOLACJI -------------------------------------------------------------
# Ten test KASUJE heartbeat, clean_stop i events.log w <HOME>/.coffee-paladin, czyli
# czarna skrzynke do raportu gwarancyjnego. Wczesniej HOME szedl prosto z sys.argv[1]
# bez sprawdzenia, wiec `python3 tests/test_wykryj_twardy_pad.py ~` niszczyl prawdziwe
# dowody. Argument jest teraz opcjonalny - bez niego test robi wlasna piaskownice.
MARKER = ".piaskownica-testu"


def odmow(powod):
    print("ODMOWA: %s" % powod, file=sys.stderr)
    print("Ten test kasuje heartbeat/clean_stop/events.log. Uruchom bez argumentu "
          "albo podaj pusty katalog, np. $(mktemp -d).", file=sys.stderr)
    sys.exit(2)


sprzatac = len(sys.argv) < 2
home = (tempfile.mkdtemp(prefix="paladin_pad_") if sprzatac
        else os.path.abspath(os.path.expanduser(sys.argv[1])))
prawdziwy_home = os.path.realpath(os.path.expanduser("~"))
if os.path.realpath(home) == prawdziwy_home:
    odmow("wskazany katalog to prawdziwy katalog domowy (%s)" % prawdziwy_home)
if prawdziwy_home.startswith(os.path.realpath(home).rstrip("/") + "/"):
    odmow("prawdziwy katalog domowy lezy wewnatrz %s" % home)

base = os.path.join(home, ".coffee-paladin")
# marker odroznia wlasna piaskownice od cudzych danych i pozwala powtorzyc przebieg
if os.path.exists(base) and not os.path.exists(os.path.join(base, MARKER)):
    odmow("%s juz istnieje i nie jest piaskownica tego testu" % base)
os.makedirs(base, exist_ok=True)
open(os.path.join(base, MARKER), "w").close()
# ---------------------------------------------------------------------------------
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
     run("3. clean_stop z bieżącej sesji nie wycisza", "PAD", puls=boot-600, czyste=time.time()),
     run("4. clean_stop z przyszłości nie wycisza", "PAD", puls=boot-600, czyste=time.time()+86400),
     run("5. stary clean_stop (3 dni) nie wycisza", "PAD", puls=boot-600, czyste=boot-3*86400),
     run("6. puls z bieżącej sesji", "cicho", puls=boot+60),
     # ZMIANA DECYZJI 02.08.2026 (pozycja 3): podłoga 30-dniowa WYRZUCAŁA dowód zamiast
     # go oznaczyć — czyli czarna skrzynka milczała dokładnie wtedy, gdy zegar był zepsuty
     # (rozładowany RTC, skok NTP). Teraz zdarzenie jest ZAPISYWANE z `confidence: low`
     # i podanym powodem; ocenę zostawiamy człowiekowi w serwisie.
     # Szczegóły i przypadki przeciwne: tests/test_pewnosc_padu.py.
     run("7. fantom 1970: zapisany, ale z niską wiarygodnością", "PAD", puls=833377),
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
if sprzatac:
    shutil.rmtree(home, ignore_errors=True)
zaliczone, wszystkie = sum(A) + sum(B) + sum(C), len(A) + len(B) + len(C)
print(f"\nWYNIK: A {sum(A)}/{len(A)}   B {sum(B)}/{len(B)}   C {sum(C)}/{len(C)}"
      f"   RAZEM {zaliczone}/{wszystkie}")
# Bez tego plik nigdy nie konczyl sie kodem bledu - byl "zielony" wylacznie dlatego,
# ze nikt nie patrzyl na kod wyjscia, a jest pierwsza komenda w AGENTS.md.
sys.exit(0 if zaliczone == wszystkie else 1)
