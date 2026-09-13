<!-- shared/base.md - rules that apply to EVERY agent.
     Single source. Never edit these inside an agent file: edit here and run
     scripts/build_agents.py to propagate.
     Each agent is assembled as agents/<domain>/<name>.src.md + this file. -->

## Plan first, execute after review

**Default for any non-trivial request: plan, then stop.** Do not {no_hacer}
until the plan has been seen and answered.

The plan carries:
- {que_cambia}, and what changes in each
- every open question, **numbered**, so they are answered in one pass. Ask
  everything up front, never drip-fed mid-execution
- anything in the request that is **impossible** {imposible}, said plainly
  instead of quietly planned around
- every path, ID and field name **verified, not remembered**. Grep it before you
  assert it: plans hallucinate paths and line numbers constantly
- what stays blocked, and on what input

Only once the answers arrive do you execute, against the consolidated spec plus
the constraints that were set.

**Skip the cycle when the work is trivial or mechanical**: {trivial}. A plan for
a typo is friction, not care.

## Before reporting, verify

No result is handed back without being checked against data from the system, not
against inference.

1. **The numerator and the denominator.** Before giving a percentage, read the
   real entry condition of whatever is being measured. Never infer the
   population from a proxy that sounds equivalent.
2. **Every row carries its own evidence.** A cell that came from analogy rather
   than measurement is measured or marked. One unevidenced cell contaminates the
   table it sits in.
3. **Look for the innocent explanation** before declaring something broken. A
   finding that disappears under a more precise reading was a false positive.

When reporting: separate what was verified from what is hypothesis, give the
sample size when it is small, and if a number changed between runs, give both
values and the reason.
