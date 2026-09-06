# NPC composition audit

> **Follow-up completed:** precise/shared skill calculations, Small size bonuses, Linguistics/specialties/untrained displays, metadata-only spell selection, weapon-targeted proficiency, bard knowledge/performance rounds and descriptive equipment now support the [valid unbuffed Warchanter](goblin-warchanter.md). Fractional NPC CRs and concentration are also derived. Items 4, 7 and 8 below, plus the proficiency/knowledge/rounds portions of item 6, describe historical gaps now addressed. Temporary buffs remain excluded by policy. Remaining priorities 4–7 are in [BACKLOG.md](../BACKLOG.md); the original audit/check counts below are retained as history.

## Fixed in this change

The NPC evaluator no longer contains an approved race/class/level list or a named-character execution path. Race rules and each selected class's own level rows are evaluated independently. Missing rules are reported against the missing selection/data, rather than declaring the combination unsupported.

| Previous restriction or defect | Replacement |
|---|---|
| Human warrior 1–5, goblin sorcerer 5–6, goblin druid 3, halfling bard 1–3 only | Any resolved race can use any resolved class progression. Regression coverage crosses all four resolved races with all 23 resolved single-class levels: **92 builds**. |
| Druid 3 resolved while druid 1–2 were gaps | Levels 1–2 now use the already-archived Druid table. Features are granted at their actual acquisition levels rather than dumped into level 3. Catalog validation prevents holes below any resolved level. |
| `_is_kiramor_progression`, elf-only Ranger/Rogue order and ranges, separate `_evaluate_kiramor` | Removed. One evaluator sums class BAB/saves and uses each class's own feature/spellcasting level. Shared simplified skills start with the lowest skill-budget class, independent of progression order. |
| Elemental Ally restricted to goblin druid 3 | Removed the invented race/level gate. The actual archetype/class relationship and availability of the selected-level companion data are still checked. Halfling druid 3 with the archetype is tested. |
| Divine ability preset restricted to druids; ranged preset absent from ordinary choices | Presets come from the selected ability array, not the NPC's class. Backend and browser use the available preset data. Missing presets produce a specific error, not a KeyError. |
| Separate `allowedFeatIds` list excluding general selection of Rapid Shot | Removed the catalog allowlist and its validation gate. Resolved feats use their actual prerequisites. General Rapid Shot on a bard is tested. |
| Feat BAB prerequisites checked against character level | Uses the sum of actual class BAB. Bard 1 cannot take Deadly Aim; bard 2 can when its other prerequisites hold. |
| Fire bloodline/domain forced by literal checks in code | Selection and evaluation use the available catalog options. Missing alternatives are catalog gaps, not assertions that Pathfinder requires fire. The catalog currently still contains only those resolved alternatives. |
| Browser assumed the first class was the caster and only displayed named caster types | Uses engine-owned spell requirements and casting-class metadata. Ranger preparation is no longer absent merely because the UI lacked a ranger branch. |
| Ranger prepared spell duplicates prohibited | Removed that invented restriction. Preparing the same spell more than once is legal. |
| Druid 1–2 conversion metadata included second-level summon options | Conversion slots are limited to spell levels actually granted by the selected Druid row. |

### Arithmetic exposed by deleting the duplicate evaluator

> **Historical calculations below:** the user subsequently approved [a different HP policy](npc-hit-points-policy.md): round each basic-NPC die down; maximize the first heroic-NPC die and round later dice up. Current fixture HP: bard 2 **15**, Cinder **32**, druid 3 **24**, Kiramor **44**. The previous 41 was not established as an official correction to the printed Kiramor.

- The single-class PC-class HP formula previously counted Constitution **twice on later levels**.
- The Kiramor-only formula omitted Constitution on the **first** Hit Die.
- The shared formula applies Constitution once per Hit Die, maximizes the first die when the first class is a PC class, averages later dice, and floors the total once. Sources: `sources/npc/aonprd/getting-started.txt:30`, `creating-npcs.txt:105` and the existing average-HP rule.
- Consequently the existing fixture results change: bard 2 **15 → 14 HP**, Cinder **34 → 29 HP**, druid 3 **27 → 23 HP**, Kiramor **40 → 41 HP**. The printed Kiramor reference remains **39**; printed source statistics are not overwritten to match the engine.
- Class-feature attack rolls now use total BAB in multiclass builds, while feature damage/uses retain the granting class's level.
- Ability previews now include selected level increases, so spell-slot previews do not ignore a casting-ability increase.

## Other examples to discuss next

These were found during the audit. They are **not claimed fixed** by deleting a gate.

1. **Companion data is a curated snapshot, not a levelled companion builder.** Elemental Ally has one `linkedCreatureRow` at level 3. Lower druid levels now work, but lower-level Elemental Ally companions still need derivation from the actual companion progression. This is the same example-driven design problem in the data model, not a legitimate race restriction.
2. **Feature choices are still sparsely catalogued.** Only elemental-fire bloodline, Fire Nature Bond, orc favored enemy, forest favored terrain, archery/Rapid Shot, and Bleeding Attack are resolved choices. Code no longer requires those specific examples, but other choices need source-backed records/effects. Simply relabelling them resolved would invent coverage.
3. **Multiple independent spellcasting classes need class-keyed spell loadouts.** The current flat loadout cannot distinguish a bard's known spells from a sorcerer's. Such a build now reports `npc.spell-loadout-ambiguous` with its caster IDs instead of an approved-combination error. One caster plus other classes is supported in either order.
4. **Precise skills are advertised in the UI but not evaluated.** The engine currently implements simplified skills. The remaining `npc.skill-method-unimplemented` error identifies that real implementation gap; deleting it would silently ignore purchased ranks.
5. **Item customization is accepted structurally but lacks evaluation.** Explicit enchantment/masterwork/charge options are still rejected with `npc.item-customization-unimplemented`. Existing catalogued item variants work. This needs actual price/effect/charge handling, not an unconditional pass.
6. **Some features are names rather than complete mechanics.** Bardic performance state, rounds/day, bardic knowledge, proficiency checks, and several conditional feat effects are not fully derived. A resolved feature label should not be mistaken for full mechanical coverage.
7. **Skills and languages remain incomplete.** Small-size Stealth handling is inconsistent between race records, unranked Ride is not emitted, and Linguistics does not grant its selected language. These still affect an exact Warchanter conversion.
8. **The Warchanter's equipment/spell catalog gaps remain.** Dogslicer has no item record; its proficiency target has no feat-choice representation; shortbow, whip, potion, Acrobatics, Linguistics, daze, ghost sound, and hideous laughter still need complete NPC records. The race/class combination itself is no longer the blocker.

## Checks and compatibility

Verification: **241 Python tests run, 240 passed, 1 skipped**; all 5 AI/schema tests passed; TypeScript typecheck, frontend build, catalog freshness check, and `git diff --check` passed.

- `tests/test_npc_composition.py`: 92 race/class/level combinations; goblin bard; mixed PC/NPC classes in both orders; archetype cross-race composition; feat prerequisites/general Rapid Shot; catalog continuity.
- Existing Kiramor tests now allow reversed class order and keep the printed reference separate from the corrected derived result.
- No Simple Monster construction rules were changed.
- The NPC catalog version changes. Existing saved drafts and finished snapshots are not rewritten. **Duplicate** an older draft/finished NPC to re-evaluate its selections against the current catalog; retain the old snapshot for comparison. Restart a running Python server to load the new evaluator/catalog.

Reproduce:

```bash
python3 -m unittest discover -s tests
python3 tools/build_npc_catalog.py --check
npm run typecheck
npm run build
```
