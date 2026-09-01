# Detailed Plan: Class-Based NPC Creation System

## 1. Decisions and terminology

### Use `creationSystem`, not `mode`

`mode` already means **Strict Mode / Free Mode** in `CONTEXT.md`, and `FinishedMonster.mode` is currently hard-coded to `"strict"`.

Add an independent axis:

```json
{
  "creationSystem": "simple-monster"
}
```

Allowed values:

- `simple-monster` — current Pathfinder Unchained array/graft system
- `npc` — Core Rulebook class-based NPC creation

Keep `mode: "strict"` orthogonal. Do not create a hybrid calculation mode.

### NPC creation is not a PC builder

NPC creation should produce mechanically normal, class-based Pathfinder statblocks, but it still uses:

- Basic/heroic NPC ability arrays
- NPC gear budgets
- Average HP
- Simplified skill generation when selected

A future PC builder could reuse the class evaluator with different ability, wealth, and HP policies. Do not promise PC character-sheet parity in this phase.

### Deterministic evaluation, not deterministic character design

Once selections are supplied, evaluation should be deterministic. The engine should not claim there is one correct feat, spell, skill, or item selection.

The engine owns:

- Legal choices
- Counts and budgets
- Prerequisites
- Derived calculations
- Source provenance

The user or proposal system owns:

- Which legal feat to choose
- Which skills to emphasize
- Which items to buy
- Which spells to prepare

---

# 2. Scope

## NPC system v1

Source scope:

- Seven Core races
- Five Core NPC classes:
  - Adept
  - Aristocrat
  - Commoner
  - Expert
  - Warrior
- Eleven Core PC classes listed in Table 14-8:
  - Barbarian, bard, cleric, druid, fighter, monk
  - Paladin, ranger, rogue, sorcerer, wizard
- Core feats
- Core equipment and magic items needed by supported builds
- Core spells
- Multiclassing
- Both simplified and precise skill generation
- Basic and heroic NPC gear tables
- Full and encounter-focused spell loadouts

## Explicit non-goals

Defer:

- Archetypes
- Prestige classes
- Traits
- Alternate racial traits
- Advanced Player’s Guide classes
- Monster racial Hit Dice
- Templates applied to NPCs
- Mythic rules
- Automatic build optimization
- SMC/NPC hybrid calculations
- AI proposal generation until manual creation is stable

---

# 3. The internal seam

The public interface remains:

```python
Engine.execute(request) -> response
```

Persistence, revision guards, history, proposals, finalization, exports, and library operations remain shared.

Introduce one real internal seam because there will now be two adapters:

```python
class CreationSystem(Protocol):
    key: str
    selection_fields: frozenset[str]

    def validate_input(self, draft) -> None: ...
    def choice_requirements(self, draft) -> dict: ...
    def evaluate(self, draft) -> dict: ...
    def creation_decisions(self, selections, trace) -> list[dict]: ...
```

Adapters:

- `SimpleMonsterCreation`
- `NpcCreation`

The deletion test supports this seam: without it, checks for `creationSystem` would spread through `engine.py`, `choices.py`, exports, and finalization.

## Responsibilities

### Shared `Engine`

- Request validation and idempotency
- Draft lifecycle
- Revision/fingerprint handling
- Persistence
- Proposal application
- Library search
- Finalization
- Export dispatch
- Selecting the creation-system adapter

### Creation-system adapter

- Allowed selection fields
- Selection shape and catalog ID validation
- Choice requirements and budgets
- Rules evaluation
- Canonical result
- Derivation trace
- Step-to-audit mapping

### Exports

Exports remain projections only. They must never calculate rules.

Both creation systems should emit a compatible canonical statblock shape, with NPC-only additions such as feats, equipment, languages, and class progression.

---

# 4. Catalog strategy

Do not add NPC data to the existing `catalog/catalog.json`. Its content hash is the current Simple Monster catalog version; changing it invalidates every persisted draft.

Add an independently versioned catalog:

```text
catalog/
├── catalog.json              # existing Simple Monster catalog
├── catalog.schema.json
├── npc.json                  # new NPC catalog
└── npc.schema.json
```

Add a small catalog registry:

```python
catalogs.for_system("simple-monster")
catalogs.for_system("npc")
```

Each draft’s existing `catalogVersion` refers to its creation system’s catalog.

Compatibility behavior:

- Draft missing `creationSystem` → treat as `simple-monster`
- Existing Simple Monster catalog and fingerprints remain accepted
- New drafts always write `creationSystem`
- Duplicating a legacy draft writes the explicit default
- Finished snapshots add `creationSystem`
- Existing `kind: "FinishedMonster"` and `monster.*` operations remain unchanged for compatibility

## NPC catalog sections

```json
{
  "schemaVersion": "1",
  "catalogVersion": "sha256:...",
  "sources": {},
  "abilityArrays": {},
  "gearBudgets": {},
  "races": {},
  "classes": {},
  "classFeatures": {},
  "skills": {},
  "feats": {},
  "items": {},
  "spells": {},
  "derivedRules": {}
}
```

### Class records

Each class should contain source-backed level rows rather than formulas inferred from progression names:

```json
{
  "id": "npc-class.ranger",
  "category": "pc",
  "hitDie": "d10",
  "classSkills": ["skill.climb", "skill.survival"],
  "skillSelections": 6,
  "levels": {
    "4": {
      "bab": 4,
      "fortitude": 4,
      "reflex": 4,
      "will": 1,
      "featureGrants": [],
      "choiceSlots": []
    }
  }
}
```

This makes source comparison, breakpoint testing, and multiclass summation straightforward.

### Feat prerequisites

Do not evaluate prerequisite prose. Store a typed prerequisite expression:

```json
{
  "all": [
    {"abilityAtLeast": {"dexterity": 13}},
    {"babAtLeast": 1},
    {"hasFeat": "feat.point-blank-shot"}
  ]
}
```

Supported operands should initially be limited to:

- Ability score
- BAB
- Character level
- Class level
- Skill ranks
- Race
- Alignment
- Existing feats
- Class features
- Spellcasting/caster level

Unknown prerequisite forms are catalog gaps, not guessed rules.

### Money

Store all prices as integer copper pieces. Never use floating-point gp.

---

# 5. Draft schema

Example:

```json
{
  "schemaVersion": "1",
  "creationSystem": "npc",
  "catalogVersion": "sha256:...",
  "concept": {
    "name": "Kiramor, the Forest Shadow",
    "role": "ranged forest guardian",
    "description": "Elf ranger 4/rogue 2",
    "targetCR": 5
  },
  "selections": {
    "statblockUse": "full",
    "raceId": "npc-race.elf",
    "racialChoices": {},
    "classProgression": [
      {"classId": "npc-class.ranger", "levels": 4},
      {"classId": "npc-class.rogue", "levels": 2}
    ],
    "abilityGeneration": {},
    "skillGeneration": {},
    "feats": [],
    "classFeatureChoices": {},
    "spellLoadout": {},
    "gearProfile": {},
    "gear": [],
    "details": {}
  }
}
```

## Derived, never selected

The following must not be writable selections:

- Total level
- Basic/heroic status
- BAB
- Saves
- HP
- AC
- Initiative
- Attacks and damage totals
- CMB/CMD
- Skill totals
- Spell DCs
- Gear budget totals
- Recommended CR

`targetCR` is concept guidance only. It must never adjust NPC statistics.

---

# 6. NPC creation workflow

## Before You Begin

Inputs:

- Name
- Role/concept
- Optional target CR
- `statblockUse`:
  - `full`
  - `encounter`

`encounter` permits source-authorized omissions such as unused lower-level spells and generic nonmagical gear. It does not change the NPC’s mechanical capabilities.

## Step 1: Basics

Selections:

- Race
- Ordered class progression
- Alignment
- Optional religion
- Relevant racial and class choices

Derived:

- Total level
- Basic vs heroic:
  - Any PC class level → heroic
  - NPC classes only → basic
- Size, speed, racial senses and traits
- Recommended CR, once separately sourced

Initial scope does not permit racial Hit Dice or templates.

## Step 2: Ability Scores

Supported methods:

### Assigned array

- Basic: 13, 12, 11, 10, 9, 8
- Heroic: 15, 14, 13, 12, 10, 8
- User assigns each value exactly once

### Preset role

- Melee
- Ranged
- Divine
- Arcane
- Skill
- Basic or heroic row derived automatically
- Arcane Charisma casters expose the source-defined Int/Cha swap

### Custom

The source explicitly allows custom adjustment for NPCs that do not fit the presets. Represent this as an intentional source-valid method rather than a hidden override:

```json
{
  "method": "custom",
  "scores": {},
  "rationale": "..."
}
```

Custom scores remain fully auditable but do not receive array-budget validation.

Calculation order:

1. Assigned/preset/custom base scores
2. Racial adjustments
3. One chosen +1 increase for every four total levels
4. Permanent item bonuses
5. Ability modifiers

All intermediate values go into the derivation trace.

## Step 3: Skills

Methods:

### Simplified

For one class:

- Number selected = class value + Int modifier
- Human bonus applied
- Selected skills receive ranks equal to class level

For two classes:

- Class with fewer selections supplies that many skills
- Those skills receive ranks equal to total character level
- Difference supplies new skills
- New skills receive ranks equal to the second class’s level

For three or more classes:

- Simplified method is invalid; require precise method

The source says selections should be “mostly” class skills but gives no enforceable ratio. Therefore:

- Highlight class skills
- Warn about unusual choices
- Do not invent a hard limit

### Precise

```json
{
  "method": "precise",
  "ranks": {
    "skill.perception": 6,
    "skill.stealth": 6
  }
}
```

Validate:

- Total rank budget
- Maximum ranks = total HD
- Class-skill +3
- Relevant ability modifier
- Armor check penalty
- Racial, feat, class-feature, and item bonuses

Open source question: confirm the minimum skill selections/ranks when Intelligence is negative.

## Step 4: Feats

Generate explicit feat slots:

```json
{
  "slotId": "general-5",
  "kind": "general",
  "grantedAtLevel": 5,
  "allowedFeatIds": []
}
```

Include:

- General feats
- Fighter bonus feats
- Ranger combat-style feats
- Monk bonus feats
- Wizard bonus feats
- Other class-specific feat slots

Selections must record the slot, not merely the final feat list. This allows prerequisites to be checked at the level the feat was acquired.

Validation:

- Exact slot counts
- Allowed feat categories
- Prerequisites at acquisition level
- Duplicate rules
- Mutually exclusive choices
- Typed numeric effects

The AONPRD Step 4 page is empty. Feat counts and prerequisites must be sourced from the character advancement table, feat chapter, and class tables rather than inferred from ID 357.

## Step 5: Class Features

Automatic features come from class level rows.

Choice slots include:

- Rage powers
- Rogue talents
- Favored enemies
- Favored terrains
- Ranger combat styles
- Hunter’s bond
- Cleric domains
- Sorcerer bloodlines
- Wizard schools
- Familiar/bond choices
- Similar Core class decisions

### Spellcasting

NPC spellcasting must use actual class rules:

- Caster level
- Casting ability
- Minimum ability score
- Spells per day
- Bonus spells
- Spells known
- Prepared vs spontaneous
- Domain/school/bloodline additions
- Save DC = 10 + spell level + casting modifier

This exposes a meaningful Kiramor difference: with Wisdom 10, ranger 4 does not have sufficient Wisdom to cast 1st-level ranger spells, even though the class has reached spellcasting level.

For `encounter` statblocks:

- Highest two spell levels must be complete
- Lower levels may be explicitly marked omitted
- Omission is recorded in the audit rather than silently filled

## Step 6: Gear

Inputs:

```json
{
  "gearProfile": {
    "experienceProgression": "medium",
    "fantasyLevel": "normal"
  }
}
```

Allowed values:

- Progression: slow, medium, fast
- Fantasy: low, normal, high

Derived budget:

1. Basic/heroic line
2. Effective gear level adjusted by progression
3. Fantasy multiplier
4. Weapon/protection/magic/limited-use/gear category targets

### Important clarification

Table 14-9 values are approximate, category leftovers may transfer, and the example explicitly permits modest over/underspending.

Therefore:

- Total and category deltas are reported
- Category targets are not hard caps
- No invented percentage tolerance
- A nonzero delta produces a warning, not an error
- Every selected item must still have a valid catalog price

Items need typed effects for:

- Armor and shields
- Weapon attack/damage/enhancement
- Ability enhancement
- AC bonuses
- Save bonuses
- Skill bonuses
- Movement
- Charged items
- Potions/scrolls/wands

Magic weapons and armor should be item instances whose price is calculated from base item, masterwork cost, enhancement bonus, and properties—not thousands of pre-generated catalog entries.

## Step 7: Details

Selections:

- Name
- Alignment
- Religion
- Languages
- Personality traits
- Attack presentation/order
- Combat gear vs other gear grouping

Derived in a fixed order:

1. Final ability scores/modifiers
2. Racial size modifiers
3. Class BAB and base saves
4. Hit Dice and average HP
5. Feat/class/item effects
6. Initiative
7. AC, touch AC, flat-footed AC
8. Attacks and damage
9. CMB/CMD
10. Skill totals
11. Spell statistics
12. Senses, defenses, qualities, and languages

Each total needs an auditable breakdown:

```json
{
  "path": "/canonical/defenses/reflex",
  "rule": "class base saves + Dexterity + resistance + miscellaneous",
  "inputs": [
    {"source": "ranger 4", "value": 4},
    {"source": "rogue 2", "value": 3},
    {"source": "Dexterity", "value": 4}
  ],
  "value": 11,
  "sourceRefs": []
}
```

---

# 7. Canonical result

Reuse the current common fields:

```json
{
  "creationSystem": "npc",
  "level": 6,
  "recommendedCR": 5,
  "npcCategory": "heroic",
  "raceId": "npc-race.elf",
  "classProgression": [],
  "abilityScores": {},
  "abilityModifiers": {},
  "hitDice": 6,
  "hitDiceExpression": "4d10+2d8+...",
  "bab": 5,
  "defenses": {},
  "attacks": [],
  "cmb": 6,
  "skills": {},
  "feats": [],
  "classFeatures": [],
  "spells": [],
  "gear": [],
  "languages": [],
  "specialAbilities": []
}
```

`defenses`, `attacks`, `skills`, `spells`, and `abilityModifiers` remain compatible with current exports and previews.

---

# 8. Choice-requirements interface

Keep the existing operation:

```json
{"operation": "draft.choiceRequirements"}
```

Extend its response without adding NPC-specific operations:

```json
{
  "creationSystem": "npc",
  "requirements": [],
  "automaticSelections": {
    "racialTraits": [],
    "classFeatures": [],
    "featGrants": []
  },
  "selectionBudgets": {
    "skills": {},
    "feats": {"slots": []},
    "spells": {},
    "gear": {
      "budgetCp": 465000,
      "spentCp": 0,
      "categories": {}
    }
  }
}
```

Requirements may identify nested slots such as:

```text
/selections/feats/2/featId
/selections/classFeatureChoices/ranger-1/favoredEnemy
```

Mutations can continue replacing the enclosing top-level selection field; no change to `draft.applyChanges` is necessary.

---

# 9. Web UI

Replace the fixed `STEPS` array with creation-system-specific workflow definitions.

## New draft flow

First choice:

- Simple Monster
- Class-Based NPC

This choice becomes immutable for the draft. Converting systems creates another draft later; it never mutates a draft’s rules system.

## NPC rail

1. Basics
2. Ability Scores
3. Skills
4. Feats
5. Class Features
6. Gear
7. Details

Required UI changes:

- Do not require target CR for NPC concept completion
- Show total level and basic/heroic classification
- Display feat slots and prerequisite failures
- Display class-feature slots by acquisition level
- Show gear target/spent/delta in cp/gp
- Show full calculation breakdowns
- Library rows show creation system and level/CR
- Preview adds ability scores, BAB, feats, gear, and class progression

Manual creation must ship before the AI panel understands NPC rules.

---

# 10. Implementation phases

## Phase 0 — Source and policy foundation

Deliverables:

- Locally hash-anchored source extracts for:
  - Core Rulebook pp. 448–454
  - Races
  - Character advancement
  - PC and NPC class tables
  - Skills
  - Feats
  - Equipment and magic items
  - Relevant spells
- ADR defining `creationSystem`
- `CONTEXT.md` terminology additions
- Source-gap matrix
- Kiramor calculation worksheet

Resolve before implementation:

- Average HP rounding
- Favored-class bonuses for NPCs
- CR formula for PC/NPC/mixed class progressions
- Minimum skills under negative Intelligence
- Gear-level behavior outside Table 14-9 boundaries
- Whether statblock examples contain errata

The current local Core Rulebook excerpt covers spells only; it is insufficient for NPC mode.

**Exit criterion:** no numeric rule in the first vertical slice depends solely on memory or the web page.

## Phase 1 — Extract the creation-system seam

Work:

- Add `creationSystem`, defaulting legacy drafts to `simple-monster`
- Add catalog registry
- Move Simple Monster selection validation, requirements, evaluation, and audit steps behind its adapter
- Keep `Engine.execute` unchanged
- Add creation system to library and finished snapshots
- Update finished validation to accept both systems
- Preserve old Simple Monster catalog version

**Exit criterion:** every existing test passes with byte-equivalent Simple Monster evaluations and exports.

## Phase 2 — One end-to-end NPC vertical slice

Support:

- Human
- Warrior levels 1–5
- Melee preset or assigned basic arrays
- Simplified skills
- General feat slots with a small source-backed feat subset
- Mundane weapons and armor
- Medium-progression normal-fantasy gear
- Full derived statistics
- JSON/Markdown/HTML finalization

Fixture: a human warrior 3 built only through public `Engine.execute`.

**Exit criterion:** create → requirements → applyChanges → valid evaluation → finalize → reload → export works without manual canonical values.

## Phase 3 — Complete basic NPC creation

Add:

- All seven Core races
- All five NPC classes through level 20
- Precise skills
- Adept spellcasting
- Core mundane equipment
- Relevant Core feats
- Full Table 14-9 boundaries and gear profiles
- NPC web rail

Fixtures:

- Commoner 1
- Warrior 3
- Expert 5
- Aristocrat multiclass example
- Adept caster

**Exit criterion:** every Table 14-6, 14-7, 14-8, and 14-9 row has source-parsing tests and public-interface coverage.

## Phase 4 — Heroic classes and Kiramor

Add all eleven Core PC classes, including:

- Full level tables
- Class choices
- Bonus feat slots
- Multiclass aggregation
- Prepared/spontaneous casting
- Core magic weapons, armor, potions, and common permanent items
- Core feat prerequisites and numeric effects

Kiramor becomes the principal acceptance fixture:

```json
{
  "race": "elf",
  "classes": [
    ["ranger", 4],
    ["rogue", 2]
  ],
  "abilityMethod": "ranged-preset"
}
```

The engine must reproduce every mechanically derivable value or emit an explicit documented source discrepancy.

**Exit criterion:** Kiramor can be created, finalized, and exported entirely through NPC selections.

## Phase 5 — Hardening and catalog completeness

- Remaining Core feats/items/spells
- All class-feature choice paths
- Encounter/full spell completeness
- Charged-item pricing
- Conditional bonuses
- Performance and catalog-validation tests
- AI proposal tooling updated for active creation system

---

# 11. Test strategy

Follow the repository’s current pattern: test through `Engine.execute`, not internal helpers.

## Source-table tests

Independently parse source text and compare against catalog entries:

- Every ability array row
- Every racial adjustment
- Every class level row
- Every skill-selection value
- Every gear row
- General feat progression

## Calculation tests

- Ability arrays: basic/heroic, permutations, racial modifiers, levels 4/8/12/16/20
- Single and two-class simplified skills
- Three-class precise-skill requirement
- BAB/save multiclass summation
- Feat prerequisites at acquisition level
- Gear progression and fantasy multipliers
- Armor/max-Dex/ACP interaction
- Weapon Finesse and ranged attacks
- HP and rounding
- Spell-access ability requirements
- CMB/CMD and size modifiers

## Lifecycle tests

For both creation systems:

- Persistence
- History/restore
- Duplicate
- Archive/restore
- Finalization idempotency
- Tamper detection
- JSON validation
- Markdown/HTML export
- Library search

## Regression rule

The entire current Simple Monster suite must remain unchanged and green throughout.

---

# 12. Kiramor-specific source issue

Do not make “match the printed Kiramor statblock” the only oracle.

From the visible numbers:

- Ranger 4 base saves: +4/+4/+1
- Rogue 2 base saves: +0/+3/+0
- Abilities add Con +1, Dex +4, Wis +0
- Rules-derived saves appear to be **Fort +5, Ref +11, Will +1**
- Printed saves are **+6/+12/+2**, suggesting an unlisted +1 resistance bonus or example error

Likewise:

- Average `4d10 + 2d8 + 6` is 37 under ordinary averaging
- Printed HP is 39
- A favored-class allocation or another convention may explain it, but it is not stated

The Kiramor fixture should therefore store both:

1. Rules-derived expected result
2. Printed example result
3. Classified delta with provenance

Never insert hidden bonuses merely to force equality.

---

# 13. Later conjunction with Simple Monster Creation

The safe integration is a **comparison**, not mixed arithmetic.

Future operation:

```json
{
  "operation": "draft.compareBenchmarks",
  "payload": {"draftId": "..."}
}
```

For an NPC draft it could compare:

- HP
- AC
- Saves
- Attack bonus
- Damage
- DCs
- Skill bonuses

against:

- Simple Monster array rows
- Bestiary CR benchmarks

It must not mutate the NPC or apply array values.

A later conversion should create a new draft or immutable proposal:

```text
NPC draft → proposed Simple Monster draft
Simple Monster draft → proposed NPC concept/class progression
```

Never let class-derived bonuses and array totals coexist in one evaluation; that would recreate the double-counting the current engine deliberately avoids.

---

## Definition of done

NPC creation is complete when:

- A Core class-based NPC can be built without manually entering any derived statistic
- Every numeric result has source-backed trace data
- Legal choices are exposed by `draft.choiceRequirements`
- Invalid feats, ranks, spells, and items are rejected deterministically
- Approximate source rules produce warnings rather than invented tolerances
- Kiramor can be built and compared with its printed example
- Existing Simple Monster drafts remain valid
- Both systems finalize through the same `Engine.execute` interface
- Exports contain enough selections and provenance for repeatable offline validation
