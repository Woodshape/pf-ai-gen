# Pathfinder Simple Monster Builder

The first local vertical slice is Python/stdlib and exposes one public seam:
`monster_builder.Engine.execute(request) -> response`.

## Run

```bash
python3 -m unittest discover -s tests -v
printf '%s\n' '{"protocolVersion":"1","requestId":"r1","operation":"draft.create","payload":{"draft":{}}}' | python3 -m monster_builder
```

JSONL is only CLI framing; the operation contract is the same in-process.
The current slice covers the versioned catalog, Worg CR 2, typed draft changes,
strict evaluation, provenance traces, and individual Step-6 spell level/metamagic
resolution. Spell-list CR bands, frequencies, and list benefits remain open.
