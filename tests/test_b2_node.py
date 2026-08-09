#!/usr/bin/env python3
"""Verify that node is protected by command line, not by process name.

After a SIGTTIN incident, node/npm/npx/bun/deno were added to never_patterns by
name. That also made heavy Node builds untouchable, exactly the workload the guard
must be able to pause. The intended contract is:
  - plain `node build.js` is pausable,
  - a process with claude/codex/mcp/language-server/.vscode in argv is untouchable,
  - skip_foreground_tty protects interactive sessions regardless of name.

These tests call the real pick_targets on live processes so `ps` sees their argv.

Run with:  python3 testy/test_b2_node.py
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
    # Test processes are young; disable the age gate so this checks patterns only.
    unknown_min_seconds=0,
    skip_foreground_tty=True,
)


def spawn(*args):
    """Start a live background process in its own non-foreground process group."""
    return subprocess.Popen(["python3", "-c", "import time; time.sleep(120)", *args],
                            stdout=subprocess.DEVNULL, start_new_session=True)


def spawn_skrypt(podkatalog):
    """Start an interpreter running a script path and return (process, directory).

    This matches a real MCP server or language server command such as
    `node /Users/x/.claude/mcp/server.js`.
    """
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
        build = spawn("build.js")          # Pretend to be: node build.js.
        # A real MCP server is an interpreter plus a script path. Putting the path
        # after `-c` does not occur in normal commands. Identity comes from the
        # program name and executed script, not from data the process handles.
        agent, kat_agenta = spawn_skrypt(".claude/mcp/server.py")
        procesy = [build, agent]
        import time
        time.sleep(1)

        def cele(comm, proc):
            procs = [(proc.pid, 1, 95.0, comm)]
            return [t[0] for t in guard.pick_targets(CFG, procs, {})]

        print("1) plain node build.js IS pausable")
        check("comm=node, args=build.js -> in targets", build.pid in cele("node", build))

        print("2) agent backends are untouchable by ARGUMENTS")
        check("comm=node, args with .claude/mcp -> outside targets",
              agent.pid not in cele("node", agent))

        print("3) by NAME, only things that never compute remain untouchable")
        check("comm=claude -> outside targets", build.pid not in cele("claude", build))
        check("comm=codex -> outside targets", build.pid not in cele("codex", build))
        check("comm=tmux -> outside targets", build.pid not in cele("tmux", build))
        for comm in ("node", "npm", "npx", "bun", "deno"):
            check("'%s' is NOT in never_patterns by name" % comm,
                  comm not in CFG["never_patterns"])

        print("4) argument patterns cover the whole backend")
        for wzor in ("claude", "codex", "cursor", "mcp", "language-server", ".vscode"):
            check("'%s' in never_arg_patterns" % wzor, wzor in CFG["never_arg_patterns"])

        print("5) SIGTTIN net remains: skip_foreground_tty enabled by default")
        check("skip_foreground_tty=True in DEFAULTS",
              guard.DEFAULTS.get("skip_foreground_tty") is True)
    finally:
        for p in procesy:
            p.kill()
            p.wait()
        import shutil
        if kat_agenta:
            shutil.rmtree(kat_agenta, ignore_errors=True)   # Fake MCP server directory.

    padniete = [n for n, ok in WYNIKI if not ok]
    print("\nRESULT: %d/%d" % (len(WYNIKI) - len(padniete), len(WYNIKI)))
    if padniete:
        sys.exit(1)


if __name__ == "__main__":
    main()
