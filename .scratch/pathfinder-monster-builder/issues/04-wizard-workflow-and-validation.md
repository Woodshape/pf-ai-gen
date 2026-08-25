# Wie soll der 9-Schritte-Wizard Monster Drafts führen?

Type: prototype
Status: resolved
Blocked by: none

## Question

Wie präsentiert der englische Browser-Wizard `Before You Begin` und die Steps 1–9, welche Entscheidungen sind pro Schritt sichtbar, wann werden Abhängigkeiten und Fehler angezeigt, darf der Benutzer zurückspringen, und wie werden KI-Vorschläge und Reality-Check-Anpassungen nachvollziehbar dargestellt?

## Answer

Der kanonische Wizard verwendet die **Guided-Rail-Struktur aus Variante A**. Die HTML/CSS-Oberfläche des Prototyps bleibt wegwerfbar; verbindlich ist die Interaktionsentscheidung.

### Layout und Navigation

- Eine linke, immer sichtbare Creation Rail zeigt `Before You Begin` und Steps 1–9 mit Nummer, Kurzname und Status (`Ready`, `Needs input`, `Invalid`, `Optional`).
- Der aktuelle Step erhält den Hauptbereich. Dort werden die sichtbaren Entscheidungen, Auswahlparameter, Quellreferenzen und – bei Step 1 – eine Baseline-Vorschau angezeigt.
- Ein rechter Bereich zeigt Live-Validation, den sichtbaren Draft-Zustand und nach gültiger Strict-Evaluation den Reality Check.
- `Back` und direkte Rail-Navigation erlauben jederzeit den Rücksprung zu früheren Entscheidungen. Auch spätere Steps dürfen zur Inspektion geöffnet werden; sie werden nicht aus dem Pfad entfernt, nur weil eine Abhängigkeit noch offen ist.
- `Continue` ist ein Komfortpfad, kein alleiniger Zustandsmechanismus. Ein unvollständiger oder ungültiger Step blockiert das Weiterführen und die Finalisierung, nicht aber das Speichern oder Inspizieren.

### Validierung und Abhängigkeiten

- Jede Draft-Änderung erzeugt eine neue Revision und löst sofort eine deterministische Evaluation aus.
- Abhängigkeiten werden direkt am betroffenen Step und in der Rail sichtbar. Ein Issue enthält stabilen Code, Draft-Pfad, Severity (`incomplete` oder `invalid`), konkrete Behebung und SourceRef; ein Link öffnet den zuständigen Step.
- Unvollständige und ungültige Drafts bleiben lesbar und editierbar. `canonical` und `effective` bleiben bis zu einer vollständigen, gültigen Strict-Evaluation nicht verfügbar.
- Die Engine repariert keine Auswahl stillschweigend und importiert keine normalen Pathfinder-Neuberechnungen in Arraywerte.

### AI-Proposals

- Der Header öffnet ein Proposal-Panel mit Proposal-ID, Base-Revision/Fingerprint, typisierten Changes, Diff, Rationale, Annahmen und SourceRefs.
- Ein Proposal ist zunächst nicht angewendet. Der Benutzer wählt Changes einzeln aus und muss die atomare Übernahme ausdrücklich bestätigen.
- Die Engine validiert alle ausgewählten Changes erneut. Bei einer zwischenzeitlich geänderten Draft-Revision ist das Proposal stale und muss neu erzeugt werden; automatisches Rebase oder Überschreiben ist ausgeschlossen.
- Nicht-kanonische AI-Ideen bleiben als Plain Text sichtbar und besitzen keine Change-ID. Sie können nicht übernommen werden.

### Reality Check

- Der Reality Check erscheint erst nach einer gültigen Strict-Evaluation und ist ein separater Review-Bereich.
- Findings enthalten Beobachtung, betroffene Entscheidung/Step und SourceRefs. `Acknowledge`, `Resolve through Step` und `Dismiss` ändern nur den Review-Status, nicht die kanonischen Werte.
- Ein Strict-MVP zeigt keinen manuellen Free-Override-Button als aktive Funktion. Free Mode bleibt die ausdrücklich getrennte, spätere Schicht über einem gültigen kanonischen Ergebnis.

Damit ist die Wizard-Entscheidung für Persistenz, Export und den ersten AI-Adapter festgelegt: Diese Teile integrieren sich in eine revisionierte Guided Rail, nicht in einen unabhängigen Schritt- oder Canvas-Navigator.

## Prototype artifact

[Open the throwaway browser prototype](../prototypes/04-wizard-workflow.html) directly in a browser. It is an in-memory English UI with three switchable variants (`?variant=A`, `?variant=B`, `?variant=C`). Variant A is retained as the primary interaction reference; the other variants remain comparison material.
