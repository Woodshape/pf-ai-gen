# Elemental Ally Source Assessment (gate sign-off)

Verdict: the source gate for the Elemental Ally slice **passes**. All four required AoN
pages are archived and hash-anchored; every level-3 fire eidolon row value below is
resolvable from their line-citable extracts. No remembered values were used.

## Archived sources

| sourceId | Extract | Upstream |
|---|---|---|
| `source.aon-elemental-ally` | `sources/npc/aonprd/elemental-ally.txt` (16 lines) | `ArchetypeDisplay.aspx?FixedName=Druid Elemental Ally`, Monster Summoner's Handbook pg. 16 |
| `source.aon-eidolon-unchained` | `sources/npc/aonprd/eidolon-unchained.txt` (46 lines) | `ClassDisplay.aspx?ItemName=Eidolon (Unchained)`, Table 1–6 Eidolon Base Statistics |
| `source.aon-eidolon-uc-subtypes` | `sources/npc/aonprd/eidolon-uc-subtypes.txt` (12 lines) | `EidolonUCSubtypes.aspx`, "Elemental" subtype, Pathfinder Unchained pg. 33 |
| `source.aon-eidolon-base-forms` | `sources/npc/aonprd/eidolon-base-forms.txt` (3 lines) | `EidolonBaseForms.aspx`, "Quadruped", Advanced Player's Guide pg. 60 |
| `source.aon-eidolon-base-forms-biped` | `sources/npc/aonprd/eidolon-base-forms-biped.txt` (3 lines) | `EidolonBaseForms.aspx`, "Biped", Advanced Player's Guide pg. 60 (reference only) |
| `source.aon-eidolon-uc-base-forms-biped` | `sources/npc/aonprd/eidolon-uc-base-forms-biped.txt` (3 lines) | `EidolonUCBaseForms.aspx`, "Biped", Pathfinder Unchained pg. 34 |
| `source.aon-summoner-uc-evolutions-slam` | `sources/npc/aonprd/summoner-uc-evolutions-slam.txt` (1 line) | `SummonerUCEvolutions.aspx`, "Slam", Pathfinder Unchained pg. 36 |

Note: the archetype detail URL uses `FixedName=`, not `ItemName=`; `ItemName=Elemental%20Ally`
returns AoN's "Sequence contains no elements" error page.

## Gate certification

1. **Exists on AoN.** The Druid archetype index (`Archetypes.aspx?Class=Druid`) lists
   Elemental Ally (PFS Legal); its detail page is archived at
   `elemental-ally.txt` line 1 with source line 2 ("Source Monster Summoner's Handbook pg. 16").
2. **Replacements per the archived text.** "This ability replaces nature's bond and wild
   shape" (`elemental-ally.txt:7`); "This ability replaces wild empathy" (`:11`, Elemental
   Empathy); "This ability replaces resist nature's lure" (`:13`, Elemental Resistance at 4th).
   Druid 3 needs only the first two: Nature Bond (level 1) and Wild Empathy (level 1).
   Wild Shape (4th) and Resist Nature's Lure (4th) are recorded as replaced but resolve no
   Druid-3 statistic.
3. **Druid 3 mapping.** "Their abilities and statistics are determined using the rules for
   elemental eidolons for the summoner class from page 33 of Pathfinder RPG Pathfinder
   Unchained, as if the elemental ally were a summoner of her druid level, except they gain
   no additional evolution pool (just those evolutions from their base form and base
   evolutions from their subtype)" (`elemental-ally.txt:4`; continued at `:6`). So Druid 3 is
   a summoner level 3 with **no evolution pool**: the row uses only base-form evolutions and
   subtype base evolutions. Table 1–6 row "3rd" (`eidolon-unchained.txt:8`) and the Elemental
   subtype of PFU pg. 33 (`eidolon-uc-subtypes.txt:2`) are exactly the cited rules.
4. **Level-3 fire row fully resolvable.** The unchained eidolon base statistics row
   (`eidolon-unchained.txt:8`), the PFU Biped base form starting statistics
   (`eidolon-uc-base-forms-biped.txt:3`), the Slam evolution (`summoner-uc-evolutions-slam.txt:1`),
   the Elemental subtype base-form list (`eidolon-uc-subtypes.txt:5`),
   and the archived Core combat rules resolve every required field.

## Curated selection: Biped base form with its slam attack

The archetype states "Each of the four elementals has its own base form, skills, and feats"
(`elemental-ally.txt:5`), and the Elemental subtype lists four source-authorized base forms:
Aberrant, Biped, quadruped, or serpentine (`eidolon-uc-subtypes.txt:5`). The bounded slice
resolves exactly one row, so the fire eidolon's form is pinned to **Biped** as an
explicit curated selection (not a rule value). The other three forms and unpinned
skill/feat assignments remain explicit non-resolved choices; only the row values below are
resolved. Skill ranks (12) and feats (2) stay source-backed budgets without assignments.

The subtype's base-form list grants Biped "limbs (arms), limbs (legs), slam"
(`eidolon-uc-subtypes.txt:5`). The PFU Slam evolution deals 1d8 as a primary attack and
can "replace the claws from its base form" (`summoner-uc-evolutions-slam.txt:1`), so the
biped elemental eidolon attacks with one slam instead of the generic PFU biped claw line.
The biped requires limbs (arms) for the slam; the subtype grants them. The generic APG
Biped extract (`eidolon-base-forms-biped.txt`) is retained for reference only.

## Level-3 fire elemental eidolon row (derivation with archived lines)

Inputs: unchained eidolon at class level 3 (`eidolon-unchained.txt:8`, summoner level per
`:26`), no evolution pool (`elemental-ally.txt:4`), PFU Biped base form
(`eidolon-uc-base-forms-biped.txt:3`), Elemental subtype base-form list and fire base
evolutions at 1st level (`eidolon-uc-subtypes.txt:5,7`).

| Value | Derivation | Lines |
|---|---|---|
| Type outsider | "Eidolons are outsiders" | `eidolon-unchained.txt:3` |
| Alignment Neutral | subtype alignment | `eidolon-uc-subtypes.txt:4` |
| Size Medium; speed 30 ft. | PFU Biped starting statistics | `eidolon-uc-base-forms-biped.txt:3` |
| HD 3 (d10, +Con each); hp 19 | floor(3 × (5.5 + 1)) = 19.5, round down | `eidolon-unchained.txt:8,27`; `getting-started.txt:39` |
| BAB +3 | 3rd row; BAB equals HD | `eidolon-unchained.txt:8,28` |
| Armor total +4 = table +2 + form +2 natural | table armor "modified by the base form" | `eidolon-unchained.txt:8,32`; `eidolon-uc-base-forms-biped.txt:3` |
| AC 15, touch 11, flat-footed 14 | 10 + 4 + Dex +1; touch drops armor; flat-footed drops Dex | `combat.txt:35,41` |
| Fort +4, Ref +2, Will +3 | good/poor/good per form; +3 good/+1 bad at 3rd; +Con 1, +Dex 1, +Wis 0 | `eidolon-uc-base-forms-biped.txt:3`; `eidolon-unchained.txt:8,29` |
| Slam +6 (1d8+4) | subtype grants Biped slam; slam evolution 1d8, primary attack; BAB + Str +3; sole natural attack adds 1–1/2 Str (+4) | `eidolon-uc-subtypes.txt:5`; `summoner-uc-evolutions-slam.txt:1`; `eidolon-unchained.txt:8,33`; `combat.txt:195` |
| Str 17, Dex 13, Con 13, Int 7, Wis 10, Cha 11 | form starting scores + Str/Dex bonus +1 | `eidolon-uc-base-forms-biped.txt:3`; `eidolon-unchained.txt:8,33` |
| Initiative +1 | Dexterity modifier | `combat.txt:13` |
| CMB +6; CMD 17 | BAB + Str + size 0; 10 + BAB + Str + Dex | `combat.txt:539-544` |
| Darkvision 60 ft. | 1st-level special | `eidolon-unchained.txt:37` |
| Link, share spells, evasion | 1st/2nd-level specials | `eidolon-unchained.txt:38-40` |
| Immunity to paralysis and sleep; immunity (fire) | 1st-level base evolutions, all elemental / fire | `eidolon-uc-subtypes.txt:7` |
| Cannot wear armor | Armor Bonus rule | `eidolon-unchained.txt:32` |
| 12 skill ranks; 2 feats; max 3 attacks | 3rd-row values; assignments unpinned | `eidolon-unchained.txt:8,30,31,35,46` |

Ability modifiers: Str 17 +3, Dex 13 +1, Con 13 +1, Int 7 −2, Wis 10 +0, Cha 11 +0
(`getting-started.txt` ability-modifier table, already anchored).

## Elemental Empathy (Druid 3 consequence)

"An elemental ally rolls 1d20 and adds her druid level and her Charisma modifier"
(`elemental-ally.txt:8`), replacing Wild Empathy (`:11`). The archetype feature entry
carries the check bonus where the Wild Empathy feature previously carried it.

## Remaining gaps

Druid levels other than 3, other elements (air/earth/water rows), the Aberrant/Biped/
Serpentine base forms, other archetypes, animal companions, eidolon levels other than 3,
and eidolon skill/feat assignments remain explicit source gaps.