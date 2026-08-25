# Welche Regel-Daten müssen als kanonischer Katalog vorliegen?

Type: grilling
Status: resolved
Blocked by: none

## Question

Welche vollständigen, strukturierten Daten benötigt die deterministische Regel-Engine, damit sie die Simple Monster Creation Steps 1–9 exakt aus `Pathfinder Unchained.pdf` und `Pathfinder Unchained.txt` ausführen kann? Entscheide insbesondere über Arrays nach CR, Creature/Class/Subtype/Template/Size-Grafts, Spell Lists, Monster Options, Skills, Damage Table, zulässige Anpassungen und die Speicherung von PDF-Seiten- sowie TXT-Zeilen-Provenienz.

## Answer

Die Engine verwendet einen versionierten, eingecheckten JSON-Regelkatalog. PDF und TXT bleiben die maßgeblichen Quellen; das PDF wird nicht zur Laufzeit geparst. Der Katalog wird aus beiden Quellen extrahiert und geprüft.

### Kanonische Katalogbereiche

Der Katalog enthält mindestens:

- **Arrays:** Combatant, Expert und Spellcaster mit CR-Schlüsseln für Main Statistics und Attack Statistics.
- **Grafts:** Creature Type, Class, Subtype, Template und Size mit Voraussetzungen, automatischen Eigenschaften, numerischen Adjustments, Ersetzungen, freien Grants, optionalen Grants, CR-Stufen und Suggestions.
- **Spell Lists:** Primary/Secondary-Spells nach CR-Band und der jeweilige List-Benefit.
- **Spell-Metadaten:** Spell-ID, Name, Level nach Klasse und Quellenbuch; die noch fehlenden APG-/UM-/UC-Einträge sind ein separates Recherche-Ticket.
- **Monster Options:** Kategorie, Unterkategorie, Parameter, Voraussetzungen, CR-Skalierung und ein typisierter Effect-Handler.
- **Skills:** Skill-ID, Default-Verhalten, Good/Master-Semantik und Grants.
- **Damage:** Table 5–9, Natural-Attack-Dice by Size und Attack-Profiles.
- **Derived Rules:** CMB, Concentration, Hit Dice, Initiative, Perception und Speed.
- **Fixtures:** die Beispielmonster aus dem Kapitel für spätere Regressionstests.

Komplexe Effekte werden nicht als frei ausführbare Formeln im JSON gespeichert. Das JSON beschreibt Daten, Parameter und Constraints; deterministische, typisierte Effect-Handler implementieren die Rechenlogik. KI- und Benutzer-JSON dürfen nur katalogisierte IDs und gültige Parameter verwenden.

### Provenienz

Jeder für Berechnung, Validierung oder KI-Vorschläge relevante Eintrag erhält eine `SourceRef` mit:

- Quelldatei und stabiler `sourceId`.
- gedruckter PDF-Seite und PDF-Viewer-Seite.
- 1-indexiertem TXT-Zeilenbereich.
- Abschnitt, Tabellenname und Entry-Name, sofern vorhanden.
- SHA-256-Hash des verwendeten Quelldokuments bzw. Extrakts.

Abgeleitete Werte müssen ihre beitragenden Regel-Einträge referenzieren können. Suggestions werden separat von verbindlichen Rules markiert (`required`, `automatic`, `optional`, `replacement`, `suggestion`).

### Ergänzende lokale Quellen

`beastiary.pdf` enthält die benötigten Bestiary-Tabellen:

- Table 1–1: Monster Statistics by CR, gedruckte S. 291.
- Table 3–1: Natural Attacks by Size, gedruckte S. 302.

`Pathfinder_RPG_Core_Rulebook.pdf` enthält die Core-Class-Spell-Lists und die zugehörigen Kurzbeschreibungen. Die Unchained-Spell-Lists verwenden zusätzlich markierte APG-, UM- und UC-Spells; deren Level-Metadaten fehlen noch und werden über das Ticket [Welche nicht im Core Rulebook enthaltenen Spell-Metadaten braucht der Katalog?](09-non-core-spell-metadata.md) ermittelt.

### Strict-Mode-Grenze

Die erste Engine-Version unterstützt keine frei eingegebenen Reality-Check- oder Golden-Rule-Wertänderungen. Benutzer und KI wählen gültige Arrays, Grafts, Options, Spells und Parameter; daraus werden alle abgeleiteten Werte neu berechnet. Eine manuelle Änderung eines berechneten Werts ist kein gültiger Monster Draft.
