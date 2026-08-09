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
PLIKI = ["guard.py", "heat", "safe-run", "fleet", "thermal-report"]

bledy = []
sprawdzonych = 0


def sygnatury(drzewo):
    """Return module-level function signatures.

    Class methods are skipped because calls go through objects; matching by bare name
    would produce false alarms.
    """
    out = {}
    for w in drzewo.body:
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


for nazwa in PLIKI:
    sciezka = os.path.join(SRC, nazwa)
    if not os.path.exists(sciezka):
        continue
    with open(sciezka, encoding="utf-8") as f:
        zrodlo = f.read()
    try:
        drzewo = ast.parse(zrodlo)
    except SyntaxError as e:
        bledy.append("%s: nie parsuje sie (%s)" % (nazwa, e))
        continue
    sygn = sygnatury(drzewo)

    for wezel in ast.walk(drzewo):
        if not isinstance(wezel, ast.Call) or not isinstance(wezel.func, ast.Name):
            continue
        s = sygn.get(wezel.func.id)
        if s is None:
            continue
        sprawdzonych += 1
        gdzie = "%s:%d  %s()" % (nazwa, wezel.lineno, wezel.func.id)

        # 1. Unknown keyword argument.
        if not s["ma_kwargs"]:
            dozwolone = set(s["pozycyjne"]) | set(s["kwonly"])
            for kw in wezel.keywords:
                if kw.arg is not None and kw.arg not in dozwolone:
                    bledy.append("%s: nieznany argument '%s' (definicja w linii %d, przyjmuje: %s)"
                                 % (gdzie, kw.arg, s["linia"], ", ".join(dozwolone) or "brak"))

        # 2. Too many positional arguments.
        if not s["ma_gwiazdke"]:
            podane = len([a for a in wezel.args if not isinstance(a, ast.Starred)])
            if not any(isinstance(a, ast.Starred) for a in wezel.args) and podane > len(s["pozycyjne"]):
                bledy.append("%s: %d argumentow pozycyjnych, a funkcja przyjmuje %d (linia %d)"
                             % (gdzie, podane, len(s["pozycyjne"]), s["linia"]))

        # 3. Missing required argument.
        rozwija = any(isinstance(a, ast.Starred) for a in wezel.args) or \
                  any(k.arg is None for k in wezel.keywords)
        if not rozwija:
            wymagane = len(s["pozycyjne"]) - s["domyslne"]
            nazwane = {k.arg for k in wezel.keywords if k.arg}
            pokryte = len(wezel.args) + len([n for n in s["pozycyjne"][:wymagane] if n in nazwane])
            if pokryte < wymagane:
                bledy.append("%s: brakuje argumentow - wymaga %d, dostaje %d (linia %d)"
                             % (gdzie, wymagane, pokryte, s["linia"]))
            for n in s["kwonly_wymagane"]:
                if n not in nazwane:
                    bledy.append("%s: brakuje wymaganego argumentu nazwanego '%s'" % (gdzie, n))

print("SPRAWDZONYCH WOLAN: %d w %d plikach" % (sprawdzonych, len(PLIKI)))
if bledy:
    for b in bledy:
        print("  [FAIL] %s" % b)
    print("\n%d bled(ow)" % len(bledy))
    sys.exit(1)
print("  wszystkie wolania zgodne z sygnaturami")
sys.exit(0)
