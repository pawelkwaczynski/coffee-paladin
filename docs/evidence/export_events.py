#!/usr/bin/env python3
"""Export the guard's event log with a positive list of fields.

The raw file ~/.coffee-paladin/history_events.jsonl names every job the guard
touched. Job names are chosen by the user, so on a working machine they spell
out clients, unpublished experiments and schedules. This script therefore never
copies a field it was not told to copy: unknown keys are dropped, free-text
fields are dropped, and a job name survives only when it is one of the
well-known binaries listed below. Everything else becomes job-001, job-002, ...
numbered by first appearance.

    python3 docs/evidence/export_events.py                 # summary on stdout
    python3 docs/evidence/export_events.py -o events.jsonl # filtered stream too
    python3 docs/evidence/export_events.py --self-test     # prove the filter drops

Nothing here is a statistic anyone should trust blindly: the summary counts
what the log says, including its own gaps (a pause_start without a pause_end is
a crash or a kill, not a rounding error).
"""
import argparse
import collections
import json
import os
import sys

DEFAULT_SRC = os.path.expanduser("~/.coffee-paladin/history_events.jsonl")

# Fields that leave the machine. Anything not here is dropped, whatever it holds.
KEEP = (
    "time", "epoch", "type", "source",
    "chip_c", "cpu_pct", "pause_s", "duration_s",
    "cores", "cpu_limit_pct", "exit_code", "reason_code", "killed_by_time",
)

# Process names that describe a class of load, not a person's work. A name that
# is not here is replaced by an anonymous label.
PUBLIC_NAMES = {
    "ffmpeg", "ab-av1", "ollama", "llama-server", "Python", "python", "python3",
    "swiftc", "rclone", "kissat", "cadical", "drat-trim", "timeout", "bash", "sh",
    "env", "node", "cargo", "rustc", "clang", "xcodebuild", "make", "ninja",
    "Google Chrome", "Google Chrome Helper (Renderer)", "mediaanalysisd",
    "corespotlightd", "VTDecoderXPCService", "msearch2", "photoanalysisd",
}


def filter_record(rec, labels):
    """Return the exportable view of one event, or None if it is not an event."""
    if not isinstance(rec, dict) or "type" not in rec:
        return None
    out = {k: rec[k] for k in KEEP if k in rec}
    name = rec.get("name")
    if isinstance(name, str):
        if name in PUBLIC_NAMES:
            out["name"] = name
        else:
            if name not in labels:
                labels[name] = "job-%03d" % (len(labels) + 1)
            out["name"] = labels[name]
    return out


def export(src, dst=None):
    labels = {}
    counts = collections.Counter()
    names = collections.Counter()
    first = last = None
    pauses_open = 0
    out = open(dst, "w") if dst else None
    with open(src) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            view = filter_record(rec, labels)
            if view is None:
                continue
            counts[view["type"]] += 1
            names[view.get("name", "?")] += 1
            first = first or view.get("time")
            last = view.get("time") or last
            if out:
                out.write(json.dumps(view, ensure_ascii=False) + "\n")
    if out:
        out.close()
    pauses_open = counts["pause_start"] - counts["pause_end"]
    return {
        "first": first, "last": last, "events": sum(counts.values()),
        "by_type": dict(counts), "anonymised_names": len(labels),
        "top_names": names.most_common(12), "pauses_without_end": pauses_open,
    }


def self_test():
    """The filter must be able to fail: feed it a secret and check it is gone."""
    labels = {}
    secret = {"time": "2026-01-01 00:00:00+0100", "type": "pause_start",
              "name": "acme-client-q4-forecast", "pid": 1, "pgid": 1,
              "reason": "cmdline /Users/someone/acme/run.sh --token=abc",
              "cmd": "should never be copied", "chip_c": 91.5}
    view = filter_record(secret, labels)
    text = json.dumps(view)
    for leak in ("acme", "token", "someone", "cmdline", "pid", "should never"):
        if leak in text:
            print("SELF-TEST FAILED: %r leaked: %s" % (leak, text))
            return 1
    if view["name"] != "job-001" or view["chip_c"] != 91.5:
        print("SELF-TEST FAILED: unexpected view %s" % text)
        return 1
    # A public binary keeps its name; the same private name keeps its label.
    if filter_record({"type": "job_start", "name": "ffmpeg"}, labels)["name"] != "ffmpeg":
        print("SELF-TEST FAILED: public name rewritten")
        return 1
    if filter_record(secret, labels)["name"] != "job-001":
        print("SELF-TEST FAILED: label not stable")
        return 1
    print("self-test OK: %s" % text)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("-o", "--output", help="write the filtered JSONL here")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if not os.path.exists(a.src):
        sys.exit("no event log at %s" % a.src)
    summary = export(a.src, a.output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
