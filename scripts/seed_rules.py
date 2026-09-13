#!/usr/bin/env python3
"""Seed RULES.md from the rules already written into the agents.

Step 07 needs a ledger: every rule, the failure that produced it, and the last
time that failure was seen. A system that has been running a while already holds
most of that, scattered. Section headings carry dates, and the rules that came
from a real incident usually say so in the prose ("Mistake made 06-ago-2026",
"Real case (2026-08-27)", "Corrected by ...").

This collects what is recoverable and writes the rest as TODO, so the gap is
visible instead of silently absent. It never invents a cause: a rule with no
evidence in the text gets `from: TODO` and stays unmeasurable until a person
fills it in.

    python3 scripts/seed_rules.py <agents-root> [--out RULES.md]

Existing entries are preserved: re-running adds only rules not already listed,
so the provenance you fill in by hand is never overwritten.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

MONTHS = {m: i + 1 for i, m in enumerate(
    ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct",
     "nov", "dic"])}

ISO = re.compile(r"\((\d{4})-(\d{2})-(\d{2})\)")
ES = re.compile(r"\b(\d{1,2})-(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)-(\d{4})\b", re.I)

# Prose that marks a rule as having come from a real incident rather than a
# preference. These are what make a rule measurable.
EVIDENCE = re.compile(
    r"(mistake made[^.]*\.|real case[^.]*\.|corrected by[^.)]*[.)]|"
    r"do not repeat[^.]*\.|proven with[^.]*\.|that turned[^.]*\.|"
    r"eso convirtió[^.]*\.|error de [^.]*\.)", re.I)

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def one_line(match):
    """Evidence as a single line: a list item that wraps stops being a list item."""
    if not match:
        return None
    return " ".join(match.group(0).split())[:220]


def strip_date(heading):
    """The date belongs in `added`, not in the rule's name."""
    return ISO.sub("", ES.sub("", heading)).replace("()", "").strip(" —-")


def parse_date(text):
    m = ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    m = ES.search(text)
    if m:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2).lower()],
                        int(m.group(1))).isoformat()
        except (ValueError, KeyError):
            pass
    return None


def agent_name(text):
    m = FRONTMATTER.match(text)
    if not m:
        return None
    fields = dict(
        (k.strip(), v.strip())
        for k, v in (l.split(":", 1) for l in m.group(1).splitlines() if ":" in l))
    if "tools" not in fields and "model" not in fields:
        return None
    return fields.get("name")


def sections(text):
    out, name, buf = [], None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if name:
                out.append((name, "\n".join(buf)))
            name, buf = line[3:].strip(), []
        elif name:
            buf.append(line)
    if name:
        out.append((name, "\n".join(buf)))
    return out


def collect(root):
    rules = []
    shared = root / "shared" / "base.md"
    if shared.exists():
        for heading, body in sections(shared.read_text(encoding="utf-8", errors="replace")):
            rules.append({
                "name": heading, "applies": "all agents (`shared/base.md`)",
                "added": parse_date(heading) or parse_date(body),
                "evidence": one_line(EVIDENCE.search(body))})

    for path in sorted(root.glob("*/*.md")):
        if path.parent.name.startswith(".") or path.name.endswith(".src.md"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        name = agent_name(text)
        if not name:
            continue
        for heading, body in sections(text):
            if any(r["name"] == heading for r in rules):
                continue  # already carried by the shared file
            added = parse_date(heading)
            found = EVIDENCE.search(body)
            if not added and not found:
                continue  # a plain section, not a dated or incident-born rule
            rules.append({
                "name": heading, "applies": f"`{name}`",
                "added": added or parse_date(body),
                "evidence": one_line(found)})
    return rules


def render(rules, today):
    out = ["# Rules", "",
           "Every rule the system holds, with the failure that produced it and the",
           "last time that failure was seen. This file is what makes step 07",
           "possible: a rule with no `from` cannot be measured, because there is no",
           "failure to watch for.",
           "",
           "A rule whose failure has not recurred since it was written is either",
           "working or unnecessary. Those two are distinguishable only by removing",
           "it and watching.",
           "",
           f"Seeded from the agent files on {today}. Entries marked TODO carry no",
           "recoverable cause: until one is filled in, that rule cannot be retired",
           "on evidence, only on opinion.",
           "", "---", ""]
    for r in sorted(rules, key=lambda x: (x["added"] or "9999", x["name"])):
        out.append(f"### {strip_date(r['name'])}")
        out.append("")
        out.append(f"- **watches:** {r.get('watches') or 'TODO (name the failure this prevents)'}")
        out.append(f"- **added:** {r['added'] or 'TODO (no date in the text)'}")
        out.append(f"- **from:** {r['evidence'] or 'TODO (no incident recorded)'}")
        out.append(f"- **applies to:** {r['applies']}")
        out.append("- **last confirmed:** TODO")
        out.append("- **status:** active")
        out.append("")
    out += ["---", "", "## Removed", "",
            "Rules leave the system through this section, never by deletion, so the",
            "reason survives.", "", "_(none yet)_", ""]
    return "\n".join(out) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if not args.root.is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 1

    out = args.out or args.root / "RULES.md"
    rules = collect(args.root)

    if out.exists():
        existing = out.read_text(encoding="utf-8")
        kept = [r for r in rules if f"### {strip_date(r['name'])}" not in existing]
        if not kept:
            print(f"{out}: already lists every rule found; nothing added")
            return 0
        body = render(kept, date.today()).split("---\n\n", 1)[1]
        out.write_text(existing.rstrip("\n") + "\n\n" + body, encoding="utf-8")
        print(f"{out}: added {len(kept)} rule(s), kept what was already there")
        return 0

    out.write_text(render(rules, date.today()), encoding="utf-8")
    dated = sum(1 for r in rules if r["added"])
    evidenced = sum(1 for r in rules if r["evidence"])
    print(f"wrote {out}")
    print(f"{len(rules)} rules: {dated} with a date, {evidenced} with a recorded cause")
    print(f"{len(rules) - evidenced} need a cause filled in before they can be measured")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
