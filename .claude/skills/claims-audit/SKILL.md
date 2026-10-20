---
name: claims-audit
description: Find places where this repository claims more than its evidence supports — decorative tests, mechanisms nothing reaches, claims broader than the code, and conventions described as structure. Use when adding a claim to the README or docs, after changing a mechanism, before publishing, or when asked to audit the claims.
---

# Claims audit

This repository's value is that its claims are backed. An unsupported sentence
costs more than a missing feature, because a reader who finds one stops trusting
the rest. This skill is the audit that found twenty-seven of them, written down
so it can be re-run.

## The four shapes

Classify every finding. The classes are the ones `docs/errata.md` already uses —
match them, do not invent new ones.

- **A — a convention described as structure.** Nothing in the code violates the
  claim today, and nothing prevents violating it. *Found this way: a node could
  write `human_decision` and forge a human approval; the docs called that a
  "structural property rather than a convention".*
- **B — a decorative test.** The setup suggests it proves X; the assertions pass
  with the mechanism removed. *Found this way: a test monkeypatched both model
  entry points to explode, then only called a three-line dict lookup.*
- **C — a mechanism nothing reaches.** Code and tests exist, no execution path
  goes there. *Found this way: `tools.schemas_for` renders tool schemas for a
  model; no node gives a model tool choice.*
- **D — a claim broader than the code.** True in a narrow case, stated generally.
  *Found this way: "a bad tool degrades one step" — `invoke` contains the
  exception, but nothing read the error, so the step reported success on no data.*

## Method

Prove every finding by experiment, not by reading. The strongest proof breaks the
mechanism and shows the test still passes, or runs the pipeline and shows the
claimed thing never happens.

```bash
uv run --with pytest --with langgraph pytest -q
uv run --with langgraph python examples/run_pipeline.py
```

1. **Collect the claims.** Both READMEs, `docs/architecture*.md`,
   `docs/design*.md`, `docs/scope*.md`, every `src/` docstring that asserts a
   property, and the generated diagram labels in `docs/src/*.json`. A claim in a
   diagram counts.
2. **For each, find what the code does.** Open the file at the line. Grep for the
   consumer: a mechanism with no caller outside `tests/` is class C and the grep
   is the proof.
3. **Try to break it.** Remove the guard, no-op the function, add an adversarial
   node or judge, then run the test that supposedly pins it. Green after the
   break is class B, and the command plus output is the evidence.
4. **Write it up** in `docs/errata.md`'s existing format: the claim quoted with
   `file:line`, what the code does instead, the experiment, the class, and an
   empty "how it was fixed" slot. **Record before repairing** — once repaired the
   gap vanishes from the history, and how a claim came to outrun its evidence is
   the useful part.

## Deciding what to do about one

The shape of the claim decides, not how hard the fix is:

| The claim is | Do this |
|---|---|
| a **mechanism** | make it structural, so it does not depend on anyone remembering |
| a **scope** | state the scope precisely — where it holds, where it stops |
| a **wish** | delete it, or move it to `docs/scope.md` with the condition that reopens it |

None of the three is "add a feature". For a demonstration repository an
honestly-bounded claim is usually worth more than the feature that would make the
broader one true, and scope creep makes the argument harder to read.

## Two traps this audit fell into itself

- **Repairs create fresh instances.** Deleting a test left ten doc sites citing
  it; renaming one left four. Both are worse than what they replaced. After any
  repair, check that every test name and file cited in the docs exists.
- **`\b` does not match inside underscores.** A residue scan with
  `\bdeployer\b` reported zero while twelve test names still contained it. Use a
  substring scan.
