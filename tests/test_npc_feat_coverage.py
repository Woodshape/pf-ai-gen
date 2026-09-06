"""Public Engine regressions for source-backed NPC feat effects."""
import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine
from test_npc_composition import draft_for, evaluate
from tools.audit_npc_feats import inventory, probes

ROOT = Path(__file__).resolve().parents[1]


class NpcFeatCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "catalog/npc.json").read_text())

    def draft(self, feat, **choice):
        draft = draft_for(self.catalog, "npc-race.halfling", "npc-class.bard", 2)
        draft["selections"]["feats"] = [{"slotId": "general-1", "featId": feat, **choice}]
        return draft

    def valid(self, draft):
        result = evaluate(draft)
        self.assertEqual(result["status"], "valid", result["issues"])
        return result["canonical"]

    def test_metadata_enrichment_is_idempotent_and_source_backed(self):
        from tools.enrich_npc_spell_metadata import enrich as spells
        from tools.enrich_npc_weapon_metadata import enrich as weapons
        for name, enrich in (("spells", spells), ("items", weapons)):
            records = json.loads((ROOT / f"catalog/npc/{name}.fragment.json").read_text())["records"]
            enriched = enrich(copy.deepcopy(records))
            self.assertEqual(enrich(copy.deepcopy(enriched)), enriched)
        self.assertEqual(self.catalog["items"]["item.greatsword"]["effects"]["handedness"], "two-handed")
        self.assertEqual(self.catalog["spells"]["spell.fireball"]["school"], "evocation")

    def test_audit_inventory_and_reported_defects(self):
        self.assertEqual(len(inventory()), 99)
        for probe in probes().values():
            self.assertEqual(probe["actual"], probe["expected"])
        for row in inventory():
            self.assertEqual(row["catalogStatus"], "resolved", row)
            record = self.catalog["feats"][row["id"]]
            self.assertTrue(record["treatments"])
            self.assertTrue(record["rulesText"])
            self.assertIn(record["supportStatus"], {"calculated", "gm-handled", "partial", "selection-only"})

    def test_base_and_conditional_modifiers_do_not_leak(self):
        base = self.valid(self.draft("feat.endurance"))
        for feat, field, delta in (("feat.toughness", "hp", 3), ("feat.improved-initiative", "initiative", 4)):
            with self.subTest(feat=feat):
                result = self.valid(self.draft(feat))
                self.assertEqual(result[field], base[field] + delta)
        fort = self.valid(self.draft("feat.great-fortitude"))
        self.assertEqual(fort["defenses"]["fortitude"], base["defenses"]["fortitude"] + 2)
        dodge = self.valid(self.draft("feat.dodge"))
        for field in ("ac", "touch"):
            self.assertEqual(dodge["defenses"][field], base["defenses"][field] + 1)
        self.assertEqual(dodge["defenses"]["flatFooted"], base["defenses"]["flatFooted"])
        self.assertEqual(dodge["cmd"], base["cmd"] + 1)
        casting = self.valid(self.draft("feat.combat-casting"))
        self.assertEqual(casting["spells"]["concentration"], base["spells"]["concentration"])
        self.assertIn({"condition": "casting on the defensive or while grappled", "stat": "concentration", "bonus": 4}, casting["conditionalModifiers"])

    def test_skill_focus_choice_and_prerequisites(self):
        base = self.valid(self.draft("feat.endurance"))
        skill_id = base["skills"][0]["skillId"]
        focused = self.valid(self.draft("feat.skill-focus", skillId=skill_id))
        self.assertEqual(focused["skills"][0]["total"], base["skills"][0]["total"] + 3)
        missing = evaluate(self.draft("feat.skill-focus"))
        self.assertIn("npc.feat-choice-invalid", {issue["code"] for issue in missing["issues"]})
        mounted = self.draft("feat.mounted-combat")
        mounted["selections"]["skillGeneration"]["skills"][0] = "skill.ride"
        self.valid(mounted)
        self.assertIn("npc.feat-prerequisite", {issue["code"] for issue in evaluate(self.draft("feat.mounted-combat"))["issues"]})
        # Total BAB at level 2 cannot retroactively qualify a level-1 feat.
        self.assertIn("npc.feat-prerequisite", {issue["code"] for issue in evaluate(self.draft("feat.weapon-focus", weaponId="item.rapier"))["issues"]})

    def test_school_dcs_and_choice_discovery(self):
        draft = self.draft("feat.spell-focus", school="enchantment")
        base = self.valid(self.draft("feat.endurance"))
        focused = self.valid(draft)
        for level, ids in focused["spells"]["known"].items():
            for spell_id in ids:
                bonus = int(self.catalog["spells"][spell_id]["school"] == "enchantment")
                self.assertEqual(focused["spells"]["saveDcBySpell"][spell_id], base["spells"]["saveDcByLevel"][level] + bonus)
        response = Engine().execute({"protocolVersion": "1", "requestId": "feat-choices", "operation": "draft.create", "payload": {"draft": draft}})
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["draft"]["selections"]["feats"], draft["selections"]["feats"])

    def test_natural_spell_qualifies_after_wild_shape_is_acquired(self):
        draft = draft_for(self.catalog, "npc-race.human", "npc-class.druid", 4)
        draft["selections"]["classProgression"].append({"classId": "npc-class.warrior", "levels": 1})
        draft["selections"]["feats"].append({"slotId": "general-5", "featId": "feat.natural-spell"})
        result = self.valid(draft)
        self.assertTrue(any(feat["featId"] == "feat.natural-spell" for feat in result["feats"]))
        shape = next(feature for feature in result["classFeatures"] if feature["featureId"] == "npc-class-feature.druid-wild-shape")
        self.assertEqual(shape["wildShape"], {"usesPerDay": 1, "hoursPerUse": 4})
        self.assertEqual(result["size"]["id"], "size.medium")

    def test_scaling_and_equipment_effects_via_engine(self):
        draft = draft_for(self.catalog, "npc-race.human", "npc-class.warrior", 10)
        draft["selections"]["gear"] = [{"itemId": "item.longsword"}, {"itemId": "item.light-steel-shield"}]
        base = self.valid(draft)
        skill_id = base["skills"][0]["skillId"]
        draft["selections"]["feats"][0] = {"slotId": "general-1", "featId": "feat.skill-focus", "skillId": skill_id}
        focused = self.valid(draft)
        self.assertEqual(focused["skills"][0]["total"], base["skills"][0]["total"] + 6)
        draft["selections"]["feats"][0] = {"slotId": "general-1", "featId": "feat.shield-focus"}
        shield = self.valid(draft)
        self.assertEqual(shield["defenses"]["ac"], base["defenses"]["ac"] + 1)
        self.assertEqual(shield["defenses"]["flatFooted"], base["defenses"]["flatFooted"] + 1)
        self.assertEqual(shield["defenses"]["touch"], base["defenses"]["touch"])
        draft["selections"]["feats"][0] = {"slotId": "general-1", "featId": "feat.weapon-focus", "weaponId": "item.longsword"}
        weapon = self.valid(draft)
        self.assertEqual(weapon["attacks"][0]["attackBonuses"], [bonus + 1 for bonus in base["attacks"][0]["attackBonuses"]])
        draft["selections"]["feats"][4] = {"slotId": "general-9", "featId": "feat.improved-critical", "weaponId": "item.longsword"}
        critical = self.valid(draft)
        self.assertEqual(critical["attacks"][0]["critical"], "17-20/x2")

    def test_feat_choices_and_riders_survive_finalization_and_exports(self):
        from monster_builder.exports import render_html, render_markdown
        engine = Engine()
        draft = self.draft("feat.combat-casting")
        created = engine.execute({"protocolVersion": "1", "requestId": "feat-export-create", "operation": "draft.create", "payload": {"draft": draft}})
        saved = created["result"]["draft"]
        finished = engine.execute({"protocolVersion": "1", "requestId": "feat-export-finalize", "operation": "monster.finalize", "payload": {
            "draftId": saved["draftId"], "baseRevision": saved["revision"], "baseFingerprint": saved["fingerprint"]}})
        self.assertTrue(finished["ok"], finished)
        snapshot = finished["result"]["monster"]
        self.assertEqual(snapshot["result"]["conditionalModifiers"][0]["bonus"], 4)
        for render in (render_html, render_markdown):
            text = render(snapshot, "audit")
            self.assertIn("+4 concentration", text)
            self.assertIn("casting on the defensive or while grappled", text)

    def test_iteratives_at_each_bab_threshold(self):
        from monster_builder.creation_systems.npc import NpcCreation
        weapon = {"itemId": "item.longbow", "name": "Longbow", "category": "weapon", "effects": self.catalog["items"]["item.longbow"]["effects"]}
        for bab, count in ((6, 2), (11, 3), (16, 4)):
            attacks = NpcCreation._attacks([weapon], bab, {"strength": 0, "dexterity": 2}, {}, "size.medium", weapon_proficiencies={"martial"}, rapid_shot=True)
            self.assertEqual(len(attacks[0]["attackBonuses"]), count)
            self.assertEqual(len(attacks[1]["attackBonuses"]), count + 1)
            self.assertEqual(attacks[1]["attackBonuses"][2:], [bonus - 2 for bonus in attacks[0]["attackBonuses"][1:]])


if __name__ == "__main__":
    unittest.main()
