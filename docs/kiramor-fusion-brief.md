# Kiramor Fusion Run Brief (Phase 4 bounded slice)

Single source of truth for a `/fh-collaborate` run implementing the Core Rulebook
"Creating NPCs" baseline example as a source-backed NPC slice:

**Kiramor, the Forest Shadow — elf ranger 4 / rogue 2 — must become buildable,
evaluable, finalizable, and exportable entirely through NPC selections**, with the
dual-oracle acceptance fixture from `docs/kiramor-worksheet.md` §4.

Exit criterion (NPC_MODE_PLAN.md Phase 4): Kiramor can be created, finalized, and
exported through `Engine.execute`. Do NOT broaden beyond this slice.

---

## 0. Prepared state (already done — do not redo)

Committed before this run:

- `sources/reference/aonprd/{ranger,rogue,magic-weapons,magic-armor,potions}.html` —
  official current AoN snapshots fetched 2026-09-03.
- `sources/npc/aonprd/{ranger,rogue,magic-weapons,magic-armor,potions}.txt` —
  deterministic extracts written by `tools/extract_npc_aon_sources.py` (68 extracts
  green, `--check` passes).
- `tools/extract_npc_aon_sources.py` — extractor entries added for the five pages.
- All line numbers below are verified against these extracts.

Remaining work is bookkeeping + fragments + engine + test. Follow the exact
citations; never add a number without a line anchor (`docs/npc-source-gap-matrix.md`
ruling 1).

## 1. Delegation DAG (proposed)

```
T1 source-bookkeeping ──► T2 catalog-fragments ──► T3a engine-multiclass ──► T3b integrate+gates ──► T4 acceptance-export
                                    └──► T2b fixtures/docs (parallel to T3a) ────┘
```

| Task | Depends on | Deliverable |
|---|---|---|
| T1 | — | MANIFEST + SOURCE_FILES entries for 5 new sources |
| T2 | T1 | Fragment records: elf, ranger 1–4, rogue 1–2, 11 class features, Deadly Aim, 7 items, ranged presets |
| T2b | T1 | `tests/fixtures/kiramor-{npc,printed}.json` + worksheet/gap-matrix updates (contract-only; no engine) |
| T3a | T2 | `monster_builder/creation_systems/npc.py` multiclass slice extensions |
| T3b | T2b, T3a | `tests/test_kiramor.py` green; catalog rebuilt; full suite green |
| T4 | T3b | Acceptance: build+finalize+export Kiramor in `.monster-builder`; report |

## 2. T1 — Source bookkeeping (exact edits)

1. `sources/npc/MANIFEST.json` — add to `parentSources` (file = `sources/reference/aonprd/<name>.html`,
   sha256 = actual, `officialUrl` + `retrievedAt` + description, following the existing entry shape):
   - `aon-ranger-html` → https://aonprd.com/ClassDisplay.aspx?ItemName=Ranger
   - `aon-rogue-html` → https://aonprd.com/ClassDisplay.aspx?ItemName=Rogue
   - `aon-magic-weapons-html` → https://aonprd.com/Rules.aspx?Name=Magic%20Weapons&Category=Magic%20Items (redirect target)
   - `aon-magic-armor-html` → https://aonprd.com/Rules.aspx?Name=Magic%20Armor&Category=Magic%20Items
   - `aon-potions-html` → https://aonprd.com/Rules.aspx?Name=Potions&Category=Magic%20Items
   and to `extracts` (file = `sources/npc/aonprd/<name>.txt`, same hash) with matching IDs
   `aon-ranger`, `aon-rogue`, `aon-magic-weapons`, `aon-magic-armor`, `aon-potions`.
2. `tools/build_npc_catalog.py` `SOURCE_FILES` — append:
   - `("source.aon-ranger", "sources/npc/aonprd/ranger.txt", "Official current AoN Ranger class rules and level progression")`
   - `("source.aon-rogue", "sources/npc/aonprd/rogue.txt", "Official current AoN Rogue class rules and level progression")`
   - `("source.aon-magic-weapons", "sources/npc/aonprd/magic-weapons.txt", "Official current AoN Core magic weapon enhancement rules and Table 15-8")`
   - `("source.aon-magic-armor", "sources/npc/aonprd/magic-armor.txt", "Official current AoN Core magic armor enhancement rules and Table 15-3")`
   - `("source.aon-potions", "sources/npc/aonprd/potions.txt", "Official current AoN Core potion rules and Table 15-12")`
3. Gate: `python3 tools/build_npc_catalog.py --check` still passes (no fragment change yet);
   `python3 -m unittest tests.test_npc_source_tables tests.test_npc_catalog` green.

## 3. T2 — Catalog fragments (record shapes follow existing resolved records)

Copy the JSON shapes of the neighboring resolved records (bard class row, halfling
race, druid nature-bond choice, cloak item, weapon-finesse feat). Every record gets
`sourceRef` with `sourceId` + `section` + exact `txtLines` from the lists below.

### 3.1 `races.fragment.json` — resolve `npc-race.elf` (replace gap stub)
Anchor: `source.aon-core-races`, "Elf Racial Traits", lines 28–36.
- `abilityAdjustments` {dexterity: 2, intelligence: 2, constitution: -2} (L29)
- `sizeId` "size.medium", no size modifiers (L30 "Medium... no bonuses or penalties")
- `speed` {land: 30} (L31)
- `senses` ["Low-Light Vision"] (L32)
- `traits` ["Elven Immunities", "Elven Magic", "Keen Senses", "Weapon Familiarity"] (L33–35)
- `skillBonuses` {"skill.perception": 2} (L34 Keen Senses)
- NO `saveBonuses` — the +2 vs enchantment is conditional (Phase 5); stays in trait text
- `languages` ["Common", "Elven"], `bonusLanguages` ["Celestial","Draconic","Gnoll","Gnome","Goblin","Orc","Sylvan"] (L36)

### 3.2 `classes.fragment.json` — resolve ranger levels 1–4, rogue levels 1–2
Ranger (anchor `source.aon-ranger`; replace gap stub, `supportedLevels` [1,2,3,4]):
- top: category "pc", hitDie "d10" (L6), classSkills = [climb, craft, handle-animal, heal,
  intimidate, knowledge-dungeoneering, knowledge-geography, knowledge-nature, perception,
  profession, ride, spellcraft, stealth, survival, swim] (L9), skillSelections 6 (L10)
- rows (txtLines 14–17): 1: bab1 F2 R2 W0 grants [favored-enemy, track, wild-empathy];
  2: bab2 F3 R3 W0 grants [combat-style]; 3: bab3 F3 R3 W1 grants [endurance, favored-terrain];
  4: bab4 F4 R4 W1 grants [hunters-bond], `spellsPerDay` {"1": 0} (L17 — the table cell is 0)
- `castingAbility` "wisdom", `castingMode` "prepared", `supportedLevels` [1,2,3,4]
Rogue (anchor `source.aon-rogue`; `supportedLevels` [1,2]):
- category "pc", hitDie "d8" (L5), classSkills = rogue list (L9), skillSelections 8 (L10)
- rows (txtLines 13–14): 1: bab0 F0 R2 W0 grants [sneak-attack, trapfinding];
  2: bab1 F0 R3 W0 grants [evasion, rogue-talent]
Leave levels 3–20 as existing gap rows.

### 3.3 `class-features.fragment.json` — add records (kind "automatic" unless noted)
Anchor lines all in `source.aon-ranger` / `source.aon-rogue` / `source.aon-creating-npcs`:
- `npc-class-feature.ranger-proficiencies` (rogue equivalent too) — Weapon and Armor
  Proficiency paragraphs
- `ranger-favored-enemy` — kind "choice-slot", choiceId "favoredEnemy",
  allowedValues ["humanoid-orc"], option name "Humanoid (orc)"; lines 68–70
  (humanoids require an associated subtype). Effect text: +2 attack/damage/skills vs them.
- `ranger-track` — L71 (Survival to follow tracks +½ level, min 1; text only)
- `ranger-wild-empathy` — L72–74; effect `checkBonus = level + Charisma modifier`
- `ranger-combat-style` — kind "choice-slot", choiceId "combatStyle",
  allowedValues ["archery"], option archery grants feat `feat.rapid-shot`.
  L75–77 describe the styles; the full style feat list is NOT locally archived —
  the archery→Rapid Shot grant is anchored by the printed example selecting
  Rapid Shot as his ranger combat style feat (creating-npcs.txt L112). Note this
  bounded provenance in the record's `entry`.
- `ranger-endurance` — L78 (bonus feat Endurance at 3rd; no numeric integration)
- `ranger-favored-terrain` — kind "choice-slot", choiceId "favoredTerrain",
  allowedValues ["forest"], L81 + L90–92; text: +2 initiative/other bonuses in terrain
  (conditional; NOT added to global initiative)
- `ranger-hunters-bond` — kind "choice-slot", choiceId "huntersBond",
  allowedValues ["companion-bond"] ONLY (L93: two forms). The animal-companion
  form (wolf) requires Bestiary wolf rows that are not archived → selecting it must
  yield a deterministic `npc.catalog-gap` issue in the engine branch (L93–95).
- `ranger-spells` — L96–100: divine, prepared, Wis caster; CL = ranger level − 3 (L100);
  gate L97.
- `rogue-sneak-attack` — L34–37 + table L13; dice-by-level map {1: "1d6", 2: "1d6"}
- `rogue-trapfinding` — L38 (conditional trap skills; text only)
- `rogue-evasion` — L39
- `rogue-talent` — kind "choice-slot", choiceId "rogueTalent", allowedValues
  ["bleeding-attack"] — anchored ONLY by the printed example (creating-npcs.txt
  L121 statblock "rogue talents (bleeding attack)"); the general talent list is not
  archived. Record `entry` states this bounded provenance. Text only, no numeric effect.

### 3.4 `feats.fragment.json`
- Add `feat.deadly-aim`: category "combat", prerequisites
  {"all":[{"abilityAtLeast":{"dexterity":13}},{"babAtLeast":1}]},
  effects {} (trade-off feats are never auto-applied — see §5),
  sourceRef `source.aon-feats` lines 86 and 371–374.
- Extend `derived-rules.fragment.json` `npc-rule.general-feat-slots.allowedFeatIds`
  with `feat.deadly-aim` and `feat.point-blank-shot` (ranged list,
  creating-npcs.txt L65). `feat.rapid-shot` stays OUT — it arrives via the combat style grant.

### 3.5 `items.fragment.json`
- Resolve `item.longbow` (gap stub): priceCp 7500, weightLb 3, effects
  {damageDieBySize {small "1d6", medium "1d8"}, damageType "P", rangeIncrement 100,
  noStrengthToDamage: true} — equipment.txt L176, L55, L250. Add `critMultiplier` 3.
- Add `item.rapier-masterwork` "Masterwork Rapier": 2000 + 30000 = 32000 cp
  (equipment.txt L295 +300 gp + rapier row); effects = rapier effects + {"attackBonus": 1} (L294);
  critRange 18 (equipment Table: Weapons rapier row).
- Add `item.longbow-plus-1` "Longbow +1": 7500 + 30000 + 200000 = 237500 cp
  (equipment L176 + magic-weapons Table 15-8 L21 + mwk L295);
  effects = longbow + {"attackBonus": 1, "damageBonus": 1} — magic weapons apply
  enhancement to BOTH attack and damage (magic-weapons.txt L4); masterwork attack
  bonus does not stack with enhancement (same line).
- Add `item.studded-leather-plus-1` "Studded Leather +1": 2500 + 15000 + 100000 = 117500 cp
  (equipment studded row L325 + mwk armor +150 gp equipment.txt L381ff + magic-armor
  Table 15-3 L17 "+1 armor 1,000 gp"); effects: armorBonus 4 (3 base + 1 enhancement),
  maxDex 5, armorCheckPenalty 0 (magic armor is masterwork: ACP −1, magic-armor.txt L4),
  critRange none.
- Add `item.potion-of-cure-moderate-wounds` "Potion of Cure Moderate Wounds":
  category magic, priceCp 30000 (potions.txt L19–23: Table 15-12 2nd-level potion,
  cleric/druid/wizard column 300 gp); category "magic", npcGearCategory "limitedUse".
- Add `item.potion-of-invisibility` "Potion of Invisibility": priceCp 40000
  (Table 15-12 sorcerer column, 2nd level; invisibility is sor/wiz 2 per
  core-rulebook-extract.spell-lists.txt L103); npcGearCategory "limitedUse".
- Add `item.arrows-20` "Arrows (20)": priceCp 100, weight 3 lb (equipment.txt L177);
  category "goods".

### 3.6 `ability-arrays.fragment.json`
Add `ranged` preset to BOTH arrays (creating-npcs.txt Table 14-6, lines 16–22):
- basic ranged: str 11, dex 13, con 12, int 9, wis 10, cha 8
- heroic ranged: str 13, dex 15, con 14, int 10, wis 12, cha 8
Mirror the existing `presets` record shape exactly.

### 3.7 Rebuild + gates
`python3 tools/build_npc_catalog.py` (writes `catalog/npc.json`, new catalogVersion);
`python3 tools/build_npc_catalog.py --check`; NPC source-table/catalog tests green.
Do NOT touch `catalog/catalog.json` (Simple Monster catalog is frozen).

## 4. T3a — Engine extensions (`monster_builder/creation_systems/npc.py`)

Bounded to the new slice; follow existing patterns (sorcerer/druid branches):
1. **Slice gate**: replace/extend the `supported` whitelist with:
   race `npc-race.elf`, progression exactly `[ranger N1, rogue N2]` (ordered),
   `N1 ∈ 1..4`, `N2 ∈ 1..2`, total level `N1+N2`. Keep all existing slices green.
2. **Multiclass aggregation** (character-classes.txt L36–38: add hit points, BAB,
   and save bonuses from each class):
   - `bab = Σ row.bab`; saves = Σ rows; `hitDiceExpression` per class die counts
     ("4d10+2d8+6" for 4/2).
   - HP: `npc-rule.average-hp` (firstLevelMax, floor, Con per level): first HD of the
     FIRST class is maximum; every later HD average + Con. ranger4/rogue2:
     floor(10 + 3×(5.5+1) + 2×(4.5+1)) = 40.
   - `npcCategory` "heroic" from the first PC class; CR = total − 1 = 5.
3. **Two-class simplified skills** (creating-npcs.txt L21–23, the example's exact
   procedure): start with the class with FEWER selections (ranger 6): count =
   6 + Int mod (+ race bonus) skills at ranks = total level, must be that class's
   class skills; the DIFFERENCE (rogue 8 − ranger 6 = 2) more skills must be NEW
   (not in the first set), class skills of the second class, at ranks = second class
   level (2). Skill totals: level-group ranks + 3 class + ability + ACP + race bonuses.
4. **Feature choices**: extend `_selected_class_features` with ranger/rogue branches
   keyed on `classFeatureChoices` entries: favoredEnemy=humanoid-orc,
   combatStyle=archery (grants Rapid Shot → attacks), favoredTerrain=forest,
   huntersBond=companion-bond (animal companion selection → catalog-gap issue),
   rogueTalent=bleeding-attack (text only). Wild empathy checkBonus = level + Cha.
5. **Ranger spells**: extend `_spells` for `npc-class.ranger` (Wis-based prepared):
   base slots from the row (0 at ranger 4) + Wis bonus spells
   (`_bonus_spell_count`, getting-started.txt Table lines 89–101). Require
   `spellLoadout.prepared` to match total slots exactly; validate ranger-list
   membership (`levelsByClass.ranger`); caster level = ranger level − 3 (ranger.txt
   Spells paragraph); DC = 10 + level + Wis mod; gate warning (not error) when
   Wisdom < 10 + spell level makes a slot uncastable (ranger.txt L97). For the
   fixture (Wis 12): 0 base + 1 bonus slot, spell.entangle prepared, CL 4, DC 13.
6. **Attacks**: extend `_attacks` with item `effects.attackBonus` (masterwork or
   enhancement, attack only) and `effects.damageBonus` (enhancement), honor
   `effects.noStrengthToDamage` (skip Strength for projectile weapons,
   equipment.txt L55/L250), and grant a Rapid Shot second attack at −2 when the
   combat style grant is present (feats.txt Rapid Shot: one extra attack, −2 on all).
   Weapon Finesse already handled. Deadly Aim / Point-Blank Shot are NOT applied
   (voluntary trade-offs and conditional bonuses stay out of the strict result).
7. **Feat slots**: general slots at 1/3/5 for level 6; Endurance + Rapid Shot arrive
   as feature grants, not selectable slots.
8. **`choice_requirements`**: surface the new choices + multiclass classProgression
   entries + ranged-preset + spell loadout so `draft.choiceRequirements` stays
   truthful (the UI may not render them yet — engine-first acceptance).
9. Guard: no changes to the Simple Monster system or shared engine lifecycle.

## 5. T2b — Fixture contract (worksheet §4)

`tests/fixtures/kiramor-npc.json` — draft:
- concept: name "Kiramor, the Forest Shadow", role, alignment "N" in details
- raceId npc-race.elf; classProgression [ranger 4, rogue 2]
- abilityGeneration: method "ranged-preset", arrayId npc-ability-array.heroic,
  levelIncreases {"4": "dexterity"}
- skillGeneration: simplified, ranger 7 skills [climb, heal, knowledge-geography,
  knowledge-nature, perception, stealth, survival] (Int mod +1 → budget 7)
  + rogue 2 [escape-artist, swim]
- feats: general-1 point-blank-shot, general-3 deadly-aim, general-5 weapon-finesse
- classFeatureChoices: favoredEnemy humanoid-orc, combatStyle archery,
  favoredTerrain forest, huntersBond companion-bond, rogueTalent bleeding-attack
- spellLoadout.prepared {"1": ["spell.entangle"]}
- gearProfile medium/normal (heroic level 6 = 465000 cp)
- gear: longbow-plus-1, rapier-masterwork, studded-leather-plus-1, arrows ×2,
  potion-of-cure-moderate-wounds, potion-of-invisibility (spent 457200 cp →
  budget warning is expected)

`tests/fixtures/kiramor-printed.json` — printed oracle (all refs cite
`source.aon-creating-npcs` L109–133): init +4 (+6 forests), AC 18/14/14, hp 39
(4d10+2d8+6), saves +6/+12/+2 (+2 vs enchantment), immune sleep, evasion, Str 13
Dex 18 Con 12 Int 14 Wis 10 Cha 8, BAB +5, CMB +6, CMD 20, the five feats, the ten
skills, languages Common/Elven/Orc/Sylvan, SQ nature bond (wolf), track, trapfinding +1,
gear as printed.

## 6. Classified deltas (assert these, never absorb them)

| Field | Rules-derived | Printed | Delta | Classification |
|---|---|---|---|---|
| Int / Wis | 12 / 12 | 14 / 10 | ±2 | The example's ability assignment deviates from Table 14-6 ranged-heroic (preset: Int 10, Wis 12 + elf). Unresolved (gap #17: no errata snapshot). |
| Fort / Ref / Will | +5 / +11 / +2 | +6 / +12 / +2 | +1 / +1 / 0 | Uniform +1 on Fort/Ref fits the unlisted resistance-bonus hypothesis (worksheet §3); Will matches only under preset Wis 12. Unresolved. |
| HP | 40 | 39 | −1 | Rules-derived now uses the anchored max-first-HD rule (`npc-rule.average-hp.firstLevelMax`, getting-started.txt L30) — supersedes the worksheet's Phase-0 ordinary-averaging estimate of 37. Update worksheet §2/§3 accordingly. Printed 39 stays unexplained. |
| Skills | 7 ranger + 2 rogue (preset Int 12) | 10 skills (Int 14 → 8+2) | count | Printed skill totals reconcile with printed abilities and ACP 0 magic armor EXCEPT Acrobatics +13, which needs 6 rogue-class ranks the procedure does not grant. Record as example inconsistency. |
| Languages | Common, Elven | + Orc, Sylvan | — | Int-based bonus languages are not modeled in the slice (Phase 5). |
| Hunter's bond | companion-bond | nature bond (wolf) | — | Wolf companion rows are not source-resolved; animal-companion form emits a catalog-gap issue. |
| Initiative | +4 | +4 (+6 in forests) | — | Favored-terrain initiative bonus is conditional; recorded in feature text only. |

## 7. Invariants (must hold at the end of the run)

1. `python3 tools/build_npc_catalog.py --check` clean; new catalogVersion.
2. Full test suite green, INCLUDING the entire Simple Monster suite unchanged
   (NPC_MODE_PLAN.md regression rule). `node --test tests/test_ai_tools.mjs tests/test_pi_schema.mjs` green.
3. `tests/test_kiramor.py` asserts: rules-derived canonical block, printed fixture
   values, and the classified deltas with provenance.
4. Acceptance: a Kiramor NPC draft created in the `.monster-builder` workspace via
   `Engine.execute` (draft.create → applyChanges → monster.finalize), then
   `monster.export` markdown + html + json all succeed; the finalized monster
   appears in `library.search`.
5. No `[DEBUG-*]` instrumentation or throwaway files remain; the final architect
   integration turn summarizes what shipped vs. what stayed a recorded gap.