# NPC feat support audit

The original audit below describes runtime/catalog commit `3f8c29f`. Its historical counts and checklist are retained; current implementation progress follows.

## Implementation status

`python3 tools/audit_npc_feats.py` now reports all **99 source-resolved** recommendations: **51 calculated**, **33 intentionally GM-handled** (including metamagic ownership), **1 partial**, and **14 selection-only**. Source resolution is deliberately separate from mechanical support; selection-only feats cannot finalize an NPC.

Implemented in this pass:

- Source-backed records, full-text rules, typed prerequisites, required choices and three transitive prerequisite records. Prerequisites receive acquisition-level abilities/BAB/class levels, skill ranks, caster level, features and grants. Required school targets match their prerequisite chain.
- Permanent HP, saves, initiative, dodge/shield AC, proficiency, skill/weapon bonuses and threat ranges; labelled conditional bonuses; individual spell-school DCs. Individual archived spell headers supply metadata, not simulated spell effects.
- Both reproduced defects pass public Engine regressions: proficient-shield Finesse **+4**, BAB +6 Rapid Shot **+6/+6/+1**. Full-attack thresholds also run through public Engine checks at BAB +6/+11/+16/+20.
- Optional combat previews and explicit `selections.combatOptions` requests: `{weaponId, offHandWeaponId?, action: "attack" | "full-attack", options: [feat IDs]}`. Shared routines handle Power Attack, Deadly Aim, Rapid Shot, Manyshot, two-weapon chains/Double Slice, Vital Strike chains, several unarmed actions, Cleave, Combat Expertise, Arcane Strike, Pinpoint Targeting and Whirlwind Attack. Conditions, costs and defense changes remain separate from base statistics. Incompatible action combinations are rejected. Pair routines currently support resolved melee weapons; shield-equipped, thrown-weapon and double-weapon pairs remain unsupported rather than inheriting incorrect base attack/defense numbers.
- Generic feat choices and optional routines survive draft persistence/finalization and appear in UI, structured, Markdown and HTML exports. Exact gear-budget rows and Warrior progression reach level 20. Druid 4 supplies Wild Shape qualification without applying its temporary form to base statistics.

**Not complete:** Channel Smite, Command Undead, Deadly Stroke, Extra Channel, Improved Channel, Rapid Reload, Run, Shield Master, Shield Slam, Spirited Charge, Trample, Turn Undead, Two-Weapon Defense and Two-Weapon Rend remain explicitly selection-only. Weapon Focus's virtual unarmed/grapple/ray targets are not yet selectable (catalog weapon targets are calculated). Greater Weapon Focus has the corresponding transitive-target limitation. Selected metamagic spell variants remain unsupported; ownership and slot-adjustment metadata do not imply activation support. Wizard, cleric, monk, fighter and paladin progression/grant/waiver gaps remain; cleric source metadata is explicitly a gap, not a valid spell-less cleric. These limitations prevent claiming the entire backlog milestone complete.

Reproduction: `python3 tools/build_feat_fragment.py`, `python3 tools/enrich_npc_spell_metadata.py`, `python3 tools/enrich_npc_weapon_metadata.py`, then `python3 tools/build_npc_catalog.py`. Public checks live in `tests/test_npc_feat_coverage.py`, `tests/test_npc_combat.py`, and `tests/test_npc_class_dependencies.py`.

## Original audit

## Answer

Yes: distinguish feats that modify this statblock from feats the GM uses as rules information. Keep a third treatment for optional attack/state variants, so Power Attack, Vital Strike, Two-Weapon Fighting and Rapid Shot do not silently replace the base statistics. Conditional modifiers also need their conditions preserved.

**The engine does not currently model this distinction explicitly.** It requires resolved catalog records for selected feats. A few effects are calculated; other accepted feats have empty effects and are simply named. Consequently, `catalogStatus: resolved` and `effects: {}` do not establish mechanical completeness. Information-only support should be intentional, not a disguise for unimplemented modifiers.

“GM-handled” means no separately calculated statblock value is needed, **not** that the feat has no game mechanics. Those feats still require source-backed identities, feat slots, prerequisites, necessary choices and readable export. Unlike descriptive equipment, arbitrary feat strings would bypass build rules and cannot substitute for real support.

## Scope and counts

Source: [Core Rulebook, Creating NPCs, Step 4: Feats](https://aonprd.com/Rules.aspx?ID=357), p. 452; archived [NPC extract, lines 53–66](../sources/npc/aonprd/creating-npcs.txt#L53), and the full local [Core feats chapter](../sources/npc/aonprd/feats.txt).

- Deduplicate recommendations across all 11 character-role lists; they are **recommendations, not legal-build allowlists**.
- Expand `item creation feats (all)` to the **8 Core** feats, and `metamagic feats (all)` to the **9 Core** feats. This report does not claim every later-published AoN metamagic/item-creation feat is covered.
- Expand `Armor Proficiency (all)` to Light, Medium and Heavy. Shield Proficiency is separately listed; Tower Shield Proficiency is not included by that phrase.
- `Skill Focus (Ride)` is a choice of Skill Focus, not a separate feat.
- AoN really contains a bare `M` in its Two-Weapon Fighter list; the archived HTML confirms it is not our extraction error. It is not an identifiable feat and is excluded from the count, with the anomaly retained here. It plausibly stands for Two-Weapon Fighting, but no silent source correction is needed: Two-Weapon Fighting already appears elsewhere in the union.

Result: **99 identifiable Core feats**, each audited below.

| Current NPC support | Count | Meaning |
|---|---:|---|
| Working numerical effects within supported builds/equipment | 4 | Improved Initiative, Iron Will, Lightning Reflexes, Martial Weapon Proficiency |
| Calculated, but incomplete | 2 | Weapon Finesse, Rapid Shot |
| Accepted/listed, required numerical effects absent | 2 | Deadly Aim, Point-Blank Shot |
| Catalog record exists but is a gap | 74 | Cannot be selected in a valid NPC, even when the desired treatment is only GM-facing |
| No catalog record | 17 | Unknown ID rather than a usable feat |
| **Total** | **99** | **8 selectable; 91 not yet selectable** |

Endurance is another resolved, name-only feat in the NPC catalog, but it is **not in these Step-4 lists**, so it is not counted among the 99. It could legitimately be GM-handled, or have conditional reminders, without changing unconditional base saves/skills. Its existence must not become a reason to prohibit other feats outside this minimum list.

## What the code actually does

- [`NpcCreation._feats`](../monster_builder/creation_systems/npc.py) rejects non-resolved records, validates slots, collects initiative/save bonuses and weapon-proficiency targets, and otherwise exports names. [`_attacks`](../monster_builder/creation_systems/npc.py) has explicit Weapon Finesse and Rapid Shot handling. There is no general combat-option selection/composition model.
- The UI disables non-resolved feat records in [`npc.tsx`](../monster_builder/web/src/steps/npc.tsx). It supports a weapon target for Martial Weapon Proficiency, but not skill/school/subtype/spell-list choices for other feats.
- The prerequisite evaluator already supports class levels, skill ranks, caster level and class-feature operands in [`npc/prerequisites.py`](../monster_builder/npc/prerequisites.py). **The selected-feat caller does not supply those contexts**: it supplies ability scores, total BAB, total level and selected feat IDs. Unknown prerequisite results are reported as unmet prerequisites. Acquisition-level checks and matching target choices in prerequisite chains also need attention.
- Feats are evaluated before skills, derived class features and spellcasting in the main flow. Supplying proper prerequisites should reuse shared derivation/context, not duplicate class/skill calculations in every feat.
- Generic save effects can already express Great Fortitude, but its record is missing. Other reusable families should cover dodge/shield AC, HP, selected-skill/weapon bonuses and conditional riders; they do not require individual character paths.
- Spell Focus requires **school metadata and per-spell DC adjustments**. It does not require implementing every spell's effects. Metamagic ownership can be listed without activation; a selected prepared/cast variant needs correct slot adjustments, eligibility and applicable DC changes. Current spell loadouts contain spell IDs, not metamagic selections.

### Reproduced defects in currently accepted feats

`python3 tools/audit_npc_feats.py` inventories the source/catalog and runs these public `Engine.execute(draft.create)` probes without changing saved drafts:

| Probe | Engine output | Required output |
|---|---|---|
| Halfling bard 2, Weapon Finesse, rapier and proficient light steel shield | Rapier **+5** | **+4**, including the shield's -1 ACP under Weapon Finesse; damage stays unchanged |
| Human warrior 5/ranger 1, BAB +6, Dex 14, longbow and Rapid Shot | **+6/+6** | Full-attack option **+6/+6/+1** |

Sources: Weapon Finesse ([feat text line 1035](../sources/npc/aonprd/feats.txt#L1035), including its shield clause), Rapid Shot ([line 851](../sources/npc/aonprd/feats.txt#L851)) and the normal iterative-attack rules. The current attack builder starts with only one ordinary attack and constructs Rapid Shot from two copies of it, so the latter is an underlying full-attack-model gap, not merely a missing feat label.

## Full checklist

Treatment describes **what correct support requires**, not a claim it exists:

- **B**: base or equipment-dependent statblock modifier.
- **A**: separately calculated attack/action/state option; never silently applied to the base block.
- **R**: conditional numerical rider, with its triggering condition.
- **GM**: rules/permission resolved by the GM; list the feat and required choices without simulating play.
- **M**: metamagic ownership is listable; using a spell variant requires spell-loadout metadata/mechanics.

Treatments can overlap. “Gap” and “Absent” both mean **not currently supported as a selected NPC feat**, including for GM-only use. The source column points to the full feat description, not just its abbreviated summary-table prerequisites.

| Feat | Treatment | Current engine | Required behavior / limitation | Source |
|---|---|---|---|---|
| Alignment Channel | GM | Absent | Chosen alignment subtype changes channel targets; preserve choice and channel prerequisite. | [L241](../sources/npc/aonprd/feats.txt#L241) |
| Arcane Strike | A | Gap | Swift-action weapon damage +1, +1 per five caster levels (cap +5); magic for DR. Optional state, not base damage. | [L257](../sources/npc/aonprd/feats.txt#L257) |
| Armor Proficiency, Heavy | B | Gap | Remove heavy-armor nonproficiency attack penalties; retain ordinary skill ACP. Validate Light and Medium prerequisites/grants. | [L261](../sources/npc/aonprd/feats.txt#L261) |
| Armor Proficiency, Light | B | Gap | Remove light-armor nonproficiency attack penalties; retain ordinary skill ACP. | [L267](../sources/npc/aonprd/feats.txt#L267) |
| Armor Proficiency, Medium | B | Gap | Remove medium-armor nonproficiency attack penalties; retain ordinary skill ACP; requires Light proficiency. | [L272](../sources/npc/aonprd/feats.txt#L272) |
| Brew Potion | GM | Gap | Crafting permission; caster level 3. Ownership need not simulate crafting or give free potions. | [L302](../sources/npc/aonprd/feats.txt#L302) |
| Channel Smite | A | Gap | Optional channel damage on a qualifying melee hit, channel save DC and one channel use; needs channel mechanics. | [L311](../sources/npc/aonprd/feats.txt#L311) |
| Cleave | A/GM | Absent | Normal highest-BAB attack, conditional additional attack; show -2 AC while used. GM handles target adjacency/hit trigger. | [L315](../sources/npc/aonprd/feats.txt#L315) |
| Combat Casting | R | Gap | +4 concentration when casting defensively or grappled, including qualifying spell-like abilities; not all concentration. | [L319](../sources/npc/aonprd/feats.txt#L319) |
| Combat Expertise | A | Gap | Trade melee attack/CMB for dodge AC: 1 + floor(BAB/4); account for touch AC/CMD and state duration. | [L322](../sources/npc/aonprd/feats.txt#L322) |
| Combat Reflexes | GM | Gap | Additional AoOs from Dexterity bonus and permission while flat-footed; no ordinary attack-line bonus. Optional count reminder. | [L326](../sources/npc/aonprd/feats.txt#L326) |
| Command Undead | A/GM | Gap | Channel-based control action; derived DC 10 + half cleric level + Cha and controlled-HD limit, with channel-use cost. | [L331](../sources/npc/aonprd/feats.txt#L331) |
| Craft Magic Arms and Armor | GM | Gap | Crafting permission; caster level 5 (or applicable alternate qualification). Do not automatically upgrade equipment. | [L335](../sources/npc/aonprd/feats.txt#L335) |
| Craft Rod | GM | Gap | Crafting permission; caster level 9. | [L341](../sources/npc/aonprd/feats.txt#L341) |
| Craft Staff | GM | Gap | Crafting permission; caster level 11. | [L345](../sources/npc/aonprd/feats.txt#L345) |
| Craft Wand | GM | Gap | Crafting permission; caster level 5. | [L349](../sources/npc/aonprd/feats.txt#L349) |
| Craft Wondrous Item | GM | Gap | Crafting permission; caster level 3 (or applicable alternate qualification). | [L353](../sources/npc/aonprd/feats.txt#L353) |
| Dazzling Display | GM | Gap | Weapon Focus/proficiency-dependent full-round demoralize action using existing Intimidate; no flat attack/damage bonus. | [L367](../sources/npc/aonprd/feats.txt#L367) |
| Deadly Aim | A | Listed only; maths missing | Optional ranged attack penalty 1 + floor(BAB/4), damage bonus twice that; excludes touch attacks and non-HP damage. | [L371](../sources/npc/aonprd/feats.txt#L371) |
| Deadly Stroke | A | Absent | Conditional single-attack double damage plus 1 Con bleed; do not multiply the additional damage/bleed on a critical. | [L375](../sources/npc/aonprd/feats.txt#L375) |
| Deflect Arrows | GM | Gap | Reaction/permission with free-hand, awareness and projectile restrictions; no blanket AC increase. | [L390](../sources/npc/aonprd/feats.txt#L390) |
| Dodge | B | Gap | +1 dodge to AC/touch and applicable CMD; lost when Dexterity bonus is denied, not added to flat-footed AC. | [L407](../sources/npc/aonprd/feats.txt#L407) |
| Double Slice | A | Gap | Full Strength bonus on off-hand damage in a two-weapon routine; requires hand assignment and correct normal half-Strength handling. | [L411](../sources/npc/aonprd/feats.txt#L411) |
| Elemental Channel | GM | Absent | Chosen elemental subtype changes channel targets; preserve choice and channel prerequisite. | [L416](../sources/npc/aonprd/feats.txt#L416) |
| Empower Spell | M | Gap | Possession is listable; selected variants use +2 slot levels. Numeric spell effects only need calculation if rendered. | [L421](../sources/npc/aonprd/feats.txt#L421) |
| Enlarge Spell | M | Gap | Possession is listable; selected eligible variants use +1 slot level and doubled range. | [L430](../sources/npc/aonprd/feats.txt#L430) |
| Eschew Materials | GM | Absent | Material-component permission up to 1 gp; no base number changes; do not waive costly components. | [L434](../sources/npc/aonprd/feats.txt#L434) |
| Extend Spell | M | Gap | Possession is listable; selected eligible variants use +1 slot level and doubled duration. | [L448](../sources/npc/aonprd/feats.txt#L448) |
| Extra Channel | B | Gap | +2 channel uses/day; special paladin channel-only lay-on-hands handling. Channel feature support is missing. | [L451](../sources/npc/aonprd/feats.txt#L451) |
| Far Shot | R | Gap | Range-increment penalty becomes -1 per full increment, not -2; does not simply double the weapon's range increment. | [L481](../sources/npc/aonprd/feats.txt#L481) |
| Forge Ring | GM | Gap | Crafting permission; caster level 7. | [L490](../sources/npc/aonprd/feats.txt#L490) |
| Gorgon’s Fist | A/GM | Gap | Conditional unarmed attack with Fort DC 10 + half character level + Wis; GM handles stagger condition. | [L495](../sources/npc/aonprd/feats.txt#L495) |
| Great Cleave | A/GM | Absent | Normal attack/damage; conditional chain of attacks and -2 AC state. GM resolves targets/hits. | [L499](../sources/npc/aonprd/feats.txt#L499) |
| Great Fortitude | B | Absent | +2 Fortitude. Existing generic save-effect calculation could handle it, but the feat record is absent. | [L503](../sources/npc/aonprd/feats.txt#L503) |
| Greater Spell Focus | B | Absent | Chosen-school +1 spell DC, stacking with matching Spell Focus; requires per-spell school metadata/DCs, not full spell simulation. | [L539](../sources/npc/aonprd/feats.txt#L539) |
| Greater Spell Penetration | R | Absent | Additional +2 checks against SR, stacking with Spell Penetration; do not increase base caster level or concentration. | [L544](../sources/npc/aonprd/feats.txt#L544) |
| Greater Two-Weapon Fighting | A | Gap | Third off-hand attack at -10 relative to highest attack, alongside legal existing attacks; requires two-weapon routine. | [L557](../sources/npc/aonprd/feats.txt#L557) |
| Greater Vital Strike | A | Gap | Single attack rolls weapon dice four times; flat bonuses once, extra dice not multiplied on a critical; not a full attack. | [L561](../sources/npc/aonprd/feats.txt#L561) |
| Heighten Spell | M | Gap | Selected effective spell level controls slot and level-based effects including DC (maximum 9); unlike ordinary metamagic. | [L575](../sources/npc/aonprd/feats.txt#L575) |
| Improved Bull Rush | R/GM | Gap | +2 bull-rush CMB and defense against bull rush; no maneuver AoO. Do not add to every CMB/CMD check. | [L578](../sources/npc/aonprd/feats.txt#L578) |
| Improved Channel | B | Absent | +2 channel energy save DC; requires derived channel feature. | [L583](../sources/npc/aonprd/feats.txt#L583) |
| Improved Critical | B | Gap | Chosen weapon's threat range doubles; not its critical multiplier; no stacking with other threat-range expansion. | [L591](../sources/npc/aonprd/feats.txt#L591) |
| Improved Disarm | R/GM | Gap | +2 disarm CMB and defense against disarm; no maneuver AoO. | [L597](../sources/npc/aonprd/feats.txt#L597) |
| Improved Feint | GM | Gap | Feint as a move action using existing Bluff; no flat stat modifier. | [L621](../sources/npc/aonprd/feats.txt#L621) |
| Improved Grapple | R/GM | Gap | +2 grapple CMB and defense against grapple; no maneuver AoO. | [L626](../sources/npc/aonprd/feats.txt#L626) |
| Improved Initiative | B | Working | +4 initiative is applied. | [L635](../sources/npc/aonprd/feats.txt#L635) |
| Improved Sunder | R/GM | Gap | +2 sunder CMB and defense against sunder; no maneuver AoO. | [L661](../sources/npc/aonprd/feats.txt#L661) |
| Improved Trip | R/GM | Gap | +2 trip CMB and defense against trip; no maneuver AoO. | [L666](../sources/npc/aonprd/feats.txt#L666) |
| Improved Two-Weapon Fighting | A | Gap | Second off-hand attack at -5 relative to highest attack; preserve main-hand iteratives. | [L671](../sources/npc/aonprd/feats.txt#L671) |
| Improved Unarmed Strike | B/GM | Gap | Supply a usable unarmed attack, lethal/nonlethal choice and armed/no-AoO permission; weapon-only inventory attacks are insufficient. | [L676](../sources/npc/aonprd/feats.txt#L676) |
| Improved Vital Strike | A | Absent | Single attack rolls weapon dice three times; flat bonuses once, extra dice not multiplied on a critical. | [L680](../sources/npc/aonprd/feats.txt#L680) |
| Iron Will | B | Working | +2 Will is applied. | [L691](../sources/npc/aonprd/feats.txt#L691) |
| Lightning Reflexes | B | Working | +2 Reflex is applied. | [L751](../sources/npc/aonprd/feats.txt#L751) |
| Manyshot | A | Absent | First bow full-attack hit fires two arrows; apply damage per arrow, precision/critical once and DR/resistance separately. | [L765](../sources/npc/aonprd/feats.txt#L765) |
| Martial Weapon Proficiency | B | Working for resolved weapons | Chosen martial weapon type removes -4 nonproficiency penalty; works for resolved weapon records, including matching variants. | [L769](../sources/npc/aonprd/feats.txt#L769) |
| Maximize Spell | M | Gap | Possession is listable; selected variants use +3 slot levels. Spell-effect maximization is not an NPC base-stat modifier. | [L780](../sources/npc/aonprd/feats.txt#L780) |
| Medusa’s Wrath | A | Gap | Two additional highest-BAB unarmed attacks in a qualifying full attack against specified conditions; not permanently extra attacks. | [L784](../sources/npc/aonprd/feats.txt#L784) |
| Mobility | R | Gap | +4 dodge AC against movement-provoking AoOs only; not base AC. | [L788](../sources/npc/aonprd/feats.txt#L788) |
| Mounted Combat | GM | Gap | Once/round Ride check to negate an attack on mount; no automatic rider/mount AC increase. | [L797](../sources/npc/aonprd/feats.txt#L797) |
| Natural Spell | GM | Gap | Casting permission in wild shape, with restrictions; requires Wis 13 and wild shape. Does not itself apply wild-shape buffs. | [L801](../sources/npc/aonprd/feats.txt#L801) |
| Pinpoint Targeting | GM/A | Absent | Single ranged attack ignoring target armor/natural armor/shield; no movement that round. No universal attack bonus. | [L817](../sources/npc/aonprd/feats.txt#L817) |
| Point-Blank Shot | R | Listed only; rider missing | +1 ranged attack and damage within 30 feet only; explicit contextual line or modifier, not base totals. | [L821](../sources/npc/aonprd/feats.txt#L821) |
| Power Attack | A | Gap | Melee/CMB penalty 1 + floor(BAB/4); damage +2 per step, +50% two-handed/qualifying primary natural, half off-hand/secondary. | [L824](../sources/npc/aonprd/feats.txt#L824) |
| Precise Shot | R/GM | Gap | Remove firing-into-melee -4 penalty in that situation, not unconditional +4 attack. | [L828](../sources/npc/aonprd/feats.txt#L828) |
| Quicken Spell | M | Gap | Possession is listable; selected variants use +4 slot levels, swift action and casting-time eligibility restrictions. | [L839](../sources/npc/aonprd/feats.txt#L839) |
| Rapid Reload | GM/A | Gap | Chosen crossbow reload action; hand/light crossbows can support full-attack routines, heavy crossbow still needs a move action. | [L844](../sources/npc/aonprd/feats.txt#L844) |
| Rapid Shot | A | Partial / iterative defect | Separate extra-highest-attack routine exists, but currently drops iteratives at BAB 6+; no general option-combination model. | [L851](../sources/npc/aonprd/feats.txt#L851) |
| Ride-By Attack | GM | Gap | Mounted-charge movement/AoO permission using ordinary charge math; no standalone extra damage bonus. | [L855](../sources/npc/aonprd/feats.txt#L855) |
| Run | R/GM | Gap | Running multiplier, +4 running-jump Acrobatics and retained Dex AC while running; does not increase base land speed. | [L859](../sources/npc/aonprd/feats.txt#L859) |
| Scorpion Style | A/GM | Gap | Unarmed attack with Fort DC 10 + half character level + Wis and duration from Wisdom; GM handles target speed reduction. | [L863](../sources/npc/aonprd/feats.txt#L863) |
| Scribe Scroll | GM | Gap | Crafting permission; caster level 1. Do not add scroll inventory automatically. | [L867](../sources/npc/aonprd/feats.txt#L867) |
| Selective Channeling | GM | Absent | Choose excluded channel targets up to Cha modifier; requires Cha 13 and channel energy. | [L871](../sources/npc/aonprd/feats.txt#L871) |
| Shatter Defenses | GM | Absent | Target becomes flat-footed to subsequent attacks under specified conditions; no permanent self attack/damage modifier. | [L879](../sources/npc/aonprd/feats.txt#L879) |
| Shield Focus | B | Gap | +1 equipped shield AC bonus; correct normal/flat-footed versus touch treatment. | [L883](../sources/npc/aonprd/feats.txt#L883) |
| Shield Master | A | Gap | Shield attacks remove applicable two-weapon penalties and use shield enhancement for attack/damage; not the other weapon's penalties. | [L887](../sources/npc/aonprd/feats.txt#L887) |
| Shield Proficiency | B | Gap | Remove nonproficiency attack penalties for non-tower shields; ordinary skill ACP remains. | [L891](../sources/npc/aonprd/feats.txt#L891) |
| Shield Slam | A/GM | Gap | Shield bash grants conditional free bull rush using attack roll; derive shield-bash attack and preserve target/terrain rules. | [L896](../sources/npc/aonprd/feats.txt#L896) |
| Shot on the Run | GM | Gap | Full-round movement plus one ranged attack; no flat bonus; not an ordinary full-attack routine. | [L900](../sources/npc/aonprd/feats.txt#L900) |
| Silent Spell | M | Gap | Possession is listable; selected eligible variants use +1 slot level; cannot enhance Bard spells. | [L910](../sources/npc/aonprd/feats.txt#L910) |
| Skill Focus | B | Absent | Chosen skill gets +3, or +6 at 10 ranks; Ride is a skill target, not a separate feat. | [L919](../sources/npc/aonprd/feats.txt#L919) |
| Snatch Arrows | GM | Gap | Projectile catching/throw-back permission with free-hand and prerequisite restrictions; no flat AC modifier. | [L923](../sources/npc/aonprd/feats.txt#L923) |
| Spell Focus | B | Gap | Chosen-school +1 spell DC; requires school metadata and per-spell DC handling, not full spell mechanics. | [L928](../sources/npc/aonprd/feats.txt#L928) |
| Spell Mastery | GM | Gap | Wizard-only; select known spells up to Intelligence modifier for spellbook-free preparation. Needs spell choices, not changed DCs. | [L932](../sources/npc/aonprd/feats.txt#L932) |
| Spell Penetration | R | Gap | +2 caster-level checks against SR only; base CL/concentration unchanged. | [L937](../sources/npc/aonprd/feats.txt#L937) |
| Spirited Charge | A | Gap | Mounted-charge damage multiplier x2 or x3 with lance; correct damage-multiplier composition, not a permanent weapon bonus. | [L945](../sources/npc/aonprd/feats.txt#L945) |
| Spring Attack | GM | Gap | Movement plus one melee attack with restrictions/AoO permission; no flat damage bonus and no ordinary full attack. | [L949](../sources/npc/aonprd/feats.txt#L949) |
| Still Spell | M | Gap | Possession is listable; selected eligible variants use +1 slot level and remove somatic components. | [L970](../sources/npc/aonprd/feats.txt#L970) |
| Stunning Fist | A/GM | Gap | Unarmed special attack with DC 10 + half character level + Wis, daily uses and monk exception; no base damage bonus. | [L982](../sources/npc/aonprd/feats.txt#L982) |
| Toughness | B | Gap | Add max(3, total HD) hit points after the existing HP policy; do not change die averages or Constitution accounting. | [L996](../sources/npc/aonprd/feats.txt#L996) |
| Trample | A/GM | Gap | Mounted overrun can trigger mount's hoof attack at +4 versus prone target; requires mount attack data, not a rider bonus. | [L1005](../sources/npc/aonprd/feats.txt#L1005) |
| Turn Undead | A/GM | Absent | Channel action with derived DC 10 + half cleric level + Cha; consumes channel use, GM resolves fleeing. | [L1009](../sources/npc/aonprd/feats.txt#L1009) |
| Two-Weapon Defense | B/A | Gap | +1 shield AC while actually dual-wielding, +2 with defensive actions; observe shield-bonus stacking and equipment state. | [L1013](../sources/npc/aonprd/feats.txt#L1013) |
| Two-Weapon Fighting | A | Gap | Explicit paired weapons/handedness and separate attack routine with appropriate penalties; not two independent full-bonus attacks. | [L1018](../sources/npc/aonprd/feats.txt#L1018) |
| Two-Weapon Rend | A | Gap | Conditional once/round damage 1d10 + 1.5 Strength when both weapons hit; not added to each weapon hit. | [L1023](../sources/npc/aonprd/feats.txt#L1023) |
| Vital Strike | A | Gap | Single attack rolls weapon dice twice; flat bonuses once, extra dice not multiplied on a critical; not a full attack. | [L1031](../sources/npc/aonprd/feats.txt#L1031) |
| Weapon Finesse | B | Partial / shield defect | Dex can replace Str for eligible melee attacks, never damage. Current implementation omits the proficient-shield ACP rider. | [L1035](../sources/npc/aonprd/feats.txt#L1035) |
| Weapon Focus | B | Gap | Chosen weapon +1 attack; include legal unarmed/grapple/ray targets, matching proficiency and BAB requirements. | [L1039](../sources/npc/aonprd/feats.txt#L1039) |
| Whirlwind Attack | GM/A | Gap | Highest-BAB melee attack per target; forfeits other bonus/extra attacks. GM resolves targets; mode must exclude incompatible routines. | [L1049](../sources/npc/aonprd/feats.txt#L1049) |
| Widen Spell | M | Gap | Possession is listable; selected eligible variants use +3 slot levels and doubled qualifying areas. | [L1054](../sources/npc/aonprd/feats.txt#L1054) |

## Minimum support requirement and implementation order

All **99** should be catalog-backed choices, using the correct treatment above. Supporting the feat record is separate from whether a particular NPC currently qualifies. Do not resolve a numerical feat by pretending it is GM-only, and do not require a combat simulator merely to list a permission feat.

1. **Source metadata, choices and prerequisites for the whole baseline.** Add the 17 missing records and resolve the 74 placeholders from the already-local full descriptions. Distinguish source/selection coverage from effect coverage. Wire existing prerequisite context instead of inventing per-feat validators. Preserve slots, repeatability, class grants/waivers and choice matching. The short recommendation lists are not complete prerequisites.
2. **Shared base modifiers and conditional reminders.** Reuse initiative/saves/proficiency; add HP, typed AC/CMD, selected weapon/skill bonuses, threat ranges, school-specific DCs and condition-labelled checks. Fix Weapon Finesse's shield clause. Keep all temporary states out of the base block.
3. **A shared attack-routine calculation.** Derive iteratives, hand assignment, weapon handedness and Strength multipliers once. Use it for Power Attack/Deadly Aim, Rapid Shot/Manyshot, Two-Weapon Fighting chains and Vital Strike. Support compatible combinations (e.g. Rapid Shot + Deadly Aim + Point-Blank Shot within 30 ft.) without enumerating every subset; reject incompatible actions such as Vital Strike with a full attack. Include state costs/defense penalties rather than showing only bonuses.
4. **Feature-dependent actions and spell variants.** Derive channel/DC/use counters and relevant unarmed/mounted attacks where applicable. Metamagic ownership can be supported without full spell effects, but an explicitly selected metamagic spell needs correct slot cost, applicability and DC metadata. Heighten is different from the other eight; Silent Spell cannot modify Bard spells.

### Dependencies outside the literal list

- The recommendation set is not closed under prerequisites. At least **Greater Weapon Focus** (Deadly Stroke), **Improved Shield Bash** (Shield Slam/Master), and **Improved Precise Shot** (Pinpoint Targeting) also need source-backed support. These records currently exist only as gaps. Do not waive them because the NPC recommendation page omitted them.
- Wizard/cleric/monk and higher-level class-feature coverage remains a separate limitation. For example, Spell Mastery needs Wizard 1; Natural Spell needs wild shape; channel feats need the appropriate channel ability; Greater Vital Strike needs BAB +16. A correct prerequisite rejection is not the same as an unimplemented feat or class record. Class extensions must include all lower levels and preserve genuine rules.
- A separate level-7 composition probe also exposed an existing `_gear` `KeyError: 'gearBudgetId'` when using a higher-level budget row. Higher-level reachability needs this data/guard issue addressed; it must not be hidden behind a feat allowlist or treated as an illegal combination.
- Keep feats outside this baseline available when their own data/rules are supported. The 99 are a minimum acceptance inventory, never an execution allowlist.

### Acceptance

- Each feat has source-backed acquisition requirements and all necessary choices, even when its treatment is GM-only.
- Baseline values, conditional values and optional routines are distinguishable in discovery, UI, persistence and exports.
- Numerical modifiers cannot disappear silently behind an empty effects object; an unsupported calculation remains explicit.
- Full-attack checks cover BAB +6/+11/+16 and correct off-hand/extra-attack counts; Vital Strike checks distinguish weapon dice from flat/precision/critical damage.
- Ordinary spells still do not require full spell simulation; only metadata demanded by the selected feat/variant is added.
- The coverage inventory and public probes are reproducible with `python3 tools/audit_npc_feats.py`. The probe output contains both actual and expected values: it is an audit report, not a passing-correctness assertion for those two known defects.
