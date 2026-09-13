#!/bin/bash
# Record a failure the moment it happens, with its context attached.
#
# Step 02 of the loop. Mining old transcripts for failures loses the context and
# forces a guess about what counted as one; the harness also deletes its own
# transcripts, so the evidence expires. This writes an append-only log the
# system owns instead.
#
# Wire it to two events:
#   PostToolUseFailure  (no matcher)  -> the harness says the tool failed
#   PostToolUse         (Bash)        -> a command that exited 0 while printing
#                                        a traceback: logged as a CANDIDATE, not
#                                        a failure, because the pattern also
#                                        matches a file that merely contains the
#                                        word "failed". A person or a skill
#                                        judges it later, with the output in hand.
#
# Never blocks and never fails the tool call: it exits 0 no matter what.

LOG="${INCIDENTS_LOG:-$HOME/.claude/incidents.jsonl}"
mkdir -p "$(dirname "$LOG")" 2>/dev/null

payload=$(cat)
[ -z "$payload" ] && exit 0

kind=$(printf '%s' "$payload" | jq -r '.hook_event_name // empty' 2>/dev/null)
tool=$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null)
[ -z "$tool" ] && exit 0

# PostToolUse carries the result in .tool_response; PostToolUseFailure has no
# tool_response at all and puts the message in .error. Reading only the first
# logs every real failure with an empty body, which is worse than not logging
# it: the cluster cannot classify what it cannot read.
out=$(printf '%s' "$payload" | jq -r '
  [.tool_response // .error // empty]
  | map(if type == "string" then . else tojson end) | join(" ")' 2>/dev/null)

signal="failed"
if [ "$kind" = "PostToolUse" ]; then
  # Only Bash reaches here, and only a pattern match is worth recording.
  printf '%s' "$out" | grep -qiE \
    'traceback \(most recent call last\)|command not found|no such file or directory|permission denied|modulenotfounderror|syntaxerror|^fatal:' \
    || exit 0
  signal="candidate"
fi

printf '%s' "$payload" | jq -c --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg signal "$signal" --arg out "$out" '{
    ts: $ts,
    signal: $signal,
    tool: (.tool_name // ""),
    cwd: (.cwd // ""),
    session: (.session_id // ""),
    input: ((.tool_input // {}) | tojson | .[0:400]),
    output: ($out | .[0:800])
  }' >> "$LOG" 2>/dev/null

exit 0
