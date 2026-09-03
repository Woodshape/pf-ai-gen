import copy
import json
import tempfile
import unittest
from pathlib import Path

from monster_builder import Engine


ROOT = Path(__file__).parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "goblin-druid-3-elemental-ally.json").read_text(encoding="utf-8"))
FIRE_DOMAIN_FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "goblin-druid-3-fire.json").read_text(encoding="utf-8"))
SORCERER_FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "goblin-sorcerer-6.json").read_text(encoding="utf-8"))
ARCHETYPE_ID = "npc-class-feature.druid-elemental-ally"
ARCHETYPE_BUDGET = {
    "0": {"base": 4, "wisdomBonus": 0, "domain": 0, "total": 4},
    "1": {"base": 2, "wisdomBonus": 1, "domain": 0, "total": 3},
    "2": {"base": 1, "wisdomBonus": 1, "domain": 0, "total": 2},
}


def request(request_id, operation, payload):
    return {"protocolVersion": "1", "requestId": request_id, "operation": operation, "payload": payload}


def _catalog_row():
    catalog = json.loads((ROOT / "catalog" / "npc.json").read_text(encoding="utf-8"))
    return catalog.get("classFeatures", {}).get(ARCHETYPE_ID)


ARCHETYPE_RECORD = _catalog_row()


def _gate_ready() -> bool:
    record = ARCHETYPE_RECORD
    row = (record or {}).get("linkedCreatureRow")
    return bool(
        record
        and record.get("catalogStatus") == "resolved"
        and record.get("kind") == "archetype"
        and isinstance(row, dict) and row.get("catalogStatus") == "resolved"
        and isinstance(row.get("fields"), dict) and row["fields"]
    )


GATE_READY = _gate_ready()
requires_curated_archetype = unittest.skipUnless(
    GATE_READY,
    "the Elemental Ally archetype record is not source-resolved yet; blocked on the 1.a/1.b/2.a source gate",
)


def expected_linked_creature_block():
    """Project the curated catalog row exactly as the adapter must (data-driven, no rule values here)."""
    record = ARCHETYPE_RECORD
    row = record["linkedCreatureRow"]
    fields = row["fields"]

    def normalize_refs(raw):
        return raw if isinstance(raw, list) else [raw]

    block = {
        "archetypeId": record["id"],
        "element": row["element"],
        "level": row["level"],
    }
    if "name" in row:
        block["name"] = row["name"]
    for key in sorted(fields):
        block[key] = fields[key]["value"]
    block["fieldSourceRefs"] = {key: normalize_refs(fields[key]["sourceRef"]) for key in sorted(fields)}
    return block


def archetype_selections():
    return copy.deepcopy(FIXTURE["selections"])


def archetype_draft_payload(selections=None):
    return {"draft": {"creationSystem": "npc", "concept": copy.deepcopy(FIXTURE["concept"]),
                      "selections": selections if selections is not None else archetype_selections()}}


class ElementalAllyGateStateTests(unittest.TestCase):
    """Assertions that hold under the current repository state, before and after curation."""

    def test_unknown_archetype_id_is_a_public_boundary_error(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["archetypeId"] = "npc-class-feature.does-not-exist"
        response = Engine().execute(request("unknown-archetype", "draft.create", {"draft": draft}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "catalog.unknown-id")
        self.assertEqual(response["error"]["path"], "/selections/archetypeId")

    def test_computed_linked_creature_is_not_a_selection(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["linkedCreature"] = {"name": "injected"}
        response = Engine().execute(request("computed-linked", "draft.create", {"draft": draft}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "draft.computed-selection")
        self.assertEqual(response["error"]["path"], "/selections/linkedCreature")

    def test_fire_domain_snapshot_carries_no_linked_creature_section(self):
        with tempfile.TemporaryDirectory() as workspace:
            engine = Engine(workspace=workspace)
            created = engine.execute(request("fd-create", "draft.create", {"draft": copy.deepcopy(FIRE_DOMAIN_FIXTURE)}))
            self.assertTrue(created["ok"], created)
            draft = created["result"]["draft"]
            finalized = engine.execute(request("fd-finalize", "monster.finalize", {
                "draftId": draft["draftId"], "baseRevision": draft["revision"], "baseFingerprint": draft["fingerprint"],
            }))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            self.assertNotIn("linkedCreature", monster["result"])
            for format_name in ("markdown", "html"):
                exported = engine.execute(request(f"fd-{format_name}", "monster.export", {
                    "monsterId": monster["monsterId"], "format": format_name,
                }))
                self.assertTrue(exported["ok"], exported)
                self.assertNotIn("LINKED CREATURE", exported["result"]["content"])

    @unittest.skipUnless(not GATE_READY, "the Elemental Ally archetype record is now curated")
    def test_elemental_ally_path_is_inert_until_curated(self):
        response = Engine().execute(request("inert", "draft.create", archetype_draft_payload()))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "catalog.unknown-id")
        self.assertEqual(response["error"]["path"], "/selections/archetypeId")


@requires_curated_archetype
class ElementalAllyValidEvaluationTests(unittest.TestCase):
    def test_public_engine_builds_the_archetype_slice_with_the_linked_creature(self):
        created = Engine().execute(request("ea-create", "draft.create", archetype_draft_payload()))
        self.assertTrue(created["ok"], created)
        evaluation = created["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
        canonical = evaluation["canonical"]
        self.assertEqual((canonical["level"], canonical["totalLevel"], canonical["npcCategory"], canonical["cr"]), (3, 3, "heroic", 2))
        self.assertEqual(canonical["abilityScores"], {
            "strength": 10, "dexterity": 12, "constitution": 14,
            "intelligence": 10, "wisdom": 15, "charisma": 11,
        })
        self.assertEqual((canonical["hp"], canonical["hitDiceExpression"], canonical["bab"]), (27, "3d8+6", 2))
        self.assertEqual(canonical["defenses"], {
            "ac": 16, "touch": 12, "flatFooted": 15,
            "fortitude": 5, "reflex": 2, "will": 7,
            "acBreakdown": {"armor": 2, "shield": 2, "dexterity": 1, "size": 1},
        })
        self.assertEqual((canonical["initiative"], canonical["cmb"], canonical["cmd"]), (5, 1, 12))
        self.assertEqual(canonical["languages"], ["Goblin", "Druidic"])

        features = [feature["featureId"] for feature in canonical["classFeatures"]]
        self.assertEqual(features, [
            "npc-class-feature.druid-proficiencies", "npc-class-feature.druid-spellcasting",
            "npc-class-feature.druid-orisons", ARCHETYPE_ID,
            "npc-class-feature.druidic", "npc-class-feature.druid-nature-sense",
            "npc-class-feature.druid-woodland-stride",
            "npc-class-feature.druid-trackless-step",
        ])
        self.assertNotIn("npc-class-feature.druid-wild-empathy", features)
        archetype_entry = next(f for f in canonical["classFeatures"] if f["featureId"] == ARCHETYPE_ID)
        self.assertEqual(archetype_entry["elementalEmpathy"], {"checkBonus": 3})
        self.assertEqual(archetype_entry["name"], ARCHETYPE_RECORD["name"])
        self.assertEqual(archetype_entry["replaces"], ARCHETYPE_RECORD["replaces"])
        self.assertIn("npc-class-feature.druid-nature-bond", archetype_entry["replaces"])
        self.assertTrue(archetype_entry["sourceRefs"])
        self.assertNotIn("npc-class-feature.fire-domain", features)
        self.assertEqual([attack["name"] for attack in canonical["attacks"]], ["Sickle"])

        skills = {entry["skillId"]: entry for entry in canonical["skills"]}
        self.assertEqual(skills["skill.knowledge-nature"]["total"], 8)
        self.assertEqual(skills["skill.knowledge-nature"]["classFeatureBonus"], 2)
        self.assertEqual(skills["skill.survival"]["total"], 10)

        gear = {entry["itemId"]: entry for entry in canonical["gear"]}
        self.assertEqual(gear["item.sickle"]["weightLb"], 1)
        self.assertEqual(canonical["gearBudget"]["budgetCp"], 165000)
        self.assertEqual(canonical["gearBudget"]["spentCp"], 2300)

        spells = canonical["spells"]
        self.assertEqual(spells["castingMode"], "prepared")
        self.assertEqual(spells["casterLevel"], 3)
        self.assertNotIn("domainPrepared", spells)
        self.assertEqual(spells["slotsByLevel"], ARCHETYPE_BUDGET)
        self.assertEqual(spells["saveDcByLevel"], {"0": 12, "1": 13, "2": 14})
        self.assertEqual(spells["prepared"], {
            "0": ["spell.detect-magic", "spell.light", "spell.flare", "spell.detect-magic"],
            "1": ["spell.produce-flame", "spell.entangle", "spell.cure-light-wounds"],
            "2": ["spell.flaming-sphere", "spell.barkskin"],
        })
        self.assertEqual(spells["spontaneousConversion"], {
            "name": "Summon Nature’s Ally", "from": "prepared", "excludesDomainSlots": True,
            "spellIdsBySlotLevel": {
                "1": ["spell.summon-nature-s-ally-i"],
                "2": ["spell.summon-nature-s-ally-i", "spell.summon-nature-s-ally-ii"],
            },
        })
        self.assertTrue(all(entry["sourceRefs"] for entry in evaluation["derivationTrace"]))
        warning_codes = {warning["code"] for warning in evaluation["warnings"]}
        self.assertEqual(warning_codes, {"npc.gear-budget-approximate"})

    def test_linked_creature_block_projects_the_curated_row_exactly(self):
        created = Engine().execute(request("ea-block", "draft.create", archetype_draft_payload()))
        self.assertTrue(created["ok"], created)
        block = created["result"]["evaluation"]["canonical"]["linkedCreature"]
        expected = expected_linked_creature_block()
        block_values = {key: value for key, value in block.items() if key != "sourceRefs"}
        expected_values = {key: value for key, value in expected.items() if key != "sourceRefs"}
        self.assertEqual(block_values, expected_values)
        field_ref_set = {json.dumps(ref, sort_keys=True) for refs in block["fieldSourceRefs"].values() for ref in refs}
        block_ref_set = {json.dumps(ref, sort_keys=True) for ref in block["sourceRefs"]}
        self.assertTrue(block_ref_set)
        self.assertTrue(field_ref_set.issubset(block_ref_set))
        self.assertEqual(block["element"], "fire")
        self.assertEqual(block["level"], 3)

    def test_curated_base_form_is_biped(self):
        created = Engine().execute(request("ea-biped", "draft.create", archetype_draft_payload()))
        self.assertTrue(created["ok"], created)
        block = created["result"]["evaluation"]["canonical"]["linkedCreature"]
        self.assertEqual(block["attacks"], [{
            "name": "slam", "attackType": "melee", "attackBonus": "+6",
            "damage": "1d8+4", "count": 1,
            "notes": "primary attack; sole natural attack adds 1-1/2 Strength bonus to damage",
        }])
        self.assertEqual(block["speed"], {"land": 30})
        self.assertEqual(block["defenses"], {
            "ac": 15, "touch": 11, "flatFooted": 14,
            "fortitude": 4, "reflex": 2, "will": 3,
            "acBreakdown": {"armor": 4, "dexterity": 1},
        })
        self.assertEqual((block["initiative"], block["cmb"], block["cmd"]), (1, 6, 17))
        self.assertEqual(block["abilities"]["strength"], 17)
        self.assertEqual(block["abilities"]["dexterity"], 13)

    def test_trace_projects_the_linked_creature_row(self):
        created = Engine().execute(request("ea-trace", "draft.create", archetype_draft_payload()))
        self.assertTrue(created["ok"], created)
        trace = {entry["path"]: entry for entry in created["result"]["evaluation"]["derivationTrace"]}
        self.assertIn("/canonical/linkedCreature", trace)
        entry = trace["/canonical/linkedCreature"]
        self.assertEqual(entry["value"], created["result"]["evaluation"]["canonical"]["linkedCreature"])
        self.assertTrue(entry["sourceRefs"])
        self.assertIn(ARCHETYPE_RECORD["name"], entry["calculation"])


@requires_curated_archetype
class ElementalAllyRejectionTests(unittest.TestCase):
    def evaluation_for(self, selections):
        response = Engine().execute(request("ea-eval", "draft.create", {"draft": {
            "creationSystem": "npc", "concept": copy.deepcopy(FIXTURE["concept"]),
            "selections": selections,
        }}))
        self.assertTrue(response["ok"], response)
        return response["result"]["evaluation"]

    def test_archetype_on_a_non_druid_is_rejected(self):
        selections = copy.deepcopy(SORCERER_FIXTURE["selections"])
        selections["archetypeId"] = ARCHETYPE_ID
        evaluation = self.evaluation_for(selections)
        self.assertEqual(evaluation["status"], "invalid")
        issues = {(issue["code"], issue.get("path")) for issue in evaluation["issues"]}
        self.assertIn(("npc.catalog-gap", "/selections/archetypeId"), issues)
        self.assertIn(("npc.slice-unsupported", "/selections/archetypeId"), issues)

    def test_archetype_outside_druid_level_3_is_rejected(self):
        selections = archetype_selections()
        selections["classProgression"] = [{"classId": "npc-class.druid", "levels": 2}]
        selections["spellLoadout"]["prepared"] = {"0": ["spell.detect-magic", "spell.light", "spell.flare", "spell.detect-magic"], "1": ["spell.produce-flame", "spell.entangle"]}
        evaluation = self.evaluation_for(selections)
        self.assertEqual(evaluation["status"], "invalid")
        issues = {(issue["code"], issue.get("path")) for issue in evaluation["issues"]}
        self.assertIn(("npc.slice-unsupported", "/selections/classProgression"), issues)

    def test_archetype_plus_nature_bond_conflict_is_rejected(self):
        selections = archetype_selections()
        selections["classFeatureChoices"] = {"natureBond": "fire-domain"}
        evaluation = self.evaluation_for(selections)
        self.assertEqual(evaluation["status"], "invalid")
        issues = {(issue["code"], issue.get("path")) for issue in evaluation["issues"]}
        self.assertIn(("npc.choice-invalid", "/selections/classFeatureChoices/natureBond"), issues)

    def test_domain_prepared_is_rejected_with_the_archetype(self):
        selections = archetype_selections()
        selections["spellLoadout"]["domainPrepared"] = {"1": ["spell.burning-hands"], "2": ["spell.produce-flame"]}
        evaluation = self.evaluation_for(selections)
        self.assertEqual(evaluation["status"], "invalid")
        issue = next(issue for issue in evaluation["issues"]
                     if issue["code"] == "npc.spell-levels-invalid" and issue.get("path") == "/selections/spellLoadout/domainPrepared")
        self.assertEqual(issue["details"]["expectedLevels"], [])


@requires_curated_archetype
class ElementalAllyRequirementsAndExportTests(unittest.TestCase):
    def test_choice_requirements_drop_domain_slots(self):
        requirements = Engine().execute(request("ea-requirements", "draft.choiceRequirements", archetype_draft_payload()))
        self.assertTrue(requirements["ok"], requirements)
        paths = {item["path"] for item in requirements["result"]["requirements"]}
        self.assertNotIn("/selections/classFeatureChoices/natureBond", paths)
        self.assertNotIn("/selections/spellLoadout/domainPrepared", paths)
        self.assertIn("/selections/spellLoadout/prepared", paths)
        self.assertEqual(requirements["result"]["selectionBudgets"]["spells"],
                         {"required": True, "mode": "prepared", "levels": ARCHETYPE_BUDGET})
        baseline = Engine().execute(request("fd-requirements", "draft.choiceRequirements", {"draft": copy.deepcopy(FIRE_DOMAIN_FIXTURE)}))
        self.assertTrue(baseline["ok"], baseline)
        self.assertEqual(requirements["result"]["selectionBudgets"]["gear"],
                         baseline["result"]["selectionBudgets"]["gear"])
        self.assertEqual(requirements["result"]["selectionBudgets"]["skills"],
                         baseline["result"]["selectionBudgets"]["skills"])
        self.assertEqual(requirements["result"]["selectionBudgets"]["feats"],
                         baseline["result"]["selectionBudgets"]["feats"])

    def test_exports_render_the_linked_creature_section(self):
        with tempfile.TemporaryDirectory() as workspace:
            engine = Engine(workspace=workspace)
            created = engine.execute(request("ea-export-create", "draft.create", archetype_draft_payload()))
            self.assertTrue(created["ok"], created)
            draft = created["result"]["draft"]
            finalized = engine.execute(request("ea-export-finalize", "monster.finalize", {
                "draftId": draft["draftId"], "baseRevision": draft["revision"], "baseFingerprint": draft["fingerprint"],
            }))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            self.assertIn("linkedCreature", monster["result"])
            row = ARCHETYPE_RECORD["linkedCreatureRow"]
            block = monster["result"]["linkedCreature"]
            self.assertEqual(block["element"], row["element"])
            self.assertEqual(block["level"], row["level"])
            if row.get("name"):
                self.assertEqual(block.get("name"), row["name"])
            markdown = engine.execute(request("ea-md", "monster.export", {
                "monsterId": monster["monsterId"], "format": "markdown",
            }))["result"]["content"]
            self.assertIn("## LINKED CREATURE", markdown)
            element_title = block["element"].replace("-", " ").replace("_", " ").title()
            identity_parts = [part for part in (block.get("name"), element_title, f"level {block['level']}") if part]
            self.assertIn(f"## LINKED CREATURE\n{'; '.join(identity_parts)}", markdown)
            section = markdown.split("## LINKED CREATURE", 1)[1]
            self.assertIn("Neutral Medium outsider; Speed 30 ft.", section)
            self.assertIn("Init +1; Senses darkvision 60 ft.", section)
            self.assertIn("AC 15 (+4 armor, +1 Dex), touch 11, flat-footed 14; hp 19 (3 HD); Fort +4, Ref +2, Will +3", section)
            self.assertIn("Melee slam +6 (1d8+4)", section)
            self.assertIn("Str 17, Dex 13, Con 13, Int 7, Wis 10, Cha 11", section)
            self.assertIn("BAB +3; CMB +6; CMD 17", section)
            self.assertIn("Skills 12 ranks; Feats 2; Max Attacks 3", section)
            self.assertIn("Qualities link, share spells, evasion", section)
            html = engine.execute(request("ea-html", "monster.export", {
                "monsterId": monster["monsterId"], "format": "html",
            }))["result"]["content"]
            self.assertIn("<h2>LINKED CREATURE</h2>", html)
            exported = engine.execute(request("ea-json", "monster.export", {
                "monsterId": monster["monsterId"], "format": "json",
            }))["result"]["content"]
            self.assertEqual(exported["result"]["linkedCreature"], block)


@requires_curated_archetype
class ElementalAllyLifecycleTests(unittest.TestCase):
    def test_create_finalize_reload_export_through_the_public_engine(self):
        with tempfile.TemporaryDirectory() as workspace:
            engine = Engine(workspace=workspace)
            created = engine.execute(request("ea-life-create", "draft.create", archetype_draft_payload()))
            self.assertTrue(created["ok"], created)
            draft = created["result"]["draft"]
            finalized = engine.execute(request("ea-life-finalize", "monster.finalize", {
                "draftId": draft["draftId"], "baseRevision": draft["revision"], "baseFingerprint": draft["fingerprint"],
            }))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            self.assertEqual(monster["creationSystem"], "npc")

            reloaded = Engine(workspace=workspace)
            loaded_draft = reloaded.execute(request("ea-life-draft", "draft.get", {"draftId": draft["draftId"]}))
            loaded_monster = reloaded.execute(request("ea-life-monster", "monster.get", {"monsterId": monster["monsterId"]}))
            self.assertTrue(loaded_draft["ok"], loaded_draft)
            self.assertTrue(loaded_monster["ok"], loaded_monster)
            self.assertEqual(loaded_draft["result"]["evaluation"]["status"], "valid")
            self.assertEqual(loaded_monster["result"]["monster"], monster)
            for format_name in ("json", "markdown", "html"):
                exported = reloaded.execute(request(f"ea-life-{format_name}", "monster.export", {
                    "monsterId": monster["monsterId"], "format": format_name,
                }))
                self.assertTrue(exported["ok"], exported)


if __name__ == "__main__":
    unittest.main()