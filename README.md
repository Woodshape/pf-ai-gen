# Pathfinder Simple Monster Builder

The first local vertical slice is Python/stdlib and exposes one public seam:
`monster_builder.Engine.execute(request) -> response`.

## Run

```bash
python3 -m unittest discover -s tests -v
printf '%s\n' '{"protocolVersion":"1","requestId":"r1","operation":"draft.create","payload":{"draft":{}}}' | python3 -m monster_builder
```

JSONL is only CLI framing; the operation contract is the same in-process.
The current slice covers the versioned catalog, Worg CR 2, Griffon CR 4,
and the strict pre-Reality-Check Medusa CR 7 path, typed draft changes,
strict evaluation, provenance traces, and all 60 Step-6
spell lists with CR-band frequencies, spell DCs, metamagic, and source-backed
benefits. All 51 numeric or choice-based list benefits have typed effects;
direct field changes are applied, while context-dependent modifiers remain
explicit conditional modifiers. Gaze and poison have typed Medusa-path effects;
unsupported natural-attack dice remain explicit source gaps rather than guesses.

Runtime is Python/stdlib only. Regenerating the checked-in catalog additionally
requires the `pdftotext` executable for source table coordinates.
