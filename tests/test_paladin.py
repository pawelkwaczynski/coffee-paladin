#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify 21 coffee-paladin rebrand checks: eggs, animation, translations, art, regression.

Does not touch user processes or the real ~/.coffee-paladin. It only reads source files
and runs the CLI in read-only mode. Run with:  python3 tests/test_paladin.py
"""
import io, os, re, struct, subprocess, sys

SRC = os.path.dirname(os.path.abspath(__file__)) + "/.."
BIN = os.path.expanduser("~/.local/bin")
results = []


def test(name, condition, detail=""):
    results.append((name, bool(condition)))
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", name,
                           ("  -> " + detail) if detail and not condition else ""))


def read_file(f):
    return io.open(os.path.join(SRC, f), encoding="utf-8").read()


def cli(args):
    p = subprocess.run([os.path.join(BIN, "heat")] + args, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout


print("=== coffee-paladin: 21 tests (strengthened after review rounds) ===")

# 0. Installed CLI == source; otherwise the rest tests an old binary.
import filecmp
test("0. installed heat = current source",
     filecmp.cmp(os.path.join(SRC, "heat"), os.path.join(BIN, "heat"), shallow=False),
     "~/.local/bin/heat differs from source - the rest of the tests prove nothing")

# 1. One egg: --paladin. Old flags must be truly removed, not dead options.
#    --espresso/--paladin/--knight once did almost the same thing.
rc2, o2 = cli(["--paladin"])
heat_source = read_file("heat")
test("1. only egg command is --paladin (old flags removed from source)",
     rc2 == 0 and "--espresso" not in heat_source and "--knight" not in heat_source,
     "code=%s, espresso=%s, knight=%s" % (rc2, "--espresso" in heat_source,
                                         "--knight" in heat_source))

# 2. Color art must be full quality: half-blocks, >=40 lines. This is the version a
#    modern terminal shows. Check source because the test runs without a tty and would
#    otherwise get the fallback.
mk = re.search(r'PALADIN_COLOR = """\n(.*?)\n"""', heat_source, re.S)
color_art = mk.group(1).split("\n") if mk else []
color_width = max((len(re.sub(r"\x1b\[[0-9;]*m", "", l)) for l in color_art), default=0)
test("2. color art: >=40 half-block lines, width fits within 80 columns",
     len(color_art) >= 40 and 60 <= color_width <= 80
     and sum(l.count("\u2580") + l.count("\u2584") for l in color_art) > 800
     and "coffee-paladin" in o2 and "Shield the Process" in o2
     and "github.com/pawelkwaczynski/coffee-paladin" in o2,
     "lines: %d, width: %d" % (len(color_art), color_width))

# 3. One command carries the full guard report: temperature, oath, and statistics.
test("3. --paladin: temperature and statistics, WITHOUT the English oath",
     re.search(r"\d+[.,]\d+\s*C", o2) is not None
     and re.search(r"\d+\s+(pauz|pause)", o2) is not None
     and "coffee first" not in o2          # Line removed at the author's request.
     and "coffee-paladin" in o2
     and "pawelkwaczynski/coffee-paladin" in o2   # URL after repository rename.
     and "pawelkwaczynski/thermal-guard" not in o2,
     "missing report part or old address/oath remains")

# 4. Animation: 8 frames, every line equal length for monospace safety.
hb = read_file("heatbar.swift")
m = re.search(r"let PALADIN_FRAMES: \[String\] = \[(.*?)\n\]", hb, re.S)
frames = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)) if m else []
def decode_frame(s):
    return re.sub(r"\\u\{([0-9A-Fa-f]+)\}", lambda x: chr(int(x.group(1), 16)), s).split("\\n")
sizes = [{len(l) for l in decode_frame(k)} for k in frames]
all_widths = set()
for r in sizes:
    all_widths |= r
test("4. 8 frames, constant width IN EACH frame and BETWEEN frames",
     len(frames) == 8 and all(len(r) == 1 for r in sizes) and len(all_widths) == 1,
     "frames: %d, widths across full set: %s" % (len(frames), all_widths))

# 5. All frames have the same line count, so the figure does not float.
lines = {len(decode_frame(k)) for k in frames}
test("5. all frames have the same line count", len(lines) == 1, "lines: %s" % lines)

# 6. Rebrand: name and motto in the menu bar.
test("6. APPNAME/MOTTO actually USED in UI (not only declared)",
     'let APPNAME = "coffee-paladin"' in hb
     and "SIGNATURE = \"\\(APPNAME)" in hb
     and "labelWithString: \"\\(APPNAME)  \u00b7  v\\(VERSION)\")" in hb
     and "labelWithString: MOTTO" in hb
     and "thermal-guard  ·  v" not in hb,
     "declaration without use or old name still in header")

# 7. Translations: welcome keys in 4 dictionaries plus a clear quit label.
# Each dictionary must have non-English translations for both keys.
def translations(en_key):
    return [m for m in re.findall(re.escape(en_key) + r'\s*:\s*"((?:[^"\\]|\\.)*)"', hb)]
tp = translations('"The paladin stands guard. Choose how to begin:"')
tq = translations('"Quit coffee-paladin (protection stops)"')
test("7. real translations of welcome text and quit label in 4 languages",
     len(tp) == 4 and len(tq) == 4
     and all(t_ != "The paladin stands guard. Choose how to begin:" for t_ in tp)
     and all(t_ != "Quit coffee-paladin (protection stops)" for t_ in tq),
     "welcome: %d translations, quit: %d" % (len(tp), len(tq)))

# 8. Two-part regression: (a) guard source compiles and passes --once in isolation,
#    (b) the live install works. This intentionally reads the real ~/.coffee-paladin.
import time, tempfile, py_compile, shutil
st = os.path.expanduser("~/.coffee-paladin/status.json")
age = time.time() - os.path.getmtime(st)
# Only the current daemon session. Searching the whole log kept the gate red forever
# after one old loop error. That reports machine history, not current state, so slice
# from the last startup entry.
_full = io.open(os.path.expanduser("~/.coffee-paladin/guard.log"),
                 encoding="utf-8", errors="replace").read()
_starts = [i for i, l in enumerate(_full.splitlines()) if "coffee-paladin start" in l]
log = "\n".join(_full.splitlines()[_starts[-1]:]) if _starts else _full
source_ok = True
tmp = tempfile.mkdtemp(prefix="paladin_test_once_")
try:
    # Put cfile in tmp; otherwise py_compile leaves __pycache__ in the source tree.
    py_compile.compile(os.path.join(SRC, "guard.py"),
                       cfile=os.path.join(tmp, "guard.pyc"), doraise=True)
    # TG_BASE is mandatory. `--once` is not read-only: it calls
    # managed_pids_from_saferun(), which unlinks registration files, and ensure_dirs(),
    # which chmods the data directory. Without TG_BASE, this test deleted registrations
    # for live safe-run jobs from the real ~/.coffee-paladin managed/ directory.
    p = subprocess.run([sys.executable, os.path.join(SRC, "guard.py"), "--once"],
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, TG_LANG="en", TG_BASE=tmp))
    source_ok = p.returncode == 0 and "state=" in p.stdout
except Exception:
    source_ok = False
finally:
    shutil.rmtree(tmp, ignore_errors=True)
test("8. regression: guard source compiles and reports + live install is healthy",
     source_ok and age < 60 and "LOOP ERROR" not in log and "BLAD petli" not in log,
     "source_ok=%s, status age: %.0fs" % (source_ok, age))

# --- Official art, dependency-free: read PNG/GIF headers manually ---

def png_wh(p):
    with open(p, "rb") as f:
        d = f.read(33)
    assert d[:8] == b"\x89PNG\r\n\x1a\n" and d[12:16] == b"IHDR", "not a PNG: " + p
    return struct.unpack(">II", d[16:24])


def gif_wh_frames(p):
    d = open(p, "rb").read()
    assert d[:6] in (b"GIF89a", b"GIF87a"), "not a GIF: " + p
    w, h = struct.unpack("<HH", d[6:10])
    return w, h, d.count(b"\x21\xf9\x04")     # Graphic Control blocks = frames.


B = os.path.join(SRC, "branding")

# 9. Official art sources are in the repo and are what they should be.
try:
    ow, oh = png_wh(os.path.join(B, "paladin.png"))
    gw, gh, gk = gif_wh_frames(os.path.join(B, "paladin.gif"))
    ok9 = ow >= 1000 and oh >= 1400 and gk >= 8 and gh > gw      # Portrait, not thumbnail.
except Exception:
    ow = oh = gw = gh = gk = 0
    ok9 = False
test("9. official sources: paladin.png (large portrait) + paladin.gif (animation)",
     ok9, "png %sx%s, gif %sx%s frames=%s" % (ow, oh, gw, gh, gk))

# 10. Derived assets used by the app exist, are animated, and have reasonable size.
try:
    ww, wh, wk = gif_wh_frames(os.path.join(B, "paladin_welcome.gif"))
    fw, fh = png_wh(os.path.join(B, "paladin_welcome.png"))
    size_bytes = os.path.getsize(os.path.join(B, "paladin_welcome.gif"))
    ok10 = (wk >= 8 and 300 <= wh <= 700 and size_bytes < 3 * 1024 * 1024
            and abs(fw / max(fh, 1) - ww / max(wh, 1)) < 0.05     # Same crop as animation.
            # The menu-header thumbnail was removed; it must not return indirectly.
            and not os.path.exists(os.path.join(B, "paladin_icon.png"))
            and "paladin_icon" not in hb)
except Exception:
    ww = wh = wk = fw = fh = size_bytes = 0
    ok10 = False
test("10. derived assets: animated welcome.gif + PNG in same frame, no menu thumbnail",
     ok10, "welcome %sx%s frames=%s (%.1f MB), png %sx%s"
           % (ww, wh, wk, size_bytes / 1048576.0, fw, fh))

# 11. Art provenance is recorded where someone will see it: CREDITS and README.
try:
    credits = read_file("branding/CREDITS.md")
    rd = read_file("README.md")
    ok11 = ("paladin.gif" in credits and "asny autora" in credits
            and "own design" in rd)
except Exception:
    credits = rd = ""
    ok11 = False
test("11. art provenance note in CREDITS.md and README", ok11,
     "CREDITS: %s, README: %s" % ("asny autora" in credits, "own design" in rd))

# 12. The welcome window prefers animation, and install.sh copies it.
sh = read_file("install.sh")
test("12. Swift loads paladin_welcome.gif (with fallback) and install.sh copies it",
     'contentsOfFile: base + "/paladin_welcome.gif"' in hb
     and 'contentsOfFile: base + "/paladin_welcome.png"' in hb
     and "iv.animates = true" in hb
     and "paladin_welcome.gif" in sh,
     "missing GIF path in Swift or install.sh")

# 13. --ascii must force the character version even in a truecolor terminal.
#     Without a pty this cannot be tested honestly because heat checks isatty().
import pty
def through_pty(args, env_extra, raw=False):
    collected = []
    pid, fd = pty.fork()
    if pid == 0:
        # Without this, the child inherits TERM_PROGRAM from the terminal that ran
        # the tests, so a "plain terminal" is not plain.
        for variable in ("TERM", "TERM_PROGRAM", "COLORTERM", "TMUX", "NO_COLOR", "TG_NO_IMAGE"):
            os.environ.pop(variable, None)
        os.environ.update(env_extra)
        os.execv(os.path.join(BIN, "heat"), [os.path.join(BIN, "heat")] + args)
        os._exit(127)
    try:
        while True:
            d = os.read(fd, 65536)
            if not d:
                break
            collected.append(d)
    except OSError:
        pass
    os.waitpid(pid, 0)
    razem = b"".join(collected)
    return razem if raw else razem.decode("utf-8", "replace")

colored = through_pty(["--paladin"], {"COLORTERM": "truecolor", "TERM": "xterm-256color"})
forced = through_pty(["--paladin", "--ascii"], {"COLORTERM": "truecolor", "TERM": "xterm-256color"})
# Fallback to the cup from the first thermal-guard version, not a degraded paladin:
# without truecolor the figure cannot be drawn honestly, so use the character art
# that has always looked good.
test("13. truecolor -> paladin, --ascii -> cup (not a blurry paladin)",
     colored.count("38;2;") > 100 and forced.count("38;2;") == 0
     and ".------------." in forced and "~~~~~~~~~~" in forced
     and "Shield the Process" in forced,
     "color: %d sequences, --ascii: %d, cup: %s"
     % (colored.count("38;2;"), forced.count("38;2;"), "`-----'" in forced))

# 14. Clicking the menu name opens the paladin panel anchored under the bar.
test("14. paladin panel: clickable name + anchor under the bar icon",
     "final class PaladinPanel" in hb
     and "PaladinPanel.shared.toggle()" in hb
     and "override func mouseUp" in hb
     and "Bar.shared?.item.button" in hb
     and "cancelTracking()" in hb,          # The menu must close before the panel opens.
     "missing panel or bar anchoring")

# 15. Quit means program exit, not hiding the icon. Label and effect must match:
#     stop both daemon and menu bar, and ask before this irreversible step.
test("15. Quit stops DAEMON and bar after window confirmation",
     'bootout", "gui/\\(uid)/pl.pawel.coffee-paladin"' in hb
     and 'bootout", "gui/\\(uid)/pl.pawel.coffee-paladin-bar"' in hb
     # Confirmation is mandatory, but the test cannot pin the window class. Since
     # 2.1.5 this is a custom centered paladin window, not NSAlert. Check the effect:
     # a question before the irreversible step and exit only after consent.
     and 'T("Turn off thermal protection for this Mac?")' in hb
     and "NSApp.runModal(for: win)" in hb
     and "guard result.rawValue == 0 else { return }" in hb
     and "protection keeps running" not in hb,     # Old misleading promise must be gone.
     "missing daemon stop or old label remains")

# 16. AI-agent skill must exist, have valid front matter, and teach real program
#     behavior: level, safe-run, and the SIGCONT ban.
try:
    sk = read_file("skills/coffee-paladin/SKILL.md")
    ok16 = (sk.startswith("---") and "name: coffee-paladin" in sk
            and "description:" in sk
            and "status.json" in sk and "safe-run" in sk
            and "SIGCONT" in sk and "level" in sk
            and "skills/coffee-paladin/SKILL.md" in sh)   # Installer deploys it.
except Exception:
    sk = ""
    ok16 = False
test("16. AI-agent skill exists and teaches the real guard interface", ok16,
     "missing skill, header, or install.sh entry")

# 17. Real image in a terminal that supports it, such as Ghostty/kitty/WezTerm.
#     The test reassembles protocol chunks and compares them with the PNG byte for
#     byte. Bad chunk assembly or an incorrect m flag is the common protocol bug.
import base64, hashlib
sur = through_pty(["--paladin"], {"TERM": "xterm-ghostty", "TERM_PROGRAM": "ghostty",
                                "COLORTERM": "truecolor"}, raw=True)
blocks = re.findall(rb"\x1b_G([^;]*);([A-Za-z0-9+/=]*)\x1b\\", sur)
png = os.path.expanduser("~/.coffee-paladin/paladin_welcome.png")
try:
    oryg = open(png, "rb").read()
    assembled = base64.b64decode(b"".join(b for _, b in blocks))
    ok17 = (len(blocks) > 1
            and b"a=T,f=100,t=d,r=" in blocks[0][0]
            and all(b"m=1" in h for h, _ in blocks[:-1]) and b"m=0" in blocks[-1][0]
            and hashlib.sha256(assembled).digest() == hashlib.sha256(oryg).digest())
except Exception:
    ok17 = False
# In a terminal without image support, do not send the image or it prints junk.
plain = through_pty(["--paladin"], {"TERM": "xterm-256color", "COLORTERM": "truecolor"}, raw=True)
test("17. Ghostty image reassembles byte for byte; plain terminal has none",
     ok17 and b"\x1b_G" not in plain and plain.count("▀".encode()) > 500,
     "chunks: %d, image in plain terminal: %s" % (len(blocks), b"\x1b_G" in plain))

# 18. README screenshots: every link must point to an existing file, and the whole
#     directory must fit the repo budget. WebP, not PNG, is a 10x difference.
rd = read_file("README.md")
used = set(re.findall(r"docs/screens/([\w.]+)", rd))
kat = os.path.join(SRC, "docs", "screens")
try:
    files = set(os.listdir(kat))
    size_bytes = sum(os.path.getsize(os.path.join(kat, f)) for f in files)
except Exception:
    files, size_bytes = set(), 0
broken = sorted(used - files)
test("18. screenshots: README links point to files, directory below 2 MB",
     len(used) >= 10 and not broken and size_bytes < 2 * 1024 * 1024
     and all(f.endswith(".webp") for f in files),
     "broken: %s, size: %.1f MB, files: %d" % (broken, size_bytes / 1048576.0, len(files)))

# 19. README describes the agent skill in both languages, and the description matches
#     the skill. A description promising behavior the skill omits is worse than none.
description_en = "## Your AI agent can talk to it" in rd
description_pl = "## Twój agent AI umie z nim rozmawiać" in rd
agreement = all(
    (k in rd and k in sk) for k in ("status.json", "safe-run", "SIGCONT", "dry_run", "unpausable")
)
test("19. README describes the skill (EN+PL) and does not promise more than the skill says",
     description_en and description_pl and agreement
     and "~/.claude/skills/coffee-paladin" in rd,
     "EN=%s PL=%s agreement=%s" % (description_en, description_pl, agreement))

# 20. README in three additional languages exists, is truly translated rather than
#     copied from English, has working images, and keeps the same facts as the original.
def chars_in(txt, start_code, end_code):
    return sum(1 for c in txt if start_code <= ord(c) <= end_code)

languages = {}
for file_path, check_fn in (("README.zh.md", lambda s: chars_in(s, 0x4E00, 0x9FFF) > 800),
                      ("README.ru.md", lambda s: chars_in(s, 0x0400, 0x04FF) > 2000),
                      ("README.es.md", lambda s: s.count("ó") + s.count("é") + s.count("í") > 60)):
    try:
        s_ = read_file(file_path)
        images = set(re.findall(r"(?:docs/screens|branding)/([\w.]+)", s_))
        bad = [o for o in images
               if not (os.path.exists(os.path.join(SRC, "docs/screens", o))
                       or os.path.exists(os.path.join(SRC, "branding", o)))]
        languages[file_path] = (check_fn(s_) and len(images) >= 5 and not bad
                        # Same hard facts as the original; otherwise the translation lies.
                        and "89" in s_ and "60" in s_ and "595" in s_
                        and "MIT" in s_
                        and "pawelkwaczynski/coffee-paladin" in s_)
    except Exception:
        languages[file_path] = False
links_present = all(("(%s)" % p) in rd for p in ("README.zh.md", "README.ru.md", "README.es.md"))
test("20. README zh/ru/es: real translations, good images, matching numbers, links",
     all(languages.values()) and links_present,
     "%s, README links: %s" % (languages, links_present))

# 22. A dictionary literal with the same key twice is a WARNING to swiftc and a
# CRASH to the user. Version 2.6.1 shipped that way: the build log held one note,
# the installer said "menu bar did not start", and launchctl showed SIGTRAP.
_duplicates = []
_bar = io.open(os.path.join(SRC, "heatbar.swift"), encoding="utf-8").read()
for _lang in ("PL", "RU", "ZH", "ES"):
    _body = _bar.split("let %s: [String: String] = [" % _lang, 1)[1].split("\n]\n", 1)[0]
    _seen = set()
    # Entries come in two shapes: key and value on one line, or the value on the
    # next. Matching only the second shape is how the first duplicate slipped by.
    for _key in re.findall(r'^    ("(?:[^"\\]|\\.)*")\s*:', _body, re.M):
        if _key in _seen:
            _duplicates.append("%s %s" % (_lang, _key[:45]))
        _seen.add(_key)
test("22. no translation dictionary repeats a key (that crashes the bar at launch)",
     not _duplicates, "; ".join(_duplicates))

ok = sum(1 for _, w in results if w)
print("\nRESULT: %d/%d" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
