# Rules

Every rule the system holds, with the failure that produced it and the last time
that failure was seen. This file is what makes step 07 possible: a rule with no
`from` cannot be measured, because there is no failure to watch for.

A rule whose failure has not recurred since it was written is either working or
unnecessary. Those two are distinguishable only by removing it and watching.

---

### verify paths before asserting them

- **watches:** missing path
- **added:** 2026-08-14
- **from:** a plan that referenced three files that did not exist
- **applies to:** all agents (`shared/base.md`)
- **last confirmed:** 2026-09-02, the same failure recurred in the paid agent
- **status:** active

### run course code with the venv interpreter, not `python3`

- **watches:** missing python module
- **added:** 2026-09-12
- **from:** `ModuleNotFoundError` twice, six weeks apart, in two different
  projects, both from calling `python3` directly
- **applies to:** any agent that runs project code
- **last confirmed:** not yet re-tested
- **status:** proposed, awaiting review

---

## Removed

Rules leave the system through this section, never by deletion, so the reason
survives.

### (none yet)
