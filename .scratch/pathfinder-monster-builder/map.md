# Pathfinder Unchained Monster Builder — Wayfinding Map

Type: map
Label: wayfinder:map
Status: open

## Destination

A local-first browser tool that guides a user through *Pathfinder Unchained* Simple Monster Creation from `Before You Begin` through Steps 1–9, validates every choice with a deterministic rules engine, calculates the monster automatically, and exports a finished Monster Sheet. An optional local AI or pi SDK adapter may turn natural-language Monster Concepts into valid Monster Draft proposals, but the deterministic engine remains authoritative.

## Notes

- Domain: Pathfinder 1e monster creation using the local `Pathfinder Unchained.pdf` and `Pathfinder Unchained.txt`.
- Consult `pathfinder-simple-monster-creation`, `domain-modeling`, `prototype`, and `tdd` when relevant.
- The user interface is English.
- The application is local and must remain usable without AI.
- Strict engine mode permits only source-valid arrays, grafts, options, spells, skills, and damage values; it rejects invented values and hidden derivations. Free mode is an explicit, non-canonical override layer on top of a valid strict result.
- AI produces a short rationale and a proposal; the user can inspect and edit the same draft through the frontend or a future machine interface.
- Use one primary class graft. Normal Pathfinder multiclass simulation and house-rule multiclassing are not part of the strict mode.
- Strict engine mode has no user-defined Reality Check adjustment layer; it accepts source-defined selections only and recalculates derived values.
- The MVP persists Drafts, Proposals, and immutable finished-monster snapshots as versioned JSON files; authoritative writes still pass through the shared tool interface. Draft files contain the current snapshot plus at most 20 older snapshots. Free Mode, Free Overrides, and the Reality-Check workflow remain backlog work.

## Decisions so far

<!-- Baseline destination decisions were established during charting; resolved ticket decisions will be indexed here. -->

- [Welche Regel-Daten müssen als kanonischer Katalog vorliegen?](issues/01-rule-catalog-and-provenance.md): Use a versioned, source-provenanced JSON rules catalog; typed deterministic effects are separate from declarative data, and strict mode excludes arbitrary manual value adjustments.
- [Welche Draft- und Validierungsgrenzen hat die deterministische Regel-Engine?](issues/02-draft-schema-and-engine-invariants.md): Separate the current editable Monster Draft, immutable/iterative AI Proposals, and deterministic Evaluations. Strict mode accepts only catalogued selections; free mode overlays explicitly accepted monster-field overrides on a valid strict result without recalculating other fields. Reality-check items remain separate review records, and exports use the final effective result only.
- [Wie sprechen Frontend, CLI/JSON und lokale KI mit dem Tool?](issues/03-shared-tool-interface.md): Use one versioned JSON operation contract (`execute`), with JSONL only as CLI framing. Typed, revision-guarded Draft changes are authoritative; incomplete/invalid Drafts remain inspectable, while technical and evaluation errors are separate. AI can read Draft JSON and submit immutable Proposals, but only explicit user-confirmed, engine-validated typed Changes are applied. Non-canonical AI ideas remain plain text, and Free/Reality-Check operations are deferred to the MVP backlog.
- [Wie soll der 9-Schritte-Wizard Monster Drafts führen?](issues/04-wizard-workflow-and-validation.md): Use Variant A's Guided Rail: all steps stay visible, the current step gets the main workspace, earlier choices are always editable, validation runs live, and AI/Reality Check remain explicit review boundaries.
- [Wie werden Entwürfe und fertige Monster lokal gespeichert?](issues/05-local-persistence-lifecycle.md): Use a configurable JSON workspace instead of SQLite for the MVP. Drafts have stable opaque IDs, atomic current-plus-20-history snapshots, explicit active/finalized/archived lifecycle states, immutable finished-monster snapshots, rebuildable search indexing, and duplication rather than reopening finalized work.
- [Welche Monster-Sheet- und Export-Verträge sind verbindlich?](issues/06-monster-sheet-and-export-contract.md): Export only valid immutable FinishedMonster snapshots. Use Unchained's three-section statblock plus optional Special Abilities, deterministic field annotations for numeric derivations, explicit spell frequencies/caster metadata, and a separate Concept/AI/Steps 1–9 audit. HTML, print/PDF, Markdown, and JSON are deterministic projections of the same structured export; Draft JSON remains separate.
- [Welche lokale KI-Integration wird zuerst unterstützt?](issues/07-first-ai-adapter.md): Use an in-process Pi SDK adapter with Pi/provider defaults and an `openai-codex/gpt-5.6-luna` fallback. Require a hard-gated `catalog_list` call before read-only catalog tools and a typed terminating `emit_proposal`; Ollama is backlog, CR inference is visible `sum(class levels) - 1`, and user confirmation remains in `proposal.accept`.
- [Welche Tests beweisen die 1:1-Regeltreue?](issues/08-rule-fidelity-acceptance-tests.md): Test only the public `execute` interfaces with independent source expectations. Use Worg, Griffon, and pre-Reality-Check Medusa as strict golden fixtures; cover all tables, CR bands, grafts, options, spells, skills, damage, and exports. The Goblin Druid 4 / Rogue 1 case is represented with one primary class graft and visible secondary-class concept guidance; Reality Check and Free remain deferred.
- [Welche nicht im Core Rulebook enthaltenen Spell-Metadaten braucht der Katalog?](issues/09-non-core-spell-metadata.md): Add 39 APG/UM/UC base spells with source-qualified IDs, printed source pages, original `levelsByClass`, derived `highest`, Unchained list memberships, and a separate metamagic-variant model. Resolve Step-6 DCs from an explicit cleric/sorcerer/wizard source when needed, then the declared cleric→sorcerer→wizard fallback, then the highest class level; preserve the source when cleric and sorcerer/wizard levels differ. Five additional ACG tags were found and remain a follow-up inventory, not a silent Core fallback.
- [Welche konkreten Implementierungsschritte folgen nach den Regelentscheidungen?](issues/10-implementation-roadmap.md): Build the versioned local catalog first, then the public `execute` engine vertical slice, source-backed regression coverage, JSON Draft/Snapshot persistence, deterministic FinishedMonster exports, Guided-Rail UI, and finally the optional Pi AI adapter. The ACG follow-up is resolved before claiming complete non-Core catalog coverage.

## Next implementation milestone

- **Start with the catalog:** create the versioned JSON schema/catalog, import the Issue 01 rule data and all 39 APG/UM/UC spell records, then complete the five-spell ACG follow-up.
- **Then build one vertical slice:** expose `draft.create`, `draft.applyChanges`, and `draft.evaluate` through `execute`, and prove it end-to-end with the Worg CR 2 fixture including Step-6 spell/DC resolution.
- Follow the remaining delivery order and acceptance criteria in [Issue 10](issues/10-implementation-roadmap.md).

## Out of scope

- A hosted or multi-user online service.
- A general Pathfinder character builder or normal multiclass character-level simulator.
- A hidden house-rule mode or arbitrary manual value edits that bypass the Simple Monster Creation engine.
- Importing and converting arbitrary existing monster statblocks; that can be a separate effort after creation is stable.
- Supporting rulesets other than Pathfinder 1e *Pathfinder Unchained* Simple Monster Creation.
