# Welche Draft- und Validierungsgrenzen hat die deterministische Regel-Engine?

Type: grilling
Status: resolved
Blocked by: none

## Question

Wie wird ein Monster Draft fachlich modelliert, und welche Invarianten muss die Regel-Engine erzwingen? Entscheide insbesondere, welche Werte Eingaben, gewählte Quellenentscheidungen oder abgeleitete Werte sind, wie optionale Steps und Graft-Abhängigkeiten dargestellt werden, wie ungültige Kombinationen abgelehnt werden und wie explizite Reality-Check-Anpassungen vom normalen Ergebnis getrennt bleiben.

## Answer

## Entscheidung: Draft, Proposal und Ergebnis sind getrennte Modelle

Der `Monster Draft` ist die aktuelle, editierbare Beschreibung eines Monsters. Er enthält Concept-Daten und ausschließlich explizite, katalogisierte Entscheidungen. Er enthält keine von der Engine berechneten Zahlen.

Eine AI oder ein Benutzer kann zunächst ein `Proposal` erzeugen. Ein Proposal ist nicht autoritativ. Es bleibt als unveränderlicher Ausgangspunkt erhalten; seine Änderungen werden erst nach Benutzerbestätigung auf den aktuellen Draft angewendet. Danach ist ausschließlich die aktuelle Draft-Revision maßgeblich. Deshalb darf sich das fertige Ergebnis vom ursprünglichen Proposal unterscheiden.

Die Engine erzeugt aus dem aktuellen Draft eine `Evaluation`:

```text
MonsterDraft
  schemaVersion
  draftId
  catalogVersion
  revision
  fingerprint
  concept
  selections

DraftProposal
  proposalId
  baseDraftId
  baseRevision
  baseFingerprint
  typedChanges
  assumptions
  rationale

Evaluation
  status: incomplete | invalid | valid
  mode: strict | free
  canonical
  effective
  issues
  derivationTrace
```

`canonical` ist das Ergebnis der normalen Simple-Monster-Creation-Regeln. Im `strict`-Modus sind `canonical` und `effective` identisch. Im `free`-Modus ist `effective` das kanonische Ergebnis mit ausdrücklich akzeptierten Free Overrides.

Jede Änderung am Draft erzeugt eine neue Revision und einen neuen Fingerprint. AI-Proposals sind immer an die Revision gebunden, von der sie ausgehen. Ein veraltetes Proposal darf keine neueren Benutzeränderungen überschreiben.

## Eingaben, Quellenentscheidungen und abgeleitete Werte

### Concept-Daten

Concept-Daten beschreiben die Absicht, nicht die Regelberechnung:

- Name, Rolle, Thema und narrative Beschreibung.
- Optionales `targetCR` als Absicht. Das autoritative CR liegt in den Draft-Selections; wenn beide angegeben sind, müssen sie übereinstimmen, andernfalls entsteht mindestens eine Warnung.
- Beabsichtigte Kreatur, Bewegung und Einsatzweise als Leitplanken.

### Explizite Draft-Selections

Selections sind Benutzer- oder AI-Entscheidungen. Sie enthalten IDs aus der versionierten Regelbasis und typisierte Parameter, niemals kopierte Regelzahlen:

- CR und genau ein Array.
- Creature-Type-Graft und höchstens ein primäres Class-Graft.
- Unterstützte Subtype-Grafts, höchstens ein Template-Graft und die Size-Auswahl.
- Save-Swap, Ability-Modifier-Zuordnung und optionale bzw. elective Graft-Entscheidungen.
- Spell-List bzw. einzelne katalogisierte Spells und zulässige Spell-Parameter.
- Monster-Optionen mit katalogisierten IDs und typisierten Parametern. Die Kategorie und der Slot werden von der Engine aus Array und Grafts bestimmt; sie werden nicht aus dem Client vertraut.
- Good-/Master-Skill-Auswahl.
- Angriffsdarstellung, Waffen- oder Natural-Attack-Profil und andere durch die Quelle definierte Angriffsentscheidungen.
- Direkte, nicht abgeleitete Concept-Werte wie Basisbewegung, sofern sie für den Monsterentwurf erforderlich sind.

Ein fehlender optionaler Step wird als bewusst nicht gewählt behandelt. Ein noch nicht beantworteter erforderlicher Step bleibt `incomplete`; er bekommt keinen erfundenen Defaultwert.

### Abgeleitete Werte

Die Engine berechnet aus den Selections unter anderem:

- Array-Baselines und alle ausdrücklich erlaubten Graft-/Option-Adjustments.
- AC, Touch AC, Flat-Footed AC, Saves, CMD, hp, Ability DC und Spell DC.
- Ability-Modifikatorwerte, Skill-Boni, Perception, Initiative, Concentration und Hit Dice.
- Option-Budgets, Slot-Zuordnung, automatisch gewährte bzw. ersetzte Optionen und deren Effekte.
- Spell Uses, Spell-Level, Spell-DCs und List-Benefits.
- Angriffsbons, durchschnittlichen Schaden, Damage Dice und Damage Expressions.
- CMB, Bewegungsgrants und alle übrigen Monsterwerte.

Die Engine wendet keine normalen Pathfinder-Neuberechnungsformeln auf Arraywerte an. Ein Graft oder eine Option darf nur die Werte verändern, die der katalogisierte Effekt ausdrücklich nennt.

## Harte Invarianten

### Source-Rules

Diese Regeln folgen dem Simple-Monster-Creation-Kapitel:

1. Ein Draft hat genau ein CR-basiertes Array. Die Arraywerte sind bereits Gesamtwerte.
2. Ein Creature-Type-Graft wird immer gewählt. Bei einem Class-Graft bleiben die automatischen Type-Traits erhalten, aber die Statistik-Adjustments des Type-Grafts werden nicht angewendet.
3. Ein Class-Graft hat ein Required Array; es wird nur der höchste für das CR passende CR-Eintrag angewendet.
4. Subtype-Fähigkeiten sind automatisch. Durch Subtypes gewährte Optionen und Skills sind zusätzlich und verbrauchen kein normales Budget.
5. Template-Prerequisites, CR-Grenzen sowie erforderliche Types/Subtypes müssen erfüllt sein. Template-Automatic-Traits zählen dagegen gegen normale Optionen und Skills bzw. ersetzen diese; sie dürfen das normale Maximum überschreiten.
6. Ein Size-Graft darf nur innerhalb seiner CR-Grenzen gewählt werden. Es verändert nur die im Graft genannten Werte; Touch AC bleibt höchstens AC und Flat-Footed AC mindestens 1.
7. Step 6 gilt für den Spellcaster-Array. Nicht-Spellcaster erhalten einzelne oder wenige Spells nur über eine katalogisierte Option bzw. einen entsprechenden Graft.
8. Option-Kategorien, `any`-Slots, Universal-Optionen, Replacement-/Free-Grants und alle Optionsparameter werden aus Katalog und Grafts geprüft. Duplikate sind zulässig, wenn die Option sie erlaubt bzw. sie sinnvoll katalogisiert ist.
9. Good- und Master-Skills verwenden den Array-Bonus direkt; der Ability-Modifikator wird nicht noch einmal addiert. Perception erhält den Good-Bonus automatisch.
10. Array-Schaden ist zunächst ein durchschnittlicher Wert. Damage Dice und Expressions werden erst aus dem gewählten Waffen- oder Natural-Attack-Profil und Table 5–9 abgeleitet.
11. CMB, Concentration, Hit Dice, Initiative, Perception und Speed folgen den ausdrücklich definierten Other-Calculations-Regeln.

### Product-Constraints des Strict-Modus

Nicht jede dieser Grenzen ist eine wörtliche Verbotsregel der Quelle; sie macht die Software deterministisch und nachvollziehbar:

- Genau ein primäres Class-Graft; normale Multiclass-Simulation ist nicht Teil des Strict-Modus.
- Höchstens ein Template-Graft; Template-Stacking wird in Version 1 nicht unterstützt.
- Komplexe oder nicht katalogisierte Subtypes werden als unsupported abgelehnt, nicht durch erfundene Grafts ergänzt.
- Golden-Rule-Anpassungen, freie zusätzliche Optionen und nicht modellierte zusätzliche Angriffe sind keine Strict-Selections. Sie benötigen entweder einen katalogisierten Effekt oder den `free`-Modus.
- Regelwerte werden nur über katalogisierte IDs und Parameter referenziert. Unbekannte IDs, falsche Parameter oder eine nicht unterstützte Katalogversion sind harte Fehler.

Jede Invariante wird im Validierungsfehler als `source-rule`, `product-constraint` oder `catalog-data` gekennzeichnet. Dadurch bleibt sichtbar, ob ein Fehler aus Pathfinder Unchained, aus dem Strict-Produktumfang oder aus einem fehlenden/inkompatiblen Katalogeintrag stammt.

## Validierung und Berechnung

Die Engine ist eine reine, deterministische Auswertung: Sie mutiert keinen Draft und repariert keine Eingabe stillschweigend. Externe JSON- und AI-Eingaben gelten zunächst als untrusted und müssen an der Engine-Schnittstelle gegen Draft-Schema, Katalogversion, IDs und typisierte Parameter validiert werden.

Jeder Issue enthält mindestens einen stabilen Fehlercode, einen Pfad in Draft oder Evaluation, eine Severity und die relevanten SourceRefs:

- `incomplete`: erforderliche Entscheidung fehlt noch.
- `invalid`: eine vorhandene Entscheidung verletzt eine Invariante.
- `valid`: alle erforderlichen Entscheidungen sind vorhanden und es gibt keine Errors.
- `warning` und `suggestion` blockieren die Validierung nicht; ein `error` blockiert Finalisierung.

Ein `free`-Ergebnis setzt eine vollständige, gültige Strict-Evaluation voraus. Free ist ein Override-Layer und kein Bypass der Regeln.

## AI-Dialog

Der AI-Adapter arbeitet iterativ am selben Draft:

1. AI erzeugt ein initiales, möglicherweise noch unvollständiges Proposal.
2. Der Benutzer übernimmt einzelne oder alle typisierten Änderungen und kann selbst weitere Selections ändern.
3. Der Benutzer bittet die AI mit dem aktuellen Draft erneut um Ergänzungen, Alternativen oder eine Erklärung.
4. Jedes neue Proposal referenziert die aktuelle Draft-Revision und wird vor der Übernahme durch dieselbe deterministische Engine validiert.

Die AI darf rationale Vorschläge, Annahmen und offene Entscheidungen liefern, aber weder den Draft direkt mutieren noch berechnete Werte als Selections einschleusen.

## Reality Check und Free-Modus

Ein `RealityCheckItem` ist ein Review-Eintrag, kein berechneter Wert und kein Override. Er kann `open`, `acknowledged`, `resolved-strict`, `accepted-free` oder `dismissed` sein:

- `resolved-strict`: Eine Änderung an gültigen Selections beseitigt den Befund in der kanonischen Evaluation.
- `accepted-free`: Ein verknüpftes Free Override behebt die sichtbare Abweichung, während das kanonische Ergebnis abweicht.
- `dismissed`: Die Abweichung wird bewusst akzeptiert und begründet.

Der `free`-Modus darf nur monsterrelevante Ergebnisfelder überschreiben, niemals Draft-Identität, Katalogversion, SourceRefs, Revision, Status, Trace oder andere System-/Hintergrundfelder. Ein Override enthält mindestens Pfad, kanonischen Wert, effektiven Wert, Grund, Autor (`user` oder `ai`) und Benutzerbestätigung.

Free Overrides werden unabhängig angewendet: Sie lösen in Version 1 keine Neuberechnung anderer Felder aus. Wenn beispielsweise der Angriffswert und der CMB abweichen sollen, müssen beide ausdrücklich überschrieben werden. Ein AI-vorgeschlagenes Override wird erst nach Benutzerbestätigung wirksam.

Overrides sind an Draft- und Canonical-Result-Fingerprint gebunden. Nach einer Änderung an den Selections werden sie stale und müssen ausdrücklich neu bestätigt werden.

Editor und Evaluation zeigen bis zum Export sowohl `canonical` als auch `effective`. Ein Strict-Monster-Sheet verwendet das kanonische Ergebnis; ein Free-Monster-Sheet wird ausschließlich aus dem final bestätigten `effective`-Ergebnis erzeugt und enthält nicht zusätzlich die kanonische Vergleichsversion.

## Provenienz und Folgetickets

Draft und Evaluation speichern die Katalogversion und referenzieren SourceRefs statt Regeltext oder Regelzahlen zu duplizieren. Jede abgeleitete Zahl muss ihre beitragenden Katalogeinträge und Selections über einen DerivationTrace nachvollziehbar machen.

Damit sind die Grundlagen für Ticket 03 (gemeinsame Draft-/Proposal-/Evaluation-Schnittstelle), Ticket 04 (Wizard-Zustände), Ticket 05 (getrennte Speicherung von Draft, Proposal, Evaluation und Review) und Ticket 06 (Export des jeweils gewählten Ergebnisses) festgelegt.

### Quellenabgleich

- Before You Begin, Array und Other Calculations: `Pathfinder Unchained.pdf`, gedruckte S. 194–203 (PDF viewer S. 1–10); `Pathfinder Unchained.txt`, Zeilen 1–801.
- Creature-/Class-Grafts: gedruckte S. 204–213 (PDF viewer S. 11–20); TXT Zeilen 802–1750.
- Subtype-Grafts: gedruckte S. 214–215 (PDF viewer S. 21–22); TXT Zeilen 1751–1938.
- Template- und Size-Grafts: gedruckte S. 216–217 (PDF viewer S. 23–24); TXT Zeilen 1939–2135.
- Spells: gedruckte S. 218–227 (PDF viewer S. 25–34); TXT Zeilen 2136–3131.
- Monster Options: gedruckte S. 228–239 (PDF viewer S. 35–46); TXT Zeilen 3132–4333.
- Skills und Damage: gedruckte S. 240–241 (PDF viewer S. 47–48); TXT Zeilen 4334–4497.
