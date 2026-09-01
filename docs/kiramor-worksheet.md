# Kiramor Rules-versus-Print Worksheet (Phase 0)

Kiramor, the Forest Shadow — elf ranger 4 / rogue 2 — is the plan's principal
acceptance fixture (NPC_MODE_PLAN.md §12). This worksheet separates what is derivable
by rule from what is printed, classifies every delta, and fixes how the engine treats
them. It will be consumed by task 6.a (`tests/test_kiramor.py`,
`tests/fixtures/kiramor-npc.json`, `tests/fixtures/kiramor-printed.json`).

## 1. Provenance of the two oracles

| Oracle | Local carrier | Anchor status |
|--------|---------------|---------------|
| Printed statblock values (+6/+12/+2 saves, 39 hp, 4d10+2d8+6, Dex +4 / Con +1 / Wis 0) | `NPC_MODE_PLAN.md` §12 | Hash-anchored to the plan document (`sources/npc/MANIFEST.json` → `npc-mode-plan`), **not** to any game source. The underlying Core Rulebook example page is not locally present (gap #15 in `docs/npc-source-gap-matrix.md`). |
| Rules-derived values | Ranger 4 / rogue 2 class data | **GAP** until class tables are anchored (gap #5). The arithmetic below is the computation contract; the class-table inputs must become source-anchored before the fixture can assert "rules-derived" status. |

The plan document itself is a local project artifact. Recording its numbers as the
printed oracle is honest provenance for the fixture, but it does not satisfy the plan's
"no numeric rule depends solely on memory" exit criterion; the CRB example page must be
added to `sources/npc/` before task 6.a finalizes the fixture.

## 2. Rules-derived computation (computation contract)

Inputs from the plan's printed description: ranger 4, rogue 2, abilities include
Dex +4, Con +1, Wis 0 (Wisdom 10).

### Base saves from class level rows

| Component | Fort | Ref | Will |
|-----------|------|-----|------|
| ranger 4 | +4 | +4 | +1 |
| rogue 2 | +0 | +3 | +0 |
| Multiclass sum | **+4** | **+7** | **+1** |

### Ability modifiers

| Component | Fort | Ref | Will |
|-----------|------|-----|------|
| Constitution +1 | +1 | — | — |
| Dexterity +4 | — | +4 | — |
| Wisdom 0 | — | — | +0 |
| **Rules-derived total** | **+5** | **+11** | **+1** |

### Hit points

Average per die under ordinary averaging (max/2 + ½): d10 → 5.5, d8 → 4.5.

```
4d10  → 4 × 5.5 = 22
2d8   → 2 × 4.5 = 9
Con +1 × 6 HD = 6
Total = 37
```

**Rules-derived HP: 37.**

### Wisdom gate on ranger spellcasting

Ranger 4 grants 1st-level ranger spells, but casting requires Wisdom 10 + spell level.
With Wisdom 10 the character cannot cast 1st-level ranger spells (0-level-equivalent
access only, and the ranger list has none). This is a real rules difference the engine
must expose rather than paper over: the class has reached spellcasting level, the
ability has not. It is a meaningful Kiramor outcome independent of the save/HP deltas.

## 3. Delta classification

| Field | Rules-derived | Printed | Delta | Classification |
|-------|--------------|---------|-------|----------------|
| Fortitude | +5 | +6 | +1 | **Unresolved discrepancy** — hypothesis A: unlisted +1 resistance bonus on the example; hypothesis B: example arithmetic error. Not distinguishable locally (gap #16). |
| Reflex | +11 | +12 | +1 | Same as Fortitude; a uniform +1 across all three saves fits a resistance bonus, per hypothesis A. |
| Will | +1 | +2 | +1 | Same as above. |
| HP | 37 | 39 | +2 | **Unresolved discrepancy** — hypothesis A: human favored-class bonus (+1 hp per ranger/rogue level for the favored class) partially applied; the allocation that yields exactly +2 is not stated in any local source. Hypothesis B: example uses a different averaging convention or an error. |

The uniform +1 save delta and the +2 hp delta are recorded, never absorbed. Inserting
hidden bonuses to force equality is prohibited by the plan (§12) and by ADR-0001 D7.

## 4. Fixture contract for task 6.a

`tests/test_kiramor.py` must assert all three of:

1. **Rules-derived expected result** — computed by the engine from anchored class rows
   and the selections in `tests/fixtures/kiramor-npc.json` (elf, ranger 4/rogue 2,
   ranged-preset abilities).
2. **Printed example result** — the values in `tests/fixtures/kiramor-printed.json`,
   each annotated with `npc-mode-plan` provenance until a game-source anchor exists.
3. **Classified delta** — the two discrepancies above with their hypotheses and
   provenance, emitted as visible annotations/audit data.

The engine reproduces every mechanically derivable value or emits an explicit
documented source discrepancy. If later anchoring shows the printed page (with errata
status), the classification is updated in this worksheet and the fixture annotations;
the derivation trace itself never changes to match print.