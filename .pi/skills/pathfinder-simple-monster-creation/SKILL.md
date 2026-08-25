---
name: pathfinder-simple-monster-creation
description: Create, convert, or audit Pathfinder RPG monsters by following Pathfinder Unchained's Simple Monster Creation Steps 1–9 exactly, using the local Pathfinder Unchained, Bestiary, and Core Rulebook PDFs plus their extracted TXT files for rule validation, spell levels, and damage references.
---

# Pathfinder Unchained: Simple Monster Creation

## Purpose

Use this skill to build Pathfinder RPG monsters with the **Simple Monster Creation** system from *Pathfinder Unchained*, following the source in order from Step 1 through Step 9. This is a source-anchored workflow, not a replacement rules system.

- Apply source-defined rules and choices only. Strict Mode does not apply arbitrary manual Reality Check or Golden Rule value edits.
- Preserve the source's terminology: **array**, **graft**, **good skill**, **master skill**, **combat/magic/social/universal option**, **ability DC**, and **spell DC**.
- When a source rule is needed, read the relevant extracted `.txt` file; use the corresponding PDF only to resolve tables, layout, or ambiguous extraction.
- If a referenced spell or Bestiary rule has no local source entry, report the unresolved source gap instead of inferring its value.
- If the user asks for an exact procedure or exact rule, quote or closely transcribe the source instead of paraphrasing it.

## Local source files and page map

Resolve these paths relative to this `SKILL.md` (the skill directory is `.pi/skills/pathfinder-simple-monster-creation/`):

- Simple Monster Creation PDF: `../../../Pathfinder Unchained.pdf`
- Simple Monster Creation text: `../../../Pathfinder Unchained.txt`
- Bestiary supplemental PDF: `../../../beastiary.pdf` (filename supplied by the user)
- Bestiary supplemental text: `../../../beastiary.txt`
- Core Rulebook supplemental PDF: `../../../Pathfinder_RPG_Core_Rulebook.pdf`
- Core Rulebook supplemental text: `../../../Pathfinder_RPG_Core_Rulebook.txt`

Use the extracted `.txt` files for searchable agent access. The PDFs are the visual verification sources. The PDF is an excerpt whose first PDF-viewer page is printed page 194. The table below gives both page conventions and the current 1-indexed line ranges in the extracted text. The text ranges include extracted page headers, page numbers, and form-feed boundaries.

| Section | Printed PDF pages | PDF viewer pages | `Pathfinder Unchained.txt` lines |
|---|---:|---:|---:|
| Before You Begin, overview, Other Calculations, Golden Rule | 194–195 | 1–2 | 1–187 |
| Step 1: Array | 196–203 | 3–10 | 188–801 |
| Step 2: Creature Type or Class Graft | 204–213 | 11–20 | 802–1750 |
| Step 3: Subtype Graft | 214–215 | 21–22 | 1751–1938 |
| Step 4: Template Graft | 216 | 23 | 1939–2090 |
| Step 5: Size Graft | 217 | 24 | 2091–2135 |
| Step 6: Spells | 218–227 | 25–34 | 2136–3131 |
| Step 7: Monster Options | 228–239 | 35–46 | 3132–4333 |
| Step 8: Skills | 240 | 47 | 4334–4409 |
| Step 9: Damage | 241 | 48 | 4410–4497 |

When citing a rule, use both forms, for example: `Pathfinder Unchained.pdf, printed p. 228 (PDF viewer p. 35); Pathfinder Unchained.txt, lines 3132–4333.` For supplemental data, cite the same way, for example: `beastiary.pdf, printed p. 302 (PDF viewer p. 2); beastiary.txt, lines 148–160.` If a future edit changes a text file, re-run the line search and update the line reference rather than trusting stale line numbers.

### Supplemental source map

| Supplemental use | PDF reference | Extracted text reference |
|---|---|---|
| Bestiary Table 1–1: Monster Statistics by CR | `beastiary.pdf`, printed p. 291, viewer p. 1 | `beastiary.txt`, lines 1–68 |
| Bestiary natural-attack rules and Table 3–1: Natural Attacks by Size | `beastiary.pdf`, printed p. 302, viewer p. 2 | `beastiary.txt`, lines 68–165 |
| Core class spell lists and spell-level entries | `Pathfinder_RPG_Core_Rulebook.pdf`, printed pp. 224–239, viewer pp. 1–16 | `Pathfinder_RPG_Core_Rulebook.txt`, lines 1–1672 |
| Core spell entries present in the supplied excerpt | `Pathfinder_RPG_Core_Rulebook.pdf`, printed p. 239, viewer p. 16 | `Pathfinder_RPG_Core_Rulebook.txt`, lines 1673–1749 |

`Pathfinder Unchained.txt` remains authoritative for Simple Monster Creation list membership, CR bands, benefits, grafts, and options. `beastiary.txt` supplies the referenced Bestiary tables. `Pathfinder_RPG_Core_Rulebook.txt` supplies Core spell class/level metadata. Spell names marked APG, UM, or UC require an additional local source entry before their level or legality is treated as known.

## Source lookup protocol

- For Steps 1–5 and 7–8, read the relevant range of `Pathfinder Unchained.txt` before selecting or applying a rule.
- For Step 6, read the relevant Unchained spell-list range first, then cross-reference Core spell levels in `Pathfinder_RPG_Core_Rulebook.txt`. Treat any APG/UM/UC spell without a local source entry as unresolved.
- For Step 9, read `beastiary.txt` Table 3–1 before assigning natural-attack dice and Table 1–1 when a CR-based damage benchmark is needed.
- Use the PDFs only when the extracted text makes a table or rule ambiguous, and cite both the PDF page and TXT range in the result.

## Required workflow

### Before You Begin: Monster Concept

This is the source's pre-step setup (PDF printed pp. 194–195; text lines 1–187). Establish the monster concept before selecting an array:

1. Decide the target **CR** and the monster's main role in the story and encounter.
2. Decide the creature type, subtype, class identity (if any), template (if any), size, movement modes, and main combat/social/magic function.
3. If using a class graft or template graft, inspect its required/suggested array before Step 1.
4. Record the initial concept so the final **Reality Check** can compare the finished monster against it.

A monster can be changed if needed to fit the concept, but Strict Mode reports baseline mismatches rather than applying arbitrary manual value changes.

### Step 1: Array

**Source:** PDF printed pp. 196–203 (viewer pp. 3–10); text lines 188–801.

Choose exactly one baseline array unless a later source rule says otherwise:

- **Combatant:** primarily physical power; high attacks, hit points, and defenses; weak skills; mostly combat options.
- **Expert:** skills, interaction, and cunning tactics; moderate general statistics; strong skills and flexible options.
- **Spellcaster:** primarily magic; weaker physical combat; automatically receives spells through Step 6.

If a class graft or template requires a particular array, follow that requirement. Read the appropriate main-statistics and attack-statistics tables for the chosen array and the monster's CR. Record the entries as follows:

- CR, AC, touch AC, flat-footed AC, Fortitude/Reflex/Will, CMD, hp, ability DC, and spell DC.
- Swap two saving throws only when that better fits the monster, as permitted by the array instructions.
- Assign the array's three listed **ability modifiers** to the monster's three most important abilities. These are modifiers, not ability scores. All other ability modifiers default to +0 unless a source rule or concept gives a penalty.
- Record the array's master-skill and good-skill bonuses and counts. A notation such as `+11 (2)` means two master skills at +11.
- Record the number and categories of options: combat, magic, social, universal, or any.
- Choose the attack presentation from the array's attack table: high/low weapon attacks or the two-/three-natural-attack columns. Use high values for main attacks and low values for weaker or secondary attacks; mixing attack and damage columns is allowed when the source recommends it.
- Record attack bonuses and **average damage values** now. Damage dice are assigned only in Step 9.

Array numbers are already the monster's totals. Do not recalculate AC, attack bonuses, saving throws, skills, or similar values from ability modifiers, Hit Dice, armor, class levels, or items after recording the array. Later grafts and options adjust only the values they explicitly name. Use the source's DC rule: non-spell abilities use the ability DC; a spell adds its spell level (using the cleric or sorcerer/wizard level when applicable, otherwise the highest spell level in the spell description) to the array's spell DC.

### Step 2: Creature Type or Class Graft

**Source:** PDF printed pp. 204–213 (viewer pp. 11–20); text lines 802–1750.

Choose whether the monster is primarily defined by its creature type or by a character class:

- For a type-defined monster, apply the relevant creature-type graft, including automatic traits, statistic adjustments, and any desired elective adjustments.
- For a class-defined monster, apply the class graft and use its **Required Array**. Still select the appropriate creature-type graft for automatic traits, but do not apply that type graft's statistic adjustments when the monster has a class graft.

For creature-type grafts, apply:

1. **Automatic Traits** exactly as listed.
2. **Statistic Adjustments** exactly as listed, unless a class graft prevents them.
3. **Elective Adjustments** only when chosen and appropriate; these commonly suggest skills, spells, or options.

For class grafts, read and apply the relevant sections:

- Special Rules.
- Required Array.
- Statistic Adjustments.
- The highest applicable CR entry only (do not stack lower CR entries with it). Class-graft options replace array-granted options unless the source says otherwise.
- Suggested Ability Modifiers, Suggested Options, and Suggested Spell Lists.

Keep any decisions deferred by the graft for the later step where the graft says to make them.

### Step 3: Subtype Graft (Optional)

**Source:** PDF printed pp. 214–215 (viewer pp. 21–22); text lines 1751–1938.

If the monster has a subtype, apply every listed subtype ability. Subtype abilities are automatic, not optional. Unlike template automatic traits, subtype-granted options and skills do **not** count against the monster's normal option or skill allotment; they are added on top of it. Include all relevant subtypes, including racial subtypes, even when a subtype has no entry in this chapter.

Use the source's “Other Subtypes” and “Complex Subtypes” guidance rather than fabricating a graft for a subtype the chapter explicitly excludes.

### Step 4: Template Graft (Optional)

**Source:** PDF printed p. 216 (viewer p. 23); text lines 1939–2090.

If the monster imitates a listed template, check the template's:

- Minimum or maximum CR.
- Required creature type or subtype.
- Suggested array.
- Automatic traits.
- Suggested ability modifiers.

Template automatic traits replace the normal allotment where applicable and **do** count against normal options, skills, and similar limits, unlike subtype grafts. Apply all automatic traits even if they exceed the normal maximum. If a class graft is also present, use judgment to preserve the important class and template abilities while following the source.

### Step 5: Size Graft (Optional)

**Source:** PDF printed p. 217 (viewer p. 24); text lines 2091–2135.

The baseline monster is Medium. If it is another size, apply the corresponding size graft. These grafts adjust only the values listed in the source; do not import the normal core-rule size recalculations for AC, hit points, attacks, or damage.

Apply these source adjustments:

| Size | Restrictions | Adjustments |
|---|---|---|
| Fine | CR 2 or lower | touch AC +8, flat-footed AC +8, CMB –16, CMD –8; Fly and Stealth as additional master skills |
| Diminutive | CR 4 or lower | touch AC +4, flat-footed AC +4, CMB –8, CMD –4; Fly and Stealth as additional master skills |
| Tiny | CR 6 or lower | touch AC +2, flat-footed AC +2, CMB –4, CMD –2; Fly as an additional good skill (or increase good to master) and Stealth as an additional master skill |
| Small | none listed | touch AC +1, flat-footed AC +1, CMB –2, CMD –1; Stealth as an additional good skill |
| Large | CR 2 or higher | touch AC –1, flat-footed AC +1, CMB +2, CMD +1 |
| Huge | CR 4 or higher | touch AC –2, flat-footed AC +3, CMB +4, CMD +2; cannot have Stealth as a master skill |
| Gargantuan | CR 6 or higher | touch AC –4, flat-footed AC +5, CMB +8, CMD +4; cannot have Fly as a master skill or Stealth as a good/master skill |
| Colossal | CR 8 or higher | touch AC –8, flat-footed AC +6, CMB +16, CMD +8; cannot have Fly or Stealth as a good/master skill |

Touch AC never exceeds total AC, and flat-footed AC never falls below 1.

### Step 6: Spells (Optional)

**Source:** PDF printed pp. 218–227 (viewer pp. 25–34); text lines 2136–3131.

Use this step for a spellcaster array. A non-spellcaster that only knows a few spells should normally use another array and take **secondary magic** in Step 7 instead.

When using the spellcaster array:

1. Choose the spell list that best matches the monster's theme, class graft, bloodline, domain, patron, or other source guidance.
2. In the monster's CR band, select the listed **primary spells**, usable once per day.
3. From the band one step below the monster's CR band, use both primary and secondary spells three times per day.
4. From the band two steps below the monster's CR band, use the primary spells at will.
5. Remember the source restriction that CR 0–3 monsters receive no at-will or three-times-per-day spell sets, and CR 4–7 monsters receive no at-will spell set.
6. Apply the benefit at the bottom of the chosen spell list.

The source's CR bands are 0–3, 4–7, 8–11, 12–15, and 16+. If selecting individual spells instead of a list, use the source's spell-level bands: 0/1st, 2nd/3rd, 4th/5th, 6th/7th, and 8th/9th. Spell DCs use the Step 1 spell-DC column plus the spell's level as described in Step 1. Use `Pathfinder Unchained.txt` for the selected list, uses, and list benefit; use `Pathfinder_RPG_Core_Rulebook.txt` for Core spell levels by class. For APG/UM/UC spells, consult a supplied supplemental source. If the spell is not present locally, mark it unresolved and do not guess its level or legality.

### Step 7: Monster Options

**Source:** PDF printed pp. 228–239 (viewer pp. 35–46); text lines 3132–4333.

Options replace the normal feat, universal-monster-rule, magic-item, and special-ability selection process. Use the counts and categories supplied by the chosen array and all grafts.

- Categories are **combat**, **magic**, **social**, and **universal**.
- Combat options are grouped as cunning, monstrous, powerful, quick, and tough; magic options as creature, offensive, support, and versatile; social options as inspiration and miscellaneous.
- A universal option can be selected in place of any category. An **any** slot can select from any category, including universal.
- Options from grafts may replace array options, add to them, or be free, according to the graft's exact wording.
- Duplicate options are generally allowed when they make sense; check the source entry and reality-check the result.
- Unless specified otherwise, use the monster's ability DC for option saving throws.
- When an option refers to high or low damage, use the high/low **weapon** damage value from Step 1, not the natural-attack damage column, unless the source explicitly says otherwise.
- Many options simplify universal monster rules. Use the simplified option wording in this chapter and use the array ability DC instead of recalculating a Bestiary DC. For an unmodified rule not covered by an option, use the Bestiary rule and apply the source's guidance on whether it costs an option.

Read the exact option entry before applying it. Record each option and the statistics/abilities it changes. After selecting the prescribed options, perform the source's check for whether the monster has too few or too many abilities. In Strict Mode, report that mismatch; add or remove an option only when a source array or graft explicitly grants it or the user makes a separate, out-of-scope manual change.

### Step 8: Skills

**Source:** PDF printed p. 240 (viewer p. 47); text lines 4334–4409.

Assign the array's and grafts' skills as **master** or **good**:

- A master skill uses the array's master bonus; a good skill uses the array's good bonus.
- Unlisted skills default to the relevant ability modifier.
- Perception automatically uses the good skill modifier without spending a good-skill slot; Perception can still be raised to master.
- Graft, spell-list, subtype, template, and option-granted skills are handled exactly as their entries say.
- Do not add the monster's ability modifier on top of a listed good/master bonus. For example, a listed +17 master skill remains +17 even if the corresponding ability modifier is +7.
- Choose skills that fit the highest ability modifiers and the monster's concept. Keep the total close to the source's allotment unless a source graft or option changes it.

### Step 9: Damage

**Source:** PDF printed p. 241 (viewer p. 48); text lines 4410–4497.

The array supplies average damage, not damage dice. For each attack, cross-reference its total average damage and the weapon/natural-attack die size in the source's **Table 5–9: Damage Dice Values**. For natural attacks, read **Table 3–1: Natural Attacks by Size** in `beastiary.txt` (lines 148–160) and use its damage die, damage type, and primary/secondary classification.

If the monster needs more attacks than the array column provides, follow the source's exact process:

1. Combine the relevant array damage values into a total.
2. If many are secondary attacks, increase the total by 25% or 50% as appropriate.
3. Divide the total among the attacks, unevenly if the concept calls for a stronger primary attack.
4. Alternatively, use the **extra attack** option when both attack count and damage output should increase.

Use `beastiary.txt` Table 1–1 (lines 5–24) for the source's CR-based average-damage benchmarks when the Golden Rule discusses additional attacks. Strict Mode keeps Step 1 average damage unchanged except for a source-defined option or graft; report any mismatch for review instead of changing it.

## Calculations performed after the nine steps

Use the source's “Other Calculations” guidance (PDF printed p. 195; viewer p. 2; text lines 168–187):

- **CMB:** equal to the monster's high attack bonus, with explicit graft/size/option adjustments.
- **Concentration:** CR plus the most applicable ability modifier; for spell-like abilities this is typically Charisma.
- **Hit Dice:** equal to CR for calculations; treat CR below 1 as 1 Hit Die.
- **Initiative:** Dexterity modifier unless modified by improved initiative, a graft, or an ad hoc adjustment.
- **Perception:** automatically uses the good skill modifier unless master Perception is assigned.
- **Speed:** assign appropriate speed and movement modes; these do not cost monster options unless the source says otherwise.

## Final reality check

Compare the finished monster with the initial concept and `beastiary.txt` Table 1–1 benchmarks. Check offense, defense, saves, hit points, attack count, damage, DCs, action economy, movement, resistances/immunities, skills, and spell access. In Strict Mode, this is a validation report: it identifies mismatches but does not apply arbitrary Golden Rule or Reality Check changes.

## Output protocol for monster-building requests

1. Ask only for missing concept inputs needed to begin; do not guess a CR or role when it matters.
2. Work through the steps in order and label every decision `Before You Begin`, `Step 1`, ..., `Step 9`.
3. At each step, show the chosen source entry, the values taken from it, and any adjustments applied.
4. Cite both the printed PDF page (and PDF viewer page) and the `.txt` line range for the step or rule being used.
5. Separate source-derived values from discretionary concept choices and unresolved validation warnings. Strict Mode has no user-defined adjustment layer.
6. Cite supplemental Bestiary or Core Rulebook references whenever they contribute to a calculation or spell validation.
7. Finish with a Pathfinder-style formatted statblock. Keep the statblock's defenses, attacks, spells, options, skills, and statistics consistent with the decisions recorded in Steps 1–9.
