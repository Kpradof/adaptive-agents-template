---
name: induce-rules
description: Turn the recorded incident log into proposed rules. Reads the failures the agents actually hit, groups the ones that repeat, and drafts a rule with its evidence attached for approval. Use when asked to review incidents, propose rules from failures, or close the loop on what went wrong this week.
---

# Induce rules from what actually failed

Step 03. The incident log holds failures the agents hit, recorded at the moment
they happened by `hooks/record-failure.sh`. This turns the ones that repeat into
rules, and only those.

A rule is expensive: every agent that carries it pays attention for it on every
request. So the bar is a failure that happened **more than once**, and the draft
has to carry the evidence that says so.

## Steps

1. **Cluster.**

   ```bash
   python3 scripts/cluster_incidents.py --min 2 --json /tmp/clusters.json
   ```

   Nothing at 2+ means nothing to induce. Say so and stop: a rule written from a
   single incident is a guess with a citation.

2. **Read the candidates before counting them.** `failed` is what the harness
   itself flagged. `candidate` is a command that exited 0 while printing
   something error-shaped, which is a real failure about half the time and a
   file containing the word "failed" the rest. Open the example. Decide. A
   candidate that survives reading becomes evidence; one that does not is
   dropped and never enters a count.

3. **Prefer the rolled-up family over the specific shape.** Three missing
   modules with three different names are one failure: the wrong interpreter.
   The rule that fixes the family is worth writing; three rules naming three
   packages are not.

4. **Draft one rule per cluster**, in this shape:

   ```markdown
   ### run project code with the venv interpreter, not `python3`
   - **watches:** missing python module
   - **added:** 2026-09-13
   - **from:** ModuleNotFoundError 3 times over 2 days, three different packages,
     every one of them a bare `python3` call
   - **applies to:** any agent that runs project code
   - **last confirmed:** not yet re-tested
   - **status:** proposed
   ```

   `watches` is the field that makes the rule measurable: it is the cluster
   name, copied exactly, so `measure_rules.py` can ask later whether that
   failure came back. `from` is the evidence that justified writing it. A rule
   with neither can only ever be removed on opinion.

5. **Say where it belongs, and why.**

   | The failure hits | The rule goes in |
   |---|---|
   | every agent | `shared/base.md` |
   | one domain | that agent's `<name>.src.md` |
   | one recurring procedure | the skill for it, under errors and fixes |

   A rule that only one agent can hit does not belong in the shared file. Shared
   rules are read on every request by every agent, so each one added there costs
   attention everywhere.

6. **Stop and hand the draft back.** Do not write to `RULES.md`, `shared/base.md`
   or any `.src.md` before approval. Approval is what turns a proposal into
   behavior every future run inherits, which is also what makes it the step that
   a bad proposal has to get past.

7. **On approval:** append to `RULES.md`, write the rule into its destination,
   then run `python3 scripts/build_agents.py` so the generated agents pick it up,
   and `--check` to confirm they did.

8. **Later, measure it.** `python3 scripts/measure_rules.py` compares each
   rule's `watches` against everything the log has seen since the rule was
   written. Four verdicts, and the two in the middle are the ones worth acting
   on: `not working` means the failure came back anyway, `unobserved` means the
   rule has never been seen preventing anything, which is the case for removing
   it and watching. Run it on a schedule, not once.

## What not to do

**Do not induce from a single incident.** Write it in `RULES.md` under a
`status: watching` entry instead, with the date. If it happens again the cluster
will find it and the entry already has its first occurrence recorded.

**Do not write a rule that restates a failure.** "Do not call a missing module"
is not a rule. What to do instead is: name the interpreter, the path, the check
that catches it first.

**Do not let the log grow unread.** An incident log nobody reviews is the same
accumulation problem one level down. Review on a schedule, and prune entries
whose rule already landed.
