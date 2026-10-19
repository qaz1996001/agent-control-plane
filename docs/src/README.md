# Diagram sources

The four SVGs in `docs/` are generated from the JSON in this directory.
Edit the JSON and re-render; do not hand-edit the SVG, because the next
render will overwrite it.

Rendered with [`fireworks-tech-graph`](https://github.com/qaz1996001) as
an Agent Skill, style 1 (Flat Icon), `quality_profile: showcase`,
`text_policy: strict`. The generator is not a dependency of the package
and is not needed to run the tests or the examples — only to change a
diagram.

```bash
FW=/path/to/fireworks-tech-graph/scripts/fireworks.py

python3 "$FW" validate architecture docs/src/dataflow.json
python3 "$FW" render   architecture docs/src/dataflow.json docs/dataflow.svg
python3 "$FW" check    docs/dataflow.svg
```

Same three commands for `flow`, `state` and `scenarios`.

`render` refuses rather than degrading: it fails on a node gap under
40px, a container gutter under 20px, and on any label that would be
truncated (`text_policy: strict`). Widen the card or the canvas; do not
shorten a label that the prose depends on.

`check` re-validates the written SVG — XML identity, marker references,
collisions, semantic geometry, composition.

## Conventions

- **Coordinates are hand-authored absolute pixels.** There is no
  auto-layout. Moving one node means checking the gaps around it.
- **Labels are Chinese only**, including in the diagrams embedded by the
  English `architecture.md`. The prose and the Mermaid diagrams in
  `design.md` are bilingual; these are not. Recorded as a known
  inconsistency in [`../scope.md`](../scope.md) rather than left
  unmentioned.
- **The four `flow` values** (`read`, `write`, `control`, `feedback`)
  carry a different meaning per diagram and are re-labelled in each
  one's `legend`.
- **Numbers in labels must come from a real run.** `scenarios.json`
  quotes the token estimate, the settled count and a drift z-score.
  Re-run `examples/run_pipeline.py budget gate` and copy what it prints
  rather than carrying the old values forward.
- `*.report.json` and `*.rep.json` are generator output and are
  gitignored.
