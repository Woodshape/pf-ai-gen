# NPC Source-Gap Matrix (Phase 0)

Status legend:

- **anchored** — data is present in a hash-anchored local source; catalog rows may cite it.
- **partial** — some required rules are anchored; the listed remainder stays unavailable locally.
- **GAP** — not present in a local source and must not be implemented from memory.

The official Archives of Nethys pages were snapshotted on 2026-09-02. Raw HTML
lives under `sources/reference/aonprd/`; deterministic, line-citable text lives
under `sources/npc/aonprd/`. Every file and upstream URL is recorded in
`sources/npc/MANIFEST.json`. Source availability does **not** make the current
catalog records resolved: a row remains `catalogStatus: "gap"` until a parser or
curated fragment gives it an anchored `sourceRef`.

| # | Source domain | Needed by | Local source | Status | Classification and consequence |
|---|---------------|-----------|--------------|--------|-------------------------------|
| 1 | NPC creation workflow, Steps 1–7 (CRB pp. 448–454) | Phase 2+ | `aonprd/creating-npcs.txt` lines 1–108 | **anchored** | The workflow, full/encounter statblock guidance, and quick-NPC procedure may now be implemented from this extract. |
| 2 | Basic and heroic arrays; preset arrays; racial adjustment table | Phase 2 | `aonprd/creating-npcs.txt` lines 9–33 | **anchored** | Arrays and Table 14-6/14-7 values may now replace their catalog gaps. |
| 3 | Seven Core races: adjustments, size, speed, senses, traits, languages | Phase 2+ | `aonprd/core-races.txt` lines 1–128 | **anchored** | Core race records may now be curated. |
| 4 | Five NPC classes through level 20 | Phase 2+ | `aonprd/npc-classes.txt` lines 1–172 | **anchored** | Adept, aristocrat, commoner, expert, and warrior HD, skills, BAB, saves, features, and spell rows may now be curated. |
| 5 | Eleven Core PC classes through level 20 | Heroic phase | Class overview only in `aonprd/character-classes.txt`; individual class pages are not archived | **GAP** | AoN has official pages for each class, so a full PDF is not required; snapshot those pages before hydrating heroic class rows. |
| 6 | Character advancement, feat/ability progression, multiclassing, favored class | Phase 2+ | `aonprd/character-classes.txt` lines 13–47 | **anchored** | Total-level advancement and multiclass arithmetic may now be implemented. |
| 7 | Skill ranks, class-skill bonus, rank cap, key ability, trained-only, ACP | Phase 2+ | `aonprd/skills.txt` lines 1–38; `aonprd/skill-descriptions.txt` lines 1–53; NPC class skills in `aonprd/npc-classes.txt` | **anchored** | Core skill records and skill-total calculation may now be curated. Individual skill-use/DC pages are outside the NPC statistic slice. |
| 8 | Core feats and prerequisites | Phase 2+ | `aonprd/feats.txt` lines 1–1062 | **partial** | General feat rules, table, and descriptions are anchored. PC-class bonus-feat schedules still depend on the unarchived individual class pages. |
| 9 | Weapons, armor, goods, services, and magic items | Phase 2+ | `aonprd/equipment.txt` lines 1–774 | **partial** | Mundane prices and statistics are anchored. Magic-item chapters and enhancement pricing remain GAP until separately snapshotted from AoN. |
| 10 | Table 14-9 NPC gear budgets, allocation categories, progression adjustments, and fantasy multipliers | Phase 2+ | `aonprd/creating-npcs.txt` lines 71–102 | **anchored** | Table 14-9 supplies basic/heroic level rows; the preceding prose explicitly defines slow/medium/fast level adjustment and low/normal/high fantasy scaling. The existing nine profile combinations are source-supported. |
| 11 | Spell descriptions (levels, components, schools, DC inputs, effects) | Heroic phase | Local CRB excerpt contains only an opening alphabetical fragment | **partial** | Spell-list membership is safe; full per-spell rules remain GAP until official AoN spell pages are snapshotted. |
| 12 | Class spell lists for NPC/PC casters | Basic/heroic phases | `sources/npc/core-rulebook-extract.spell-lists.txt` | **anchored** | Bard, cleric, druid, paladin, ranger, and sorcerer/wizard lists are locally anchored; the adept class page supplies its list relationship. |
| 13 | Core combat calculations | Phase 2+ | `aonprd/combat.txt` lines 1–617 | **anchored** | Attacks, AC, saves, initiative, CMB/CMD, and iterative attacks may now be implemented. |
| 14 | Simple Monster Creation and NPC-likeness guidance | Comparison only | `sources/npc/pathfinder-unchained.npc-likeness.txt` | **anchored** | Comparison-only; never mix Simple Monster arithmetic into NPC calculation. |
| 15 | Bestiary Table 1-1 benchmark | Future comparison | `sources/npc/bestiary.table-1-1.txt` | **anchored** | Comparison-only; never used to compute NPC statistics. |
| 16 | Kiramor worked example | Acceptance fixture | `aonprd/creating-npcs.txt` lines 109–133 | **anchored** | The printed values now have a primary-source anchor. Keep the computed and printed oracles distinct where they disagree. |
| 17 | Errata affecting Kiramor or this printing | Kiramor acceptance | No errata snapshot | **GAP** | Do not invent hidden bonuses or silently normalize printed discrepancies. Add matching official errata only if a discrepancy needs adjudication. |

## Rulings binding downstream tasks

1. **No memory-sourced numbers.** A catalog row is unresolved until it cites one
   of the anchored extracts with exact line provenance.
2. **Gaps are explicit, not silent.** The adapter emits deterministic
   `catalog-data` issues for unresolved rows.
3. **Snapshots, not live requests, are build inputs.** Runtime and catalog builds
   never depend on AoN availability or changing HTML.
4. **AoN is sufficient for the planned Core-only v1.** Remaining domains are
   available from official AoN pages and can be archived phase-by-phase; no full
   Core Rulebook PDF is currently required.
5. **Phase 2 is source-unblocked, not implementation-complete.** The next bounded
   task is the human warrior levels 1–5 catalog slice and one production-catalog
   lifecycle fixture.
