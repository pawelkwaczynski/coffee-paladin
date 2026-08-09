#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Statically verify that each local function call matches its signature.

`do_resume(cfg, st, reason)` accepted three arguments while the main loop called it as
`do_resume(..., only_keys=gotowe)`. Python does not know until runtime, and runtime was
a rare cooled-down resume path wrapped in a broad `except`. A job frozen for overheating
did not resume; it waited for SIGTERM after the pause time limit.

That escaped many tests, two fuzzers, semgrep, and ruff `--select ALL`. Pyflakes does not
check call signatures, and tests did not touch that branch.

This test walks AST and compares every call to a function defined in the same file with
its signature: unknown keyword arguments, too many positional arguments, and missing
required arguments. It is cheap and also covers branches nobody runs.

Run with:  python3 tests/test_sygnatury.py
"""
import ast
import os
import sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["guard.py", "heat", "safe-run", "fleet", "thermal-report"]

errors = []
checked = 0


def signatures(tree):
    """Return module-level function signatures.

    Class methods are skipped because calls go through objects; matching by bare name
    would produce false alarms.
    """
    out = {}
    for w in tree.body:
        if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = w.args
            out[w.name] = {
                "pozycyjne": [x.arg for x in a.posonlyargs] + [x.arg for x in a.args],
                "domyslne": len(a.defaults),
                "kwonly": [x.arg for x in a.kwonlyargs],
                "kwonly_wymagane": [x.arg for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is None],
                "ma_gwiazdke": a.vararg is not None,
                "ma_kwargs": a.kwarg is not None,
                "linia": w.lineno,
            }
    return out


for name in FILES:
    path = os.path.join(SRC, name)
    if not os.path.exists(path):
        continue
    with open(path, encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        errors.append("%s: does not parse (%s)" % (name, e))
        continue
    signature_map = signatures(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        s = signature_map.get(node.func.id)
        if s is None:
            continue
        checked += 1
        location = "%s:%d  %s()" % (name, node.lineno, node.func.id)

        # 1. Unknown keyword argument.
        if not s["ma_kwargs"]:
            allowed = set(s["pozycyjne"]) | set(s["kwonly"])
            for kw in node.keywords:
                if kw.arg is not None and kw.arg not in allowed:
                    errors.append("%s: unknown argument '%s' (definition on line %d, accepts: %s)"
                                 % (location, kw.arg, s["linia"], ", ".join(allowed) or "none"))

        # 2. Too many positional arguments.
        if not s["ma_gwiazdke"]:
            supplied = len([a for a in node.args if not isinstance(a, ast.Starred)])
            if not any(isinstance(a, ast.Starred) for a in node.args) and supplied > len(s["pozycyjne"]):
                errors.append("%s: %d positional arguments, but function accepts %d (line %d)"
                             % (location, supplied, len(s["pozycyjne"]), s["linia"]))

        # 3. Missing required argument.
        expands = any(isinstance(a, ast.Starred) for a in node.args) or \
                  any(k.arg is None for k in node.keywords)
        if not expands:
            required = len(s["pozycyjne"]) - s["domyslne"]
            named = {k.arg for k in node.keywords if k.arg}
            covered = len(node.args) + len([n for n in s["pozycyjne"][:required] if n in named])
            if covered < required:
                errors.append("%s: missing arguments - requires %d, gets %d (line %d)"
                             % (location, required, covered, s["linia"]))
            for n in s["kwonly_wymagane"]:
                if n not in named:
                    errors.append("%s: missing required named argument '%s'" % (location, n))

print("CHECKED CALLS: %d in %d files" % (checked, len(FILES)))
if errors:
    for b in errors:
        print("  [FAIL] %s" % b)
    print("\n%d error(s)" % len(errors))
    sys.exit(1)
print("  all calls match signatures")
sys.exit(0)
