#!/usr/bin/env python3
"""Ask of every rule: has the failure it was written for happened again?

Step 07, the half that is usually missing. A ledger that records which rule
exists and where it came from is bookkeeping. The measurement is the comparison
between the failure a rule was written to prevent and what the incident log has
seen since the rule was written.

    python3 scripts/measure_rules.py [--rules RULES.md] [--log incidents.jsonl]
    python3 scripts/measure_rules.py --write    # also fill in `last confirmed`

Three verdicts, and the third is the honest one that most ledgers hide:

  holding       the failure has not recurred since the rule was written. The
                rule is working, or it was never needed. Those two are only
                separable by removing it and watching, which is the point.
  not working   the failure recurred after the rule existed. Whatever the rule
                says, it is not preventing this. First candidate for rewrite.
  unmeasurable  the rule names no failure to watch for, so nothing about it can
                be checked. It can only ever be removed on opinion.

Each rule is linked to a failure by a `watches:` field naming the shape from
`cluster_incidents.py`. Where a rule has no `watches`, the shape is inferred
from its `from` text, and the rule is reported as inferred so the guess is never
mistaken for a declaration.
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_LOG = Path(os.environ.get("INCIDENTS_LOG",
                                  Path.home() / ".claude" / "incidents.jsonl"))

_spec = importlib.util.spec_from_file_location("ci", HERE / "cluster_incidents.py")
_ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ci)


def read_rules(path):
    """Parse RULES.md into entries. Stops at the Removed section: what left the
    system is history, and measuring it again would resurrect it as a finding."""
    rules, current = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"##\s+Removed\b", line, re.I):
            break
        if line.startswith("### "):
            current = {"name": line[4:].strip()}
            rules.append(current)
        elif current is not None:
            m = re.match(r"\s*[-*]\s*\*\*(.+?):\*\*\s*(.*)", line)
            if m:
                current[m.group(1).strip().lower()] = m.group(2).strip()
    return rules


def shape_of(rule):
    """The failure this rule watches for, and whether it was declared or guessed."""
    declared = rule.get("watches")
    if declared and not declared.upper().startswith("TODO"):
        return declared, True
    origin = rule.get("from", "")
    if not origin or origin.upper().startswith("TODO"):
        return None, False
    guessed = _ci.shape({"output": origin, "input": "", "tool": ""})
    # A shape that is just the first line of the prose back again carries no
    # information: the inference found nothing it recognised.
    if guessed.lower().startswith(origin.lower()[:24]):
        return None, False
    return guessed, False


def as_date(text):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rules", type=Path, default=ROOT / "RULES.md")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--write", action="store_true",
                    help="write the verdict into `last confirmed` in RULES.md")
    args = ap.parse_args(argv)

    if not args.rules.exists():
        print(f"no ledger at {args.rules}: nothing to measure", file=sys.stderr)
        return 1

    rules = read_rules(args.rules)
    incidents = _ci.load(args.log)
    for i in incidents:
        i["_shape"] = _ci.shape(i)
        i["_family"] = _ci.family(i["_shape"])
        i["_date"] = as_date(i.get("ts", ""))

    today = date.today()
    results, updates = [], {}
    for rule in rules:
        shape, declared = shape_of(rule)
        added = as_date(rule.get("added", ""))
        if shape is None:
            results.append((rule["name"], "unmeasurable", 0, 0, None, declared))
            continue

        family = _ci.family(shape)
        matching = [i for i in incidents if i["_family"] == family]
        since = [i for i in matching
                 if added is None or (i["_date"] and i["_date"] >= added)]
        before = len(matching) - len(since)
        last = max((i["_date"] for i in since if i["_date"]), default=None)
        if since:
            verdict = "not working"
        elif before:
            verdict = "holding"
        else:
            # Zero occurrences either side. Calling that "holding" is the exact
            # false comfort this whole step exists to remove: the rule has never
            # been observed doing anything.
            verdict = "unobserved"
        results.append((rule["name"], verdict, before, len(since), last, declared))
        if verdict == "holding" and added:
            updates[rule["name"]] = (
                f"{today.isoformat()}, the failure has not recurred since "
                f"{added.isoformat()}")
        elif since:
            updates[rule["name"]] = (
                f"{today.isoformat()}, the failure recurred "
                f"{len(since)} time(s), last on {last.isoformat() if last else '?'}")

    if not incidents:
        print(f"the log at {args.log} is empty.\n"
              "Every rule reads as holding only because nothing has been recorded "
              "yet: that is an absence of evidence, not evidence a rule works.\n")

    width = min(max((len(r[0]) for r in results), default=20), 58)
    marks = {"holding": "ok  ", "not working": "FAIL",
             "unobserved": "  ? ", "unmeasurable": "----"}
    details = {
        "not working": lambda b, s, l: f"recurred {s}x, last {l}",
        "holding": lambda b, s, l: f"{b} before the rule, 0 since",
        "unobserved": lambda b, s, l: "never seen either side of the rule",
        "unmeasurable": lambda b, s, l: "names no failure to watch for",
    }
    for name, verdict, before, since, last, declared in results:
        tag = "" if declared or verdict == "unmeasurable" else "  (shape inferred)"
        print(f"{marks[verdict]} {name[:width]:<{width}}  "
              f"{details[verdict](before, since, last)}{tag}")

    counts = {v: sum(1 for r in results if r[1] == v)
              for v in ("holding", "not working", "unobserved", "unmeasurable")}
    print(f"\n{len(results)} rules: {counts['holding']} holding, "
          f"{counts['not working']} not working, "
          f"{counts['unobserved']} unobserved, "
          f"{counts['unmeasurable']} unmeasurable")
    if counts["unobserved"]:
        print("Unobserved is not the same as working. Those rules have never been "
              "seen preventing anything, which is the case for removing one and "
              "watching what happens.")
    if counts["unmeasurable"]:
        print("An unmeasurable rule can only be removed on opinion. Give it a "
              "`watches:` field naming the failure it prevents.")

    if args.write and updates:
        text = args.rules.read_text(encoding="utf-8")
        for name, value in updates.items():
            pattern = re.compile(
                r"(### " + re.escape(name) + r"\n(?:.*\n)*?- \*\*last confirmed:\*\* )(.*)")
            text = pattern.sub(lambda m: m.group(1) + value, text, count=1)
        args.rules.write_text(text, encoding="utf-8")
        print(f"\nwrote `last confirmed` for {len(updates)} rule(s) in {args.rules}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
