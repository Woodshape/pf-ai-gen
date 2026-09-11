# Goblin Warchanter

> **Draft — not engine-validated.** This review sheet preserves the supplied printed statistics, including the flagged discrepancies below. It is a manual Markdown rendering, not a finalized engine export.

**CR** 1/2 · **XP** 200  
Goblin bard 1  
NE Small humanoid (goblinoid)

**Init** +4; **Senses** darkvision 60 ft.; **Perception** +5

## Defense

**AC** 18, touch 15, flat-footed 14 (+3 armor, +4 Dex, +1 size)  
**hp** 9 (1d8+1)  
**Fort** +1, **Ref** +6, **Will** +3; +1 vs. fear and charm¹

## Offense

**Speed** 30 ft.  
**Melee** dogslicer +1 (1d4/19–20) or whip +1 (1d2 nonlethal)¹  
**Ranged** shortbow +6 (1d4+1/×3)¹ ²

**Special Attacks** bardic performance 5 rounds/day (countersong, distraction, fascinate, inspire courage +1)

### Spells Known

**CL** 1st; **concentration** +2

- **1st (2/day total):** cure light wounds, hideous laughter (DC 12)
- **0 (at will):** daze (DC 11), ghost sound (DC 11), mage hand, message

## Tactics

**During Combat** The warchanter continues her bardic performance during combat, using her whip to try to trip PCs. She casts hideous laughter on any PC who seems to be particularly dangerous and cure light wounds on herself after she is first wounded.

**Morale** The warchanter fights to the death.

## Statistics

| Str | Dex | Con | Int | Wis | Cha |
|---:|---:|---:|---:|---:|---:|
| 8 | 18 | 13 | 8 | 12 | 13 |

**Base Atk** +0; **CMB** −2; **CMD** 12  
**Feats** Martial Weapon Proficiency (dogslicer)  
**Skills** Acrobatics +7, Linguistics +3, Perception +5, Perform (sing) +5, Ride +8³, Stealth +15  
**Languages** Common, Goblin  
**SQ** bardic knowledge +1

**Combat Gear** potion of cure light wounds  
**Other Gear** studded leather, dogslicer, shortbow with 20 arrows, whip, 20 gp

## Review Flags

1. **Active inspire courage assumed:** the printed attack bonuses, melee damage, and +1 saves against fear/charm fit an already-active performance. Without it, melee attacks are +0 with 1d4−1 / 1d2−1 damage; shortbow is +5 with 1d4−1 damage. The conditional save bonus disappears. Printed CMB −2 is the base value, before applicable performance bonuses.
2. **Shortbow damage discrepancy:** even with inspire courage, damage should be **1d4**, not 1d4+1, because Strength 8 imposes −1 damage.
3. **Ride discrepancy:** with studded leather's −1 armor check penalty, unranked Ride should be **+7**. Printed +8 is the unarmored value.

## Conversion Status

- **Engine result after the composition fix:** invalid (`npc.catalog-gap`); goblin bard 1 is now supported as a combination. The remaining blockers are specific unresolved feat, equipment, skill, and spell records.
- **Not mechanically represented in full:** dogslicer and its feat target, several unresolved gear/skill/spell records, Perform specialty, Common learned through Linguistics, unranked Ride, currency, and active-performance effects.
- **Additional engine issue:** the current single-class skill calculation omits the Small-size +4 Stealth bonus.
- **Ability generation:** heroic array before racial modifiers—Str 10, Dex 14, Con 13, Int 8, Wis 12, Cha 15. This reproduces the printed scores exactly.
- Dogslicer and other unrepresentable details appear on this review sheet because they are preserved from the source, **not because the engine successfully derived them**.

**Saved draft ID:** `draft-f9702971f85a47c7b46a4bb849b5392d`  
**Portable input:** `docs/goblin-warchanter-draft.json`  
**Full assessment:** `docs/goblin-warchanter-assessment.md`
