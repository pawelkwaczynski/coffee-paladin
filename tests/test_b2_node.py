#!/usr/bin/env python3
"""Regresja B2 (01.08.2026): node chroniony po LINII POLECEN, nie po nazwie.

Po incydencie SIGTTIN (Neo, 31.07) node/npm/npx/bun/deno trafily do never_patterns
po nazwie - skutek uboczny: ciezki build w Node byl nietykalny, czyli dokladnie
ten przypadek, dla ktorego narzedzie powstalo (znalazl Codex). Teraz:
  - zwykly `node build.js` JEST pauzowalny,
  - proces z claude/codex/mcp/language-server/.vscode w argumentach jest nietykalny,
  - interaktywne sesje chroni skip_foreground_tty niezaleznie od nazwy.

Testy wolaja PRAWDZIWE pick_targets na zywych procesach (ps widzi ich argumenty).

Uruchomienie:  python3 testy/test_b2_node.py
"""
import os
import subprocess
import sys
import tempfile

KATALOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TG_BASE"] = tempfile.mkdtemp(prefix="tg_test_b2_")
sys.path.insert(0, KATALOG)
import guard  # noqa: E402

WYNIKI = []


def check(nazwa, warunek, szczegol=""):
    WYNIKI.append((nazwa, bool(warunek)))
    print("  [%s] %s%s" % ("PASS" if warunek else "FAIL", nazwa,
                           (" - " + szczegol) if (szczegol and not warunek) else ""))


CFG = dict(
    guard.DEFAULTS,
    cpu_min_percent=20.0,
    count_children=False,
    # w tescie procesy sa mlode - wylaczamy prog wieku, testujemy WZORCE, nie wiek
    unknown_min_seconds=0,
    skip_foreground_tty=True,
)


def spawn(*args):
    """Zywy proces w tle (wlasna grupa - nie jest pierwszoplanowy na zadnym tty)."""
    return subprocess.Popen(["python3", "-c", "import time; time.sleep(120)", *args],
                            stdout=subprocess.DEVNULL, start_new_session=True)


def spawn_skrypt(podkatalog):
    """Interpreter uruchamiajacy SKRYPT z podanej sciezki - realna postac serwera MCP
    czy language servera (`node /Users/x/.claude/mcp/server.js`). Zwraca (proces, katalog)."""
    import tempfile
    kat = tempfile.mkdtemp()
    sciezka = os.path.join(kat, podkatalog)
    os.makedirs(os.path.dirname(sciezka), exist_ok=True)
    with open(sciezka, "w") as f:
        f.write("import time\ntime.sleep(120)\n")
    return subprocess.Popen(["python3", sciezka],
                            stdout=subprocess.DEVNULL, start_new_session=True), kat


def main():
    procesy = []
    kat_agenta = None
    try:
        build = spawn("build.js")          # udaje: node build.js
        # realna postac serwera MCP: interpreter + SCIEZKA DO SKRYPTU. (Wczesniej sciezka
        # stala na koncu, za kodem `-c`; taka linia polecen nie wystepuje w naturze,
        # a od 02.08 argumenty-dane nie daja juz nietykalnosci - tozsamosc niesie
        # nazwa programu i uruchamiany skrypt, nie to, co proces przetwarza.)
        agent, kat_agenta = spawn_skrypt(".claude/mcp/server.py")
        procesy = [build, agent]
        import time
        time.sleep(1)

        def cele(comm, proc):
            procs = [(proc.pid, 1, 95.0, comm)]
            return [t[0] for t in guard.pick_targets(CFG, procs, {})]

        print("1) zwykly node build.js JEST pauzowalny")
        check("comm=node, args=build.js -> w targets", build.pid in cele("node", build))

        print("2) zaplecze agentow nietykalne po ARGUMENTACH")
        check("comm=node, args z .claude/mcp -> poza targets",
              agent.pid not in cele("node", agent))

        print("3) po NAZWIE nietykalne zostalo tylko to, co nigdy nie liczy")
        check("comm=claude -> poza targets", build.pid not in cele("claude", build))
        check("comm=codex -> poza targets", build.pid not in cele("codex", build))
        check("comm=tmux -> poza targets", build.pid not in cele("tmux", build))
        for comm in ("node", "npm", "npx", "bun", "deno"):
            check("'%s' NIE jest w never_patterns po nazwie" % comm,
                  comm not in CFG["never_patterns"])

        print("4) wzorce argumentow obejmuja cale zaplecze")
        for wzor in ("claude", "codex", "cursor", "mcp", "language-server", ".vscode"):
            check("'%s' w never_arg_patterns" % wzor, wzor in CFG["never_arg_patterns"])

        print("5) siatka SIGTTIN zostala: skip_foreground_tty domyslnie wlaczone")
        check("skip_foreground_tty=True w DEFAULTS",
              guard.DEFAULTS.get("skip_foreground_tty") is True)
    finally:
        for p in procesy:
            p.kill()
            p.wait()
        import shutil
        if kat_agenta:
            shutil.rmtree(kat_agenta, ignore_errors=True)   # katalog z atrapa serwera MCP

    padniete = [n for n, ok in WYNIKI if not ok]
    print("\nWYNIK: %d/%d" % (len(WYNIKI) - len(padniete), len(WYNIKI)))
    if padniete:
        sys.exit(1)


if __name__ == "__main__":
    main()
