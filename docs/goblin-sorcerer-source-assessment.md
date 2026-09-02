# Goblin Sorcerer (Level 5, fire theme, wand) — Source Assessment

> Every implemented claim below is backed by a current-site `aonprd.com` snapshot archived under `sources/reference/aonprd/`, normalized under `sources/npc/aonprd/`, and hash-anchored in `sources/npc/MANIFEST.json`. No newly acquired legacy-site page is used.
> Date: 2026-09-02 (rev. 3: implementation source gate)

## 1. Goblin racial statistics

**PC-race racial traits** — AoN Races: Goblin
URL: https://aonprd.com/RacesDisplay.aspx?ItemName=Goblin
Source listed on page: "Source Inner Sea Races pg. 244, Pathfinder RPG Bestiary pg. 156, Advanced Race Guide pg. 114"

Exact claims from the page ("Goblin Racial Traits"):
- "+4 Dexterity, –2 Strength, –2 Charisma: Goblins are fast but weak, and they're unpleasant to be around."
- "Goblinoid: Goblins are humanoids with the goblinoid subtype."
- "Small: Goblins are Small and gain a +1 size bonus to their AC, a +1 size bonus on attack rolls, a –1 penalty on combat maneuver checks and to their Combat Maneuver Defense, and a +4 size bonus on Stealth checks."
- "Normal Speed: Goblins are fast for their size, and have a base speed of 30 feet."
- "Darkvision: Goblins can see in the dark up to 60 feet."
- "Skilled: +4 racial bonus on Ride and Stealth checks."
- "Languages: Goblins begin play speaking Goblin. Goblins with high Intelligence scores can choose from the following languages: Common, Draconic, Dwarven, Gnoll, Gnome, Halfling, and Orc."

Alternate racial traits on the same page (all "replaces skilled" unless noted): Cave Crawler (ARG pg. 114; replaces fast movement), City Scavenger, Eat Anything, Hard Head Big Teeth (bite 1d4 primary), Junk Tinker (Inner Sea Races pg. 215), Over-Sized Ears, Tree Runner, Weapon Familiarity (dogslicer/horsechopper proficiency). Oversized goblin variant (Monster Codex pg. 104): Medium size, +2 Str, +2 Dex, –2 Cha instead of normal modifiers.

Favored class option, sorcerer (same page, also on the Sorcerer page): "Goblin (Advanced Race Guide pg. 116, Goblins of Golarion pg. 31): Add +1 spell known from the sorcerer spell list. This spell must be at least one level below the highest spell level the sorcerer can cast, and must have the fire descriptor." — directly supports the fire theme at every level.

**NPC statistics (Bestiary stat block)** — AoN Monsters: Goblin, CR 1/3
URL: https://aonprd.com/MonsterDisplay.aspx?ItemName=Goblin
Exact claims: "Goblin warrior 1 NE Small humanoid (goblinoid)"; "Init +6; Senses darkvision 60 ft.; Perception –1"; "AC 16, touch 13, flat-footed 14 (+2 armor, +2 Dex, +1 shield, +1 size) hp 6 (1d10+1)"; "Str 11, Dex 15, Con 12, Int 10, Wis 9, Cha 6"; "Racial Modifiers +4 Ride, +4 Stealth"; "Languages Goblin"; Treasure: "NPC gear (leather armor, light wooden shield, short sword, short bow with 20 arrows, other treasure)".
Note: the same category list (verified on that page) contains a **Goblin Firestarter, CR 4** (link: https://aonprd.com/MonsterDisplay.aspx?ItemName=Goblin%20Firestarter) — an official pre-built fire-themed goblin NPC near the target level. Its contents were not fetched in this pass.

## 2. Sorcerer class progression through level 5

URL: https://aonprd.com/ClassDisplay.aspx?ItemName=Sorcerer
Source: PRPG Core Rulebook pg. 70.

Table: Sorcerer (levels 1–5, exact):
| Level | BAB | Fort | Ref | Will | Special | 1st | 2nd |
|---|---|---|---|---|---|---|---|
| 1st | +0 | +0 | +0 | +2 | Bloodline power, cantrips, eschew materials | 3 | – |
| 2nd | +1 | +0 | +0 | +3 | — | 4 | – |
| 3rd | +1 | +1 | +1 | +3 | Bloodline power, bloodline spell | 5 | – |
| 4th | +2 | +1 | +1 | +4 | — | 6 | 3 |
| 5th | +2 | +1 | +1 | +4 | Bloodline spell | 6 | 4 |

Spells Known (Table: Sorcerer Spells Known), level 5 exact: "0: 6 | 1st: 4 | 2nd: 2".
Cantrips: "These spells are cast like any other spell, but they do not consume any slots and may be used again."
Bloodline: "A sorcerer must pick one bloodline upon taking her first level of sorcerer." / "At 3rd level, and every two levels thereafter, a sorcerer learns an additional spell, derived from her bloodline. These spells are in addition to the number of spells given on Table: Sorcerer Spells Known." Bonus feats only at 7th/13th/19th — no bloodline feat at level 5.
Other level-1 features (exact): simple-weapon proficiency only, no armor/shield proficiency; Eschew Materials bonus feat at 1st; spellcasting key stat Charisma ("To learn or cast a spell, a sorcerer must have a Charisma score equal to at least 10 + the spell level"; "The Difficulty Class ... is 10 + the spell level + the sorcerer's Charisma modifier").
Hit Die: d6. Starting Wealth: "2d6 x 10 gp (average 70 gp)."

## 3. Core fire bloodline: Elemental (fire)

URL: https://aonprd.com/BloodlineDisplay.aspx?ItemName=Elemental
Source: PRPG Core Rulebook pg. 75. This is the Core bloodline that covers fire: "At first level, you must select one of the four elements: air, earth, fire, or water." Fire column (exact): energy type **Fire**; Elemental Movement "+30 feet base speed" (granted at 15th, not relevant at 5).

Exact claims relevant at level 5:
- Class Skill: Knowledge (planes).
- Bonus Spells: "burning hands* (3rd), scorching ray* (5th), protection from energy (7th), elemental body I (9th), ..." with the footnote: "*These spells always deal a type of damage determined by your element. In addition, the subtype of these spells changes to match the energy type of your element."
- Bloodline Arcana: "Whenever you cast a spell that deals energy damage, you can change the type of damage to match the type of your bloodline."
- Elemental Ray (Sp), 1st level: "1d6 points of damage of your energy type + 1 for every two sorcerer levels you possess ... a number of times per day equal to 3 + your Charisma modifier." → at 5th: 1d6+2 fire, ranged touch, 30 ft.
- Elemental Resistance (Ex), 3rd level: "you gain energy resistance 10 against your energy type" (→ fire resistance 10).
- Bloodline powers beyond level 5 (9th Elemental Blast, 15th Elemental Movement, 20th Elemental Body) are on the page but out of scope.

## 4. Minimal Core spell loadout, levels 0–2 (verified spells only)

Bloodline bonus spells (fixed, verified via the bloodline page): **burning hands** (3rd) and **scorching ray** (5th), both always fire for this bloodline.
- Burning Hands — https://aonprd.com/SpellDisplay.aspx?ItemName=Burning%20Hands — "evocation [fire]; Level ... sorcerer 1, wizard 1"; "1d4 points of fire damage per caster level (maximum 5d4)"; Reflex half; 15-ft. cone.
- Scorching Ray — https://aonprd.com/SpellDisplay.aspx?ItemName=Scorching%20Ray — "evocation [fire]; Level ... sorcerer 2, wizard 2"; "4d6 points of fire damage" per ray, ranged touch, extra ray every 4 levels beyond 3rd (one ray at CL 5).
- Flaming Sphere — https://aonprd.com/SpellDisplay.aspx?ItemName=Flaming%20Sphere — "evocation [fire]; Level ... sorcerer 2, wizard 2"; "3d6 points of fire damage", "moves 30 feet per round", Reflex negates, 1 round/level. Sorcerer list membership verified.

Spells-known budget at 5th: 6 cantrips + 4 first-level + 2 second-level known, plus the 2 bloodline spells. The implemented loadout uses current-site snapshots for acid splash, detect magic, light, mage hand, prestidigitation, and read magic; grease, mage armor, magic missile, and shield; and flaming sphere and mirror image. Burning hands and scorching ray are added separately by the bloodline. No broader spell catalog is claimed resolved.

## 5. Wand: creation, pricing, use rules

**Wand rules** — URL: https://aonprd.com/Rules.aspx?Name=Wands&Category=Magic%20Items (Source PRPG Core Rulebook pg. 496). Exact claims:
- "A wand is a thin baton that contains a single spell of 4th level or lower. A wand has 50 charges when created—each charge allows the use of the wand's spell one time."
- "The price of a wand is equal to the level of the spell × the creator's caster level × 750 gp."
- Activation: "Wands use the spell trigger activation method, so casting a spell from a wand is usually a standard action that doesn't provoke attacks of opportunity."
- Table 15–17: 1st-level spells → caster level 1st (minor slot 06–60); 2nd-level spells → CL 3rd.
- Wand Costs table, Sorcerer column: 1st-level spell **750 gp**; 2nd-level spell **6,000 gp**.
- Wand cost re-confirmed on a current-site AoN UC page: "a wand of burning hands, which has a price of 750 gp" — https://aonprd.com/Rules.aspx?ID=1436 (Ultimate Campaign pg. 174, Using Components example; live-fetched 2026-09-02).
- Gap: no per-item current-site page for "Wand of Burning Hands" was located (https://aonprd.com/MagicItemsDisplay.aspx?ItemName=Wand%20of%20Burning%20Hands returns 404 on the current site); the 750 gp price stands on the Wands pricing formula + Table 15–17 and the UC example page above.

**Use rules** — URL: https://aonprd.com/Skills.aspx?ItemName=Use%20Magic%20Device (Source PRPG Core Rulebook pg. 108). Exact claims:
- "Normally, to use a wand, you must have the wand's spell on your class spell list." → a sorcerer uses a wand of burning hands/scorching ray without any check.
- UMD table: "Use a wand | 20"; "Failing the roll does not expend a charge."

**One fitting wand:** **Wand of burning hands** (CL 1, 750 gp, 50 charges = 15 gp/charge — the 15 gp/charge minimum is stated on https://aonprd.com/Rules.aspx?ID=1430). A wand of scorching ray (2nd-level spell) prices at 6,000 gp (sorcerer column) — above the level-5 heroic NPC gear budget (see §6).

**Other magic gear:** A current-site [Cloak of Resistance](https://aonprd.com/MagicWondrousDisplay.aspx?FinalName=Cloak%20of%20Resistance1) snapshot verifies the +1 cloak at 1,000 gp and its +1 resistance bonus on all saves. It fits the 1,400 gp Protection allocation. No staff pricing was verified, so no staff is asserted.

## 6. NPC heroic ability/gear rows (archived Creating NPCs page)

Source: current-site AoN page https://aonprd.com/Rules.aspx?Name=Creating%20NPCs&Category=- (live-fetched 2026-09-02; content identical to the local archive `sources/reference/aonprd/creating-npcs.html` — PRPG Core Rulebook pg. 448 ff.). Exact claims from the live page:

- Heroic NPC ability scores: "The ability scores for a heroic NPC are: 15, 14, 13, 12, 10, and 8." (Basic: 13, 12, 11, 10, 9, 8.)
- "Apply the NPC's racial modifiers after the scores have been assigned. For every four levels the NPC has attained, increase one of its scores by 1."
- Table 14–6, Arcane NPC, Heroic column (exact): Str 8, Dex 14, Con 12, Int 15*, Wis 10, Cha 13* — with the footnote: "*If the arcane caster's spellcasting relies on Charisma, exchange these scores with one another." → for a sorcerer: Int 13, Cha 15 before racial modifiers.
- Combined with goblin racial modifiers (§1: +4 Dex, –2 Str, –2 Cha), the preset becomes Str 6, Dex 18, Con 12, Int 13, Wis 10, Cha 13. The required level-4 ability increase can then raise Charisma to 14.
- Table 14–9: NPC Gear, row "Basic Level 6 | Heroic Level 5" (exact): Total gp value **3,450 gp**; Weapons 1,400 gp; Protection 1,400 gp; Magic **—**; Limited Use 450 gp; Gear 200 gp. (First nonzero Magic allocation in the table is 500 gp at Basic 8 / Heroic 7.)
- Wand classification (exact, same page): "Weapons: This includes normal, masterwork, and magic weapons, as well as magic staves and wands used by spellcasters to harm their enemies. For example, a wand of scorching ray would count as a weapon, but a staff of life would count as a piece of magic gear." → A wand of burning hands for this spellcaster NPC counts against the **Weapons** budget (1,400 gp at Heroic 5), not the "—" Magic column: the 750 gp wand fits cleanly. A 6,000 gp wand of scorching ray fits neither the Weapons budget nor the 3,450 gp total.

## 7. Suggested level-5 stat block skeleton (all values sourced above)

Goblin sorcerer 5 — derived ability scores Str 6, Dex 18, Con 12, Int 13, Wis 10, Cha 14 after the level-4 increase; hp 22 from five average d6 Hit Dice plus Constitution; BAB +2; base saves Fort +2, Ref +5, Will +4 before feats and gear; fire resistance 10. Base spells/day are 1st ×6 and 2nd ×4, increased to 7 and 5 by Charisma 14; spells known are 6/4/2 plus burning hands and scorching ray from the bloodline. Elemental ray is 1d6+2 fire, 5/day. The 3,450 gp gear budget includes a 750 gp wand of burning hands and a 1,000 gp cloak of resistance +1. The implemented fixture's Iron Will, Lightning Reflexes, and cloak produce final saves +3/+8/+7. No CR is asserted because this source gate does not include the classed-NPC CR rule.

## Sources index

| Claim | URL / file |
|---|---|
| Goblin PC racial traits, favored class option | https://aonprd.com/RacesDisplay.aspx?ItemName=Goblin |
| Goblin NPC stat block (CR 1/3) | https://aonprd.com/MonsterDisplay.aspx?ItemName=Goblin |
| Sorcerer table, spells known, class features | https://aonprd.com/ClassDisplay.aspx?ItemName=Sorcerer |
| Elemental bloodline (fire) | https://aonprd.com/BloodlineDisplay.aspx?ItemName=Elemental |
| Burning Hands | https://aonprd.com/SpellDisplay.aspx?ItemName=Burning%20Hands |
| Scorching Ray | https://aonprd.com/SpellDisplay.aspx?ItemName=Scorching%20Ray |
| Flaming Sphere | https://aonprd.com/SpellDisplay.aspx?ItemName=Flaming%20Sphere |
| Other selected spells | Current `SpellDisplay.aspx` pages listed and hashed individually in `sources/npc/MANIFEST.json` |
| Wand rules + Table 15–17 | https://aonprd.com/Rules.aspx?Name=Wands&Category=Magic%20Items |
| Wand of burning hands = 750 gp (example) | https://aonprd.com/Rules.aspx?ID=1436 |
| Wand recharge/15 gp-charge context | https://aonprd.com/Rules.aspx?ID=1430 |
| Bluff, Spellcraft, and Use Magic Device | Current `Skills.aspx` pages listed and hashed individually in `sources/npc/MANIFEST.json` |
| Cloak of Resistance +1 | https://aonprd.com/MagicWondrousDisplay.aspx?FinalName=Cloak%20of%20Resistance1 |
| Heroic NPC abilities + Table 14–9 gear (current site, live) | https://aonprd.com/Rules.aspx?Name=Creating%20NPCs&Category=- |