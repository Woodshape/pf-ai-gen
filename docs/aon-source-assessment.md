# Archives of Nethys Source Assessment for NPC Mode

## Conclusion

Archives of Nethys is sufficient for the planned Core-only class-based NPC
system. A full Core Rulebook PDF is not currently needed. The human warrior
levels 1–5 and elemental-fire goblin Sorcerer levels 5–6 are fully
source-backed by local, hash-anchored AoN snapshots.

Builds must consume the local snapshots, not live HTTP responses. Raw pages and
their SHA-256 hashes are recorded in `sources/npc/MANIFEST.json`; normalized
text is regenerated with `python3 tools/extract_npc_aon_sources.py`.

## Archived primary sources

| Domain | Official source | Local extract |
|--------|-----------------|---------------|
| Creating NPCs, Steps 1–7, Tables 14-6 through 14-9, Kiramor | [AoN Creating NPCs](https://aonprd.com/Rules.aspx?ID=353) | `sources/npc/aonprd/creating-npcs.txt` |
| Core races | [AoN Core races](https://legacy.aonprd.com/coreRulebook/races.html) | `sources/npc/aonprd/core-races.txt` |
| Advancement, multiclassing, favored class | [AoN Core classes](https://legacy.aonprd.com/coreRulebook/classes.html) | `sources/npc/aonprd/character-classes.txt` |
| Five NPC classes | [AoN NPC classes](https://legacy.aonprd.com/coreRulebook/NPCClasses.html) | `sources/npc/aonprd/npc-classes.txt` |
| Skill calculation | [AoN Using Skills](https://legacy.aonprd.com/coreRulebook/usingSkills.html) | `sources/npc/aonprd/skills.txt` |
| Skill names, abilities, trained-only, ACP | [AoN Skill Descriptions](https://legacy.aonprd.com/coreRulebook/skillDescriptions.html) | `sources/npc/aonprd/skill-descriptions.txt` |
| Core feats | [AoN Feats](https://legacy.aonprd.com/coreRulebook/feats.html) | `sources/npc/aonprd/feats.txt` |
| Mundane equipment | [AoN Equipment](https://legacy.aonprd.com/coreRulebook/equipment.html) | `sources/npc/aonprd/equipment.txt` |
| Combat arithmetic | [AoN Combat](https://legacy.aonprd.com/coreRulebook/combat.html) | `sources/npc/aonprd/combat.txt` |

All snapshots were retrieved on 2026-09-02. The Creating NPCs page identifies
its content as *Pathfinder RPG Core Rulebook* pages 448–454; the legacy pages
are organized under AoN's Core Rulebook section.

## Coverage decision

The archived set covers every numeric dependency of the first production
slice: basic ability arrays, human racial traits, warrior HD/BAB/saves/skills,
level advancement, skill totals, general feats, mundane weapons and armor, NPC
gear budgets, and combat statistics.

The goblin Sorcerer phase additionally archives current-site pages for Goblin,
Sorcerer, the Elemental bloodline, sixteen selected spells, three selected
skills, wands, a cloak of resistance +1, and the classed-NPC CR rule. Later phases should continue to
archive only the individual class, item, spell, and condition pages they need.
These are acquisition tasks, not reasons to request the full PDF.
Official errata is still required only if a printed-example discrepancy such as
Kiramor's values must be adjudicated.

## Gear-profile finding

Table 14-9 is indexed by **basic level** and **heroic level**, with category
allocations for weapons, protection, magic, limited-use items, and gear. Its
preceding prose also defines the existing profile dimensions: fast progression
uses one level higher, slow uses one lower, high fantasy doubles values, and low
fantasy halves them. The nine progression/fantasy combinations are therefore
source-supported; their level boundaries still need explicit validation when
the catalog rows are hydrated.
