# Pathfinder Simple Monster Builder

The first local vertical slice is Python/stdlib and exposes one public seam:
`monster_builder.Engine.execute(request) -> response`.

## Run

```bash
python3 -m unittest discover -s tests -v
printf '%s\n' '{"protocolVersion":"1","requestId":"r1","operation":"draft.create","payload":{"draft":{}}}' | python3 -m monster_builder
MONSTER_BUILDER_WORKSPACE=.monster-builder python3 -m monster_builder
```

JSONL is only CLI framing; the operation contract is the same in-process.
Pass `workspace=...` to `Engine`, or set `MONSTER_BUILDER_WORKSPACE` for the
CLI, to persist atomic JSON Draft snapshots. Persistent operations include
history/restore, duplication, and archive/restore; at most 20 older revisions
are retained. With no workspace configured, `Engine` remains process-local.
The current slice covers the versioned catalog, Worg CR 2, Griffon CR 4,
the strict pre-Reality-Check Medusa CR 7 path, and catalogs all source-listed
class, subtype, and template grafts. Required arrays, highest-only class CR entries,
replacement/additional option and skill budgets, prerequisites, save choices,
as-if-CR spellcasting, movement, numeric graft adjustments, and provenance
traces run through the public interface. All 159 Step-7 table options plus the
three required unmodified-rule options are catalogued with source text; direct
numeric effects and hard prerequisites use typed evaluation, while complex
encounter actions remain explicit source-rule abilities rather than guessed
simulations. Sheet-changing option effects now include additional master skills,
scaled caster-level checks, healing, defenses, resistances, and immunities. The
engine also covers all 60 Step-6 spell lists and 51 typed numeric or choice-based
list benefits. APG/UM/UC/ACG spell and Core metamagic metadata are locally
hash-anchored with their official-source URLs. Public `execute` tests cover all
93 Step-1 rows, every attack profile, all 231 Table 5-9 cells, all 162 options on
a valid path, prerequisites, typed scaling, size limits, and spell-band edges.
The Witch graft is deliberately rejected
because its source omits the rank of Knowledge (arcana); unsupported natural-attack
dice remain explicit source gaps rather than guesses.

Runtime is Python/stdlib only. Regenerating the checked-in catalog additionally
requires the `pdftotext` executable for source table coordinates.
