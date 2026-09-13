#!/usr/bin/env python3
"""Freeze the Claude Code transcripts before they rotate away.

Claude Code deletes old transcripts on its own. During one afternoon of work on
this project the corpus went from 10 files to 8, and the two largest sessions
erased themselves while they were being counted. Anything measured against the
live directory stops being reproducible within days, so the first step of the
pipeline is to take a copy and never touch the originals again.

    python3 scripts/snapshot_traces.py

Copies every ~/.claude/projects/*/*.jsonl into data/raw/ (one subdirectory per
project, so two sessions of the same project keep their grouping), then reports
how many tool calls the snapshot holds, by tool.
"""

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SOURCE = Path.home() / ".claude" / "projects"

# Transcript lines that carry no conversation. Everything else is worth keeping.
CONTROL_TYPES = {"mode", "permission-mode", "last-prompt", "ai-title",
                 "file-history-snapshot", "summary"}


def copy_transcripts():
    """Copy each transcript into data/raw/<project>/<session>.jsonl."""
    copied, skipped = [], []
    for src in sorted(SOURCE.glob("*/*.jsonl")):
        dest = RAW / src.parent.name / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size == src.stat().st_size:
            skipped.append(dest)
            continue
        shutil.copy2(src, dest)
        copied.append(dest)
    return copied, skipped


def iter_blocks(path):
    """Yield every content block of a transcript, with the line's type.

    The content is nested one level down, under "message", and is a list of
    blocks: a single assistant turn can hold text, then a tool call, then
    another. Lines that fail to parse are skipped rather than fatal, because a
    transcript can be truncated mid-write when a session is killed.
    """
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("type") in CONTROL_TYPES:
                continue
            message = row.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict):
                    yield row, block


def count_tools(paths):
    """Count tool_use blocks by tool name, and pair results back to their tool.

    A tool_result does not say which tool produced it: it carries only
    tool_use_id. The id -> name map built here is what every later step needs to
    say things like "81 of the silent failures were Bash".
    """
    by_tool = Counter()
    names = {}
    results = 0
    for path in paths:
        for _row, block in iter_blocks(path):
            kind = block.get("type")
            if kind == "tool_use":
                by_tool[block.get("name", "?")] += 1
                names[block.get("id")] = block.get("name")
            elif kind == "tool_result":
                results += 1
    return by_tool, names, results


def main():
    if not SOURCE.exists():
        print(f"no transcripts at {SOURCE}", file=sys.stderr)
        return 1

    copied, skipped = copy_transcripts()
    print(f"copied {len(copied)} transcript(s), {len(skipped)} already current")

    paths = sorted(RAW.glob("*/*.jsonl"))
    size = sum(p.stat().st_size for p in paths)
    print(f"snapshot holds {len(paths)} transcript(s), {size / 1_048_576:.1f} MB\n")

    by_tool, _names, results = count_tools(paths)
    total = sum(by_tool.values())
    print(f"{total} tool calls, {results} results\n")
    width = max((len(t) for t in by_tool), default=4)
    for tool, n in by_tool.most_common():
        print(f"  {tool:<{width}}  {n:>5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
