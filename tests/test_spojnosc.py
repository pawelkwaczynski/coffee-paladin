"""Check cross-file contracts that tend to drift during changes.

Eight categories, each from a real failure:
  1. string passed to T() without a dictionary entry -> English text in non-English UI;
  2. version must match in four places: guard, thermal-report, heatbar, plugin.json;
  3. tool without --help: `thermal-report --help` generated a report on Desktop;
  4. install.sh creates something uninstall.sh does not remove: skill, symlinks, fleet snapshot;
  5. guard logs a tag unknown to parsers -> evidence report loses events;
  6. guard.py and thermal-report copies of generations() must not drift;
  7. timestamp parsers in four tools must return the same result;
  8. .app bundle must be created and removed symmetrically without touching /Applications.

Run with:  python3 tests/test_spojnosc.py
Does not touch the real ~/.coffee-paladin.
"""
import ast
import importlib.machinery
import io
import json
import os
import re
import sys
import tempfile
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp()
errors = []

# 1. Every string passed to T() must have entries in all 4 dictionaries in every
#    file that owns dictionaries, not only guard.py. Checking only guard.py missed
#    translations in thermal-report and fleet, while AGENTS.md requires EN/PL/RU/ZH/ES
#    everywhere. Read AST, not regex: regex returned raw source text, so "\n## BATTERY\n"
#    appeared as backslash+n and did not match the dictionary key containing a real
#    newline. AST yields the value T() actually sees, including adjacent literal
#    concatenation and escapes.
def called_T(text):
    result = set()
    for w in ast.walk(ast.parse(text)):
        if (isinstance(w, ast.Call) and isinstance(w.func, ast.Name) and w.func.id == "T"
                and w.args and isinstance(w.args[0], ast.Constant)
                and isinstance(w.args[0].value, str)):
            result.add(w.args[0].value)
    return result


for file_path in ("guard.py", "thermal-report", "fleet", "heat", "safe-run"):
    path = os.path.join(SRC, file_path)
    if not os.path.exists(path):
        continue
    content = io.open(path, encoding='utf-8').read()
    mod = importlib.machinery.SourceFileLoader(
        're_' + re.sub(r'\W', '_', file_path), path).load_module()
    if not all(hasattr(mod, n) for n in ("PL", "RU", "ZH", "ES")):
        continue                      # File without its own dictionaries.
    called = called_T(content)
    for name in ("PL", "RU", "ZH", "ES"):
        d = getattr(mod, name)
        missing = sorted(k for k in called if k not in d)
        if missing:
            errors.append("%s: %s is missing %d translations (for example %r)"
                         % (file_path, name, len(missing), missing[0][:60]))
source = io.open(os.path.join(SRC, 'guard.py'), encoding='utf-8').read()

# 2. Version is the same in all four places.
versions = {}
versions['guard.py'] = re.search(r'^GUARD_VERSION = "([^"]+)"', source, re.M).group(1)
versions['thermal-report'] = re.search(r'^VERSION = "([^"]+)"', io.open(os.path.join(SRC,'thermal-report')).read(), re.M).group(1)
versions['heatbar.swift'] = re.search(r'let VERSION = "([^"]+)"', io.open(os.path.join(SRC,'heatbar.swift')).read()).group(1)
versions['plugin.json'] = json.load(open(os.path.join(SRC,'.claude-plugin/plugin.json')))['version']
if len(set(versions.values())) != 1:
    errors.append("versions differ: %s" % versions)

# 3. Every tool responds to --help.
for tool_name in ("heat","safe-run","fleet","thermal-report"):
    s = io.open(os.path.join(SRC,tool_name)).read()
    if '"--help"' not in s:
        errors.append("%s does not handle --help" % tool_name)

# 4. install.sh installs what uninstall.sh removes.
inst = io.open(os.path.join(SRC,'install.sh')).read()
uninst = io.open(os.path.join(SRC,'uninstall.sh')).read()
for binary in ("coffee-paladin", "coffee-paladin-bar", "heat", "safe-run", "thermal-report", "fleet", "thermalstate"):
    if '"$BIN/%s"' % binary not in uninst:
        errors.append("uninstall.sh does not remove %s" % binary)

# 4b. The .app bundle is an installation artifact like binaries. If the installer
#     can create it in two possible locations, the uninstaller must remove both.
#     This test is intentionally static: earlier live installer checks left junk in
#     the real HOME and required manual cleanup after failed tests.
if ('coffee-paladin.app' not in inst or 'APP_CONTENTS="$APP_BUNDLE/Contents"' not in inst
        or 'APP_MACOS="$APP_CONTENTS/MacOS"' not in inst
        or 'APP_RESOURCES="$APP_CONTENTS/Resources"' not in inst):
    errors.append("install.sh does not create coffee-paladin.app/Contents structure")
if 'CFBundleExecutable' not in inst or 'CFBundleIdentifier' not in inst or 'LSUIElement' not in inst:
    errors.append("install.sh does not write required Info.plist keys for bundle")
if 'heatbar_version' not in inst or 'let VERSION = ' not in inst:
    errors.append("install.sh does not read bundle version from heatbar.swift")
if 'tools/make_icon.sh' not in inst or 'AppIcon.icns' not in inst:
    errors.append("install.sh does not build AppIcon.icns with a separate tool")
if 'codesign -s - -f "$APP_BUNDLE"' not in inst:
    errors.append("install.sh does not ad-hoc sign the whole bundle")
if 'ln -s "$BAR_EXEC" "$BIN/coffee-paladin-bar"' not in inst:
    errors.append("install.sh does not leave coffee-paladin-bar compatibility symlink")
if '__BAR_EXEC__' not in io.open(os.path.join(SRC, 'pl.pawel.coffee-paladin-bar.plist')).read():
    errors.append("bar LaunchAgent lacks __BAR_EXEC__ placeholder")
for app in ('"/Applications/coffee-paladin.app"', '"$HOME/Applications/coffee-paladin.app"'):
    if app not in uninst:
        errors.append("uninstall.sh does not remove bundle %s" % app)

# 5. Log tags used by guard are known to every parser.
#    The old assertion was "grep the source": it checked whether "[PAUSE]" appeared
#    in a file, so it passed when the text was in a comment, dead code, or a broken
#    parser. Feed parsers a real log line with each tag and verify they counted it.
tags = sorted(set(re.findall(r'tag="([A-Z]+)"', source)))
try:
    import shutil as _sh5
    import tempfile as _tf5
    _t5 = _tf5.mkdtemp()
    os.environ["TG_BASE"] = _t5
    _today = __import__("time").strftime("%Y-%m-%d")
    with io.open(os.path.join(_t5, "guard.log"), "w", encoding="utf-8") as _f:
        for _tag in tags:
            _f.write("%s 10:00:00+0200  [%s] proces testowy (pid 1) - powod\n" % (_today, _tag))
    _g5 = importlib.machinery.SourceFileLoader('tag_g', os.path.join(SRC, 'guard.py')).load_module()
    _stat = _g5.day_stats() if hasattr(_g5, "day_stats") else None
    if _stat is not None and not any(v for v in _stat.values()):
        errors.append("day_stats recognized NONE of the tags %s "
                     "- log parser is broken or tags drifted" % tags)
    # thermal-report: feed it a log and verify it really counted every line.
    # The previous check searched source for literal "[PAUSE]" and reported a false
    # alarm because the parser uses a regex alternative (\[(PAUSE|RESUME|...)\]).
    # Grepping source confuses text presence with code behavior.
    import subprocess as _sp5
    _target5 = os.path.join(_t5, "raport.txt")
    _sp5.run([sys.executable, os.path.join(SRC, "thermal-report"), "--file", _target5, "--days", "2"],
             capture_output=True, text=True, timeout=120,
             env=dict(os.environ, TG_BASE=_t5, TG_LANG="en"))
    _report = io.open(_target5, encoding="utf-8", errors="replace").read()
    _unknown = [t for t in tags if ("[%s]" % t) not in _report]
    if _unknown:
        errors.append("thermal-report DID NOT COUNT lines with tags %s - "
                     "evidence report loses those interventions" % _unknown)
    _sh5.rmtree(_t5, ignore_errors=True)
except Exception as _e5:
    errors.append("cannot check log tags: %s: %s" % (type(_e5).__name__, _e5))

# 6. `generations()` exists in guard.py and thermal-report as an intentional copy because
#    tools are standalone and do not import the daemon. Both must return the same result.
#    Copied logic is debt that returns; at least this keeps it watched.
try:
    import shutil as _sh
    import tempfile as _tf
    _t = _tf.mkdtemp()
    _p = os.path.join(_t, "history.csv")
    for _n in ("", ".1", ".2", ".3"):
        io.open(_p + _n, "w").write("x")
    _g = importlib.machinery.SourceFileLoader('pg', os.path.join(SRC, 'guard.py')).load_module()
    _tr = importlib.machinery.SourceFileLoader('ptr', os.path.join(SRC, 'thermal-report')).load_module()
    if not hasattr(_tr, "generations"):
        errors.append("thermal-report lacks generations() - rotation will truncate evidence again")
    elif _g.generations(_p) != _tr.generations(_p):
        errors.append("generations() drifted between guard.py and thermal-report: %s vs %s"
                     % ([os.path.basename(x) for x in _g.generations(_p)],
                        [os.path.basename(x) for x in _tr.generations(_p)]))
    _sh.rmtree(_t, ignore_errors=True)
except Exception as _e:
    errors.append("cannot compare generations(): %s: %s" % (type(_e).__name__, _e))

# 7. Timestamp parser lives in four files as an intentional copy: guard.abs_epoch,
#    thermal-report.abs_epoch, heat.abs_epoch, safe-run.abs_epoch. All must return the same
#    result for offset, legacy, and junk timestamps, or one tool silently skips every
#    fresh history.csv row.
try:
    _samples = ["2026-08-02 23:30:00+0200", "2026-08-02 23:30:00", "2026-08-02 23:30:00-0800",
               "xyzzy", "", "2026-13-45 99:99:99"]
    _impl = {}
    for _file_path, _name in (("guard.py", "abs_epoch"), ("thermal-report", "abs_epoch"),
                          ("heat", "abs_epoch"), ("safe-run", "abs_epoch")):
        _m = importlib.machinery.SourceFileLoader(
            'cz_' + re.sub(r'\W', '_', _file_path), os.path.join(SRC, _file_path)).load_module()
        if not hasattr(_m, _name):
            errors.append("%s lacks %s() - timestamp with offset will break parsing" % (_file_path, _name))
            continue
        _impl[_file_path] = [getattr(_m, _name)(x) for x in _samples]
    if len(set(tuple(v) for v in _impl.values())) > 1:
        errors.append("timestamp parser drifted between files: %s"
                     % {k: v for k, v in _impl.items()})
except Exception as _e:
    errors.append("cannot compare timestamp parser: %s: %s" % (type(_e).__name__, _e))

print("CHECKS: 8 categories")
if errors:
    for b in errors: print("  ERROR: %s" % b)
    sys.exit(1)
print("  everything consistent")
