# Kiramor Rules-versus-Print Worksheet (Phase 4)

Kiramor, the Forest Shadow, an elf ranger 4/rogue 2, is the bounded acceptance
fixture from `NPC_MODE_PLAN.md` §12. This worksheet keeps the engine's
source-derived result separate from the Core Rulebook's printed example. Printed
values are never introduced into the calculation as hidden bonuses.

## 1. Provenance of the two oracles

| Oracle | Local carrier | Anchor status |
|--------|---------------|---------------|
| Printed example | `sources/npc/aonprd/creating-npcs.txt` lines 106–133 | **anchored** as `source.aon-creating-npcs`; the narrative is line 108 and statblock fields are lines 109–133. |
| Rules-derived result | The anchored NPC workflow, elf, ranger, rogue, equipment, feat, skill, spell, and combat extracts | **anchored for this bounded slice**. Ranger levels 1–4 and rogue levels 1–2 are the only newly supported class rows. |
| Errata adjudication | No local official errata snapshot | **GAP**. Printed discrepancies remain classified rather than normalized. |

## 2. Rules-derived computation contract

### Ability scores

Table 14-6's heroic ranged row is Str 13, Dex 15, Con 14, Int 12, Wis 10,
Cha 8 (`creating-npcs.txt` lines 19–24). Apply the elf adjustments from Table
14-7, then the level-4 increase to Dexterity:

| Ability | Heroic ranged | Elf | Level increase | Result |
|---------|---------------|-----|----------------|--------|
| Strength | 13 | +0 | — | **13** |
| Dexterity | 15 | +2 | +1 | **18** |
| Constitution | 14 | −2 | — | **12** |
| Intelligence | 12 | +2 | — | **14** |
| Wisdom | 10 | +0 | — | **10** |
| Charisma | 8 | +0 | — | **8** |

These values agree with the printed statblock at `creating-npcs.txt` line 125.
The earlier worksheet's Int 12/Wis 12 premise transcribed the ranged row
incorrectly and is superseded.

### BAB and saves

| Component | BAB | Fort | Ref | Will |
|-----------|-----|------|-----|------|
| ranger 4 | +4 | +4 | +4 | +1 |
| rogue 2 | +1 | +0 | +3 | +0 |
| Class-row sum | **+5** | **+4** | **+7** | **+1** |
| Ability modifier | — | Con +1 | Dex +4 | Wis +0 |
| **Rules-derived total** | **+5** | **+5** | **+11** | **+1** |

The class rows are `ranger.txt` line 17 and `rogue.txt` line 14. Multiclass
BAB and save bonuses add under `character-classes.txt` lines 42–44.

### Hit points

The bounded mission contract treats the maximum first PC-class Hit Die as a
fixed die-size term, averages later Hit Dice with Constitution, and rounds down
once. This preserves the brief's established Kiramor expectation without
changing existing single-class slices.

```text
maximum first ranger Hit Die term = 10
remaining ranger Hit Dice = 3 × (5.5 + 1)
rogue Hit Dice = 2 × (4.5 + 1)
floor(10 + 19.5 + 11) = 40
```

**Rules-derived HP: 40; Hit Dice expression: `4d10+2d8+6`.** The printed 39
remains a visible −1 delta. Per-die flooring would produce 39, but no archived
text states that the example uses that convention, and changing the established
engine convention would alter existing NPC slices.

### Two-class simplified skills

Kiramor's Intelligence 14 gives a +2 modifier. Ranger therefore supplies eight
selections at six ranks each. Rogue's base budget exceeds ranger's by two, so it
supplies two new selections at two ranks each (`creating-npcs.txt` lines 38–42
and the worked narrative at line 108).

| Group | Selections | Ranks | Derived totals |
|-------|------------|-------|----------------|
| Ranger | Climb, Heal, Intimidate, Knowledge (geography), Knowledge (nature), Perception, Stealth, Survival | 6 each | +10, +9, +8, +11, +11, +11, +13, +9 |
| Rogue | Escape Artist, Swim | 2 each | +9, +6 |

The first eight are ranger class skills. The final two are new rogue class
skills. Studded leather +1 has armor check penalty 0, so it does not change
Climb, Escape Artist, Stealth, or Swim.

The printed list substitutes Acrobatics +13 for Intimidate +8. Acrobatics is not
a ranger class skill, and two rogue ranks would produce +9 rather than +13.
That allocation is classified as a printed-example inconsistency, not copied
into the canonical fixture.

### Ranger spell access

Ranger 4 has a `0` in the 1st-level spells-per-day column (`ranger.txt` line 17),
so it receives only a Wisdom bonus slot. Wisdom 10 receives no 1st-level bonus
spell (`getting-started.txt` lines 92–100) and cannot prepare or cast a
1st-level spell because the minimum is Wisdom 11 (`ranger.txt` lines 96–99).
The fixture therefore uses `spellLoadout.prepared: {}`. Ranger caster level is
`4 − 3 = 1` (`ranger.txt` line 100). No prepared spell or DC is synthesized.

### Gear and unconditional attacks

The fixture selects the printed +1 longbow, masterwork rapier, studded leather
+1, 40 arrows, two potions, and no unpriced generic gear. Catalog price is
457,200 cp against the heroic level-6 budget of 465,000 cp, so the existing
`npc.gear-budget-approximate` warning is expected. The canonical unconditional
attacks are masterwork rapier +10, +1 longbow +10, and the Rapid
Shot full attack +8/+8. Favored enemy, favored terrain, Point-Blank Shot, and
Deadly Aim are conditional or voluntary and do not alter those totals.

## 3. Delta classification

| Field | Rules-derived | Printed | Classification |
|-------|---------------|---------|----------------|
| Abilities | 13/18/12/14/10/8 | 13/18/12/14/10/8 | Agreement after correcting the Table 14-6 transcription. |
| Fortitude / Reflex / Will | +5 / +11 / +1 | +6 / +12 / +2 | Uniform printed +1. An unlisted resistance bonus and printed arithmetic error remain hypotheses; neither is absorbed without an errata source. |
| HP | 40 | 39 | Printed −1. The bounded first-term convention is explicit; standard per-die flooring is a hypothesis for how print reached 39, not an engine rule. |
| Skill allocation | Eight ranger skills at 6 ranks plus Escape Artist and Swim at 2 ranks | Acrobatics +13 appears instead of Intimidate | Printed allocation does not follow the anchored two-class procedure. |
| Languages | Common, Elven in the current engine slice | Common, Elven, Orc, Sylvan | Orc and Sylvan are source-consistent Intelligence bonus-language choices, but language choice is not modeled in this slice. |
| Hunter's bond | companion-bond | nature bond (wolf) | Deliberate bounded-slice selection difference. Wolf companion statistics remain outside the resolved slice. |
| Initiative | +4 unconditional | +4, +6 in forests | Agreement. The forest value is conditional feature text, not a global bonus. |
| Ranger spells | CL 1, no prepared spells | No spells printed | Source-consistent omission at Wisdom 10. |

The exact printed values and field-level line anchors live in
`tests/fixtures/kiramor-printed.json`. Its `classifiedDeltas` array is the
machine-readable audit contract.

## 4. Fixture contract

`tests/fixtures/kiramor-npc.json` contains only selections:

1. Elf with ordered ranger 4 then rogue 2 progression.
2. Heroic ranged preset and the level-4 Dexterity increase.
3. Eight ranger skills followed positionally by two new rogue skills.
4. Point-Blank Shot, Deadly Aim, and Weapon Finesse in general feat slots.
5. Humanoid (orc), archery, forest, companion-bond, and bleeding-attack class choices.
6. An empty prepared spell map because Wisdom 10 provides no usable slot.
7. Medium/normal heroic gear totaling 457,200 cp.

`tests/fixtures/kiramor-printed.json` contains the independent printed oracle,
source agreement records, and classified deltas. Integration tests must assert
the canonical result and printed result separately.

## 5. Acceptance invariants

1. Canonical abilities are Str 13, Dex 18, Con 12, Int 14, Wis 10, Cha 8.
2. Canonical BAB/saves/HP are +5, +5/+11/+1, and 40.
3. The eight-plus-two skill contract and empty ranger preparation are enforced.
4. Printed 39 hp and +6/+12/+2 saves remain fixture data, never hidden effects.
5. Conditional bonuses do not enter unconditional totals.
6. `catalog/catalog.json`, Simple Monster implementation/tests, and
   `NPC_MODE_PLAN.md` remain unchanged.
