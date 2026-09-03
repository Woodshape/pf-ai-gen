# NPC catalog fragments

These fragments are the deterministic input to `tools/build_npc_catalog.py`.

## Scope and source policy

The local Core Rulebook PDF remains a 16-page spell excerpt. Official Archives
of Nethys pages for the Phase 2 rules are now archived and hash-anchored under
`sources/reference/aonprd/`, with deterministic text extracts under
`sources/npc/aonprd/`. See `docs/npc-source-gap-matrix.md` for exact coverage.

Source acquisition does not silently resolve the scaffold: records keep
`catalogStatus: "gap"` until a parser or curated fragment supplies exact values
and line-level `sourceRef` provenance. The current resolved slices are human
warrior levels 1–5, an elemental-fire goblin Sorcerer at levels 5–6, a
Fire-domain goblin Druid at level 3 (prepared divine casting), and a
goblin Druid at level 3 with the Elemental Ally archetype (Monster Summoner's
Handbook pg. 16) and its linked level-3 fire elemental eidolon row (unchained
eidolon rules, Elemental subtype, PFU Biped base form with the Slam evolution; see
`docs/elemental-ally-source-assessment.md`). The fixture's
four selected Druid skills are resolved; unselected class-skill records such as
Perception remain gaps even where their source table is already archived.
Everything outside those bounded slices remains a gap.

The complete class spell lists in the PDF excerpt remain independently
anchored. `spells.fragment.json` is **generated** by
`tools/parse_npc_sources.py` from `sources/npc/core-rulebook-extract.spell-lists.txt`
(hash in `sources/npc/MANIFEST.json`). Every spell record carries
`levelsByClass` plus per-row `listMembership` line provenance with
`catalogStatus: "partial"` — list membership is resolved. Twenty-two spells
used by the goblin Sorcerer and Druid slices are curated from current AoN
pages and resolved; other spell rules remain gaps. The excerpt's two-column
extraction lost
the cleric 7th-level and druid 3rd-level lists at page boundaries; the parser
records these as `emptySections` instead of guessing.

## Fragment inventory

| Fragment | Records | Status |
|----------|---------|--------|
| `ability-arrays.fragment.json` | 2 (basic, heroic) | resolved |
| `races.fragment.json` | 8 races | human and goblin resolved |
| `classes.fragment.json` | 16 classes (5 NPC + 11 PC) × levels 1–20 | warrior levels 1–5, Sorcerer levels 1–6, and Druid level 3 resolved |
| `class-features.fragment.json` | 22 feat-slot, choice-slot, archetype, and automatic kinds | bounded warrior, Sorcerer, and Druid features plus the Elemental Ally archetype with its level-3 fire eidolon row resolved |
| `skills.fragment.json` | 35 Core skills | slice selections resolved |
| `feats.fragment.json` | 142 Core feats | slice selections resolved |
| `items.fragment.json` | 65 items | slice selections resolved |
| `gear-budgets.fragment.json` | 9 profiles (slow/medium/fast × low/normal/high) | medium/normal rows for production slices resolved |
| `spells.fragment.json` | 616 spells, 1431 membership rows | selected loadout resolved; remainder partial |

Each `*.fragment.json` file has one `section` and a list of `records`. Records
carry typed fields, a `catalogStatus`, and a source reference. The generated
catalog adds source file hashes and a deterministic catalog version.

Names, IDs, and current structural shapes follow `NPC_MODE_PLAN.md`
(hash-anchored as `source.npc-mode-plan`); no numeric rule value is stored from
memory. Money is integer copper pieces (`null` while prices are gaps). The Core
feat chapter is now anchored, but feat prerequisites stay `null` until curated
and checked against the typed prerequisite schema.

## Rebuilding

```
python3 tools/expand_npc_fragments.py      # one-shot structural expansion (idempotent for existing IDs)
python3 tools/parse_npc_sources.py --write # regenerate the spells fragment from the anchored extract
python3 tools/build_npc_catalog.py         # rebuild catalog/npc.json
python3 tools/build_npc_catalog.py --check # verify checked-in output matches
```

Note: `tools/expand_npc_fragments.py` runs at import time (it is a one-shot
script); do not import it from tests. Use the builder and parser tools instead.