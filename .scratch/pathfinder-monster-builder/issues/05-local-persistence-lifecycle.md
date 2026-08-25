# Wie werden Entwürfe und fertige Monster lokal gespeichert?

Type: grilling
Status: resolved
Blocked by: none

## Question

Welche lokale Datenstruktur und welcher Lebenszyklus gelten für Monster Drafts und fertige Monster? Entscheide über SQLite-Entitäten, eindeutige Identität, Statuswechsel, Speichern/Laden, Suche, Duplizieren sowie den kleinen erlaubten Änderungsverlauf, ohne daraus eine vollständige Versionsverwaltung zu machen.

## Answer

## Entscheidung: Versionierte JSON-Dateien statt SQLite im MVP

Der MVP verwendet keinen SQLite-Speicher. SQLite-Entitäten sind deshalb keine autoritative Schnittstelle; ein späterer SQLite-Adapter kann dieselben fachlichen Entitäten abbilden. Alle autoritativen Schreibvorgänge laufen weiterhin über die gemeinsame Operationsschnittstelle.

Der konfigurierbare Workspace hat dieses Layout:

```text
<workspace>/
  drafts/<draftId>.json
  proposals/<proposalId>.json
  monsters/<monsterId>.json
  index.json
```

`index.json` ist nur ein rebuildbarer Such-Cache. Die Draft-, Proposal- und Monsterdateien sind die Quelle der Wahrheit. Evaluations werden für Drafts nicht als eigene Dateien gespeichert, da sie abgeleitet sind.

## Identität und Datenstruktur

- `draftId`, `monsterId` und `proposalId` sind opake, typisierte UUIDs, z. B. `draft_<uuid>`, `monster_<uuid>` und `proposal_<uuid>`. IDs werden nie wiederverwendet und enthalten keine fachliche Bedeutung.
- Eine Draft-Revision ist eine monotone Ganzzahl innerhalb eines Drafts.
- Der Fingerprint ist ein SHA-256-Hash des kanonischen JSON-Inhalts.
- Eine Draft-Datei enthält den aktuellen Snapshot und höchstens 20 ältere vollständige Snapshots:

```json
{
  "schemaVersion": "1",
  "current": { "revision": 21, "fingerprint": "...", "draft": {} },
  "history": [
    { "revision": 20, "fingerprint": "...", "draft": {} }
  ]
}
```

Die Snapshots enthalten nur Concept-Daten und explizite Draft-Selections, niemals berechnete Regelwerte. `current` plus maximal 20 `history`-Einträge bilden bewusst eine kleine Historie, keine vollständige Versionsverwaltung.

Ein `FinishedMonster` ist ein eigener, unveränderlicher Snapshot. Er enthält mindestens seine `monsterId`, die Quell-`draftId`, Quell-Revision und Quell-Fingerprint, die `catalogVersion`, das berechnete Ergebnis sowie dessen DerivationTrace. Im Strict-MVP sind kanonisches und effektives Ergebnis identisch. Der Snapshot wird nicht stillschweigend gegen einen neueren Katalog neu berechnet.

## Lebenszyklus

### Drafts

Ein Draft hat unabhängig vom Evaluation-Status (`incomplete`, `invalid`, `valid`) einen Persistenzstatus:

```text
active -> finalized
active -> archived
finalized -> archived
archived -> vorheriger Status durch restore
```

Nur ein vollständiger und gültiger Strict-Draft darf finalisiert werden. Die Finalisierung erzeugt ein fertiges Monster und setzt den Quelldraft auf `finalized`; dieser bleibt danach schreibgeschützt. Ein finalisierter Draft wird durch `restore` nicht wieder editierbar.

### Fertige Monster

```text
active -> archived
archived -> active durch restore
```

Fertige Monster sind unveränderlich. Es gibt kein normales Hard-Delete. Ein neues fertiges Monster mit neuer Identität entsteht durch Duplizieren in einen neuen Draft und erneutes Finalisieren. Wiederholtes Finalisieren derselben Draft-Revision ist idempotent und liefert den bereits vorhandenen Snapshot zurück.

## Speichern, Laden und Wiederherstellen

`draft.create` und `draft.applyChanges` schreiben automatisch; ein separates `save` gibt es nicht. Vor jeder Mutation werden `baseRevision`, `baseFingerprint` und bei Wiederholungen der `requestId` geprüft.

Der Persistenzadapter verwendet einen Lock pro Draft und schreibt zunächst in eine temporäre Datei, die anschließend atomar ersetzt wird. Bei einer Draft-Mutation werden aktueller Snapshot und Historie in einem Schreibvorgang aktualisiert.

- `draft.get` lädt den aktuellen Snapshot.
- `draft.history.get` liest ältere Snapshots.
- `draft.restoreRevision` übernimmt einen älteren Snapshot als **neue** aktuelle Revision; es gibt kein In-place-Rollback.
- `draft.restore` und `monster.restore` machen Archivierung rückgängig.
- Beschädigte oder inkompatible JSON-Dateien erzeugen sichtbare Ladefehler und werden nicht stillschweigend repariert.
- Schema-Migration erfolgt nur über einen expliziten Import-/Migrationsschritt.
- Ein fertiger Snapshot bleibt auch bei nicht mehr unterstützter Katalogversion lesbar. Ein Draft mit einer nicht unterstützten Katalogversion bleibt ladbar, ist aber nicht evaluierbar.

Die Finalisierung verändert zwei Dateien in einfacher, wiederholbarer Reihenfolge: zuerst wird der fertige Monster-Snapshot atomar geschrieben, danach der Quelldraft mit Status `finalized` und `monsterId`. Beim Laden kann ein passender Monster-Snapshot anhand von Draft-Fingerprint und Quellrevision erkannt werden; ein Abbruch zwischen den Schritten bleibt dadurch sicher wiederholbar. Ein komplexes Transaktionssystem ist nicht erforderlich.

## Proposals und Duplizieren

Proposals bleiben unveränderlich gespeichert, solange der zugehörige Draft aktiv ist. Akzeptierte Proposals bleiben zur Nachvollziehbarkeit erhalten; stale oder abgelehnte Proposals dürfen explizit bereinigt werden. Sie gehören nicht zur Draft-Historie und können nicht zur Wiederherstellung verwendet werden. Nach Archivierung werden sie mit dem Draft archiviert; automatisch gelöscht werden sie nicht.

`draft.duplicate` und `monster.duplicate` erzeugen jeweils einen neuen aktiven Draft:

- Concept und explizite Selections werden kopiert.
- `draftId` und Revision werden neu erzeugt (`revision: 1`).
- Historie, Evaluation, berechnete Werte und Proposals werden nicht kopiert.
- `derivedFrom` verweist auf die ursprüngliche Draft-Revision oder das fertige Monster.

## Suche

`library.search` arbeitet über `index.json`. Der Index enthält Such- und Filterfelder für Name, Rolle, Thema, Beschreibung, Typ, Status und CR. Aktive Drafts und fertige Monster werden standardmäßig gefunden; archivierte Einträge benötigen `includeArchived`. Proposals gehören nicht zur normalen Monsterbibliothek. Der Index kann jederzeit durch Scannen der autoritativen Dateien neu aufgebaut werden.

## Persistenz-Operationen

Zusätzlich zu den bestehenden Draft-Operationen gelten:

```text
draft.history.get
draft.restoreRevision
draft.duplicate
draft.archive
draft.restore

monster.finalize
monster.get
monster.duplicate
monster.archive
monster.restore
library.search
```
