# Backlog

Completed milestone (1–3): shared skill rules (including precise ranks), mechanically relevant vs descriptive equipment, metadata-based spell selection, and a valid [unbuffed Goblin Warchanter](docs/goblin-warchanter.md). Base NPC CR and concentration are derived as well.

## Next required milestone: NPC feat coverage

Support every identifiable Core feat recommended by [Creating NPCs, Step 4](https://aonprd.com/Rules.aspx?ID=357): **99 distinct feats**, including the Core armor-proficiency, item-creation and metamagic groups. See the [complete feat-by-feat audit](docs/npc-feat-support-audit.md).

- Distinguish intentional GM-facing support, calculated base/conditional modifiers and optional combat routines. Empty effects must not hide missing calculations.
- Add 17 missing records and resolve 74 placeholders, with prerequisites and required choices. Include transitive prerequisites outside the recommendation list; this is a minimum inventory, not an allowlist.
- Fix Weapon Finesse's shield ACP and Rapid Shot's missing iteratives. Share attack/handedness/damage calculations across combat options; do not apply optional modes or temporary buffs to base statistics.
- Wire existing prerequisite context and provide needed school/metamagic metadata without implementing complete spell effects. Address qualifying class/feature/level-data gaps, including the higher-level gear-row failure recorded in the audit.

After the feat milestone, remaining priorities stay in order:

4. **Broaden class-feature choices and effects.** Replace the sparse fire/orc/forest/archery/Bleeding Attack coverage with source-backed alternatives. Distinguish selection metadata from implemented mechanics. Temporary buffs remain outside base statistics.
5. **Derive companion progressions.** Replace the level-3 Elemental Ally snapshot with levelled companion rules, including every lower level. Do not add more character-specific snapshots.
6. **Separate spellcasting by class.** Add independent class-keyed loadouts, spell slots, caster levels, casting abilities and DCs for multiclass casters; preserve existing single-caster inputs.
7. **Implement item customization.** Derive masterwork/enhancement/property/charge effects and pricing from base items. Until then, use existing mechanical variants or descriptive equipment with no automatic effects.

Acceptance for each: public Engine checks, source/policy provenance for derived rules, and consistent choice discovery, UI, persistence and exports. Never use named NPCs or race/class combinations as runtime allowlists.
