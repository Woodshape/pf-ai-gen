# NPC Source-Gap Matrix (Phase 0)

Status legend:

- **anchored** — data is present in a hash-anchored local source; catalog rows may cite it.
- **extractable** — present in a local parent source and reduced to a hash-anchored fragment in `sources/npc/` (see `MANIFEST.json`).
- **GAP** — not present in any local source; must be classified as an explicit catalog gap and must not be implemented from memory.

Anchoring convention: catalog `sourceRef` entries may cite `sources/npc/` extract files
(by `file` + `sha256`, the mechanism `catalog.py` already validates) or parent `.txt`
files by `sourceId` + `txtLines`, exactly like the existing catalog. The parent files
`Pathfinder_RPG_Core_Rulebook.txt`, `Pathfinder Unchained.txt`, and `beastiary.txt` are
immutable; `catalog/catalog.json` is frozen.

| # | Source domain | Needed by (phase / task) | Local source | Status | Classification and consequence |
|---|---------------|--------------------------|--------------|--------|-------------------------------|
| 1 | NPC creation workflow, Before You Begin + Steps 1–7 (CRB pp. 448–454): basic/heroic ability arrays, `statblockUse` full/encounter, step definitions | Phase 2+ (3.a, 4.a) | None (local CRB PDF = 16-page spell excerpt) | **GAP** | Explicit catalog gap. Workflow field names in the plan remain product decisions; every numeric rule printed on these pages is unimplemented until an anchored extract exists. |
| 2 | Basic (13/12/11/10/9/8) and heroic (15/14/13/12/10/8) ability arrays | 2.a (3.a) | None | **GAP** | Explicit catalog gap. The vertical slice may only implement arrays once anchored; no memory-sourced rows. |
| 3 | Seven Core races: ability adjustments, size, speed, senses, traits, languages | 3.b | None | **GAP** | Explicit catalog gap; engine rejects races it cannot anchor. |
| 4 | Five NPC class tables (adept, aristocrat, commoner, expert, warrior) through level 20: BAB, saves, HD, skill ranks, features, choice slots, spells/day | 3.b, 4.a | None | **GAP** | Explicit catalog gap. Class level rows are table-driven only. |
| 5 | Eleven Core PC class tables (Table 3-x per class) through level 20 | 5.a | None | **GAP** | Explicit catalog gap. |
| 6 | Character advancement: +1 ability increase every four total levels, multiclass rules, XP/level relationship | 3.a, 4.a | None | **GAP** | Explicit catalog gap; the every-four-levels increase stays unimplemented until anchored. |
| 7 | Core skill list, class skills, Armor Check Penalty, max ranks = total HD | 3.a, 3.b | None | **GAP** | Explicit catalog gap. |
| 8 | Core feats, prerequisite prose, general feat progression, fighter/ranger/monk/wizard bonus feats | 3.b, 5.a | None | **GAP** | Explicit catalog gap. Typed prerequisite expressions may only encode forms after the feat chapter is anchored; unknown forms stay gaps. |
| 9 | Core weapons, armor, goods; magic item prices; magic weapon/armor instance pricing | 3.b, 5.a | None | **GAP** | Explicit catalog gap; no item price from memory. |
| 10 | Table 14-9 NPC gear budgets + basic/heroic lines + slow/medium/fast and low/normal/high fantasy profiles | 3.b, 4.a | None | **GAP** | Explicit catalog gap. No extrapolation outside anchored rows (plan: no invented tolerances). |
| 11 | Spell descriptions (levels, components, schools, DC inputs) | 5.a | CRB spell excerpt: only ~letter-A fragment, two-column reading order partially scrambled | **extractable** (partial) | `sources/npc/core-rulebook-extract.txt` pp. 11–16. Full descriptions remain a GAP; list membership alone is safe. |
| 12 | Class spell lists for NPC/PC casters (adept = cleric/druid lists) | 4.a, 5.a | CRB spell excerpt, complete class lists | **anchored** | `sources/npc/core-rulebook-extract.spell-lists.txt` (hash in `MANIFEST.json`). Bard 0–6, Cleric 0–9, Druid 0–9, Paladin 1–4, Ranger 1–4, Sorcerer/Wizard 0–9. |
| 13 | Simple Monster Creation chapter: array/graft semantics, NPC-likeness guidance, class-level−1 CR convention | Phase 1+ comparisons | `Pathfinder Unchained.txt` (full chapter, already anchored) | **anchored** | NPC-likeness guidance curated at `sources/npc/pathfinder-unchained.npc-likeness.txt` (parent lines 3555–3559). |
| 14 | Bestiary Table 1-1 (Monster Statistics by CR) and Table 1-2 (Hit Dice by CR) | Future `draft.compareBenchmarks` (plan §13) | `beastiary.txt` (already anchored) | **anchored** | Curated at `sources/npc/bestiary.table-1-1.txt` (parent lines 5–27). Comparison-only; never used to compute NPC statistics. |
| 15 | Printed "Kiramor, the Forest Shadow" example statblock | 6.a acceptance fixture | Only inside `NPC_MODE_PLAN.md` §12 | **GAP** | Treated as unanchored until a hash-anchored copy is added; worksheet records both oracles with provenance (see `docs/kiramor-worksheet.md`). |
| 16 | Errata status of printed examples (Kiramor saves/HP) | 6.a | None locally; no errata corpus | **GAP** | Cannot distinguish "unlisted resistance bonus" from "example error"; resolved by the dual-oracle Kiramor fixture, never by hidden bonuses. |

## Rulings binding downstream tasks

1. **No memory-sourced numbers.** Any catalog row lacking an anchored `sourceRef` is a
   catalog-gap error, matching how `catalog.py` already rejects entries without
   provenance.
2. **Gaps are explicit, not silent.** Where the plan's workflow requires data under GAP
   status, the adapter emits deterministic `catalog-data` issues naming the gap, as the
   Simple Monster engine already does (`class-graft.catalog-gap` precedent).
3. **Fragments are derived, parents are authoritative.** Files under `sources/npc/` are
   hash-anchored views of immutable parents; if a fragment and its parent ever
   disagree, the parent hash in `MANIFEST.json` decides.
4. **Phase 0 exit criterion** (plan §10) cannot be fully met locally: no numeric rule in
   the first vertical slice may depend solely on memory — therefore the first vertical
   slice is constrained to data that becomes anchored in tasks 2.b/3.b. Until CRB
   extracts for domains 1–10 are added to `sources/npc/`, those domains stay declared
   gaps and the vertical slice's numeric surface stays correspondingly small.