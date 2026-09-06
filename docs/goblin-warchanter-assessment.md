# Goblin Warchanter — NPC conversion assessment

> **Update after the composition fix:** the goblin/bard combination gate described below has been removed. The current draft now reports individual `npc.catalog-gap` findings, not `npc.slice-unsupported`. See [current evaluation](goblin-warchanter-current-evaluation.json) and [composition audit](npc-composition-audit.md). The original assessment and creation response below are retained as historical evidence; the printed-stat analysis remains applicable.

## Verdict

**Rules-wise: almost reproducible, but not literally as printed. Engine-wise: currently blocked.**

Created an NPC-mode draft in `.monster-builder` named **Goblin Warchanter**, ID `draft-f9702971f85a47c7b46a4bb849b5392d`. Its status is **invalid**, not finalized. The portable candidate is [goblin-warchanter-draft.json](goblin-warchanter-draft.json); the actual public `Engine.execute(draft.create)` response is [goblin-warchanter-evaluation.json](goblin-warchanter-evaluation.json).

The engine returns `npc.slice-unsupported`: its bard production slice permits **halfling bards 1–3**, not goblin bards. It returns before evaluating individual selections, so the additional gaps below come from inspecting the catalog and evaluator, not additional reported validation errors. No engine rules were changed or bypassed. The candidate preserves unrepresentable choices in explicitly non-mechanical source notes; it is not a lossless executable conversion.

Source: the user's Goblin Warchanter photograph (Goblin bard 1; Bestiary p. 156 reference). Adventure title/page is not visible and is not inferred.

## Printed stat block

**Goblin Warchanter — CR 1/2; XP 200**  
Goblin bard 1; NE Small humanoid (goblinoid)

**Init** +4; **Senses** darkvision 60 ft.; Perception +5  
**AC** 18, touch 15, flat-footed 14 (+3 armor, +4 Dex, +1 size)  
**hp** 9 (1d8+1)  
**Fort** +1, **Ref** +6, **Will** +3; +1 vs. fear and charm  
**Speed** 30 ft.

**Melee** dogslicer +1 (1d4/19–20) or whip +1 (1d2 nonlethal)  
**Ranged** shortbow +6 (1d4+1/×3)  
**Special Attacks** bardic performance 5 rounds/day (countersong, distraction, fascinate, inspire courage +1)

**Spells Known** (CL 1st; concentration +2):
- 1st (2/day): cure light wounds, hideous laughter (DC 12).
- 0 (at will): daze (DC 11), ghost sound (DC 11), mage hand, message.

**Str** 8, **Dex** 18, **Con** 13, **Int** 8, **Wis** 12, **Cha** 13  
**BAB** +0; **CMB** −2; **CMD** 12  
**Feat** Martial Weapon Proficiency (dogslicer)  
**Skills** Acrobatics +7, Linguistics +3, Perception +5, Perform (sing) +5, Ride +8, Stealth +15  
**Languages** Common, Goblin  
**SQ** bardic knowledge +1  
**Gear** potion of cure light wounds; studded leather, dogslicer, shortbow with 20 arrows, whip, 20 gp.

**Tactics:** continue performance, trip PCs with the whip, cast hideous laughter on a dangerous PC, and heal herself after first being wounded. Fights to the death.

## Printed inconsistencies and conditional values

| Field | Assessment |
|---|---|
| Attack bonuses and melee damage | Consistent **with inspire courage already active**. Unbuffed dogslicer/whip attack = BAB 0 −1 Str +1 size = **+0**; damage is **1d4−1 / 1d2−1**. Inspire courage adds +1 attack and weapon damage, producing the printed melee line. Unbuffed shortbow attack is **+5**, inspired **+6**. The tactics strongly support this interpretation, but the visible block does not label the attack lines as buffed. |
| Shortbow damage **1d4+1** | **Inconsistent even while inspired.** A non-composite bow applies a negative Strength modifier. Str 8 gives −1 damage, cancelling inspire courage's +1. Correct inspired damage is **1d4/×3**; unbuffed **1d4−1/×3**. No listed equipment or feat supplies another +1. |
| +1 saves vs. fear/charm | Consistent with active inspire courage; **not a permanent goblin/bard-1 save bonus**. Keep base saves +1/+6/+3 and label the conditional bonus. Well-versed is a level-2 feature and is not its explanation. |
| Ride **+8** | **Apparently omits studded leather's −1 armor check penalty.** Unranked Ride is +4 Dex +4 racial −1 armor = **+7** while wearing the listed armor. +8 is the unarmored value. The other printed armor-sensitive skills already include that penalty. |
| CMB −2 | Correct as the **base** maneuver bonus. If using the inspired attack state for a whip trip, apply the relevant attack bonus from inspire courage as well; do not silently treat the printed base CMB as an all-effects-included combat value. |

These are arithmetic/state issues, not an inherently illegal goblin bard concept. A literal unchanged conversion needs documented overrides for the bow damage and armored Ride, rather than pretending those totals follow from the listed build.

## What fits ordinary NPC rules

- **Heroic array fits exactly.** Assign pre-racial Str 10, Dex 14, Con 13, Int 8, Wis 12, Cha 15 (the heroic 15/14/13/12/10/8 array). Goblin −2 Str, +4 Dex, −2 Cha produces all six printed scores. No custom scores or level increases are necessary.
- **CR 1/2 / XP 200**, level 1, Small size, humanoid (goblinoid), speed 30 and darkvision 60 are consistent with this classed NPC.
- **AC**: 10 +3 armor +4 Dex +1 size = 18; touch 15; flat-footed 14. **hp**: maximum first d8 +1 Con = 9. **Saves**: bard bases 0/2/2 plus Con/Dex/Wis = 1/6/3. **Initiative** +4.
- **CMB**: 0 −1 Str −1 size = −2. **CMD**: 10 +0 −1 Str +4 Dex −1 size = 12.
- **Five skill ranks**, not six: 6 −1 Int. One each in Acrobatics, Linguistics, Perception, Perform (sing), and Stealth yields the printed trained skills. Ride needs no rank. Stealth is 1 rank +3 class +4 Dex +4 racial +4 Small −1 armor = **15**.
- The **Linguistics rank can supply Common**, despite Int 8. It need not be an automatic racial or Intelligence-bonus language.
- Bard level 1 supplies shortbow and whip proficiency; the general feat supplies dogslicer proficiency. Do not substitute goblin Weapon Familiarity: that would change the printed racial build and its skill bonuses.
- Four cantrips and two first-level spells known are correct. First-level daily slots are 1 base +1 from Cha 13 = **2 total**, not two uses of each spell. DCs are **11/12**, CL 1, concentration **+2**.
- **Performance 5 rounds/day** = 4 +1 Cha. **Bardic knowledge +1** uses half bard level, minimum 1. All listed performance types are available at bard 1.

## Current engine/catalog conversion gaps

| Area | Current limitation |
|---|---|
| Race/class combination | `monster_builder/creation_systems/npc.py` explicitly rejects goblin bard 1. This is the observed blocking error. |
| Dogslicer | No NPC item ID exists. Omitted from executable gear and preserved in source notes; no shortsword substitution was made. Its authoritative item rules would need adding. |
| Martial Weapon Proficiency | `feat.martial-weapon-proficiency` is a catalog **gap**. Feat selections accept only `slotId`/`featId`, so the dogslicer target cannot currently be expressed as a mechanical choice. |
| Other equipment | Shortbow, whip and potion of cure light wounds are catalog **gaps**. Use resolved `item.studded-leather-armor`, not the unresolved `item.studded-leather` alias. `item.arrows-20` is resolved. The 20 gp is preserved as a note, not mechanically tracked currency. |
| Skills | Acrobatics, Linguistics and Ride are catalog **gaps**. The five ranked selections fit the simplified skill budget, but the engine does not generate the unranked Ride line. Perform specialty and a language learned through Linguistics are not derived here. |
| Small Stealth modifier | The goblin race record stores +4 racial Stealth separately from Small size. The current single-class `_skills` calculation adds the racial bonus but not the **+4 size bonus**. Simply opening the goblin-bard gate would therefore still undercalculate Stealth (11 instead of 15 with the listed armor). |
| Spells | Daze, ghost sound and hideous laughter have **partial** NPC records (list membership known, descriptions not resolved). Cure light wounds, mage hand and message are resolved. The spell evaluator requires resolved records. |
| Performance and knowledge | The relevant class features are present as names but have empty numeric `effects`. There is no active-performance selection deriving the buffed attacks/conditional saves, nor full mechanical output of performance rounds or the bardic knowledge modifier. Preserve those requirements explicitly rather than claiming names alone implement them. |
| Language | The normal single-class canonical language output starts with racial languages and class-feature grants. It does not turn the Linguistics rank into Common. Source notes preserve the choice without overriding derived output. |

Opening the race/class gate alone is insufficient. A valid conversion needs source-backed catalog additions, targeted feat/language choices, missing skill handling, and a clear base-versus-active-performance presentation. None of those game mechanics is intrinsically impossible to implement. The **unchanged erroneous printed totals**, however, cannot be honestly derived from this gear/ability list under the ordinary rules.

## Evidence and reproduction

- Public engine response: `docs/goblin-warchanter-evaluation.json` (status invalid; canonical null).
- Input: `docs/goblin-warchanter-draft.json`.
- Production gates, skills, languages and schema: `monster_builder/creation_systems/npc.py`.
- Catalog statuses and numeric feature coverage: `catalog/npc.json`, `catalog/npc/class-features.fragment.json`.
- Goblin traits: `sources/npc/aonprd/goblin-race.txt`.
- Bard level tables: `sources/npc/aonprd/bard.txt`. Full class text, including proficiencies, self-inspiration, 4 + Cha rounds and minimum-1 knowledge bonus: `sources/reference/aonprd/bard.html` (archived official Bard page).
- Bow Strength penalty: `sources/npc/aonprd/combat.txt`, Strength Bonus paragraph (line 60).
- Heroic array: `catalog/npc.json` ability arrays; `docs/goblin-sorcerer-source-assessment.md`, section 6.

Re-run the conversion check:

```bash
python3 -m monster_builder validate docs/goblin-warchanter-draft.json
```

Expected current result: **invalid**, `npc.slice-unsupported`, exit code **2**. No finished monster was produced.
