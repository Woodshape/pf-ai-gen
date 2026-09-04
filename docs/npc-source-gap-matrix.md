# NPC Source-Gap Matrix (Phase 0)

Status legend:

- **anchored** — data is present in a hash-anchored local source; catalog rows may cite it.
- **partial** — some required rules are anchored; the listed remainder stays unavailable locally.
- **GAP** — not present in a local source and must not be implemented from memory.

The Archives of Nethys pages were snapshotted on 2026-09-02. New goblin, Sorcerer,
spell, skill, wand, and cloak sources use current `aonprd.com` pages. Raw HTML lives under `sources/reference/aonprd/`; deterministic, line-citable text lives
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
| 5 | Eleven Core PC classes through level 20 | Heroic phase | Current `aonprd/{sorcerer,druid,ranger,rogue}.txt` pages are archived; the other individual class pages are not | **partial** | Sorcerer levels 1–6, Druid level 3, Ranger levels 1–4, and Rogue levels 1–2 are hydrated for bounded slices. Other PC classes and levels remain gaps. |
| 6 | Character advancement, feat/ability progression, multiclassing, favored class | Phase 2+ | `aonprd/character-classes.txt` lines 13–47 | **anchored** | Total-level advancement and multiclass arithmetic may now be implemented. |
| 7 | Skill ranks, class-skill bonus, rank cap, key ability, trained-only, ACP | Phase 2+ | `aonprd/skills.txt` lines 1–38; `aonprd/skill-descriptions.txt` lines 1–53; NPC class skills in `aonprd/npc-classes.txt` | **anchored** | Core skill records and skill-total calculation may now be curated. Individual skill-use/DC pages are outside the NPC statistic slice. |
| 8 | Core feats and prerequisites | Phase 2+ | `aonprd/feats.txt` lines 1–1062; bounded grants in archived class pages and `creating-npcs.txt` | **partial** | General feat rules, table, and descriptions are anchored. Kiramor's Deadly Aim, Point-Blank Shot, Rapid Shot, Endurance, and Weapon Finesse are resolved; unarchived class bonus-feat schedules remain gaps. |
| 9 | Weapons, armor, goods, services, and magic items | Phase 2+ | Mundane equipment plus current `aonprd/{wands,cloak-of-resistance,magic-weapons,magic-armor,potions}.txt` | **partial** | Existing bounded gear and Kiramor's +1 longbow, masterwork rapier, +1 studded leather, arrows, and two potions are hydrated. Other magic items remain gaps. |
| 10 | Table 14-9 NPC gear budgets, allocation categories, progression adjustments, and fantasy multipliers | Phase 2+ | `aonprd/creating-npcs.txt` lines 71–102 | **anchored** | Table 14-9 supplies basic/heroic level rows; the preceding prose explicitly defines slow/medium/fast level adjustment and low/normal/high fantasy scaling. The existing nine profile combinations are source-supported. |
| 11 | Spell descriptions (levels, components, schools, DC inputs, effects) | Heroic phase | Current individual AoN pages for the bounded goblin Sorcerer and Druid loadouts | **partial** | Twenty-six selected spells through 3rd level are hydrated; all other spell descriptions remain gaps. |
| 12 | Class spell lists for NPC/PC casters | Basic/heroic phases | `sources/npc/core-rulebook-extract.spell-lists.txt` | **anchored** | Bard, cleric, druid, paladin, ranger, and sorcerer/wizard lists are locally anchored; the adept class page supplies its list relationship. |
| 13 | Core combat calculations and classed-NPC CR | Phase 2+ | `aonprd/combat.txt` lines 1–617; `aonprd/designing-encounters.txt` line 1 | **anchored** | Attacks, AC, saves, initiative, CMB/CMD, and PC-class NPC CR (class levels −1) may now be implemented. |
| 14 | Simple Monster Creation and NPC-likeness guidance | Comparison only | `sources/npc/pathfinder-unchained.npc-likeness.txt` | **anchored** | Comparison-only; never mix Simple Monster arithmetic into NPC calculation. |
| 15 | Bestiary Table 1-1 benchmark | Future comparison | `sources/npc/bestiary.table-1-1.txt` | **anchored** | Comparison-only; never used to compute NPC statistics. |
| 16 | Kiramor worked example | Acceptance fixture | `aonprd/creating-npcs.txt` lines 106–133 | **anchored** | Narrative choices and every printed statblock field have primary-source anchors. Keep computed and printed oracles distinct where they disagree. |
| 17 | Errata affecting Kiramor or this printing | Kiramor acceptance | No errata snapshot | **GAP** | Do not invent hidden bonuses or silently normalize printed discrepancies. Add matching official errata only if a discrepancy needs adjudication. |
| 18 | Elemental Ally druid archetype (Monster Summoner's Handbook pg. 16) | Bounded Druid 3 archetype slice | `aonprd/elemental-ally.txt` lines 1–16 | **anchored** | The archetype exists on official AoN and is hash-anchored. It replaces Nature Bond and Wild Shape (`:7`), Wild Empathy via Elemental Empathy (`:8-11`), and Resist Nature's Lure at 4th (`:13`). Druid 3 resolves Nature Bond and Wild Empathy only; Wild Shape and Resist Nature's Lure are level-4 replacements and stay unresolved. Other archetypes remain gaps. |
| 19 | Elemental eidolon statistics cited by Elemental Ally (Pathfinder Unchained pg. 33) | Level-3 fire elemental eidolon row | `aonprd/eidolon-unchained.txt` lines 1–46; `aonprd/eidolon-uc-subtypes.txt` lines 1–12; `aonprd/eidolon-base-forms.txt` lines 1–3 | **anchored** | Table 1–6 row 3rd, the Elemental subtype (PFU pg. 33), and the Quadruped base form are anchored. Exactly the level-3 fire row with the pinned Quadruped form is resolved (`docs/elemental-ally-source-assessment.md`); other levels, elements, and base forms remain gaps. Eidolon skill ranks (12) and feats (2) are sourced budgets without pinned assignments. |

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
5. **Production remains deliberately bounded.** The source-resolved slices are
   human warrior levels 1–5, the elemental-fire goblin Sorcerer at levels 5–6, the
   two level-3 goblin Druid variants, the linked level-3 fire elemental eidolon, and
   elf Ranger levels 1–4 followed by Rogue levels 1–2 for the Kiramor slice;
   broader races, classes, spells, magic items, and eidolon levels remain explicit gaps.
