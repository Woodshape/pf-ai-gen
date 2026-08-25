# Welche lokale KI-Integration wird zuerst unterstützt?

Type: grilling
Status: resolved
Blocked by: none

## Question

Welche erste lokale KI- oder pi-SDK-Integration soll natürliche Monster Concepts wie „Goblin Level 4 Druid, Level 1 Rogue“ in einen gültigen Monster-Draft-Vorschlag übersetzen? Entscheide über den ersten Adapter, Aufrufart (CLI, JSON, Prozess oder SDK), Modellkonfiguration, Offline-Verhalten, Fehlerfälle und die Stelle, an der der Benutzer den Vorschlag bestätigt.

## Answer

## Entscheidung

Der erste MVP-Adapter ist ein **in-process Pi-SDK-Adapter**. Er übersetzt einen natürlichen Monster Concept in ein unveränderliches `Proposal`; er mutiert niemals den Draft und ruft niemals `proposal.accept` auf. Der deterministische Rules Engine bleibt die einzige Instanz, die typed Changes fachlich akzeptiert.

Der Browser ruft den Adapter über die gemeinsame Application-Schnittstelle auf. Der Adapter verwendet eine kurzlebige `AgentSession` mit `SessionManager.inMemory()`. Pi-Sessions werden nicht als Produktdaten persistiert; persistiert werden nur Drafts und Proposals nach den Entscheidungen aus [Wie werden Entwürfe und fertige Monster lokal gespeichert?](05-local-persistence-lifecycle.md).

## Modellauflösung

Im MVP verwendet der Adapter die Default-Auflösung von Pi SDK und Provider. Wenn kein Default-Modell aufgelöst werden kann, versucht er `openai-codex/gpt-5.6-luna` als festen Fallback.

Der Fallback gilt nur bei fehlendem Default. Ein konfiguriertes Default-Modell, das nicht authentifiziert oder nicht erreichbar ist, wird nicht stillschweigend durch einen anderen Provider ersetzt. Das verhindert unerwartete Kosten und Datenweitergabe.

Eine direkte Ollama-Integration für ein lokales Modell ist vorgesehen, aber nicht Teil des ersten MVP-Adapters. Sie bleibt als Backlog-Adapter hinter derselben Schnittstelle. Der MVP funktioniert vollständig ohne KI; bei Offline-Betrieb oder fehlendem Modell liefert der Adapter einen technischen Fehler und der Benutzer kann den Draft manuell weiterbearbeiten.

## Agent- und Tool-Schnittstelle

Der Agent erhält keine Shell-, Datei- oder allgemeinen Schreibwerkzeuge. Er erhält ausschließlich fachlich begrenzte, read-only Katalogwerkzeuge und das abschließende Proposal-Werkzeug:

- `catalog_list`
- `catalog_search`
- `catalog_get`
- `emit_proposal`

`catalog_list` ist ein **hartes Gate** und muss der erste erfolgreiche Werkzeugaufruf sein. Der Adapter verfolgt diesen Zustand. `emit_proposal` wird technisch mit `CATALOG_REQUIRED` abgelehnt, solange `catalog_list` nicht erfolgreich abgeschlossen wurde. Dadurch hängt die Sicherheit nicht nur von einer Prompt-Anweisung ab.

`catalog_list` liefert den vollständigen maschinenlesbaren Katalog für den Entwurf: Arrays, Creature-/Class-/Subtype-/Template-/Size-Grafts, alle Monster Options, Spell-Lists und Spell-IDs sowie Skills, Attack-Profiles und Damage-Profiles. Jede Auswahl enthält IDs, Parameter, Voraussetzungen, Effekte, CR-Skalierung und SourceRefs. `catalog_search` und `catalog_get` dienen danach nur noch der gezielten Vertiefung.

Der fachliche Inhalt bleibt versioniertes JSON. JSONL ist – entsprechend dem gemeinsamen Interface-Vertrag – nur Transport-/Framingformat; falls ein großer Katalog gestreamt wird, werden JSONL-Zeilen als Transport verwendet, nicht als eigenes Domainformat.

Die Ausgabe erfolgt über ein typisiertes, terminierendes `emit_proposal`-Tool. Dessen Ergebnis wird vom Adapter als untrusted Ergebnis an `proposal.create` übergeben. `proposal.create` validiert erneut alle IDs, Parameter, Base-Revision und Katalogversion. Ein Proposal darf unvollständig sein, darf aber keine unbekannten IDs oder berechneten Zahlen als Selections einschleusen.

Die KI erhält keine Rückfragen-Schleife mit dem Benutzer. Sie macht in einem Lauf den bestmöglichen katalogisierten Vorschlag, dokumentiert `rationale`, `assumptions` und `nonCanonicalSuggestions` und lässt nicht ableitbare Felder leer. Bei einem Schema- oder Engine-Fehler ist höchstens ein begrenzter Reparaturversuch erlaubt; danach bleibt der Draft unverändert und der Adapter liefert einen technischen Fehler.

## Concept-Mapping und CR-Heuristik

Für „Goblin Level 4 Druid, Level 1 Rogue“ gilt folgende Interpretation:

```text
creatureTypeGraft: humanoid
subtype: goblinoid, sofern im Katalog vorhanden
classGraft: druid
array: spellcaster
rogue: katalogisierte Skills und Monster Options, kein zweites Class-Graft
```

`Humanoid` ist dabei ein Creature-Type-Graft, kein Template; `Druid` ist ein Class-Graft, kein Array. Bei einem Class-Graft bleiben die automatischen Traits des Creature-Type-Grafts erhalten, während dessen Statistik-Adjustments nicht zusätzlich angewendet werden.

Die Quelle bestätigt für einzelne Klassen die Orientierung `CR = Klassenlevel - 1` (`Pathfinder Unchained.txt`, Zeilen 227–240; gedruckte S. 196). Für die MVP-Abbildung mehrerer genannten Klassenlevel gilt zusätzlich die bewusst einfache Produktheuristik:

```text
inferredCR = Summe aller angegebenen Klassenlevel - 1
```

Druid 4 / Rogue 1 ergibt daher zunächst `inferredCR: 4`. Ein expliziter `targetCR` des Benutzers hat Vorrang. Fehlt `targetCR`, aber sind Klassenlevel vorhanden, wird die Heuristik als sichtbare `assumption` vorgeschlagen. Fehlen beide, bleibt CR leer und der Draft `incomplete`.

Diese Heuristik erzeugt keine normale Pathfinder-Multiclass-Simulation und keine separaten zusätzlichen Hit Dice: Die Simple-Monster-Creation-Engine verwendet weiterhin CR als HD für ihre Berechnungen (`Pathfinder Unchained.txt`, Zeilen 168–178). Die Rogue-Anteile werden nur über tatsächlich katalogisierte Skills und Options angenähert. Die Quelle beschreibt genau dieses Muster für Kreaturen mit wenigen Klassenleveln und nennt Sneak Attack als Option (`Pathfinder Unchained.txt`, Zeilen 64–77, 227–246). Nicht katalogisierbare Rogue-Wünsche bleiben Plain-Text-Vorschläge.

Der Druid-Class-Graft erzwingt das Spellcaster-Array und bringt seine eigenen Skills und Options mit (`Pathfinder Unchained.txt`, Zeilen 1184–1208). Der Agent wählt daraus und aus dem vollständigen Katalog eine passende, budgetierte Kombination; er erfindet kein Rogue- oder Multiclass-Paket.

## Offline-Verhalten und Fehler

Die KI ist optional. Der Adapter mutiert bei keinem Fehler den Draft. Mindestens folgende stabile technische Fehler werden unterschieden:

- `AI_NOT_CONFIGURED`: kein Default und kein erreichbarer Fallback
- `AI_UNAVAILABLE`: Provider oder Modell nicht verfügbar
- `AI_TIMEOUT` / `AI_ABORTED`: Laufzeitüberschreitung oder Abbruch
- `CATALOG_UNAVAILABLE`: `catalog_list` konnte nicht geladen werden
- `CATALOG_REQUIRED`: Proposal wurde vor dem Katalog-Gate ausgegeben
- `AI_OUTPUT_INVALID`: kein gültiger typisierter Tool-Output
- `PROPOSAL_INVALID`: `proposal.create` lehnt Changes oder Parameter ab
- `DRAFT_CONFLICT`: der Base-Draft ist nicht mehr anwendbar

Ein Proposal bleibt an `baseRevision` und `baseFingerprint` gebunden. Ändert sich der Draft während der Generierung, wird das Proposal höchstens als stale gespeichert; es wird weder rebased noch automatisch angewendet.

## Bestätigung

Die Benutzerbestätigung liegt ausschließlich im bestehenden Proposal-Panel des Guided-Rail-Wizards. Der Benutzer sieht Base-Revision/Fingerprint, Diff, Rationale, Annahmen und SourceRefs, wählt Changes einzeln aus und bestätigt die Übernahme ausdrücklich. Erst danach führt die gemeinsame Schnittstelle `proposal.accept` mit `confirmation.actor = user` aus und validiert die Changes atomar erneut.

CLI- oder JSON-Clients müssen dieselbe explizite Confirmation mitsenden. Der Pi-Adapter selbst hat keine Bestätigungsbefugnis und kann keinen Draft direkt ändern.

## Nicht Teil des MVP

- direkte Ollama-/lokale-Modellintegration
- automatische Modellinstallation oder Serververwaltung
- normale Pathfinder-Multiclass-Simulation
- automatische Übernahme von KI-Vorschlägen
- freie oder nicht katalogisierte Regelwerte
