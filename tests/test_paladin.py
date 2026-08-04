#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""21 testow rebrandingu coffee-paladin (eggi, animacja, tlumaczenia, grafika, regresja).
NIE dotyka procesow uzytkownika ani prawdziwego ~/.coffee-paladin - tylko czyta zrodla
i uruchamia CLI w trybie tylko-do-odczytu.  Uruchom:  python3 testy/test_paladin.py"""
import io, os, re, struct, subprocess, sys

SRC = os.path.dirname(os.path.abspath(__file__)) + "/.."
BIN = os.path.expanduser("~/.local/bin")
wyniki = []


def test(nazwa, warunek, detal=""):
    wyniki.append((nazwa, bool(warunek)))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           ("  -> " + detal) if detal and not warunek else ""))


def czytaj(f):
    return io.open(os.path.join(SRC, f), encoding="utf-8").read()


def cli(args):
    p = subprocess.run([os.path.join(BIN, "heat")] + args, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout


print("=== coffee-paladin: 21 testow (wzmocnione po recenzji Codex+Devstral) ===")

# 0. zainstalowane CLI == zrodlo (inaczej reszta testuje stara binarke)
import filecmp
test("0. zainstalowany heat = aktualne zrodlo",
     filecmp.cmp(os.path.join(SRC, "heat"), os.path.join(BIN, "heat"), shallow=False),
     "~/.local/bin/heat rozni sie od zrodla - reszta testow nic nie dowodzi")

# 1. JEDEN egg: --paladin. Stare flagi maja byc naprawde usuniete, a nie martwe
#    (kiedys --espresso/--paladin/--knight dawaly prawie to samo).
rc2, o2 = cli(["--paladin"])
zrodlo_heat = czytaj("heat")
test("1. jedyna komenda egga to --paladin (stare flagi wyciete ze zrodla)",
     rc2 == 0 and "--espresso" not in zrodlo_heat and "--knight" not in zrodlo_heat,
     "kod=%s, espresso=%s, knight=%s" % (rc2, "--espresso" in zrodlo_heat,
                                         "--knight" in zrodlo_heat))

# 2. rysunek w kolorze musi byc W PELNEJ jakosci (polbloki, >=40 linii) - to jest
#    ta wersja, ktora widzi uzytkownik nowoczesnego terminala. Sprawdzamy w zrodle,
#    bo test biegnie bez tty i sam dostalby fallback.
mk = re.search(r'PALADIN_KOLOR = """\n(.*?)\n"""', zrodlo_heat, re.S)
art_kolor = mk.group(1).split("\n") if mk else []
szer_kolor = max((len(re.sub(r"\x1b\[[0-9;]*m", "", l)) for l in art_kolor), default=0)
test("2. rysunek kolorowy: >=40 linii polblokow, szerokosc miesci sie w 80 kolumnach",
     len(art_kolor) >= 40 and 60 <= szer_kolor <= 80
     and sum(l.count("\u2580") + l.count("\u2584") for l in art_kolor) > 800
     and "coffee-paladin" in o2 and "Shield the Process" in o2
     and "github.com/pawelkwaczynski/coffee-paladin" in o2,
     "linii: %d, szerokosc: %d" % (len(art_kolor), szer_kolor))

# 3. jedna komenda niesie CALY meldunek warty: temperatura + przysiega + statystyki
test("3. --paladin: temperatura i statystyki, BEZ angielskiej przysiegi",
     re.search(r"\d+[.,]\d+\s*C", o2) is not None
     and re.search(r"\d+\s+(pauz|pause)", o2) is not None
     and "coffee first" not in o2          # linia wycieta na zyczenie autora
     and "coffee-paladin" in o2
     and "pawelkwaczynski/coffee-paladin" in o2   # adres po zmianie nazwy repo
     and "pawelkwaczynski/thermal-guard" not in o2,
     "brak czesci meldunku albo zostal stary adres/przysiega")

# 4. animacja: 8 klatek, kazda linia rownej dlugosci (monospace-safe)
hb = czytaj("heatbar.swift")
m = re.search(r"let PALADIN_FRAMES: \[String\] = \[(.*?)\n\]", hb, re.S)
klatki = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)) if m else []
def dekoduj(s):
    return re.sub(r"\\u\{([0-9A-Fa-f]+)\}", lambda x: chr(int(x.group(1), 16)), s).split("\\n")
rozmiary = [{len(l) for l in dekoduj(k)} for k in klatki]
wszystkie_szer = set()
for r in rozmiary:
    wszystkie_szer |= r
test("4. 8 klatek, stala szerokosc W KAZDEJ i MIEDZY klatkami",
     len(klatki) == 8 and all(len(r) == 1 for r in rozmiary) and len(wszystkie_szer) == 1,
     "klatek: %d, szerokosci w calym zestawie: %s" % (len(klatki), wszystkie_szer))

# 5. wszystkie klatki maja te sama liczbe linii (postac nie 'plywa')
linie = {len(dekoduj(k)) for k in klatki}
test("5. wszystkie klatki maja tyle samo linii", len(linie) == 1, "linie: %s" % linie)

# 6. rebrand: nazwa i motto w pasku
test("6. APPNAME/MOTTO faktycznie UZYTE w UI (nie tylko zadeklarowane)",
     'let APPNAME = "coffee-paladin"' in hb
     and "SIGNATURE = \"\\(APPNAME)" in hb
     and "labelWithString: \"\\(APPNAME)  \u00b7  v\\(VERSION)\")" in hb
     and "labelWithString: MOTTO" in hb
     and "thermal-guard  ·  v" not in hb,
     "deklaracja bez uzycia albo zostala stara nazwa w naglowku")

# 7. tlumaczenia: klucze powitania w 4 slownikach + etykieta wyjscia bez pulapki
# kazdy slownik musi miec NIE-angielskie tlumaczenie obu kluczy
def tlumaczenia(klucz_en):
    return [m for m in re.findall(re.escape(klucz_en) + r'\s*:\s*"((?:[^"\\]|\\.)*)"', hb)]
tp = tlumaczenia('"The paladin stands guard. Choose how to begin:"')
tq = tlumaczenia('"Quit coffee-paladin (protection stops)"')
test("7. realne tlumaczenia powitania i etykiety wyjscia w 4 jezykach",
     len(tp) == 4 and len(tq) == 4
     and all(t_ != "The paladin stands guard. Choose how to begin:" for t_ in tp)
     and all(t_ != "Quit coffee-paladin (protection stops)" for t_ in tq),
     "powitanie: %d tlumaczen, wyjscie: %d" % (len(tp), len(tq)))

# 8. regresja DWUCZESCIOWA: (a) zrodlo guarda kompiluje sie i przechodzi --once w IZOLACJI,
#    (b) zywa instalacja Pawla dziala (to celowo dotyka prawdziwego ~/.coffee-paladin - read-only)
import time, tempfile, py_compile, shutil
st = os.path.expanduser("~/.coffee-paladin/status.json")
wiek = time.time() - os.path.getmtime(st)
# TYLKO BIEZACA SESJA demona. Test szukal bledow petli w CALYM logu, wiec jeden blad
# sprzed naprawy trzymal bramke na czerwono do konca zycia pliku - a to nie jest sygnal
# o stanie maszyny, tylko o jej historii. Odcinamy od ostatniego wpisu startowego.
_pelny = io.open(os.path.expanduser("~/.coffee-paladin/guard.log"),
                 encoding="utf-8", errors="replace").read()
_starty = [i for i, l in enumerate(_pelny.splitlines()) if "coffee-paladin start" in l]
log = "\n".join(_pelny.splitlines()[_starty[-1]:]) if _starty else _pelny
zrodlo_ok = True
tmp = tempfile.mkdtemp(prefix="paladin_test_once_")
try:
    # cfile w katalogu tymczasowym: bez tego py_compile zostawia __pycache__ w drzewie zrodel
    py_compile.compile(os.path.join(SRC, "guard.py"),
                       cfile=os.path.join(tmp, "guard.pyc"), doraise=True)
    # TG_BASE jest OBOWIAZKOWE. `--once` NIE jest tylko-do-odczytu: wola
    # managed_pids_from_saferun(), ktora robi os.unlink na plikach rejestracji, oraz
    # ensure_dirs(), ktora robi chmod na katalogu danych. Bez tej zmiennej ten test
    # kasowal rejestracje DZIALAJACYCH zadan safe-run w prawdziwym ~/.coffee-paladin
    # (odtworzone 02.08.2026: zywy pid znikal z managed/ po jednym przebiegu).
    p = subprocess.run([sys.executable, os.path.join(SRC, "guard.py"), "--once"],
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, TG_LANG="en", TG_BASE=tmp))
    zrodlo_ok = p.returncode == 0 and "state=" in p.stdout
except Exception:
    zrodlo_ok = False
finally:
    shutil.rmtree(tmp, ignore_errors=True)
test("8. regresja: zrodlo guarda kompiluje sie i raportuje + zywa instalacja zdrowa",
     zrodlo_ok and wiek < 60 and "LOOP ERROR" not in log and "BLAD petli" not in log,
     "zrodlo_ok=%s, wiek statusu: %.0fs" % (zrodlo_ok, wiek))

# --- grafika oficjalna (bez zadnych zaleznosci: czytamy naglowki PNG/GIF recznie) ---

def png_wh(p):
    with open(p, "rb") as f:
        d = f.read(33)
    assert d[:8] == b"\x89PNG\r\n\x1a\n" and d[12:16] == b"IHDR", "to nie PNG: " + p
    return struct.unpack(">II", d[16:24])


def gif_wh_klatki(p):
    d = open(p, "rb").read()
    assert d[:6] in (b"GIF89a", b"GIF87a"), "to nie GIF: " + p
    w, h = struct.unpack("<HH", d[6:10])
    return w, h, d.count(b"\x21\xf9\x04")     # bloki Graphic Control = klatki


B = os.path.join(SRC, "branding")

# 9. oficjalne zrodla grafiki sa w repo i sa tym, czym maja byc
try:
    ow, oh = png_wh(os.path.join(B, "paladin.png"))
    gw, gh, gk = gif_wh_klatki(os.path.join(B, "paladin.gif"))
    ok9 = ow >= 1000 and oh >= 1400 and gk >= 8 and gh > gw      # portret, nie miniatura
except Exception:
    ow = oh = gw = gh = gk = 0
    ok9 = False
test("9. oficjalne zrodla: paladin.png (duzy portret) + paladin.gif (animacja)",
     ok9, "png %sx%s, gif %sx%s klatek=%s" % (ow, oh, gw, gh, gk))

# 10. pochodne uzywane przez aplikacje istnieja, sa animowane i maja rozsadny rozmiar
try:
    ww, wh, wk = gif_wh_klatki(os.path.join(B, "paladin_welcome.gif"))
    fw, fh = png_wh(os.path.join(B, "paladin_welcome.png"))
    waga = os.path.getsize(os.path.join(B, "paladin_welcome.gif"))
    ok10 = (wk >= 8 and 300 <= wh <= 700 and waga < 3 * 1024 * 1024
            and abs(fw / max(fh, 1) - ww / max(wh, 1)) < 0.05     # ten sam kadr co animacja
            # miniatura w naglowku menu zostala USUNIETA - ma nie wrocic bocznymi drzwiami
            and not os.path.exists(os.path.join(B, "paladin_icon.png"))
            and "paladin_icon" not in hb)
except Exception:
    ww = wh = wk = fw = fh = waga = 0
    ok10 = False
test("10. pochodne: welcome.gif animowany + PNG w tym samym kadrze, bez miniatury w menu",
     ok10, "welcome %sx%s k=%s (%.1f MB), png %sx%s"
           % (ww, wh, wk, waga / 1048576.0, fw, fh))

# 11. atrybucja ChatGPT jest zapisana tam, gdzie ktos ja zobaczy (CREDITS + README)
try:
    kred = czytaj("branding/CREDITS.md")
    rd = czytaj("README.md")
    ok11 = ("ChatGPT" in kred and "paladin.gif" in kred
            and "ChatGPT" in rd)
except Exception:
    kred = rd = ""
    ok11 = False
test("11. atrybucja 'wygenerowane w ChatGPT' w CREDITS.md i w README", ok11,
     "CREDITS: %s, README: %s" % ("ChatGPT" in kred, "ChatGPT" in rd))

# 12. okno powitalne woli animacje, a instalator faktycznie ja kopiuje
sh = czytaj("install.sh")
test("12. Swift laduje paladin_welcome.gif (z fallbackiem) i install.sh go kopiuje",
     'contentsOfFile: base + "/paladin_welcome.gif"' in hb
     and 'contentsOfFile: base + "/paladin_welcome.png"' in hb
     and "iv.animates = true" in hb
     and "paladin_welcome.gif" in sh,
     "brak sciezki GIF w Swift albo w install.sh")

# 13. --ascii ma wymuszac wersje znakowa NAWET w terminalu z truecolor.
#     Bez pty nie da sie tego sprawdzic uczciwie: heat patrzy na isatty().
import pty
def przez_pty(args, env_extra, surowo=False):
    zebrane = []
    pid, fd = pty.fork()
    if pid == 0:
        # bez tego dziecko dziedziczy TERM_PROGRAM terminala, w ktorym akurat
        # uruchomiono testy - i "zwykly terminal" wcale nie jest zwykly
        for zmienna in ("TERM", "TERM_PROGRAM", "COLORTERM", "TMUX", "NO_COLOR", "TG_NO_IMAGE"):
            os.environ.pop(zmienna, None)
        os.environ.update(env_extra)
        os.execv(os.path.join(BIN, "heat"), [os.path.join(BIN, "heat")] + args)
        os._exit(127)
    try:
        while True:
            d = os.read(fd, 65536)
            if not d:
                break
            zebrane.append(d)
    except OSError:
        pass
    os.waitpid(pid, 0)
    razem = b"".join(zebrane)
    return razem if surowo else razem.decode("utf-8", "replace")

kolorowy = przez_pty(["--paladin"], {"COLORTERM": "truecolor", "TERM": "xterm-256color"})
wymuszony = przez_pty(["--paladin", "--ascii"], {"COLORTERM": "truecolor", "TERM": "xterm-256color"})
# Fallback to filizanka z pierwszej wersji thermal-guard, nie zdegradowany paladyn:
# w terminalu bez truecolor postaci nie da sie narysowac uczciwie, wiec rysujemy
# to, co w znakach zawsze wygladalo dobrze.
test("13. truecolor -> paladyn, --ascii -> filizanka (a nie rozmyty paladyn)",
     kolorowy.count("38;2;") > 100 and wymuszony.count("38;2;") == 0
     and ".------------." in wymuszony and "~~~~~~~~~~" in wymuszony
     and "Shield the Process" in wymuszony,
     "kolor: %d sekwencji, --ascii: %d, kubek: %s"
     % (kolorowy.count("38;2;"), wymuszony.count("38;2;"), "`-----'" in wymuszony))

# 14. klikniecie nazwy w menu otwiera paladyna przypietego pod paskiem
test("14. panel paladyna: klikalna nazwa + kotwica pod ikona paska",
     "final class PaladinPanel" in hb
     and "PaladinPanel.shared.toggle()" in hb
     and "override func mouseUp" in hb
     and "Bar.shared?.item.button" in hb
     and "cancelTracking()" in hb,          # menu musi sie zamknac PRZED panelem
     "brak panelu albo kotwiczenia w pasku")

# 15. wyjscie = koniec programu, nie schowanie ikony. Etykieta i skutek musza sie zgadzac:
#     zatrzymujemy demona I pasek, i pytamy przed tym nieodwracalnym krokiem.
test("15. Quit zatrzymuje DEMONA i pasek, po potwierdzeniu w oknie",
     'bootout", "gui/\\(uid)/pl.pawel.coffee-paladin"' in hb
     and 'bootout", "gui/\\(uid)/pl.pawel.coffee-paladin-bar"' in hb
     # Potwierdzenie MUSI byc, ale test nie moze pilnowac klasy okna: od 2.1.5 to
     # wlasne okno z paladynem na srodku, nie NSAlert. Pilnujemy skutku - pytania
     # przed nieodwracalnym krokiem i tego, ze wyjscie nastepuje TYLKO po zgodzie.
     and 'T("Turn off thermal protection for this Mac?")' in hb
     and "NSApp.runModal(for: win)" in hb
     and "guard wynik.rawValue == 0 else { return }" in hb
     and "protection keeps running" not in hb,     # stara, mylaca obietnica ma zniknac
     "brak zatrzymania demona albo zostala stara etykieta")

# 16. skill dla agentow AI: musi istniec, miec poprawny naglowek i UCZYC rzeczy,
#     ktore naprawde sa w programie (level, safe-run, zakaz SIGCONT).
try:
    sk = czytaj("skills/coffee-paladin/SKILL.md")
    ok16 = (sk.startswith("---") and "name: coffee-paladin" in sk
            and "description:" in sk
            and "status.json" in sk and "safe-run" in sk
            and "SIGCONT" in sk and "level" in sk
            and "skills/coffee-paladin/SKILL.md" in sh)   # instalator go rozklada
except Exception:
    sk = ""
    ok16 = False
test("16. skill dla agentow AI istnieje i uczy realnego interfejsu guarda", ok16,
     "brak skilla, naglowka albo wpisu w install.sh")

# 17. PRAWDZIWY obrazek w terminalu, ktory to potrafi (Ghostty/kitty/WezTerm).
#     Test sklada porcje protokolu z powrotem i porownuje z plikiem PNG bajt w bajt -
#     zle poskladane chunki albo zla flaga m to najczestszy blad w tym protokole.
import base64, hashlib
sur = przez_pty(["--paladin"], {"TERM": "xterm-ghostty", "TERM_PROGRAM": "ghostty",
                                "COLORTERM": "truecolor"}, surowo=True)
bloki = re.findall(rb"\x1b_G([^;]*);([A-Za-z0-9+/=]*)\x1b\\", sur)
png = os.path.expanduser("~/.coffee-paladin/paladin_welcome.png")
try:
    oryg = open(png, "rb").read()
    zlozone = base64.b64decode(b"".join(b for _, b in bloki))
    ok17 = (len(bloki) > 1
            and b"a=T,f=100,t=d,r=" in bloki[0][0]
            and all(b"m=1" in h for h, _ in bloki[:-1]) and b"m=0" in bloki[-1][0]
            and hashlib.sha256(zlozone).digest() == hashlib.sha256(oryg).digest())
except Exception:
    ok17 = False
# a w terminalu bez tej umiejetnosci obrazka NIE wysylamy (inaczej sypie smieciami)
zwykly = przez_pty(["--paladin"], {"TERM": "xterm-256color", "COLORTERM": "truecolor"}, surowo=True)
test("17. obrazek w Ghostty sklada sie bajt w bajt; w zwyklym terminalu go nie ma",
     ok17 and b"\x1b_G" not in zwykly and zwykly.count("▀".encode()) > 500,
     "porcji: %d, obrazek w zwyklym terminalu: %s" % (len(bloki), b"\x1b_G" in zwykly))

# 18. Zrzuty ekranu w README: kazdy link musi prowadzic do istniejacego pliku,
#     a caly katalog ma sie miescic w budzecie repo (WebP, nie PNG - roznica 10x).
rd = czytaj("README.md")
uzyte = set(re.findall(r"docs/screens/([\w.]+)", rd))
kat = os.path.join(SRC, "docs", "screens")
try:
    pliki = set(os.listdir(kat))
    waga = sum(os.path.getsize(os.path.join(kat, f)) for f in pliki)
except Exception:
    pliki, waga = set(), 0
zepsute = sorted(uzyte - pliki)
test("18. zrzuty: linki w README prowadza do plikow, katalog ponizej 2 MB",
     len(uzyte) >= 10 and not zepsute and waga < 2 * 1024 * 1024
     and all(f.endswith(".webp") for f in pliki),
     "zepsute: %s, waga: %.1f MB, plikow: %d" % (zepsute, waga / 1048576.0, len(pliki)))

# 19. README opisuje skill dla agentow - w OBU jezykach - i opis zgadza sie ze skillem
#     (opis, ktory obiecuje cos, czego skill nie mowi, jest gorszy niz brak opisu).
opis_en = "## Your AI agent can talk to it" in rd
opis_pl = "## Twój agent AI umie z nim rozmawiać" in rd
zgodnosc = all(
    (k in rd and k in sk) for k in ("status.json", "safe-run", "SIGCONT", "dry_run", "unpausable")
)
test("19. README opisuje skill (EN+PL) i nie obiecuje wiecej, niz skill naprawde mowi",
     opis_en and opis_pl and zgodnosc
     and "~/.claude/skills/coffee-paladin" in rd,
     "EN=%s PL=%s zgodnosc=%s" % (opis_en, opis_pl, zgodnosc))

# 20. README w trzech dodatkowych jezykach: istnieja, sa naprawde przetlumaczone
#     (nie kopia angielskiego), maja dzialajace obrazki i te same fakty co oryginal.
def znaki_w(txt, od, do):
    return sum(1 for c in txt if od <= ord(c) <= do)

jezyki = {}
for plik, sprawdz in (("README.zh.md", lambda s: znaki_w(s, 0x4E00, 0x9FFF) > 800),
                      ("README.ru.md", lambda s: znaki_w(s, 0x0400, 0x04FF) > 2000),
                      ("README.es.md", lambda s: s.count("ó") + s.count("é") + s.count("í") > 60)):
    try:
        s_ = czytaj(plik)
        obrazki = set(re.findall(r"(?:docs/screens|branding)/([\w.]+)", s_))
        zle = [o for o in obrazki
               if not (os.path.exists(os.path.join(SRC, "docs/screens", o))
                       or os.path.exists(os.path.join(SRC, "branding", o)))]
        jezyki[plik] = (sprawdz(s_) and len(obrazki) >= 5 and not zle
                        # te same twarde fakty, co w oryginale - inaczej tlumaczenie klamie
                        and "89" in s_ and "60" in s_ and "595" in s_
                        and "MIT" in s_ and "ChatGPT" in s_
                        and "pawelkwaczynski/coffee-paladin" in s_)
    except Exception:
        jezyki[plik] = False
odn = all(("(%s)" % p) in rd for p in ("README.zh.md", "README.ru.md", "README.es.md"))
test("20. README zh/ru/es: realne tlumaczenia, dobre obrazki, zgodne liczby, odnosniki",
     all(jezyki.values()) and odn,
     "%s, odnosniki w README: %s" % (jezyki, odn))

ok = sum(1 for _, w in wyniki if w)
print("\nWYNIK: %d/%d" % (ok, len(wyniki)))
sys.exit(0 if ok == len(wyniki) else 1)
