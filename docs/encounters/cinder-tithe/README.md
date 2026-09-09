# The Cinder-Tithe Raid

**Pathfinder 1e; class-based NPC creation.** For four fresh level-2 PCs (dwarf paladin, human/kitsune feyspeaker druid, human rogue/swashbuckler, human divination wizard), accompanied by a level-2–3 bard.

**Budget: 1,405 XP**, between the CR-4 (1,200 XP) and CR-5 (1,600 XP) benchmarks. Five characters still give APL 2 here. This is an upper-CR-4-budget encounter, not a promise of difficulty: a druid companion, successful control spells, and bard support can substantially reduce the danger. No goblin dog or additional reinforcements are included. Relative to the approved proposal, only Sootfinger advances from rogue 1 to rogue 2 (+200 XP).

## Roster and finished statblocks

| NPC | Build | CR / XP | HP | AC / touch / flat-footed | Init | Main attacks |
|---|---|---|---:|---|---:|---|
| [Varkesh, the Ember-Tithe](varkesh.md) | Hobgoblin sorcerer 3; elemental fire; melee-leaning array | 2 / 600 | 23 | **16 / 12 / 14 with mage armor** | +2 | Sickle +3, 1d6+2; elemental ray +3 touch, 1d6+1 fire; burning hands 3d4, Reflex DC 13 half |
| [Sootfinger](sootfinger.md) | Goblin rogue 2; arsonist | 1 / 400 | 17 | 17 / 15 / 13 | +4 | Shortsword +6, 1d4/19–20; shortbow +6, 1d4/×3; sneak attack +1d6 |
| [Krik](goblin-warrior.md) | Goblin warrior 1; bodyguard | 1/3 / 135 | 6 | 16 / 13 / 14 | +2 | Dogslicer +3, 1d4/19–20; shortbow +4, 1d4/×3 |
| [Nib](goblin-warrior.md) | Goblin warrior 1; looter | 1/3 / 135 | 6 | 16 / 13 / 14 | +2 | As Krik |
| [Zek](goblin-warrior.md) | Goblin warrior 1; firestarter | 1/3 / 135 | 6 | 16 / 13 / 14 | +2 | As Krik |

There are three distinct statblocks, each with a `.md` sheet, printable `.html` sheet, full immutable `.json` export, and editable `.draft.json` creation input in this directory. **Krik, Nib, and Zek share the warrior statblock in `goblin-warrior.*`; track their hit points and equipment separately.** Their individual names, roles, starting positions, and combat options below remain unchanged. [roster.json](roster.json) records their actual engine IDs. All five are finalized and stored in `.monster-builder`.

**Use this guide alongside the sheets.** Engine sheets include selected Active Effects: **Varkesh's Mage Armor is already included in his printed AC 16; do not add it again.** Other buffs, including Shield, remain inactive. Narrative tactics, expendable-item attack calculations, and encounter-start resources are recorded here and in the draft details. Incendiary goods are catalogued inventory, not automatically simulated attacks.

## Scene and starting positions

> A haycart crackles beside the barn. Three soot-smeared goblins scurry among stolen sacks while a fourth waves a corked bottle above his head. Behind them, a broad-shouldered hobgoblin lifts a hand wreathed in flame. “The Ember-Tithe is due. Leave your grain and keep your lives.”

Use a roughly **60-by-80-foot farmyard**, with the party entering through the southern gate. This is an openly visible raid, not an automatic surprise round.

- **Krik:** 20 feet inside the gate, screening the leader.
- **Varkesh:** another 15–20 feet behind Krik, on ground level. No inaccessible rooftop or guaranteed hard cover.
- **Sootfinger and Nib:** beside the eastern barn, about 30 feet from the entrance. Nib drops his stolen sack when threatened.
- **Zek:** beside the burning cart on the west side, about 25 feet from the entrance, already holding his weapon rather than receiving a free draw.
- **Cover:** a few crates and fences, available to either side. Leave at least two clear approaches to Varkesh.
- **Water:** a trough and well near the gate. Farmers are safely behind the farmhouse; rescuing them does not consume mandatory PC turns.
- **Exit:** a northern orchard path. Enemies and PCs can retreat.

The haycart is the only established blaze. Its occupied squares are not a safe place to stand, but it imposes **no automatic smoke damage, spreading-fire clock, forced saving throws, or hidden extra hazard XP** on the rest of the yard. Do not expand it into a damaging environmental encounter without reconsidering the budget. A successful burning hands can ignite flammable materials it actually touches; a full-round action extinguishes burning items under that spell's rules.

## Varkesh: spell and resource card

Varkesh is an unusual hobgoblin arcane outcast, not a typical representative of his people's distrust of magic. The goblins follow him because his hands genuinely burn. His heroic array is melee-leaning — **Str 14, Dex 14, Con 15, Int 8, Wis 10, Cha 15** after racial adjustments — and with Int 8 his trained skills are **Stealth** only, keeping Perception and Intimidate untrained.

- **Before the raid:** one mage armor cast, lasting 3 hours, already active in his saved profile and displayed under **Active Effects**. He carries its leather focus. Start with **5 of 6 first-level slots remaining**, 23 hp, and **5 elemental rays**. Start with **5 of 6 first-level slots remaining**, 23 hp, and **5 elemental rays**.
- **Opening:** if threatened, cast shield on his own turn. Otherwise use an elemental ray or press in with the sickle (melee **+3, 1d6+2**; CMB +3, CMD 15) and reposition behind Krik. Casting shield costs an action and another slot; it is not a free prebuff.
- **Shield:** lasts 3 minutes; with mage armor, AC **20**, touch **12**, flat-footed **18**. Negates magic missile. CMD remains 15: armor/shield bonuses do not raise CMD.
- **Burning hands:** 15-foot cone, **3d4 fire**, Reflex **DC 13 half**. Prefer a worthwhile angle against standing opponents, not allies or downed PCs. No heightened DC, metamagic, or mythic version.
- **Elemental ray (Sp):** standard action, **+3 ranged touch**, 30 feet, **1d6+1 fire**, 5/day, no saving throw. Treat it as a spell-like ability, not a supernatural power immune to interruption.
- **Enlarge person (1st-level slot, casting time 1 round, powdered iron):** enlarge one humanoid for **3 minutes** (1 min./level). Usually a prebuff on himself before contact: Large 10-ft reach, Str +2 size (sickle **2d6+3** at +3), CMB +6, CMD 17 — but AC **15**, touch **11**, and ray **+1** (Dex −2 size, −1 attack/AC size). Equipment enlarges; projectiles leave his hands normal-sized. Multiple size effects never stack.
- **Acid splash:** +3 ranged touch, range 30 feet, 1d3 acid; bloodline arcana can change this to **1d3 fire**. At will; no splash damage despite the spell's name.
- **Concentration:** +5 normally; **+9** casting defensively or while grappled through Combat Casting. Casting a 1st-level spell defensively is DC 17.
- **Fire resistance 10** belongs to Varkesh alone. His goblin followers have no fire resistance.
- **Morale:** withdraw at 8 hp or fewer, or after Sootfinger and two warriors fall. If cornered, bargain with the stolen supplies. He does not execute fallen characters.

Mage hand, prestidigitation, and light provide magical theatrics, not invented damage or free ignition abilities. Telegraph shield as a visible force disk so its defensive turn is understandable rather than a surprise AC change.

## Sootfinger: skirmisher and incendiaries

Sootfinger's second rogue level makes him durable enough to contribute beside the bard-supported PCs without adding another enemy turn. He has **evasion, sneak attack +1d6, trapfinding +1, and Bleeding Attack**, not alchemist bombs or extracts.

- Starts visibly dragging loot. Throw his **single** alchemist's fire flask when there is a clear shot without splashing allies; otherwise use his bow. Then draw his shortsword and seek a flank with a warrior. Account for movement, drawing, cover, firing into melee, and attacks of opportunity normally.
- **Alchemist's fire:** +6 ranged touch before situational modifiers; 10-foot range increment. Direct hit 1d6 fire; splash 1 fire within 5 feet of impact. On the next round the directly hit target takes another 1d6 unless extinguished. Full-round action and DC 15 Reflex to extinguish; rolling gives +2, immersion or magical extinguishing works automatically.
- **No sneak attack on splash weapons**, including their direct hits. Consequently Bleeding Attack does not ride on alchemist's fire or oil either.
- Eligible shortsword or bow sneak attacks add **1d6**; ranged sneak attacks require a target within 30 feet as well as the ordinary qualifying conditions.
- **Bleeding Attack:** an eligible sneak attack against a living creature may also cause **1 bleed** at the start of each target turn. Does not stack with itself; bypasses DR. DC 15 Heal or any hit-point healing ends it. Do not silently add it to ordinary damage.
- **Evasion:** on an eligible successful Reflex save against a half-damage attack, takes no damage while in light/no armor and not helpless. This is not general fire resistance.
- **Morale:** flee at 6 hp or fewer, or when Varkesh falls or retreats. Drop the stolen sack rather than die over it.

## Warriors and oil

All three warriors start with shield and dogslicer ready. Torches and oil are stowed; carrying multiple items does not grant extra hands or actions.

- Dogslicer +3 already includes the light steel shield's −1 armor check penalty to Weapon Finesse attacks.
- A shortbow requires two free hands. Remove the shield with a move action and account for drawing the bow. Without the shield: **AC 15, touch 13, flat-footed 13**. An unshielded dogslicer attack would be +4.
- Ordinary dogslicers have the **fragile** quality: a natural 1 breaks the weapon; another natural 1 while broken destroys it. Apply the normal broken-condition rules during play.
- Each warrior carries one oil flask and one torch. Sootfinger carries two oil flasks. Oil is not instant alchemist's fire: preparing a fuse takes a full-round action and a thrown flask has only a **50% chance of ignition**.
- Oil poured onto a **smooth** 5-foot square burns for 2 rounds and deals 1d3 fire to creatures in its area when lit. Do not assume dirt or straw meets the smooth-surface requirement, or grant a free preparation/pour/light sequence.
- Warriors flee at 2 hp or fewer or when the leader falls or retreats. Krik screens; Nib and Zek move in to reinforce instead of all five enemies focusing one PC on round one.

## Party-specific fairness and victory

Let the paladin hold the front, let flanking and control matter, and let the bard's help work. If the dwarf retains standard **hatred**, its +1 attack bonus against goblinoids applies to every raider here. Do not give enemies unexplained counters to the diviner or immunity to the druid's and wizard's control spells. The enemy rogue uses actual positioning, not knowledge of the PCs' sheets.

Victory means driving off or capturing the raiders, not killing all five. Award the encounter's **1,405 XP once** when overcome; routed enemies count, and recapturing them does not grant the same XP again. Divide according to your table's policy for allied NPC participation. Saving the supplies earns the farmers' gratitude; any extra treasure/reward is a separate GM choice.

Loot is the equipment actually carried, minus expended flasks and ammunition. **Unspent NPC gear allowance is not a coin purse.** These are intentionally lightly equipped rural raiders, not a full wealth parcel.

## Validation and source notes

- All five NPCs: valid, no validation issues; finalized in Strict NPC mode and exported as Markdown, HTML, and full JSON. Identity, CR/level, hp/defenses, attacks, skills, and spells checked against canonical results.
- HP follows the repository's approved [NPC HP house rule](../../npc-hit-points-policy.md): basic NPC dice round down; heroic NPCs maximize the first die and round later dice up. Varkesh's 23 hp includes Toughness (+3); his expression is 3d6+9.
- Added standard [hobgoblin traits](../../../sources/npc/aonprd/hobgoblin-race.txt), lines 1–8, from the official AoN race page; no racial Hit Dice or alternate traits.
- Added/curated alchemist's fire, oil, and torches from [Core equipment](../../../sources/npc/aonprd/equipment.txt), price rows 496, 519, 527 and rules 664–665, 672, 678–679. These goods intentionally have no automatic attack routines.
- Anchored full [Bleeding Attack](../../../sources/npc/aonprd/rogue-talent-bleeding-attack.txt) rules (Core Rulebook p. 68) and the ordinary [fragile weapon](../../../sources/npc/aonprd/weapon-fragile.txt) rule (Ultimate Combat).
- Splash targeting/no precision damage: [Core combat](../../../sources/npc/aonprd/combat.txt), line 588. Bloodline: [Elemental](../../../sources/npc/aonprd/elemental-bloodline.txt), lines 5–16. Selected spell descriptions are archived alongside these sources; only standard, non-mythic rules are used.
- Class-based CR: [Adding NPCs](../../../sources/npc/aonprd/designing-encounters.txt), line 1; encounter budget follows the CR/XP table on the archived [Designing Encounters page](../../../sources/reference/aonprd/designing-encounters.html).
- Creation caught and fixed two shared issues: HP expressions now include Toughness, and sheet exports no longer invent treasure from unallocated gear budgets.

Original creation checks: `python3 -m unittest discover -s tests` — 299 tests run, 1 skipped, no failures (including the melee array, Enlarge Person swap, and active-effect regressions). `python3 tools/build_npc_catalog.py --check` and `python3 tools/extract_npc_aon_sources.py --check` pass. The encounter regression is `python3 -m unittest discover -s tests -p test_cinder_tithe.py`.
