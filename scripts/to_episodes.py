#!/usr/bin/env python3
"""Turn the frozen transcripts into episodes in the shape L2's engine expects.

    {"episode_id", "day", "topic", "conversation": [{role, content}],
     "tool_calls": [{tool, args, result, ok}]}

Two things in that shape are decisions, not conversions:

`topic` groups episodes, and `induce_skill()` refuses a mixed batch, so the topic
is what decides which episodes get distilled into one skill. It is left empty
here on purpose. `title_hint` carries the first thing asked in the episode so the
topics can be chosen against real text instead of in the abstract.

`ok` is the field the engine reads to find repeated failures, and it is the one
this corpus cannot supply honestly. Claude Code records `is_error`, which misses
any Bash command that exits 0 while printing a traceback. Correcting for that
with a pattern match over the output over-counts in the other direction: a file
containing `except ImportError` is error handling, not an error. So each tool
call carries both readings, `ok_flag` and `ok_pattern`, and `ok` follows the flag
until a hand-labelled sample says which to trust.

    python3 scripts/to_episodes.py
"""

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "episodes.json"

CONTROL_TYPES = {"mode", "permission-mode", "last-prompt", "ai-title",
                 "file-history-snapshot", "summary"}

# Patterns that suggest a failure inside output the harness marked successful.
# Deliberately narrow: every widening of this regex costs false positives, which
# is the whole point of labelling a sample by hand before trusting it.
FAILURE_PATTERN = re.compile(
    r"traceback \(most recent call last\)"
    r"|command not found"
    r"|no such file or directory"
    r"|permission denied"
    r"|modulenotfounderror"
    r"|syntaxerror"
    r"|fatal:"
    r"|^error:",
    re.I | re.M,
)

MAX_ARGS = 300
MAX_RESULT = 600


def clip(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + " ..."


def text_of(content):
    """Flatten a message's content to plain text, ignoring non-text blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [b.get("text", "") for b in content
             if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def is_tool_result_only(content):
    if not isinstance(content, list):
        return False
    kinds = {b.get("type") for b in content if isinstance(b, dict)}
    return bool(kinds) and kinds <= {"tool_result"}


# Text that arrives on a "user" line but was injected by the harness, not typed
# by a person: a background task finishing, a skill being loaded, a hook adding
# context. None of it starts a new task.
INJECTED_PREFIXES = (
    "<task-notification>",
    "<system-reminder>",
    "Base directory for this skill:",
    "Caveat: The messages below were generated",
    "<command-name>",
    "<local-command-stdout>",
)

# A reply this short is a confirmation or a correction inside the task already
# running ("sip", "dale", "no, el otro"), not a new request. It continues the
# episode instead of starting one.
CONTINUATION_CHARS = 60


def is_injected(text):
    return any(text.lstrip().startswith(p) for p in INJECTED_PREFIXES)


def read_rows(path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("type") in CONTROL_TYPES:
                continue
            if isinstance(row.get("message"), dict):
                yield row


def day_index(stamp, first_day):
    """Days since the corpus starts, 1-based, matching the course's `day`."""
    if not stamp:
        return 1
    try:
        d = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
    except ValueError:
        return 1
    return (d - first_day).days + 1


def first_date(paths):
    earliest = None
    for path in paths:
        for row in read_rows(path):
            stamp = row.get("timestamp")
            if not stamp:
                continue
            try:
                d = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
            except ValueError:
                continue
            if earliest is None or d < earliest:
                earliest = d
            break
    return earliest or datetime.now().date()


def build(path, first_day, counter):
    """Split one transcript into episodes, one per real user request.

    A user line holding only tool_result blocks is the harness feeding a tool's
    output back to the model, not a person asking for something, so it continues
    the current episode instead of starting a new one.
    """
    episodes = []
    current = None
    names = {}
    pending = {}

    for row in read_rows(path):
        message = row["message"]
        content = message.get("content")
        role = row.get("type")

        if role == "user" and not is_tool_result_only(content):
            prompt = text_of(content)
            if not prompt or is_injected(prompt):
                continue
            if current is not None and len(prompt) < CONTINUATION_CHARS:
                current["conversation"].append(
                    {"role": "user", "content": clip(prompt, 1200)})
                current["turns"] += 1
                continue
            counter["n"] += 1
            current = {
                "episode_id": f"ep-{path.parent.name[-24:]}-{counter['n']:04d}",
                "day": day_index(row.get("timestamp"), first_day),
                "topic": "",
                "title_hint": clip(prompt, 120),
                "turns": 1,
                "conversation": [{"role": "user", "content": clip(prompt, 1200)}],
                "tool_calls": [],
                "provenance": [f"{path.parent.name}/{path.name}", row.get("uuid", "")],
            }
            episodes.append(current)
            continue

        if current is None:
            continue

        if role == "assistant":
            said = text_of(content)
            if said:
                current["conversation"].append(
                    {"role": "assistant", "content": clip(said, 1200)})

        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                names[block.get("id")] = block.get("name", "?")
                pending[block.get("id")] = {
                    "tool": block.get("name", "?"),
                    "args": clip(block.get("input", {}), MAX_ARGS),
                }
            elif block.get("type") == "tool_result":
                call = pending.pop(block.get("tool_use_id"), None)
                if call is None:
                    call = {"tool": names.get(block.get("tool_use_id"), "?"),
                            "args": ""}
                body = block.get("content")
                if not isinstance(body, str):
                    body = json.dumps(body, ensure_ascii=False)
                ok_flag = not block.get("is_error")
                ok_pattern = ok_flag and not FAILURE_PATTERN.search(body or "")
                call.update({
                    "result": clip(body, MAX_RESULT),
                    "ok": ok_flag,
                    "ok_flag": ok_flag,
                    "ok_pattern": ok_pattern,
                })
                current["tool_calls"].append(call)
    return episodes


def main():
    paths = sorted(RAW.glob("*/*.jsonl"))
    if not paths:
        print("no snapshot: run scripts/snapshot_traces.py first", file=sys.stderr)
        return 1

    first_day = first_date(paths)
    counter = {"n": 0}
    episodes = []
    for path in paths:
        episodes.extend(build(path, first_day, counter))

    # An episode with no tool calls is a question the agent answered from
    # context. Nothing happened in it that a skill could be induced from.
    acting = [e for e in episodes if e["tool_calls"]]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(acting, indent=2, ensure_ascii=False), encoding="utf-8")

    calls = [c for e in acting for c in e["tool_calls"]]
    flag_bad = [c for c in calls if not c["ok_flag"]]
    pattern_bad = [c for c in calls if c["ok_flag"] and not c["ok_pattern"]]
    with_failure = [e for e in acting
                    if any(not c["ok_pattern"] for c in e["tool_calls"])]

    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"{len(episodes)} episodes, {len(acting)} of them with tool calls")
    print(f"{len(calls)} tool calls across {len({e['day'] for e in acting})} days\n")
    print(f"flagged as errors        {len(flag_bad):>4}")
    print(f"unflagged, pattern hit   {len(pattern_bad):>4}")
    print(f"episodes touching one    {len(with_failure):>4}\n")
    by_tool = Counter(c["tool"] for c in pattern_bad)
    if by_tool:
        print("unflagged failures by tool:")
        for tool, n in by_tool.most_common():
            print(f"  {tool:<12} {n:>3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
