# Welche Monster-Sheet- und Export-Verträge sind verbindlich?

Type: grilling
Status: resolved
Blocked by: none

## Question

Welche Daten und welches Layout muss ein fertiges Monster Sheet enthalten, und wie sollen HTML/Print/PDF, Markdown und JSON jeweils aussehen? Entscheide insbesondere über Pathfinder-Statblock-Struktur, Quellenangaben, sichtbare Entscheidungsbegründungen, Optionen/Spells sowie die Trennung zwischen spielbereitem Sheet und bearbeitbarem Draft.

## Answer

### Autorität und Trennung von Draft und Sheet

Ein spielbereites Monster Sheet entsteht ausschließlich aus einem unveränderlichen `FinishedMonster`-Snapshot, der aus einer vollständigen und gültigen Evaluation erzeugt wurde. Ein unvollständiger oder ungültiger Draft darf gespeichert, inspiziert und als bearbeitbarer Draft exportiert werden, aber nicht als fertiges Monster Sheet.

`MonsterDraft` und `FinishedMonsterExport` sind getrennte JSON-Verträge:

- Der Draft enthält Concept-Daten und explizite Selections und bleibt bearbeitbar.
- Der fertige Export ist eine selbstständige Momentaufnahme mit Concept, akzeptierten Selections, finalem effektiven Ergebnis, Katalogversion, Provenienz und DerivationTrace.
- Die Quell-Draft-ID, Revision und der Fingerprint werden als Herkunft referenziert.
- Draft-Historie, Proposals, UI-Daten, HTML-/Markdown-Strings und kopierter Quelltext werden nicht in den fertigen Export übernommen.
- Die Auswahlentscheidungen werden trotz der Herkunftsreferenz im fertigen Export mitgeführt, damit er ohne Workspace verständlich und transportierbar bleibt.

Im Strict-Modus ist das effektive Ergebnis das kanonische Ergebnis. Ein späterer Free-Export verwendet ausschließlich das bestätigte effektive Ergebnis und stellt keine zweite kanonische Statblock-Variante daneben.

### Pathfinder-Statblock

Die menschenlesbaren Exporte verwenden die `Unchained Monster Statistics`-Struktur aus *Pathfinder Unchained*:

```text
NAME CR/HD X
Init ...; Perception ... (senses)
Size ...; Speed ...
DEFENSES
...
ATTACKS
...
STATISTICS
...
SPECIAL ABILITIES (optional)
...
```

Die Reihenfolge und Bezeichnungen des Unchained-Formats sind verbindlich. Nur explizit modellierte Daten werden ausgegeben. Nicht modellierte Felder wie XP, Alignment, Environment, Organization oder Treasure werden nicht erfunden und weggelassen.

Die spielrelevanten Optionen werden nachvollziehbar in den passenden Abschnitten aufgeführt:

- `Defense Options` unter `DEFENSES`.
- `Attack Options` unter `ATTACKS`.
- `Utility Options` für soziale und universelle Optionen unter `STATISTICS`.
- Längere, eigenständige Fähigkeiten erscheinen in einem optionalen `SPECIAL ABILITIES`-Abschnitt im Pathfinder-Format.

Rein numerische Effekte werden weiterhin in den numerischen Ergebniswerten angewendet. Sie werden nicht in einen zusätzlichen Optionsblock verschoben. Relevante Werte können aber eine deterministisch erzeugte Feldannotation erhalten:

```json
{
  "ac": 22,
  "fieldAnnotations": {
    "ac": "Includes +2 from extra armor."
  }
}
```

Das WYSIWYG-Sheet kann daraus beispielsweise `AC 22 (includes +2 from extra armor)` darstellen. Unveränderte Basiswerte erhalten keine leere Annotation. Der vollständige Beitrag bleibt zusätzlich im `DerivationTrace` nachvollziehbar.

### Spells und Spell-Like Abilities

Spells werden kompakt, aber ohne wesentliche Spielinformationen dargestellt. Eine Ausgabe kann beispielsweise so aussehen:

```text
Caster Level 5 (druid)
Attack Spell-Like Abilities (DC 15 + spell’s level) 1/day—fly
Utility Spells 3/day—...
```

Die Darstellung enthält, sofern vorhanden:

- Kategorie wie `Defensive`, `Attack` oder `Utility`.
- Frequenz wie `constant`, `at will`, `1/day` oder `3/day`.
- Spellnamen aus dem katalogisierten Spellbestand.
- DC-Formel und explizit gewählten Caster Level bzw. die Caster Class.
- katalogisierte Einschränkungen und Parameter.

Die lokalen Spell-Listen validieren die verwendeten Spell-IDs und liefern die Metadaten für Level, Liste und SourceRef. Vollständiger kopierter Spell-Regeltext gehört nicht in den Hauptstatblock; HTML-Audit und JSON dürfen zusätzliche Level-, Listen-, Quellen- und Kurzbeschreibungsdaten enthalten. Spell-List-Benefits werden als wirksame Fähigkeiten bzw. Anpassungen sichtbar und im Audit erklärt.

### Concept, AI-Begründungen und Audit

Der Export-Audit enthält das ursprüngliche Concept aus `Getting Started`, einschließlich der dort erfassten Rolle, des Themas, der narrativen Beschreibung, des Ziel-CRs und weiterer expliziter Concept-Daten. Zusätzlich werden die AI-Rationales und Annahmen der tatsächlich akzeptierten Änderungen exportiert. Stale, abgelehnte oder nicht übernommene Proposals werden nicht als Begründung des fertigen Monsters ausgegeben.

Der Audit hat diese Reihenfolge:

```text
Monster Concept
Accepted AI Rationale
Creation Decisions: Step 1–9
Reality Check / Validation Findings
Sources
```

Für relevante Entscheidungen aus Steps 1–9 zeigt der Audit mindestens `sourceId`, gedruckte PDF-Seite, PDF-Viewer-Seite und TXT-Zeilenbereich. Der JSON-`DerivationTrace` dokumentiert zusätzlich feldgenau, welche Selections und Katalogeinträge zu einem Wert beigetragen haben. Der kompakte Statblock enthält nur einen kurzen Generierungs-/Katalogvermerk und wird nicht mit technischen IDs überladen.

Es gibt zwei Darstellungsprofile:

- `sheet`: nur der spielbereite Statblock.
- `audit`: Statblock plus Concept, akzeptierte AI-Begründungen, Steps, Quellen, Trace und Findings.

HTML kann den Audit einklappbar darstellen. Markdown und PDF hängen ihn nach dem Statblock an, wenn das Audit-Profil gewählt wurde. Print/PDF verwendet standardmäßig das `sheet`-Profil.

### Deterministische Formate

HTML ist die semantische Referenzdarstellung. Print und PDF werden mit identischem Inhalt und identischer Feldreihenfolge daraus abgeleitet. Markdown ist eine strukturgleiche Textprojektion mit denselben Überschriften und Werten. Keines dieser Formate berechnet eigene Werte.

JSON ist die strukturierte Quelle für alle Renderer. Ein fertiger Export enthält mindestens `schemaVersion`, `kind`, `monsterId`, `sourceDraft`, `catalogVersion`, `mode`, `concept`, `selections`, `result`, `fieldAnnotations`, `derivationTrace` und die strukturierten Audit-/SourceRef-Daten. Er enthält keine gerenderten HTML-/Markdown-Fragmente und keinen kopierten Quelltext. Dadurch sind HTML, Print/PDF, Markdown und JSON deterministisch aus demselben Ergebnis ableitbar.
