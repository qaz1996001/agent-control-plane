# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running anything

```bash
uv run --with pytest --with langgraph pytest -q                    # the suite
uv run --with langgraph python examples/run_pipeline.py            # all ten scenarios
uv run --with langgraph python examples/run_pipeline.py --gemma    # the same, real model
```

Bare `pytest` and bare `python` both fail: `langgraph` and `pytest` are not in the
ambient interpreter. `pyproject.toml` sets `pythonpath = ["src", "."]`, so pytest
imports `agentcp` without an install — but it still needs the dependency, which is
what `--with` supplies.

`--gemma` needs a local Ollama serving `gemma4:e4b`; without it that one scenario
prints what is missing and skips. **Do not use `ollama pull` on this machine** — its
IPv6 is dead and the pull wedges on it. See `docs/errata.md` for the IPv4 workaround.

## What this repository is arguing

An agent pipeline's control plane should be ordinary code: routing is a lookup
table, permissions an allow-list, budget a counter, approval an interrupt. The
model makes judgements *inside* a step and never decides which step comes next.

Two consequences that constrain every change:

- **`src/agentcp/` imports no model provider.** No SDK, no model id, no API key.
  A real model reaches the pipeline only by being injected as a `Judge` —
  `(prompt, context) -> dict` — and the adapter for one lives in `examples/`
  (`gemma_judge.py`). Importing a provider under `src/` retracts what
  `tests/test_judgement_boundary.py` asserts, which is the repository's argument.
- **`agents.consult` is the only function that calls a `Judge`.** Masking, provider
  choice, the budget, the quota and the audit record all sit behind it, so they are
  unavoidable rather than things each node remembers. A second entry point makes
  every one of them optional.

## Writing tests here

**Every new test must fail when the mechanism it tests is removed.** Prove it:
break the mechanism, run the test, confirm red, restore. Record the evidence in the
commit message. The suite was rebuilt to this discipline because three tests were
found that passed either way — a test that passes with the mechanism gone is worse
than no test, because it reads like evidence.

## Two files that are records, not documentation

`docs/errata.md` and `docs/fix-plan.md` have their `file:line` citations pinned to
the commits that wrote them, and both say so. **Do not update line numbers, rename
identifiers, or "fix" the claims inside them.** A record that moves with what it
records is not a record. `docs/errata.md` lists this repository's own overstated
claims, including the ones still open; new instances get appended, old ones get a
"how it was fixed" line.

## Changing the diagrams

The four SVGs in `docs/` are generated from `docs/src/*.json`. Never hand-edit an
SVG — the next render overwrites it. Re-render with the `fireworks-tech-graph`
skill (`validate` → `render` → `check`); `/redraw-diagrams` has the commands.

`text_policy` is `strict`: the renderer refuses rather than truncating, coordinates
are hand-authored absolute pixels, and there is no auto-layout. When a label no
longer fits, widen the card — do not shorten copy the prose depends on. Keep each
source file's existing indent width; rewriting it produces a 400-line diff for a
four-string change.

Numbers in `scenarios.json` labels must come from a real run. Re-run the scenario
and copy what it prints.

## Prose conventions

- **Everything is bilingual.** Every `README.md` / `docs/*.md` has a `.zh-TW.md`
  twin. They are not translations — each is its own text to the same effect. A
  change to one is not done until the other has it.
- The scenario names (`approve`, `rework`, `budget`, `mask`, `residency`, `quota`,
  `gemma`, …) name *mechanisms*, not stories. They survive domain changes.
- Output pasted into a README must come from a real run, not be hand-edited into
  shape. The field labels and widths change more often than they look like they do.

## After renaming an identifier

Scan for residue **without `\b`** — word boundaries do not match inside
underscores, so `\bdeployer\b` reports zero while
`test_deploy_is_reachable_only_by_the_deployer` is still there. Use a substring
scan:

```bash
grep -rhoE "[a-z_]*(oldword)[a-z_]*" src tests examples README*.md docs/*.md --include=*.py --include=*.md | sort -u
```

Then check that every test name and test file cited in the docs still exists —
deleting or renaming a test leaves the docs citing something that is not there,
which is worse than the decorative test it replaced.
