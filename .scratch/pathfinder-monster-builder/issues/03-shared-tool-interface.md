# Wie sprechen Frontend, CLI/JSON und lokale KI mit dem Tool?

Type: grilling
Status: resolved
Blocked by: none

## Question

Welche kanonische Schnittstelle lässt Benutzeroberfläche, CLI/JSON-Aufrufe und lokale KI denselben Monster Draft lesen, bearbeiten, validieren und berechnen? Entscheide über Befehle oder Operationen, Fehlerformate, Teilentwürfe, Vorschlagsübernahme, kurze Begründungen und die Grenze zwischen einem KI-Vorschlag und einer vom Engine akzeptierten Änderung.

## Answer

## Entscheidung: Eine gemeinsame, versionierte Operationsschnittstelle

Frontend, CLI/JSON und lokale KI verwenden denselben fachlichen Application Port. Das kanonische Wire-Format ist JSON; JSONL ist ausschließlich das zeilenweise CLI-Framing. Ein Request und eine Antwort bilden jeweils ein JSON-Objekt:

```json
{
  "protocolVersion": "1",
  "requestId": "r-123",
  "operation": "draft.applyChanges",
  "payload": {}
}
```

Die Schnittstelle wird als `execute(request) -> response` modelliert. Die Browser-Oberfläche und lokale Adapter dürfen sie im Prozess aufrufen; die CLI liest JSONL von stdin und schreibt JSONL nach stdout. Transport, Darstellung und Logs gehören nicht zur fachlichen Schnittstelle; Logs gehen bei der CLI nach stderr.

## MVP-Operationen

- `draft.create`
- `draft.get`
- `draft.applyChanges`
- `draft.evaluate`
- `draft.import`
- `proposal.validate`
- `proposal.create`
- `proposal.get`
- `proposal.accept`

`draft.evaluate` validiert und berechnet in einem deterministischen Schritt. Es verändert weder Draft noch Proposal. `draft.applyChanges` liefert den neuen Draft, die zugehörige Evaluation und die tatsächlich angewendeten Änderungen zurück.

Jede Mutation trägt `baseRevision` und `baseFingerprint`. Ein veralteter Request wird ohne automatisches Merging abgelehnt. Die Antwort enthält einen stabilen Konfliktcode und den aktuellen Stand bzw. dessen Revision/Fingerprint. `requestId` dient bei Mutationen zusätzlich als Idempotency-Key, damit Wiederholungen keine weitere Revision erzeugen.

## Drafts und Teilentwürfe

Draft-Änderungen sind typisierte, atomare Changes. Vollständige Objekt-Ersetzungen und beliebige JSON-Patches sind nicht Teil des Vertrags. Eine Änderung darf nur katalogisierte IDs und typisierte Parameter referenzieren; berechnete Regelwerte werden nie als Selections eingeschleust.

Unvollständige Drafts sowie Drafts mit bekannten, aber kombinatorisch ungültigen Entscheidungen dürfen gespeichert werden. Ihre Evaluation liefert `status: incomplete` oder `status: invalid`, Issues und keine autoritativen `canonical`-/`effective`-Ergebnisse. Erst ein vollständiger und gültiger Strict-Draft erhält berechnete Ergebnisse. Unbekannte IDs, falsche Parameter und inkompatible Katalogversionen sind dagegen harte Schnittstellenfehler.

Die JSON-Datei eines Drafts ist eine mögliche persistierte Darstellung, aber autoritative Schreibvorgänge laufen über die Operationsschnittstelle. JSON-Dateien dürfen zur Inspektion direkt gelesen werden. Direkte Änderungen werden nicht stillschweigend übernommen; `draft.import` validiert untrusted JSON, verwirft nicht vertrauenswürdige Systemfelder, berechnet Revision und Fingerprint neu und erzeugt bei Erfolg eine neue Draft-Revision.

Drafts und Proposals können als versionierte JSON-Dateien gespeichert werden; eine SQLite-Datenbank ist für den MVP nicht erforderlich. Evaluations sind abgeleitet. Ein optionaler Cache muss an `draftFingerprint` und `catalogVersion` gebunden sein und ist niemals die Quelle der Wahrheit.

## Fehlervertrag

Erwartete fachliche Draft-Probleme sind erfolgreiche Antworten:

```json
{
  "ok": true,
  "requestId": "r-123",
  "result": {
    "evaluation": {
      "status": "incomplete",
      "canonical": null,
      "effective": null,
      "issues": []
    }
  }
}
```

Technische und Boundary-Fehler verwenden dagegen `ok: false` und mindestens `code`, `kind`, `message` und `path`; optionale Felder sind `details`, `retryable` und `sourceRefs`. Die Maschinenlogik verwendet stabile Codes, nicht freie Fehlermeldungen.

Die CLI projiziert den Vertrag zusätzlich auf Exitcodes:

- `0`: gültige Operation und gültiges Ergebnis
- `2`: unvollständiges oder ungültiges fachliches Ergebnis
- `3`: Revision-/Fingerprint-Konflikt
- `4`: Protokoll-, Schema- oder Boundary-Fehler

## Proposals und KI-Grenze

Ein Proposal ist unveränderlich, an `baseRevision` und `baseFingerprint` gebunden und enthält typisierte Changes, kurze `rationale`, `assumptions` sowie optional eine Begründung pro Change. `proposal.create` registriert und prüft ein KI-Ergebnis, mutiert aber keinen Draft.

Die KI darf den Draft niemals direkt verändern. `proposal.accept` verlangt explizite Change-IDs und eine Benutzerbestätigung:

```json
"confirmation": {
  "actor": "user",
  "confirmed": true
}
```

Die Engine prüft die ausgewählten Changes erneut und wendet sie atomar an. Bei einem ungültigen Change, fehlender Bestätigung oder veraltetem Base wird nichts angewendet. Eine teilweise angenommene Proposal bleibt unverändert; wegen der neuen Draft-Revision wird sie nicht automatisch rebased oder erneut angewendet.

Nicht-kanonische Ideen werden ausschließlich als uninterpretierter Text geführt:

```json
"nonCanonicalSuggestions": [
  "Optional: BAB um 2 senken und dafür Schaden um 2 erhöhen. Passt thematisch."
]
```

Dieses Feld ist kein `typedChanges`-Bestandteil, erhält keine Change-ID und kann niemals von `proposal.accept` übernommen werden. `rationale` erklärt die katalogisierten Vorschläge; `derivationTrace` der Engine bleibt die autoritative Begründung mit Regel- und Quellenreferenzen.

## MVP-Backlog

- Free Mode und Free Overrides als separater, explizit bestätigungspflichtiger Interface-Zweig.
- Reality-Check-Workflow und die dazugehörigen Akzeptanz-/Exportregeln.

Der Strict-MVP akzeptiert keine Free-Override-Operation und interpretiert sie nicht als normale Draft-Änderung.
