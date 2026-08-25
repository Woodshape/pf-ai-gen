# Welche konkreten Implementierungsschritte folgen nach den Regelentscheidungen?

Type: implementation-plan
Status: in progress
Blocked by: 01, 02, 03, 05, 06, 08, 09

## Ziel

Die Issues 01–09 beschreiben die fachlichen Verträge. Dieses Issue übersetzt sie in die kleinste sinnvolle Lieferreihenfolge für den lokalen MVP. Die Engine bleibt die Quelle der Wahrheit; UI und KI sind darauf aufgesetzt.

## Reihenfolge

### 1. Katalog-Basis schaffen

- Eine versionierte JSON-Katalogdatei und ein lokales Schema anlegen.
- Die in Issue 01 festgelegten Arrays, Grafts, Monster Options, Skills, Damage-Dice, CR-Tabellen und Core-Spells übernehmen.
- Die 39 APG/UM/UC-Spells aus Issue 09 mit `sourceRef`, `levelsByClass`, `highest`, `listMemberships` und Metamagie-Regeln ergänzen.
- Das ACG-Folgeinventar (`Long Arm`, `Stricken Heart`, `Disguise Weapon`, `Molten Orb`, `Heart of the Metal`) abschließen, bevor „alle Nicht-Core-Marker“ als vollständig gilt.
- Lokale Provenienz (Datei, TXT-Zeile, Hash) speichern; kein Runtime-Webzugriff.

**Ergebnis:** Der Katalog lädt lokal, ist schema-validiert und enthält keine geratenen Werte.

### 2. Deterministische Engine als Vertical Slice

- Das versionierte `execute(request)`-Interface aus Issue 03 implementieren.
- `draft.create`, `draft.applyChanges` und `draft.evaluate` mit Revision Guard, `incomplete`/`invalid`-Status und stabilem `derivationTrace` umsetzen.
- Zuerst einen vollständigen Strict-Pfad (z. B. Worg CR 2) von Draft bis Evaluation liefern.
- Step 6 dabei inklusive Spell-Listen, Klassenlevel-Auflösung, Metamagie und Spell-DC berechnen.

**Ergebnis:** Ein Draft kann ohne UI reproduzierbar validiert und evaluiert werden.

### 3. Regelabdeckung und Regressionen schließen

- Steps 1–9, Arrays, Grafts, Options, Skills, Damage und Exporte gemäß Issue 08 ergänzen.
- Die unabhängigen Golden Fixtures Worg, Griffon und Medusa sowie die Negativ-/Grenzfälle als öffentliche `execute`-Tests anlegen.
- Alle CR-Bänder und Step-6-Bänder testen; unbekannte Katalog-IDs müssen als Boundary- bzw. `catalog-data`-Fehler erscheinen.

**Ergebnis:** Der Strict-Modus ist gegen die dokumentierten Quellen reproduzierbar abgesichert.

### 4. Lokale Draft-/Snapshot-Persistenz

- JSON-Workspace, atomare Writes und maximal 20 ältere Draft-Snapshots aus Issue 05 implementieren.
- `active`, `finalized`, `archived`, Duplizieren und immutable FinishedMonster abbilden.
- Persistenz ausschließlich über die gemeinsame Tool-Schnittstelle schreiben.

### 5. Finished Monster und Exporte

- `monster.finalize` nur für gültige Draft-Evaluationen erlauben.
- Das strukturierte Monster-Sheet erzeugen und daraus JSON, Markdown, HTML/Print deterministisch projizieren.
- Den Audit-Abschnitt für Concept, AI und Steps 1–9 aus Issue 06 mitschreiben.

### 6. Guided-Rail-UI

- Einen lokalen Browser-Workspace mit sichtbaren Steps 1–9, editierbaren vorherigen Entscheidungen und Live-Validierung bauen.
- Draft, Evaluation, Fehlercodes und Provenienz anzeigen; die UI darf keine Regelwerte selbst berechnen.

### 7. KI-Grenze anschließen

- Den Pi-SDK-Adapter aus Issue 07 erst nach dem Katalog-/Engine-Vertical-Slice anschließen.
- `catalog_list` hart erzwingen, danach nur Read-Tools erlauben und mit typisiertem `emit_proposal` beenden.
- Vorschläge bleiben immutable, bis `proposal.accept` sie durch die Engine validiert.

## Konkreter nächster Schritt

Mit Schritt 1 beginnen: Katalogdatei, Schema und den vollständigen APG/UM/UC-Datensatz (einschließlich der ACG-Nachprüfung) anlegen. Danach den Worg-Vertical-Slice über `execute` implementieren.

## Umsetzungsstand

**Milestone:** Worg/typed engine slice complete; Step-6 list-band resolution and small-size fixed natural damage remain explicitly out of scope.

Der erste vertikale Slice ist begonnen und lokal ausführbar:

- `catalog/catalog-v1.json` und `catalog/catalog.schema.json` enthalten die CR-Arrays, Damage-/Natural-Attack-Tabellen, Type-/Size-Grafts, den Worg-Optionspfad sowie 39 APG/UM/UC- und fünf ACG-Spell-Metadaten.
- `monster_builder.Engine.execute` unterstützt `draft.create`, `draft.get`, `draft.applyChanges` und `draft.evaluate` mit Revision/Fingerprint-Guard, Idempotency-Key, Boundary-/Domain-Fehlertrennung und stabilem Trace.
- Der Worg CR 2 und ein separater Step-6-Metadaten-/Metamagie-Fall sind als öffentliche `execute`-Tests abgesichert; JSONL läuft über `python -m monster_builder`.
- Step-6-Spell-Listen sind im Katalog quellenbelegt, werden im Slice aber noch nicht nach CR-Band in Primary/Secondary/Frequency samt List-Benefit ausgewertet.
- Fixed-1-Natural-Damage bei sehr kleinen Größen wird als expliziter `catalog-data`-Source-Gap gemeldet, nicht geraten.
- `README.md` und `pyproject.toml` dokumentieren den dependency-freien lokalen Start.

Noch nicht umgesetzt sind Step-6-Listenauflösung, Persistenz, Finalisierung/Exporte, UI, KI sowie die vollständigen Class-/Subtype-/Template-Grafts und Optionseffekte.

## Fertig-Kriterium für diesen Plan

Der MVP ist lieferbar, wenn ein lokaler Nutzer einen Strict-Draft vollständig durch Steps 1–9 führen, deterministisch evaluieren, als immutable Monster finalisieren und exportieren kann; KI bleibt bis dahin optional.
