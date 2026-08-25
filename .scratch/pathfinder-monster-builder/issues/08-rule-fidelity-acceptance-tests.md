# Welche Tests beweisen die 1:1-Regeltreue?

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

Welche Akzeptanz- und Regressionstests müssen beweisen, dass die Engine die PDF/TXT-Regeln exakt ausführt? Entscheide über bekannte Beispielmonster, Tabellen-Grenzwerte, CR-Bänder, Graft-Abhängigkeiten, Option- und Spell-Validierung, Damage-Umrechnung, Reality-Check-Markierungen und die Übereinstimmung des finalen Monster Sheets mit dem Draft.

## Answer

### Entscheidung: Verhalten wird an den gemeinsamen Schnittstellen geprüft

Die Akzeptanz- und Regressionstests prüfen das Verhalten ausschließlich über die öffentliche, versionierte `execute(request)`-Schnittstelle aus Issue 03. Dazu gehören insbesondere:

- `draft.create`, `draft.applyChanges` und `draft.evaluate` für Entwurf, Revision, Validierung und Berechnung.
- `monster.finalize` und die Export-Operationen für die Grenze zwischen Evaluation und fertigem Monster.
- `proposal.create` und `proposal.accept`, soweit ein Proposal katalogisierte Draft-Changes betrifft.

Es gibt keine verpflichtenden Tests privater Rechenfunktionen, Parser oder Effect-Handler. Ein Defekt zählt als behoben, wenn das beobachtbare Schnittstellenverhalten stimmt. Die vollständige Tabellenabdeckung wird deshalb ebenfalls über öffentlich auswertbare Drafts und Evaluations geprüft; ein interner Katalog-Spiegel wird nicht zur zweiten Quelle der Wahrheit.

Jeder Test verwendet eine unabhängige, handgeprüfte Erwartung aus der jeweiligen Quelle. Erwartungswerte dürfen nicht aus derselben Berechnung wie die zu prüfende Engine erzeugt werden.

### Testvertrag und Determinismus

Die Schnittstellentests müssen beweisen:

- Wiederholte Evaluation desselben Drafts mit derselben Katalogversion liefert dasselbe Ergebnis, dieselbe Feldreihenfolge und denselben `derivationTrace`.
- `draft.evaluate` mutiert weder Draft noch Proposal.
- Unvollständige Drafts liefern `ok: true` mit `status: incomplete`; bekannte, aber unzulässige Entscheidungen liefern `ok: true` mit `status: invalid` und stabilen Issue-Codes.
- Unbekannte IDs, falsche typisierte Parameter, ungültige Schema- oder Katalogversionen sind Boundary-Fehler (`ok: false`) und werden nicht stillschweigend repariert.
- Jede fachliche Meldung enthält einen stabilen Code, einen Draft-/Ergebnis-Pfad, die Kategorie (`source-rule`, `product-constraint` oder `catalog-data`) und — sofern eine Regel betroffen ist — die passende `SourceRef`.
- Berechnete Werte können nicht als Draft-Selections eingeschleust werden.

### Verbindliche Beispiel-Fixtures

#### Strikte Golden Fixtures

Diese drei Fixtures erhalten vollständige, literale Erwartungswerte für Draft, Evaluation, Trace und fertigen Export:

1. **Worg CR 2** — einfacher Type-Graft-Pfad mit Magical-Beast-Traits, Stat-Adjustments, Improved Combat Maneuver, Master Perception und zwei Good Skills.
2. **Griffon CR 4** — Type-Graft, Large-Size-Graft, zwei Natural-Attack-Profile, zwei Optionen und Damage-Zuordnung mit unterschiedlichen Natural-Attack-Dice.
3. **Medusa CR 7 vor dem Reality Check** — vollständige Durcharbeitung von Concept und Steps 1–9: Save-/Attack-Anpassungen des Monstrous-Humanoid-Grafts, Gaze und Poison, Skills und Damage Dice. Die im Buch danach vorgenommene Schadensreduktion ist kein Strict-Ergebnis.

Die erwarteten Werte und Entscheidungen stammen aus `Pathfinder Unchained.txt`, nicht aus einer Neuberechnung des Testcodes.

#### Homebrew-Class-Fixture

Der Standardfall **Goblin Level 4 Druid, Level 1 Rogue** muss als Concept und Proposal abbildbar sein:

- Die Klassenstufen ergeben im MVP die sichtbare CR-Annahme `4 + 1 - 1 = 4`.
- Der Draft verwendet genau einen primären Class-Graft, hier Druid, und dessen Required Array.
- Der Rogue-Anteil bleibt als Concept-/Assumption-Information sichtbar und darf nur durch separat katalogisierte Skills oder Monster Options ausgedrückt werden.
- Es gibt keinen zweiten Rogue-Class-Graft, keine gestapelten Class-Graft-Statistik-Adjustments und keine simulierten Rogue-Level-Fähigkeiten.
- Eine Proposal-Übernahme darf nur tatsächlich katalogisierte Rogue-nahe Skills/Options anwenden; nicht katalogisierte Multiclass-Behauptungen bleiben Text bzw. erzeugen einen sichtbaren Strict-Befund.

Damit ist der Homebrew-Fall repräsentierbar, ohne die beschlossene Strict-Grenze gegen Multiclass-Simulation zu brechen.

#### Kompatibilitäts- und Negativ-Fixtures

Die übrigen Buchbeispiele werden als gezielte Regressionen verwendet, aber nicht blind gegen den gedruckten End-Statblock verglichen. Goblin Fighter, Zombie Minotaur, Bat Swarm, Imp, Fire Giant, Satyr, Frost Giant Explorer und Vampire Cleric enthalten jeweils zusätzliche Optionen, Sonderfähigkeiten, freie Abweichungen oder Reality-Check-Anpassungen. Für sie wird geprüft:

- welche source-validen Entscheidungen die Engine akzeptiert,
- welche nicht-kanonischen bzw. noch nicht modellierten Teile als Warnung oder Fehler sichtbar bleiben,
- dass die Engine keine freie Buch-Anpassung stillschweigend übernimmt.

### Vollständige Tabellen- und Grenzwertabdeckung

#### Step 1 und Bestiary-Benchmarks

Über `execute` werden alle CR-Schlüssel `1/2` und `1`–`30` für Combatant, Expert und Spellcaster evaluiert. Für jede Zeile werden mindestens AC/Touch/Flat-Footed, Saves, CMD, hp, Ability DC, Spell DC, Ability-Modifikatoren, Good-/Master-Skills, Options-Budget sowie alle Attack-/Average-Damage-Profile gegen unabhängige Literale geprüft.

Zusätzlich werden die vollständigen CR-Zeilen der Bestiary Table 1–1 geprüft. Diese Benchmarkdaten dienen als Quelle für den Reality-Check, ändern aber im Strict-Modus keinen Arraywert.

Boundary-Fälle umfassen insbesondere CR `1/2`, `1`, `2`, `3`, `4`, `7`, `8`, `12`, `15`, `16`, `20`, `21` und `30` sowie Save-Swaps, Ability-Modifikator-Zuordnung und den Nachweis, dass Arraywerte nicht aus normalen Pathfinder-Formeln neu berechnet werden.

#### Graft-Abhängigkeiten

Die Schnittstellentests decken jede Graft-Familie und ihre harten Grenzen ab:

- genau ein Creature-Type-Graft; ein Class-Graft erzwingt sein Required Array und unterdrückt nur die Statistik-Adjustments des Type-Grafts, nicht dessen automatische Traits;
- beim Class-Graft wird ausschließlich der höchste passende CR-Eintrag angewendet;
- Subtype-Grants für Skills und Options sind zusätzlich und verbrauchen kein normales Budget;
- Template-Voraussetzungen für Type/Subtype/CR werden an den unteren und oberen Grenzen geprüft; Template-Automatic-Traits zählen dagegen zum normalen Budget bzw. ersetzen es entsprechend dem Katalog;
- alle Size-Grafts werden jeweils an ihrer CR-Grenze und knapp außerhalb geprüft: Fine `≤2`, Diminutive `≤4`, Tiny `≤6`, Small ohne CR-Grenze, Large `≥2`, Huge `≥4`, Gargantuan `≥6`, Colossal `≥8`;
- Touch AC überschreitet nie AC und Flat-Footed AC fällt nie unter 1;
- fehlende optionale Steps bleiben bewusst ungefüllt; erforderliche, noch nicht beantwortete Steps bleiben `incomplete`.

#### Spells und CR-Bänder

Für Spellcaster-Arrays und `secondary magic` werden die Bänder `0–3`, `4–7`, `8–11`, `12–15` und `16+` jeweils mindestens an beiden Seiten der Übergänge geprüft. Die Tests erwarten exakt:

- Primary-Spells der eigenen Band mit `1/day`;
- Primary und Secondary der nächstniedrigeren Band mit `3/day`, außer bei CR `0–3`;
- Primary der zwei Bänder niedrigeren Band `at will`, außer bei CR `0–7`;
- Spell-DC als Array-Spell-DC plus Spell-Level, einschließlich der Regel für Cleric-/Sorcerer-Wizard-Level bzw. den höchsten im Spell-Eintrag genannten Level;
- List-Benefit und dessen CR-Schwellen als Ergebnis und Trace.

Core-Spells werden mit ihren Klassen-/Level-Metadaten geprüft. APG-, UM- und UC-Spells ohne lokalen Metadatensatz aus Issue 09 bleiben ein erwarteter `unresolved`-/`catalog-data`-Befund und dürfen im Strict-Modus nicht geraten oder als gültig ausgegeben werden.

#### Monster Options

Jede katalogisierte Option erhält mindestens einen Schnittstellentest mit gültigem Einsatz. Zusätzlich werden für jede Option mit Voraussetzungen oder CR-Skalierung die ungültige Voraussetzung und jede CR-Schwelle getestet. Die Matrix umfasst:

- Combat-, Magic-, Social- und Universal-Kategorien;
- Universal-Options in einem beliebigen Slot und `any`-Slots mit jeder erlaubten Kategorie;
- Replacement-, Free- und zusätzliche Grants aus Grafts;
- zulässige und unzulässige Duplikate;
- typisierte Parameter, z. B. Schadens-/Energietyp, Ziel, gewählte Fähigkeit oder gewählte Unterart;
- harte Voraussetzungen wie `snatch` mit Improved Combat Maneuver (grab) und `corrupting touch` mit Incorporeal;
- CR-Schwellen aller skalierten Effekte, nicht nur der Schwellen von Worg, Griffon und Medusa.

Ein falscher Slot, eine fehlende Voraussetzung oder ein falscher Parameter erzeugt einen stabilen Strict-Befund. Ein Optionsüberhang oder ein bewusst nicht ausgeschöpftes Optionsbudget wird nicht automatisch repariert; der Befund und die source-defined Ursache bleiben sichtbar.

### Skills und Other Calculations

Die Tests beweisen, dass:

- Good- und Master-Boni direkt verwendet werden und der Ability-Modifikator nicht ein zweites Mal addiert wird;
- Perception automatisch den Good-Bonus erhält und nur durch eine explizite Master-Auswahl erhöht wird;
- Graft-, Spell-List-, Subtype-, Template- und Option-Grants genau nach ihrem Katalogtext gezählt bzw. als zusätzliche Grants behandelt werden;
- CMB dem hohen Angriffswert folgt, Concentration CR plus passendem Ability-Modifikator verwendet, CR unter 1 für HD wie 1 behandelt wird und Initiative/Perception/Speed den Other-Calculations-Regeln folgen.

### Damage

Die vollständige Matrix von Table 5–9 wird über `execute` an allen veröffentlichten Damage-Intervallen `4–101` und für alle Spaltendice `1d4`, `1d6`, `1d8`, `1d10`, `1d12`, `2d6`, `3d6` geprüft. Zusätzlich werden Weapon- und Natural-Attack-Profile getrennt geprüft:

- Weapons verwenden das gewählte Die und die High-/Low-Weapon-Damage der Array-Zeile;
- Natural Attacks verwenden Table 3–1 nach Größe, Damage Type und Primary-/Secondary-Klassifikation;
- mehrere Angriffe bewahren ihre source-defined Average-Damage-Werte, sofern kein katalogisierter Effekt sie verändert;
- Extra Attack und die Regeln zum Aufteilen zusätzlicher Natural Attacks werden nur über ausdrücklich katalogisierte Optionen bzw. typisierte Selections angewendet.

Der veröffentlichte Step-9-Tisch beginnt bei Damage `4–5`, während einzelne CR-`1/2`-Low-Damage-Profile den Wert `3` enthalten. Dieser Randfall ist ein absichtlicher Source-Gap-Test: Die Engine darf keinen Dice-Ausdruck extrapolieren, sondern muss den Wert als ungelöst bzw. nicht strict-validierbar melden, bis eine source-provenanceierte Entscheidung im Katalog vorliegt.

### Strict-Grenze für Reality Check und Free Mode

Der vollständige Reality-Check-/Free-Workflow ist nicht Teil dieses Tickets und bleibt MVP-Backlog. Es gibt deshalb noch keine Akzeptanztests für `RealityCheckItem`-Lebenszyklus, `accepted-free`, Overrides, Acknowledge/Dismiss oder Free-Exports.

Das Strict-Testset beweist nur:

- Eine Evaluation berechnet ausschließlich source-validierte Selections.
- Die Medusa-Schadenssenkung nach dem gedruckten Reality Check wird nicht automatisch angewendet.
- Freie zusätzliche Options, Angriffe oder Wertänderungen werden nicht als kanonische Selections akzeptiert.
- Ein vorhandener Abweichungsbefund wird nicht verschwiegen; solange der Reality-Check-Workflow fehlt, ist er höchstens ein sichtbarer Evaluation-Befund und keine mutierende Korrektur.

### Finished Monster und Export

Die Schnittstellentests prüfen die folgende Kette:

1. Ein gültiger Strict-Draft wird evaluiert und kann finalisiert werden.
2. Ein unvollständiger oder ungültiger Draft kann gespeichert und inspiziert, aber nicht als `FinishedMonster` finalisiert oder als fertiger Monster Sheet exportiert werden.
3. Der unveränderliche FinishedMonster-Snapshot enthält genau die akzeptierten Selections, die finale Evaluation, Katalogversion, SourceRefs und DerivationTrace.
4. Die Quell-Draft-ID, Revision und der Fingerprint stimmen mit der Evaluation überein; der Export enthält keine fremden Draft- oder Proposal-Änderungen.
5. JSON, HTML/Print und Markdown projizieren dieselben Werte, dieselbe Reihenfolge und dieselben Option-/Spell-Informationen. Kein Renderer berechnet eigene Werte.
6. Der Medusa-Export zeigt die Strict-Werte vor dem Reality Check und nicht die später manuell abgesenkten Schadenswerte.

### Abnahmekriterium

Issue 08 gilt als umgesetzt, wenn alle oben genannten Prüfungen als offline ausführbare Schnittstellentests vorliegen, jede Regression eine unabhängige Source-Erwartung besitzt und die Tests ohne Netzwerk oder KI-Modell laufen. Ein fehlendes oder ungelöstes Source-Datum führt zu einem sichtbaren, stabilen Befund — niemals zu einem geratenen Wert.

### Quellenabgleich

- Before You Begin, Other Calculations und Reality Check: `Pathfinder Unchained.pdf`, gedruckte S. 194–195 (PDF viewer S. 1–2); `Pathfinder Unchained.txt`, Zeilen 1–187.
- Step 1 Arrays: `Pathfinder Unchained.pdf`, gedruckte S. 196–203 (PDF viewer S. 3–10); `Pathfinder Unchained.txt`, Zeilen 188–801.
- Creature-/Class-Grafts: gedruckte S. 204–213 (PDF viewer S. 11–20); `Pathfinder Unchained.txt`, Zeilen 802–1750.
- Subtype-Grafts: gedruckte S. 214–215 (PDF viewer S. 21–22); `Pathfinder Unchained.txt`, Zeilen 1751–1938.
- Template-/Size-Grafts: gedruckte S. 216–217 (PDF viewer S. 23–24); `Pathfinder Unchained.txt`, Zeilen 1939–2135.
- Step 6 Spells: gedruckte S. 218–227 (PDF viewer S. 25–34); `Pathfinder Unchained.txt`, Zeilen 2136–3131.
- Step 7 Monster Options: gedruckte S. 228–239 (PDF viewer S. 35–46); `Pathfinder Unchained.txt`, Zeilen 3132–4333.
- Step 8 Skills und Step 9 Damage: gedruckte S. 240–241 (PDF viewer S. 47–48); `Pathfinder Unchained.txt`, Zeilen 4334–4497.
- Medusa und Buchbeispiele: `Pathfinder Unchained.txt`, Zeilen 4481–4644 (Medusa), 4645–4742 (Worg/Mastodon/Griffon), 4743 ff. (weitere Beispiele).
- Bestiary Table 1–1: gedruckte S. 291; `beastiary.txt`, Zeilen 1–68. Bestiary Table 3–1: gedruckte S. 302; `beastiary.txt`, Zeilen 68–165 (Tabelle ab Zeile 148).
