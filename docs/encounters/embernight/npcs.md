# The Green Rest — NPC-Statblocks

**PF1, mit den Regeln zur NSC-Erstellung (CRB 448–454).** Dayl und Yalana
sind HG 2, also jeweils Charakterstufe 3 mit einer SC-Klasse (CR = Stufe − 1).
Lili ist ebenfalls Druidenstufe 3, damit sie *Summon Nature's Ally II* wirken
kann; ihr HG ist damit 2.

Nicht vorgegebene Werte sind als **Arbeitsannahmen** markiert. Die Zahlen in
den Blöcken werden deterministisch über die lokale `monster_builder`-Engine
(`creationSystem: "npc"`) geprüft, nicht per Hand gerechnet. Stand der
Validierung:

- **Dayl: engine-validiert** (Halbling-Barde 3, HG 2) über
  `tests/fixtures/embernight-dayl-bard-3.json`; Ergebnis `status: "valid"`.
- **Yalana: engine-validiert** (Halbling-Klerikerin 3, HG 2) über
  `tests/fixtures/embernight-yalana-cleric-3.json`; Ergebnis `status: "valid"`.
- **Lili: engine-validiert** (Gnomen-Druidin 3, HG 2) über
  `tests/fixtures/embernight-lili-druid-3.json`; Ergebnis `status: "valid"`.

Die Engine ist die Quelle der Wahrheit: `tests/test_embernight.py` baut alle
drei NSC über die Engine und vergleicht die Statblöcke unten mit dem
kanonischen Ergebnis. Katalogstand: `sha256:d88b63f4…`.

## Dayl — Halbling-Barde 3 (HG 2)

**N Small humanoid (halfling)** · Bruder von Yalana · Unterstützer

> **Arbeitsannahmen:** Halbling, neutral, Bardenstufe 3. Er trägt ein
> Kettenhemd (leichte Rüstung); Waffen und übrige Ausrüstung liegen
> griffbereit.

**Init** +7; **Senses** Perception +8

**Defense** AC 18, touch 14, flat-footed 15 (chain shirt); hp 21 (3d8+3);
**Fort** +3, **Ref** +7, **Will** +4

**Speed** 20 ft.

**Melee** rapier +6 (1d4−2/18–20); **Ranged** sling +6 (1d3−2), 50 ft.

**Statistics** Str 6, Dex 16, Con 12, Int 13, Wis 10, Cha 17

**Base Atk** +2; **CMB** −1; **CMD** 12

**Feats** Improved Initiative, Weapon Finesse

**Skills** Diplomacy +9, Knowledge (nobility) +8, Perception +8,
Perform (sing) +9, Sense Motive +6, Stealth +11, Use Magic Device +9

**Languages** Common, Halfling

**Racial Traits** Small (+1 AC/attack, −1 CMB/CMD, +4 Stealth); slow speed
20 ft.; halfling luck (+1 on all saving throws); fearless (+2 vs. fear);
keen senses (+2 Perception); sure-footed (+2 Acrobatics and Climb); weapon
familiarity (slings and "halfling" weapons as martial weapons).

**Class Features** Bardic knowledge +1; bardic performance 11 rounds/day
(countersong, distraction, fascinate [DC 14], inspire courage +1, inspire
competence +2); versatile performance (Perform [sing] replaces Bluff and
Sense Motive); well-versed (+4 vs. bardic performance, sonic, and
language-dependent effects).

**Spells** Bard spells known, Cha-based (concentration +6; DC 13 cantrips,
DC 14 for 1st level); 0 (at will): *detect magic*, *light*, *mage hand*,
*message*, *prestidigitation*, *read magic*; 1st (4/day): *cure light
wounds*, *grease*, *charm person*, *sleep*.

**Gear** Typical bard gear (Small): rapier, sling, chain shirt (worn),
instrument, and spell component pouch; no magic items. Weapons are at hand.

## Yalana — Halbling-Klerikerin des Oghma 3 (HG 2)

**N Small humanoid (halfling)** · Wirtin und Schwester von Dayl ·
kennt das Haus und koordiniert die Evakuierung

> **Arbeitsannahmen / SL-Festlegungen:** Halbling; neutral (Oghma wird hier als
> neutraler Gott behandelt); positive Energie und spontane *cure*-Zauber;
> Domänen Wissen und Reisen. Oghma ist eine Gottheit aus einem anderen Setting;
> diese Domänenwahl muss zur Kampagnenfassung passen. Ihr hohes Int 14 spiegelt
> das Gelehrtenprofil des Wissensgottes wider. Yalana ist im Brand ungerüstet;
> normale Ausrüstung liegt im Haus.

**Init** +0; **Senses** Perception +4

**Defense** AC 11, touch 11, flat-footed 11 (unarmored); hp 24 (3d8+6);
**Fort** +5, **Ref** +2, **Will** +6

**Speed** 30 ft. (Travel domain)

**Melee** light mace +2 (1d4−1)

**Statistics** Str 8, Dex 10, Con 13, Int 14, Wis 15, Cha 14

**Base Atk** +2; **CMB** +0; **CMD** 10

**Feats** Combat Casting, Toughness

**Skills** Diplomacy +8, Knowledge (arcana) +8, Knowledge (history) +8,
Knowledge (religion) +8, Sense Motive +2 (untrained)

**Languages** Common, Halfling

**Racial Traits** Small (+1 AC/attack, −1 CMB/CMD, +4 Stealth); slow speed
20 ft.; halfling luck (+1 on all saving throws); fearless (+2 vs. fear);
keen senses (+2 Perception); sure-footed (+2 Acrobatics and Climb); weapon
familiarity (slings and "halfling" weapons as martial weapons).

**Class Features** Channel positive energy 2d6, 5/day (Will DC 13);
spontaneous casting (convert prepared spells into *cure* spells). Knowledge
domain: all Knowledge skills are class skills; lore keeper (touch; Knowledge
check result 20). Travel domain: base speed +10 ft.; agile feet 5/day
(ignore difficult terrain for 1 round).

**Spells** Cleric spells prepared, Wis-based (DC 13/14 for 1st/2nd level);
0 (4): *detect magic*, *guidance*, *light*, *stabilize*; 1st (4): *bless*,
*cure light wounds*, *shield of faith*; domain 1st: *comprehend languages*;
2nd (3): *aid*, *lesser restoration*; domain 2nd: *locate object*.

**Gear** Typical cleric gear (Small): light mace, wooden shield, medium
armor, holy symbol, and bandages; no magic items. Not worn at the start of
the scene (light mace at hand).

## Lili — Gnomen-Druidin 3 (HG 2)

**N Small humanoid (gnome)** · kommt ab Runde 4 aus dem Obergeschoss ·
Feuerwehrhilfe durch einen kleinen Wasserelementar

> **Arbeitsannahmen:** neutrale Gesinnung (Druidenregel), Wasserdomäne als
> Naturverbindung. Sie kommt aus dem Schlaf und ist zunächst ungerüstet;
> Lederrüstung und Holzschild sind im Zimmer. Der Volksbonus „besessen“
> (+2 auf ein Handwerk) ist nicht im Engine-Modell enthalten und daher in der
> Fertigkeitszeile nicht eingerechnet.

**Init** −1; **Senses** low-light vision; Perception +10

**Defense** AC 10, touch 10, flat-footed 10 (unarmored); hp 27 (3d8+9);
**Fort** +6, **Ref** +0, **Will** +5

**Speed** 20 ft.

**Melee** quarterstaff +3 (1d4)

**Statistics** Str 10, Dex 8, Con 16, Int 10, Wis 15, Cha 15

**Base Atk** +2; **CMB** +1; **CMD** 10

**Feats** Combat Casting, Spell Focus (conjuration)

**Skills** Heal +8, Survival +10, Perception +10, Knowledge (nature) +8,
Craft (alchemy) +0 (untrained; siehe „besessen“ oben)

**Languages** Common, Gnome, Sylvan, Druidic

**Racial Traits** Small (+1 AC/attack, −1 CMB/CMD, +4 Stealth); slow speed
20 ft.; low-light vision; defensive training (+4 dodge AC vs. giants);
hatred (+1 attack vs. reptilians and goblinoids); illusion resistance (+2
vs. illusions); keen senses (+2 Perception); obsessive (+2 Craft [alchemy];
not engine-modelled); gnome magic (+1 DC for illusion spells). Spell-like
abilities (1/day each, CL 3): *dancing lights*, *ghost sound*,
*prestidigitation*, *speak with animals* (burrowing mammals only).

**Class Features** Nature sense (+2 Knowledge [nature] and Survival); wild
empathy +5; woodland stride; trackless step; nature bond (water domain).
Icicle: ranged touch +2, 1d6+1 cold damage, 5/day. No wild shape before
druid level 4.

**Spells** Druid spells prepared, Wis-based (DC 13/14 for 1st/2nd level);
0 (4): *create water*, *detect magic*, *guidance*, *light*; 1st (4): *cure
light wounds*, *entangle*, *longstrider*; water domain 1st: *obscuring
mist*; 2nd (3): *barkskin*, *resist energy*; water domain 2nd: *fog cloud*.
She can convert a prepared non-domain spell into a *summon nature's ally*
spell of the same or lower level. For the small water elemental she uses
*summon nature's ally II* (casting time 1 round).

**Gear** Typical druid gear: quarterstaff, sling, leather armor, wooden
shield, spell components; no metal armor and no magic items. Not worn at the
start of the scene (quarterstaff at hand).

## Quellen und Rechenhinweise

- **Offizielle Regeln:** *Creating NPCs*, CRB 448–454: sieben Schritte,
  heroische Arrays und Klassen-/Volksanpassungen; vereinfachte Fertigkeiten;
  NSC-Talente und Ausrüstung; durchschnittliche TP. `sources/npc/aonprd/creating-npcs.txt`.
- **CR:** PC-Klassen-NSC erhalten HG = Klassenstufen − 1.
  `sources/npc/aonprd/designing-encounters.txt`.
- **Klassen:** Bard 3 `sources/npc/aonprd/bard.txt`; Cleric 3
  `sources/npc/aonprd/cleric.txt`; Druid 3 `sources/npc/aonprd/druid.txt`.
- **Rassen:** Halbling `sources/npc/aonprd/halfling.txt`; Gnom und Human
  `sources/npc/aonprd/core-races.txt`.
- **Gear:** heroische Stufe 3 hat nach Tabelle 14-9 ein Richtbudget von
  1.650 GM; die obenstehenden einfachen, nichtmagischen Ausrüstungslisten
  werden im Szenenstart nicht getragen (Ausnahme: Dayls Kettenhemd ist
  angelegt). Werte lassen sich bei Bedarf nach tatsächlichem Inhalt des Zimmers
  ergänzen.
- **Nicht durch die Regeln festgelegt:** Gesinnung Dayls/Yalanas,
  Yalanas genaue Oghma-Domänen und Ausrüstungszustand, Lilis Gesinnung,
  Domänenwahl und konkrete vorbereitete Zauber. Obige Entscheidungen sind
  verwendbare Defaults, keine Aussagen über bereits etablierte Lore.
