# Backlog

Completed milestone (1–3): shared skill rules (including precise ranks), mechanically relevant vs descriptive equipment, metadata-based spell selection, and a valid [unbuffed Goblin Warchanter](docs/goblin-warchanter.md). Base NPC CR and concentration are derived as well.

## Current milestone: NPC feat coverage (in progress)

Support every identifiable Core feat recommended by [Creating NPCs, Step 4](https://aonprd.com/Rules.aspx?ID=357): **99 distinct feats**, including the Core armor-proficiency, item-creation and metamagic groups. See the [complete feat-by-feat audit](docs/npc-feat-support-audit.md).

- Distinguish intentional GM-facing support, calculated base/conditional modifiers and optional combat routines. Empty effects must not hide missing calculations.
- Implemented: all 99 source-backed records plus three transitive prerequisites; explicit treatment/support metadata, acquisition-level prerequisite context, generic feat choices, base and conditional modifiers, school-specific DCs, metamagic ownership metadata, UI and exports.
- Implemented: Weapon Finesse shield ACP, iteratives, shared optional combat routines and explicit weapon-pair/feat combinations (`combatOptions`), Warrior levels 1–20, exact gear rows through level 20, and Druid level 4. Optional modes never change base statistics.
- Still required: finish the 14 `selection-only` calculations and virtual Weapon Focus targets; implement selected metamagic spell variants; complete qualifying wizard/cleric/monk/fighter/paladin data and class grants/waivers. Source resolution alone is not mechanical completion. The [audit's implementation status](docs/npc-feat-support-audit.md#implementation-status) lists the remaining scope.

After the feat milestone, remaining priorities stay in order:

4. **Broaden class-feature choices and effects.** Replace the sparse fire/orc/forest/archery/Bleeding Attack coverage with source-backed alternatives. Distinguish selection metadata from implemented mechanics. Temporary buffs remain outside base statistics.
5. **Derive companion progressions.** Replace the level-3 Elemental Ally snapshot with levelled companion rules, including every lower level. Do not add more character-specific snapshots.
6. **Separate spellcasting by class.** Add independent class-keyed loadouts, spell slots, caster levels, casting abilities and DCs for multiclass casters; preserve existing single-caster inputs.
7. **Implement item customization.** Derive masterwork/enhancement/property/charge effects and pricing from base items. Until then, use existing mechanical variants or descriptive equipment with no automatic effects.

Acceptance for each: public Engine checks, source/policy provenance for derived rules, and consistent choice discovery, UI, persistence and exports. Never use named NPCs or race/class combinations as runtime allowlists.
