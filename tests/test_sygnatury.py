#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kazde wolanie wlasnej funkcji musi pasowac do jej sygnatury. Sprawdzane statycznie.

POWOD POWSTANIA (04.08.2026, znalezione przez runde testowa z Codeksem):
`do_resume(cfg, st, reason)` przyjmowal trzy argumenty, a petla glowna wolala go
`do_resume(..., only_keys=gotowe)`. Python nie ma o tym pojecia do czasu wykonania, a to
wykonanie siedzialo w rzadkiej sciezce (wznowienie po ostygnieciu) opakowanej w ogolny
`except`. Efekt: zadanie zamrozone przy przegrzaniu NIE wracalo do pracy - czekalo na
SIGTERM po limicie czasu pauzy. W logu: trzy pauzy, zero wznowien. Dwa dni w wydanym kodzie.

Czego NIE zlapalo: 19 plikow testow, dwa fuzzery, semgrep, ruff `--select ALL`.
Pyflakes nie sprawdza sygnatur wolan, a testy nie dotykaly tej galezi.

Ten test przechodzi po AST i porownuje KAZDE wolanie funkcji zdefiniowanej w tym samym
pliku z jej sygnatura: nieznane argumenty nazwane, za duzo argumentow pozycyjnych,
brak wymaganych. Kosztuje ulamek sekundy i dziala takze na galeziach, ktorych nikt nie
uruchamia - a to wlasnie tam takie bledy siedza najdluzej.

Uruchomienie:  python3 tests/test_sygnatury.py
"""
import ast
import os
import sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLIKI = ["guard.py", "heat", "safe-run", "fleet", "thermal-report"]

bledy = []
sprawdzonych = 0


def sygnatury(drzewo):
    """Funkcje zdefiniowane na POZIOMIE MODULU. Metody klas pomijamy: wolanie idzie
    przez obiekt, wiec dopasowanie po samej nazwie dawaloby falszywe alarmy."""
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

        # 1) nieznany argument nazwany
        if not s["ma_kwargs"]:
            dozwolone = set(s["pozycyjne"]) | set(s["kwonly"])
            for kw in wezel.keywords:
                if kw.arg is not None and kw.arg not in dozwolone:
                    bledy.append("%s: nieznany argument '%s' (definicja w linii %d, przyjmuje: %s)"
                                 % (gdzie, kw.arg, s["linia"], ", ".join(dozwolone) or "brak"))

        # 2) za duzo argumentow pozycyjnych
        if not s["ma_gwiazdke"]:
            podane = len([a for a in wezel.args if not isinstance(a, ast.Starred)])
            if not any(isinstance(a, ast.Starred) for a in wezel.args) and podane > len(s["pozycyjne"]):
                bledy.append("%s: %d argumentow pozycyjnych, a funkcja przyjmuje %d (linia %d)"
                             % (gdzie, podane, len(s["pozycyjne"]), s["linia"]))

        # 3) brak wymaganego argumentu
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
