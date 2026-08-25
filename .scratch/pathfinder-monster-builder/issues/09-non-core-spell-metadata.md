# Welche nicht im Core Rulebook enthaltenen Spell-Metadaten braucht der Katalog?

Type: research
Status: resolved
Blocked by: none

## Question

Welche der in `Pathfinder Unchained.pdf` verwendeten APG-, UM- und UC-Spells fehlen in `Pathfinder_RPG_Core_Rulebook.pdf`, und welche minimale Spell-Metadatenstruktur (insbesondere Level nach Klasse und Quellenbuch) muss dafür aus offiziellen Quellen ergänzt werden, damit Step 6 die Spell DCs und die KI-Vorschläge korrekt validieren kann?

## Answer

### Ergebnis

Der Abgleich wurde auf den gesamten Step-6-Abschnitt angewendet, nicht auf bloße Teilstrings: `Pathfinder Unchained.txt`, Zeilen 2136–3131 (gedruckte Seiten 218–227), gegen die Core-Klassenlisten und Spell-Einträge in `Pathfinder_RPG_Core_Rulebook.txt`, Zeilen 1–1749. Ergebnis:

- **20 APG**, **15 UM** und **4 UC** eindeutige Spell-IDs, insgesamt **39**.
- Methodischer Gegencheck: Die Legacy-Step-6-HTML verlinkt 19 APG-, 12 UM- und 4 UC-Spells (**35**); vier nicht verlinkte, aber im Originalbuch/PRD belegte Entries ergänzen die Menge: `Grace` (APG) sowie `Frostbite`, `Serenity` und `Ear-Piercing Scream` (UM). Damit ist die vollständige Quellenmenge **35 + 4 = 39**.
- Die einzige plausible 38er-Zählung ist eine reine Suffixzählung: `suppressionAPG` steht in der Protection-Tabelle als `wall of suppressionAPG`, nicht als eigenständiger Spell `Suppression`.
- Zusätzlich steht `Lead blades` (APG, Ranger 1) in der Metal Spell List ohne `APG`-Suffix (`Pathfinder Unchained.txt`, Zeile 2852). Die Quellenbuch-/PRD-Prüfung muss daher neben den markierten Tags auch unmarkierte, aber eindeutig nicht im Core enthaltene Namen erfassen.
- Alle 39 fehlen im gelieferten Core-Auszug als eigenständige Spell-Einträge. Der Treffer `Grace` im Core-Abgleich ist nur `Cat’s Grace`/`Cat’s Grace, Mass` und kein eigenständiger Spell.
- Metamagic-Schreibweisen wie `Empowered corrosive touch` oder `Maximized acidic spray` sind **keine neuen Spell-IDs**. Sie referenzieren den Basisspell plus eine Metamagic-Variante.

`Pathfinder Unchained` verwendet außerdem fünf `ACG`-markierte Spells (`Long Arm`, `Stricken Heart`, `Disguise Weapon`, `Molten Orb`, `Heart of the Metal`). Sie waren nicht Teil der Frage, sind aber ebenfalls nicht Core und dürfen in einem vollständig geschlossenen Katalog nicht stillschweigend fehlen. Das generische `sourceBook`-Feld deckt sie ab; die ACG-Level-Ergänzung bleibt ein kleines Folgeinventar.

### Nicht-Core-Inventar und Level-Metadaten

Die Level stammen aus den offiziellen Paizo-PRD-Spell-Entries der jeweiligen Bücher. `S/W` bedeutet die im Original zusammengefassten Einträge `sorcerer/wizard`; beim Import werden sie in `sorcerer` und `wizard` aufgeteilt. `highest` ist der höchste Wert der Klassenkarte und wird im Katalog aus `levelsByClass` abgeleitet.

#### Advanced Player’s Guide (APG)

Quelle/Verzeichnis: [Advanced Spell Lists](https://legacy.aonprd.com/advancedPlayersGuide/advancedSpellLists.html); die gedruckten Seiten der Entries stehen zusätzlich in der Tabelle.

| Spell | APG printed page | Original levels by class | highest |
|---|---:|---|---:|
| Winds of Vengeance | 256 | cleric 9, druid 9, S/W 9 | 9 |
| Ant Haul | 201 | alchemist 1, cleric 1, druid 1, ranger 1, summoner 1, S/W 1 | 1 |
| Vomit Swarm | 254 | alchemist 2, witch 2 | 2 |
| Dragon’s Breath | 217 | alchemist 4, S/W 4 | 4 |
| Twin Form | 252 | alchemist 6 | 6 |
| Fiery Body | 221 | S/W 9 | 9 |
| Blessing of Fervor | 205 | cleric 4 | 4 |
| Draconic Reservoir | 217 | alchemist 3, S/W 3 | 3 |
| Expeditious Excavation | 220 | druid 1, S/W 1 | 1 |
| Elemental Touch | 218 | alchemist 2, S/W 2 | 2 |
| Elemental Aura | 218 | alchemist 3, S/W 3 | 3 |
| Ball Lightning | 204 | druid 4, S/W 4 | 4 |
| Wall of Suppression | 255 | S/W 9 | 9 |
| Weapon of Awe | 256 | cleric 2, inquisitor 2, paladin 2 | 2 |
| Grace | 226 | cleric 2, paladin 1 | 2 |
| Spiritual Ally | 246 | cleric 4 | 4 |
| Hydraulic Push | 228 | druid 1, S/W 1 | 1 |
| Touch of the Sea | 250 | alchemist 1, druid 1, S/W 1 | 1 |
| Fluid Form | 223 | alchemist 4, S/W 6 | 6 |
| [Lead Blades](https://paizo.com/pathfinderRPG/prd/advancedPlayersGuide/spells/leadBlades.html) | 230 | ranger 1 | 1 |

#### Ultimate Magic (UM)

Quelle/Verzeichnis: [Ultimate Magic Spell Lists](https://legacy.aonprd.com/ultimateMagic/ultimateMagicSpellLists.html).

| Spell | UM printed page | Original levels by class | highest |
|---|---:|---|---:|
| Corrosive Touch | 213 | magus 1, summoner 1, S/W 1 | 1 |
| Acidic Spray | 204 | magus 5, S/W 5 | 5 |
| Corrosive Consumption | 212 | magus 5, S/W 5 | 5 |
| Caustic Eruption | 210 | S/W 7 | 7 |
| Frostbite | 221 | druid 1, magus 1, witch 1 | 1 |
| Anticipate Peril | 206 | alchemist 1, bard 1, ranger 1, S/W 1 | 1 |
| Unprepared Combatant | 246 | bard 1, witch 1, S/W 1 | 1 |
| Prediction of Failure | 232 | witch 8, S/W 8 | 8 |
| Overwhelming Presence | 230 | bard 6, cleric 9, inquisitor 6, S/W 9 | 9 |
| Serenity | 236 | bard 4, cleric 5, S/W 6 | 6 |
| Symbol of Mirroring | 241 | witch 2, S/W 2 | 2 |
| Symbol of Slowing | 242 | cleric 4, witch 4, S/W 4 | 4 |
| Symbol of Strife | 242 | cleric 9, witch 9, S/W 9 | 9 |
| Symbol of Vulnerability | 243 | cleric 9, witch 9, S/W 9 | 9 |
| Ear-Piercing Scream | 218 | bard 1, inquisitor 1, witch 1, S/W 1 | 1 |

#### Ultimate Combat (UC)

Quelle/Verzeichnis: [Ultimate Combat Spell Lists](https://legacy.aonprd.com/ultimateCombat/ultimateCombatSpellLists.html).

| Spell | UC printed page | Original levels by class | highest |
|---|---:|---|---:|
| Debilitating Portent | 227 | cleric 4, witch 4 | 4 |
| Jolting Portent | 232 | cleric 7 | 7 |
| Pellet Blast | 238 | magus 4, summoner 3, S/W 3 | 4 |
| Wreath of Blades | 249 | magus 4, summoner 5, witch 5, S/W 5 | 5 |

The source lists above are the canonical class-level data for the named books. Current database pages may show later-added classes (for example, psychic, occultist, warpriest, or unchained summoner); those later additions must not overwrite the original sourcebook record used by this MVP.

### Minimaler Katalogvertrag

Für Step 6 und den KI-Adapter reicht pro Basisspell mindestens:

```json
{
  "id": "spell.apg.ant-haul",
  "name": "Ant Haul",
  "sourceBook": "APG",
  "sourceRef": {
    "sourceId": "advanced-players-guide",
    "printedPage": 201,
    "officialUrl": "https://paizo.com/pathfinderRPG/prd/advancedPlayersGuide/spells/antHaul.html"
  },
  "levelsByClass": {
    "alchemist": 1,
    "cleric": 1,
    "druid": 1,
    "ranger": 1,
    "summoner": 1,
    "sorcerer": 1,
    "wizard": 1
  },
  "listMemberships": ["alchemy"],
  "aliases": []
}
```

Verbindliche Regeln für die Struktur:

1. `id` ist quellenqualifiziert und stabil; der Anzeigename ist nicht der Schlüssel. `aliases` nimmt Apostroph-/OCR-Varianten auf.
2. `sourceBook` ist mindestens `APG`, `UM`, `UC` (später auch `ACG`), `sourceRef` enthält Buch, gedruckte Seite und offizielle Primärquelle. Beim Vendoring in den JSON-Katalog kommen lokale Datei/TXT-Zeilen und Hash aus Issue 01 hinzu; die URL wird nicht zur Laufzeit gescraped.
3. `levelsByClass` enthält **alle im jeweiligen Originalbuch gedruckten Klassenlevel**, nicht nur den für den DC verwendeten Wert. `highest` wird daraus berechnet und nicht vom Client vertraut. `cleric`, `sorcerer` und `wizard` müssen separat abfragbar sein.
4. Die Zugehörigkeit zur thematischen Unchained-Liste (`listMemberships`) bleibt getrennt von der Klassenliste. Ein Spell kann auf einer thematischen Step-6-Liste stehen, auch wenn die Monsterklasse ihn nicht als normalen Klassenspell führt; die Klassenlevel bestimmen dann DC/Fallback und KI-Ranking.
5. Eine Step-6-Auswahl speichert Basisspell und Variante getrennt:

   ```json
   {
     "spellId": "spell.um.acidic-spray",
     "metamagic": ["maximize"]
   }
   ```

   Die Metamagic-Erhöhung wird aus dem katalogisierten Core-Metamagic-Regel-Eintrag berechnet (`Empower +2`, `Extend +1`, `Maximize +3`, `Quicken +4`, `Widen +3`); `effectiveLevel = preferredClassLevel + metamagicIncrease`. Dadurch werden die in höheren CR-Bändern verwendeten Varianten (`Empowered`, `Maximized`, `Quickened`, `Widened`) weder als fremde Spell-ID akzeptiert noch fälschlich mit dem Basisspell-Level bewertet.

### DC-Auflösung

`Pathfinder Unchained` schreibt für Step 6 vor: Zur Array-Spell-DC wird das Spell-Level addiert; bei mehreren Klassen wird das cleric- oder sorcerer/wizard-Level verwendet, andernfalls das höchste im Spell-Eintrag (`Pathfinder Unchained.txt`, Zeilen 2161–2166; gedruckte S. 218, PDF viewer S. 25). Die Engine verwendet deshalb:

```text
preferredClass = explicit cleric/sorcerer/wizard context
              ?? cleric if present
              ?? sorcerer if present
              ?? wizard if present
              ?? highest(levelsByClass)
spellDC = arraySpellDC + levelsByClass[preferredClass] + metamagicIncrease
```

Die Quelle nennt nur cleric oder sorcerer/wizard als bevorzugte Klassen. Wenn deren Level verschieden sind (z. B. `Serenity`: cleric 5, sorcerer/wizard 6), muss der Draft die bevorzugte Quelle sichtbar festlegen (`spellLevelSource`); ohne Kontext greift eine deklarierte, reproduzierbare Katalog-Policy (cleric vor sorcerer vor wizard), nicht ein stillschweigendes Raten. Der KI-Adapter darf nur `spellId`, `metamagic`, thematische Listen-ID und diese begründete `spellLevelSource` vorschlagen; die Engine berechnet `effectiveLevel` und `spellDC` erneut.

### Quellenabgleich

- Step 6 und die Markierungen: `Pathfinder Unchained.txt`, Zeilen 2136–3131; gedruckte Seiten 218–227 (PDF viewer 25–34).
- Core-Abgleich: `Pathfinder_RPG_Core_Rulebook.txt`, Zeilen 1–1749; die gelieferten Core-Listen/Entries enthalten keine der 39 eigenständigen Nicht-Core-Überschriften.
- APG-Levelkarten: offizielles [Advanced Spell Lists](https://legacy.aonprd.com/advancedPlayersGuide/advancedSpellLists.html) und die verlinkten Einzelentries.
- UM-Levelkarten: offizielles [Ultimate Magic Spell Lists](https://legacy.aonprd.com/ultimateMagic/ultimateMagicSpellLists.html) und die verlinkten Einzelentries.
- UC-Levelkarten: offizielles [Ultimate Combat Spell Lists](https://legacy.aonprd.com/ultimateCombat/ultimateCombatSpellLists.html) und die verlinkten Einzelentries.
- ACG-Folgeinventar: offizielles [Advanced Class Guide Spell Lists](https://legacy.aonprd.com/advancedClassGuide/spells/spellLists.html).
- Metamagic-Erhöhungen: die jeweiligen offiziellen Core-Rulebook-Feats `Empower Spell`, `Extend Spell`, `Maximize Spell`, `Quicken Spell` und `Widen Spell`; sie werden als eigene katalogisierte Regel-Einträge benötigt, weil der gelieferte Core-Auszug nur Klassenlisten/Spell-Entries enthält.

Damit ist die Recherchefrage für APG/UM/UC entschieden: 39 ergänzende Basisspells mit quellengebundenen Klassenleveln, Quellenbuch und Variantenmodell; kein vollständiger Spelltext und kein Runtime-Webzugriff sind für Step 6 erforderlich.
