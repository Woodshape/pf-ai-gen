# ADR-0001: Independent `creationSystem` axis for class-based NPC creation

- **Status:** Accepted (Phase 0, NPC_MODE_PLAN.md)
- **Date:** 2026-09-01
- **Owner:** collaboration task 1.a; binding for tasks 2.a, 2.b, 3.a–3.c, 4.a–4.b, 5.a–5.b, 6.a–6.b, 7.a

## Context

The engine currently implements exactly one construction system: Pathfinder Unchained
Simple Monster Creation. The word "mode" already means Strict Mode versus Free Mode in
`CONTEXT.md`, and `FinishedMonster.mode` is hard-coded to `"strict"`. NPC_MODE_PLAN.md
adds class-based Core Rulebook NPC creation as a second construction system:

- Simple Monster Creation: CR arrays + grafts + monster options.
- Class-Based NPC Creation: Core races, classes, feats, skills, spells, gear.

Both must coexist inside one `Engine.execute` contract, one persistence model, one web
UI, and one export pipeline, without invalidating persisted Simple Monster drafts or
recreating the double-counting the engine exists to prevent.

Local source reality (see `sources/npc/MANIFEST.json`): the only hash-anchored Core
Rulebook content is the 16-page spell excerpt. NPC creation pages, races, class tables,
feats, and equipment are not locally available and cannot be sourced from memory.

## Decision

### D1. `creationSystem` is a new, independent draft axis

```json
{ "creationSystem": "simple-monster" }
```

Allowed values (v1): `"simple-monster"`, `"npc"`.

- It is **not** `mode`. Strict/Free Mode remains orthogonal and untouched.
- It is **immutable per draft**. Converting a draft between systems is done by creating
  a new draft (later, via proposal), never by mutating the rules system of an existing
  draft.
- Every new draft and every new FinishedMonster snapshot writes the field explicitly.
- Legacy persisted drafts and snapshots that omit the field resolve to
  `"simple-monster"` at read time, **without mutation**: loads, evaluations, exports,
  history, restore, duplicate, and finalize must never rewrite stored JSON to add the
  default. Duplicated legacy drafts write the explicit default because they are new
  documents.

### D2. One internal seam: the creation-system adapter

`Engine.execute` remains the only public interface. Behind it, exactly two adapters:

```python
class CreationSystem(Protocol):
    key: str
    selection_fields: frozenset[str]
    def validate_input(self, draft) -> None: ...
    def choice_requirements(self, draft) -> dict: ...
    def evaluate(self, draft) -> dict: ...
    def creation_decisions(self, selections, trace) -> list[dict]: ...
```

- `SimpleMonsterCreation` — all current array/graft/option/spell logic, moved intact.
- `NpcCreation` — the new class-based evaluator (tasks 3.a, 4.a, 5.a).

The shared `Engine` keeps: request validation, idempotency, draft lifecycle, revision
and fingerprint guards, persistence, proposal application, library search, finalization,
export dispatch, and adapter selection. The adapter owns: allowed selection fields,
selection shape and catalog-ID validation, choice requirements and budgets, rules
evaluation, the canonical result, the derivation trace, and the step-to-audit mapping.

Deletion test: if `creationSystem` conditionals would otherwise spread through
`engine.py`, `choices.py`, exports, and finalization, they belong behind the seam
instead. Exports remain projections and must never calculate rules for either system.

### D3. Independently versioned catalogs and a registry

`catalog/catalog.json` is frozen; its content hash is the Simple Monster catalog
version and any edit invalidates every persisted draft. The NPC system gets its own
independently hash-versioned `catalog/npc.json` (+ `npc.schema.json`), built by
`tools/build_npc_catalog.py` from `sources/npc/` fragments and future hash-anchored
extracts.

A small registry maps creation system to catalog:

```python
catalogs.for_system("simple-monster")  # existing catalog.json, lazy-loaded
catalogs.for_system("npc")             # npc.json, lazy-loaded
```

Each draft's existing `catalogVersion` refers to its own creation system's catalog.
Catalog-version checks in `draft.get`, persistence validation, proposal bases, and
proposal acceptance dispatch through the registry instead of comparing against one
global catalog. `Catalog.load()`, `Engine(catalog=...)`, and `Engine.from_catalog()`
keep their current behavior for the Simple Monster system.

### D4. Fingerprint policy: include `creationSystem` only when present

Draft fingerprints hash semantic content (`schemaVersion`, `catalogVersion`, `concept`,
`selections`).

- Legacy drafts (field absent) keep byte-identical fingerprints; their stored
  fingerprints must keep verifying.
- New drafts include `creationSystem` in the fingerprint payload; since each system has
  a distinct `catalogVersion`, the field is redundant for identity but is hashed anyway
  so tampering with it invalidates the fingerprint.
- A duplicated legacy draft therefore produces a new fingerprint (it is a new draft);
  `derivedFrom` preserves the lineage.
- Cross-check, not hash: a draft carrying `creationSystem: "npc"` must carry the NPC
  catalog's `catalogVersion`, and vice versa; mismatches are `catalog-data` errors.

### D5. Compatible canonical shapes, never mixed arithmetic

Both systems emit a compatible canonical statblock shape (current fields such as
`defenses`, `attacks`, `skills`, `spells`, `abilityModifiers` stay), with NPC-only
additions (feats, equipment, languages, class progression, basic/heroic classification).
`FinishedMonster.kind` stays `"FinishedMonster"` and `mode` stays `"strict"`; finished
snapshots gain `creationSystem`, and finished validation accepts both.

Class-derived bonuses and array totals must never coexist in one evaluation. Any future
cross-system comparison (plan section 13, `draft.compareBenchmarks`) is a read-only
comparison against Simple Monster array rows and Bestiary Table 1-1 benchmarks
(`sources/npc/bestiary.table-1-1.txt`), never an application of array values to an NPC.

### D6. NPC is not a PC builder

NPC creation produces mechanically normal, class-based statblocks but keeps NPC-source
policies: basic/heroic ability arrays, NPC gear budgets, average HP, and optionally
simplified skill generation. PC character-sheet parity is out of scope for this phase.

### D7. Evaluation determinism without design determinism

Given selections, evaluation is deterministic and fully traced. The engine never claims
there is one correct feat, spell, skill, or item; it owns legality, counts, budgets,
prerequisites, derived math, and source provenance. Approximate source rules surface as
warnings; unresolved rules surface as explicit catalog gaps — never guessed numbers.

## Alternatives considered

- **Overload `mode`** (`"strict" | "free" | "npc"`): rejected; it couples an orthogonal
  presentation axis with a construction system and breaks every existing `"strict"`
  snapshot check.
- **Branch on `creationSystem` inside `Engine`**: rejected by the deletion test; the
  checks would spread through every subsystem listed in D2.
- **Add NPC data to `catalog.json`**: rejected; the content hash is the persisted-draft
  compatibility anchor.
- **Fingerprint all drafts with the defaulted field**: rejected; it invalidates every
  stored legacy fingerprint, violating the Phase 1 byte-equivalence exit criterion.

## Consequences

- Task 2.a extracts the seam with a byte-equivalence gate: the full existing suite must
  pass with unchanged Simple Monster evaluations, traces, exports, and fingerprints.
- Task 2.b builds the NPC catalog against this seam and against
  `sources/npc/MANIFEST.json`; every numeric NPC rule must trace to a hash-anchored
  extract or be declared a catalog gap (see `docs/npc-source-gap-matrix.md`).
- The web UI gains an immutable creation-system choice before draft creation (task 4.b);
  manual NPC creation ships before any AI panel understands NPC rules (task 6.b).