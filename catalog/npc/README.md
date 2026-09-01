# NPC catalog fragments

These fragments are the deterministic input to `tools/build_npc_catalog.py`.

## Scope and source policy

The local Core Rulebook extract (`sources/npc/core-rulebook-extract.txt`) is a
16-page spells excerpt. The NPC workflow, race, class, advancement, skill, feat,
and equipment numbers are therefore explicit catalog gaps recorded in
`docs/npc-source-gap-matrix.md`, and every record that needs them keeps
`catalogStatus: "gap"` with null values. A future hash-anchored source can
replace individual records without changing the build pipeline.

One numeric domain IS locally anchored: the complete class spell lists of the
excerpt. `spells.fragment.json` is **generated** by
`tools/parse_npc_sources.py` from `sources/npc/core-rulebook-extract.spell-lists.txt`
(hash in `sources/npc/MANIFEST.json`). Every spell record carries
`levelsByClass` plus per-row `listMembership` line provenance with
`catalogStatus: "partial"` — list membership is resolved, spell rules (school,
components, descriptions) remain gaps. The excerpt's two-column extraction lost
the cleric 7th-level and druid 3rd-level lists at page boundaries; the parser
records these as `emptySections` instead of guessing.

## Fragment inventory

| Fragment | Records | Status |
|----------|---------|--------|
| `ability-arrays.fragment.json` | 2 (basic, heroic) | gap |
| `races.fragment.json` | 7 Core races | gap |
| `classes.fragment.json` | 16 classes (5 NPC + 11 PC) × levels 1–20 | gap |
| `class-features.fragment.json` | 16 feat-slot and choice-slot kinds | gap |
| `skills.fragment.json` | 35 Core skills | gap |
| `feats.fragment.json` | 142 Core feats | gap |
| `items.fragment.json` | 62 items (weapons, armor, shields, goods, magic) | gap |
| `gear-budgets.fragment.json` | 9 profiles (slow/medium/fast × low/normal/high) | gap |
| `spells.fragment.json` | 616 spells, 1431 membership rows | partial (generated) |

Each `*.fragment.json` file has one `section` and a list of `records`. Records
carry typed fields, a `catalogStatus`, and a source reference. The generated
catalog adds source file hashes and a deterministic catalog version.

Names, IDs, and structural shapes follow `NPC_MODE_PLAN.md` (hash-anchored as
`source.npc-mode-plan`); no numeric rule value is stored from memory. Money is
integer copper pieces (`null` while prices are gaps). Feat prerequisites stay
`null` until the feat chapter is hash-anchored; typed prerequisite expressions
are exercised in `derivedRules.npc-rule.typed-prerequisites`.

## Rebuilding

```
python3 tools/expand_npc_fragments.py      # one-shot structural expansion (idempotent for existing IDs)
python3 tools/parse_npc_sources.py --write # regenerate the spells fragment from the anchored extract
python3 tools/build_npc_catalog.py         # rebuild catalog/npc.json
python3 tools/build_npc_catalog.py --check # verify checked-in output matches
```

Note: `tools/expand_npc_fragments.py` runs at import time (it is a one-shot
script); do not import it from tests. Use the builder and parser tools instead.