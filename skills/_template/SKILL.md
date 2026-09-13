---
name: skill-name
description: One sentence saying what this does and when to load it. This is the only part the model sees before deciding to load the skill, so it has to be distinguishable from every other skill's description. Two skills whose descriptions overlap force a guess.
---

# Skill name

What this procedure accomplishes, in one or two sentences.

## When to use

The situations that should load this, and the ones that should not.

## Steps

1. ...
2. ...

## Errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | ran `python3` instead of the venv interpreter | use `.venv/bin/python` |

## Provenance

Which failures produced this skill, and when. An induced skill carries the
episode ids it was distilled from; a hand-written one carries the date and what
went wrong.
