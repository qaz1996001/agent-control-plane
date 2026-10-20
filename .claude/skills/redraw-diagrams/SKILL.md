---
name: redraw-diagrams
description: Re-render the four SVGs in docs/ from their JSON sources after editing docs/src/*.json, including what to do when strict text policy refuses to render. Use after changing any diagram label, or when docs/src/*.json and docs/*.svg may have drifted apart.
---

# Redraw the diagrams

`docs/{flow,dataflow,state,scenarios}.svg` are generated from
`docs/src/*.json`. Both the sources and the SVGs are tracked, so they can drift —
and a JSON that says one thing while its SVG says another is the failure this
skill exists to prevent. Never hand-edit an SVG; the next render overwrites it.

## The three commands, per diagram

The generator is the `fireworks-tech-graph` Agent Skill. Resolve its script path
once:

```bash
FW="$HOME/.claude/skills/fireworks-tech-graph/scripts/fireworks.py"

python3 "$FW" validate architecture docs/src/flow.json
python3 "$FW" render   architecture docs/src/flow.json docs/flow.svg --report /tmp/flow.layout.json
python3 "$FW" check    docs/flow.svg
```

Same three for `dataflow`, `state` and `scenarios`. Run all four even if you only
edited one — it is the cheapest way to find out they had already drifted.

Three things to confirm, not just `ok: true`:

- `render` → `typography.complete_text` is `true` and `typography.truncated` is empty
- `check` → `ok` is `true` (XML identity, marker references, collisions, semantic
  geometry, composition)
- the diff touches only the SVGs you meant to change

## When render refuses

`text_policy` is `strict`: it fails rather than truncating, and the error is
`TEXT_FIT: text would be truncated`. It does not say which label. To find out,
copy the JSON with `text_policy` set to `"report"`, render that copy to a scratch
path, and read `typography.truncated` in the report — it names the role and gives
the full and visible text.

Then, in order of preference:

1. **Widen the card or the canvas.** Coordinates are hand-authored absolute
   pixels with no auto-layout, so moving one node means checking the gaps around
   it: the renderer also fails on a node gap under 40px or a container gutter
   under 20px.
2. **Rewrite the label more tightly**, keeping every fact. Acceptable when the
   label is enumerating — a list of counts can lose its connecting words without
   losing its content.
3. **Do not shorten copy the prose depends on.** If a sentence elsewhere relies
   on that label saying what it says, widening is the only correct move.

If you cannot make it render, **revert that file's JSON change** and record a
to-do in `docs/errata.md`. Leaving the JSON ahead of its SVG is worse than not
making the edit.

## Two mechanical traps

- **Keep each source file's indent width.** They differ — `flow.json` is two
  spaces, the other three are one. Rewriting a file with the wrong width produced
  a 408-line diff for four changed strings. Read the original's second line and
  match it.
- **A node `id` and the arrows that target it must move together.** Renaming a
  node's `id` without its `target` references leaves an edge pointing at nothing,
  and `validate` will not always catch it.

## Numbers in labels

`scenarios.json` quotes token estimates, settled counts and a drift z-score.
These must come from a real run — re-run the scenario and copy what it prints
rather than carrying old values forward:

```bash
uv run --with langgraph python examples/run_pipeline.py budget gate
```

## Visual check

The renderer validates geometry, not appearance. Export a PNG and look at it:

```bash
python3 "$FW" export-png docs/flow.svg /tmp/flow.png --width 1600
```

If no PNG renderer is installed (CairoSVG or rsvg-convert), **say the visual check
was skipped** rather than implying the diagram was reviewed. `validate`, `render`
and `check` passing does not tell you how it looks.
