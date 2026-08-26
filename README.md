# Pathfinder Simple Monster Builder

The local Python application exposes one rules seam:
`monster_builder.Engine.execute(request) -> response`, plus a Preact/TypeScript Guided-Rail UI that calls it directly.

## Run

```bash
python3 -m unittest discover -s tests -v
python3 -m monster_builder.web --workspace .monster-builder
printf '%s\n' '{"protocolVersion":"1","requestId":"r1","operation":"draft.create","payload":{"draft":{}}}' | python3 -m monster_builder
MONSTER_BUILDER_WORKSPACE=.monster-builder python3 -m monster_builder
python3 -m monster_builder validate monster.json
```

`validate` accepts a JSON Draft, persisted draft file, or FinishedMonster JSON export. It prints the current deterministic evaluation and exits `0` for valid, `2` for incomplete/invalid, or `4` for unreadable/unsupported input. Rendered Markdown/HTML sheets are intentionally rejected because they omit authoritative selection IDs; export JSON for repeatable human/agent validation.

Open `http://127.0.0.1:8000/` for the browser workspace. It keeps Before You Begin and Steps 1–9 visible, applies revision-guarded edits, shows live engine findings/provenance, finalizes valid Strict drafts, and downloads JSON, Markdown, or HTML exports. Use `--host` and `--port` to change the local bind address.

The checked-in production assets run without Node. To change the frontend:

```bash
npm ci
npm run typecheck
npm run build
```

TypeScript source lives in `monster_builder/web/src`; the small shell is `monster_builder/web/index.html`, and Vite writes deployable assets to `monster_builder/web/dist`.

JSONL is only CLI framing; the operation contract is the same in-process and over the local browser transport. `draft.choiceRequirements` accepts either `{"draftId":"...","selectionOverrides":{}}` for a non-persisting preview or an external `{"draft":{"concept":{},"selections":{}}}` and returns basis metadata plus the system-owned input paths, control types, allowed values, exact cardinalities, restrictions, labels, and source references. Agents and the browser use this operation rather than independently interpreting graft rules.
Pass `workspace=...` to `Engine`, or set `MONSTER_BUILDER_WORKSPACE` for the
CLI, to persist atomic JSON Draft snapshots. Persistent operations include
history/restore, duplication, and archive/restore; at most 20 older revisions
are retained. Valid Strict Drafts can be finalized as immutable FinishedMonster
snapshots, then fetched, duplicated, archived/restored, or exported through
`monster.export` as JSON, Markdown, or standalone HTML/print with `sheet` and
`audit` profiles. With no workspace configured, `Engine` remains process-local.
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

Runtime is Python/stdlib plus the checked-in bundled browser assets. Frontend builds use Preact, TypeScript, and Vite. Regenerating the checked-in catalog additionally
requires the `pdftotext` executable for source table coordinates.
