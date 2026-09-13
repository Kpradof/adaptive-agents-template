#!/usr/bin/env python3
"""Group the incident log into the failures that repeat.

A single failure is noise. The same failure three times is a rule waiting to be
written, and the number of times is the evidence that justifies it.

    python3 scripts/cluster_incidents.py [--log PATH] [--min 2] [--json out.json]

Clusters by the shape of the failure, not its exact text: a path, a package name
or a line number changes between occurrences while the failure does not. Prints
each cluster with how often it happened, over how many days, and one real
example, which is what a proposed rule has to cite.

`failed` and `candidate` are kept apart. A candidate is a command that exited 0
while printing something that looks like an error, which is sometimes a real
failure and sometimes a file that contains the word "failed". Judge those by
reading the example; never fold them into a count.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_LOG = Path(os.environ.get("INCIDENTS_LOG",
                                  Path.home() / ".claude" / "incidents.jsonl"))

# Collapse the parts that differ between two occurrences of the same failure.
NOISE = [
    (re.compile(r"/[^\s\"']{8,}"), "<path>"),
    (re.compile(r"\b[0-9a-f]{8,}\b", re.I), "<hash>"),
    (re.compile(r"\bline \d+"), "line <n>"),
    (re.compile(r"\b\d{2,}\b"), "<n>"),
]

# The first of these found in the output names the failure. Order matters: the
# most specific wins, so a ModuleNotFoundError is not filed as a plain traceback.
SHAPES = [
    (re.compile(r"ModuleNotFoundError: No module named ['\"]?([\w.]+)", re.I),
     "missing python module: {0}"),
    (re.compile(r"command not found:?\s*(\S+)", re.I), "command not found: {0}"),
    (re.compile(r"No such file or directory:?\s*(\S+)?", re.I), "missing path"),
    (re.compile(r"Permission (?:denied|for this action was denied)", re.I),
     "permission denied"),
    (re.compile(r"SyntaxError", re.I), "syntax error"),
    (re.compile(r"^fatal:\s*(.+)$", re.I | re.M), "git fatal: {0}"),
    (re.compile(r"Traceback \(most recent call last\)", re.I), "python traceback"),
]


def shape(entry):
    text = f"{entry.get('output','')} {entry.get('input','')}"
    for pattern, label in SHAPES:
        m = pattern.search(text)
        if m:
            group = (m.group(1) or "").strip("\"',:") if m.groups() else ""
            return label.format(group) if "{0}" in label else label
    line = (entry.get("output") or "").strip().splitlines()
    head = line[0] if line else entry.get("tool", "?")
    for pattern, repl in NOISE:
        head = pattern.sub(repl, head)
    return head[:70] or "unclassified"


def family(shape_name):
    """The shape with its specific detail dropped.

    `missing python module: pandas` and `: matplotlib` are one failure wearing
    two names, and the rule that fixes them is the same rule. Clustering only on
    the specific name hides that: three occurrences read as three singletons.
    """
    return shape_name.split(":", 1)[0].strip()


def load(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--min", type=int, default=2,
                    help="how many times a failure must repeat to be listed (default 2)")
    ap.add_argument("--json", type=Path, help="also write the clusters here")
    args = ap.parse_args(argv)

    entries = load(args.log)
    if not entries:
        print(f"no incidents recorded yet at {args.log}")
        print("the hook writes here as failures happen; nothing to induce from yet")
        return 0

    groups = defaultdict(list)
    for e in entries:
        groups[(e.get("signal", "failed"), shape(e))].append(e)

    clusters = []
    for (signal, name), items in groups.items():
        days = sorted({(i.get("ts") or "")[:10] for i in items if i.get("ts")})
        clusters.append({
            "signal": signal, "shape": name, "count": len(items),
            "days": days, "tools": sorted({i.get("tool", "?") for i in items}),
            "example": {k: items[0].get(k) for k in ("input", "output", "cwd", "ts")},
        })
    clusters.sort(key=lambda c: (-c["count"], c["shape"]))

    total = len(entries)
    repeated = [c for c in clusters if c["count"] >= args.min]
    print(f"{total} incidents, {len(clusters)} distinct shapes, "
          f"{len(repeated)} seen {args.min}+ times\n")

    for group in ("failed", "candidate"):
        rows = [c for c in repeated if c["signal"] == group]
        if not rows:
            continue
        header = ("FAILURES the harness flagged" if group == "failed"
                  else "CANDIDATES: exited 0 but printed something error-shaped. "
                       "Read the example before counting these as failures.")
        print(header)
        for c in rows:
            span = (f"{len(c['days'])} day(s)" if c["days"] else "unknown span")
            print(f"  {c['count']:>3}x  over {span:<12} {c['shape']}")
            print(f"       tools: {', '.join(c['tools'])}")
            print(f"       e.g. {(c['example']['input'] or '')[:90]}")
            print(f"            {(c['example']['output'] or '')[:90]}")
        print()

    fams = defaultdict(int)
    fam_days = defaultdict(set)
    for c in clusters:
        if c["signal"] != "failed":
            continue
        fams[family(c["shape"])] += c["count"]
        fam_days[family(c["shape"])].update(c["days"])
    rolled = [(n, k) for k, n in fams.items()
              if n >= args.min and n > max(
                  (c["count"] for c in clusters
                   if c["signal"] == "failed" and family(c["shape"]) == k), default=0)]
    if rolled:
        print("ROLLED UP: one failure wearing several names, which is what a "
              "single rule would fix")
        for n, k in sorted(rolled, reverse=True):
            print(f"  {n:>3}x  over {len(fam_days[k])} day(s)   {k}")
        print()

    if args.json:
        args.json.write_text(json.dumps(clusters, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        print(f"clusters written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
