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

### 4. Lokale Draft-/Snapshot-Persistenz — Draft-Slice umgesetzt

- JSON-Workspace, atomare Writes und maximal 20 ältere Draft-Snapshots aus Issue 05 implementieren.
- `active`, `finalized`, `archived`, Duplizieren und immutable FinishedMonster abbilden.
- Persistenz ausschließlich über die gemeinsame Tool-Schnittstelle schreiben.

### 5. Finished Monster und Exporte — umgesetzt

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

Die Guided-Rail-UI aus Issue 04 auf die gemeinsame `execute`-Schnittstelle setzen: sichtbare Steps 1–9, editierbare frühere Entscheidungen, Live-Evaluation, Finalisierung und Exporte. Komplexe Encounter-Aktionen bleiben explizite Source-Rule-Fähigkeiten.

## Umsetzungsstand

**Milestone:** all 19 class, 41 source-listed subtype, 10 template, and 162 Step-7/unmodified-rule option records are catalogued; direct typed effects cover numeric paths and prerequisites while complex encounter actions remain source-rule abilities. The Witch class is an explicit strict-mode source gap because its Knowledge (arcana) rank is omitted.

Der erste vertikale Slice ist begonnen und lokal ausführbar:

- `catalog/catalog.json` und `catalog/catalog.schema.json` enthalten die CR-Arrays, Damage-/Natural-Attack-Tabellen, Type-/Size-Grafts, die Worg-/Griffon-/Medusa-Optionspfade, alle 60 strukturierten Step-6-Listen sowie 39 APG/UM/UC- und fünf ACG-Spell-Metadaten. Nicht-Core-Spells und Core-Metamagie sind lokal mit Hash und offizieller Quellen-URL verankert. Die Katalogversion ist ein inhaltsbasierter Fingerprint; es gibt noch keine Kompatibilitätsschicht für alte Entwicklungskataloge.
- `monster_builder.Engine.execute` unterstützt `draft.create`, `draft.get`, `draft.applyChanges` und `draft.evaluate` mit Revision/Fingerprint-Guard, Idempotency-Key, Boundary-/Domain-Fehlertrennung und stabilem Trace. Class-Grafts erzwingen Required Arrays, unterdrücken Type-Statistikänderungen, wenden nur den höchsten CR-Eintrag an und unterstützen Slots, Replacements, Save-Choices und As-if-CR-Spellcasting. Subtype-Grants sind zusätzlich; Template-Grants verbrauchen normale Slots und prüfen Voraussetzungen.
- Worg, Griffon, Medusa, Goblin Druid, Fighter, Sorcerer, Clockwork, Skeleton, Lycanthrope, Metadaten-/Metamagie, das CR-9-Aberrant-Beispiel, Draft-/FinishedMonster-Persistenz und Exporte sind in 95 öffentlichen bzw. offline ausführbaren Tests abgesichert. Die Matrix deckt alle 93 Step-1-Zeilen, jedes Attack-Profil, alle 231 Zellen von Table 5-9, alle 162 Options auf einem gültigen Pfad, harte Prärequisiten, typisierte Skalierungsgrenzen, alle Size-Grenzen und beide Seiten aller Spell-Bänder ab; JSONL läuft über `python -m monster_builder`.
- Step-6-Listen werden nach CR-Band in Primary/Secondary und `1/day`/`3/day`/`at will` aufgelöst. Alle 51 numerischen bzw. auswahlabhängigen List-Benefits besitzen typisierte Katalogeffekte; direkt bestimmbare Feldänderungen werden angewandt, kontextabhängige Modifikatoren bleiben explizit. Fehlende dynamische Choices halten den Draft sichtbar `incomplete`.
- Fixed-1- und nicht von Table 5-9 abgedeckte kleine Natural-Damage-Dice werden als explizite `catalog-data`-Source-Gaps gemeldet, nicht geraten.
- `README.md` und `pyproject.toml` dokumentieren den dependency-freien lokalen Start; nur die Katalog-Regeneration benötigt zusätzlich `pdftotext`.

Draft- und FinishedMonster-Persistenz sind mit konfigurierbarem JSON-Workspace, atomaren Writes, Lifecycle, Duplizieren und immutable Snapshots umgesetzt. Gültige Strict-Drafts können finalisiert und aus derselben strukturierten Quelle als JSON, Markdown und standalone HTML/Print mit Sheet-/Audit-Profil exportiert werden. Noch nicht umgesetzt sind Proposal-Persistenz, UI und KI. Komplexe Encounter-Aktionen bleiben bewusst als Source-Regeln im kanonischen Ergebnis, solange sie keine deterministische Monster-Sheet-Statistik verändern.

## Fertig-Kriterium für diesen Plan

Der MVP ist lieferbar, wenn ein lokaler Nutzer einen Strict-Draft vollständig durch Steps 1–9 führen, deterministisch evaluieren, als immutable Monster finalisieren und exportieren kann; KI bleibt bis dahin optional.
