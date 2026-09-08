# NPC Active Effects

Active effects are optional, source-backed **profile selections** in NPC mode. They affect the canonical statistics, are saved with the draft/FinishedMonster, and appear under **Active Effects** in Markdown and HTML (sheet and audit profiles).

In the browser, use **Spells, gear and effects → Active Effects**. Add an effect, set its supplying caster/class level, choose any energy or skill parameter, and save. Uncheck **Active** to retain a disabled selection, or remove it. Neither changes the NPC's underlying race, class, abilities, feats or gear.

## Input

```json
{
  "activeEffects": [
    {
      "effectId": "npc-effect.mage-armor",
      "sourceLevel": 3,
      "enabled": true,
      "sourceName": "Varkesh",
      "remainingDuration": "3 hours at raid start"
    },
    {
      "effectId": "npc-effect.resist-energy",
      "sourceLevel": 7,
      "energyType": "cold"
    },
    {
      "effectId": "npc-effect.inspire-courage",
      "sourceLevel": 5,
      "sourceName": "Allied bard"
    }
  ]
}
```

Place this inside `draft.selections`. Use ordinary `draft.create` or `draft.applyChanges` with `type: "set-selection", field: "activeEffects"`. Empty/omitted arrays mean no active effects. `enabled` defaults to true. `sourceName` and `remainingDuration` are optional descriptive text, not expressions or executable rules. `sourceLevel` is required, an integer from the effect's minimum level through 20. It is the supplying caster or class level, **not automatically the recipient's level**.

`draft.choiceRequirements` exposes the optional array, effect IDs, required parameters, source-level bounds and references. Catalog records live in `catalog/npc/active-effects.fragment.json` and the generated NPC catalog's `activeEffects` section. Unknown IDs, unsupported parameters, bad levels, numeric overrides and duplicate enabled effect/parameter combinations are rejected. Multiple energy types are distinct selections; repeated copies of the same spell and energy are not additive.

## Supported effects

| ID suffix (`npc-effect.`) | What changes |
|---|---|
| `mage-armor` | +4 armor AC; overlaps worn armor |
| `shield` | +4 shield AC; overlaps physical shields; magic missile negation noted |
| `protection-from-evil`, `protection-from-good`, `protection-from-chaos`, `protection-from-law` | Conditional +2 deflection AC/CMD and +2 resistance saves against the appropriate sources; mental-control and summoned-contact rules retained |
| `resist-energy` | `energyType`: acid, cold, electricity, fire or sonic; resistance 10, 20 at CL 7, 30 at CL 11 |
| `protection-from-energy` | Same energy choices; finite absorption capacity 12/CL, capped at 120, not permanent immunity |
| `rage` | **Core barbarian** Rage/Greater Rage/Mighty Rage: Strength/Constitution, HP, attacks/damage, skills, saves, AC/CMD and restrictions; includes Indomitable Will at supplying barbarian level 14 |
| `inspire-courage` | Competence to all attack rolls and weapon damage; morale saves against charm/fear; supplying bard levels 1/5/11/17 |
| `inspire-competence` | Requires `skillId`; competence to checks with that skill, not ranks/training; supplying bard level 3+ |
| `inspire-heroics` | +4 morale saves, +4 dodge AC/touch/CMD; supplying bard level 15+ |
| `heroism` | +2 morale attacks, saves and skills; no weapon damage bonus |
| `bless` | +1 morale attacks and fear saves; no damage bonus |

“Protection from Fire/Cold” means selecting the relevant energy on **Protection from Energy**, or using **Resist Energy** if resistance is intended. They are different spells with different behavior.

## Rules and stacking

- The highest same-type bonus applies. Different types stack; dodge and untyped bonuses and distinct penalties follow their normal stacking rules. Duplicate instances of one effect are rejected, including duplicate sources attempting to stack the same dodge effect.
- Mage Armor and Shield do not improve ordinary touch AC or CMD. Their incorporeal-touch exceptions are stated in Active Effects. Physical armor still imposes its Dexterity cap, armor check penalty and proficiency restrictions when worn underneath a stronger magical bonus.
- Conditional bonuses never inflate generic AC or saves. Exported conditional modifiers give the additional same-type increment above the unconditional bonus already included (for example, Protection from Evil contributes only +1 additional resistance over a +1 cloak). They retain their types and conditions: do not add two same-type conditional bonuses when both conditions happen to match. The deflection AC increment also applies to touch, flat-footed AC and CMD as the effect text states.
- General attack bonuses affect weapons, represented touch powers and CMB. Weapon-damage bonuses do not increase spell or spell-like ray damage. Optional combat routines derive from the adjusted attacks and abilities, so they do not lose or double-count buffs.
- Rage changes the Constitution-based HP total rather than adding a temporary-HP pool. Its AC penalty also affects touch, flat-footed AC and CMD. Removing it recalculates the profile from its original selections; it does not heal damage. Blocked skills are marked unavailable, and spellcasting restrictions remain visible. Unchained Rage and the *rage* spell are not aliases for this effect.
- Permanent feat prerequisites, spell loadouts, daily slot capacity, skill rank budgets and class progression are checked against the underlying build, not temporary bonuses. A buff cannot qualify an otherwise illegal permanent feat selection.
- Same-energy resistance uses the highest value, including existing class resistance. Protection from Energy is stored separately in `canonical.energyProtection`, by energy and initial capacity. In particular, it absorbs damage before **Resist Energy** is used; the two spells do not mitigate the same damage simultaneously. The exported effect text preserves this interaction rather than pretending that the pool is additional resistance.
- Canonical effects carry their source references. Derivation traces for the changed statistics include the effect sources; the original construction selections are never overwritten. Finished snapshots retain the selected effects independently of future catalog changes.

## Deliberate scope: a profile snapshot, not a combat simulator

Selecting an effect **asserts that it has already been legally activated on this NPC**. The engine validates its catalogued mechanics, parameter types and supplying level, not the activation history. This allows externally supplied spells and bard performances without incorrectly requiring the recipient to know the spell or be a bard.

The GM remains responsible for source ownership, target eligibility, range/senses, immunities, concentration, spell resistance, dispelling and resource costs. Selecting Rage does not grant a barbarian class feature. Inspire Competence cannot target its performer, and a single bard cannot maintain multiple performances at once; selections must represent legal sources. Other rage variants/archetypes need their own rules rather than silently inheriting the Core barbarian package.

There is no automatic clock, damage tracking, concentration roll, daily-slot subtraction, rage/performance round spending, fatigue transition or absorption-pool depletion. `remainingDuration` is a label only. Disable/remove expired or dispelled effects yourself, and track current HP and protection-pool expenditure during play. Exports show daily spell **capacity**, not remaining slots.

No arbitrary bonus fields or formula interpreter are accepted. New supported effects need curated catalog records; effects outside the implemented modifier/energy mechanics require an explicit engine extension instead of silently becoming descriptive-only buffs.

## Dogfood: Varkesh

[The Cinder-Tithe leader](encounters/cinder-tithe/varkesh.draft.json) has `npc-effect.mage-armor` active at source level 3. His sheet now directly shows **AC 17, touch 13, flat-footed 14**, plus the Active Effects entry. Turning it off restores AC 13/touch 13/flat-footed 10. Shield remains inactive; activating it would produce AC 21/touch 13/flat-footed 18.

The encounter guide still tracks the Mage Armor casting cost: **5 of 6 first-level slots remain**. Do not add its +4 armor bonus a second time.

## Checks

```sh
python3 -m unittest discover -s tests -p test_npc_active_effects.py
python3 -m unittest discover -s tests -p test_cinder_tithe.py
python3 tools/build_npc_catalog.py --check
python3 tools/extract_npc_aon_sources.py --check
npm run typecheck
npm run build
```
