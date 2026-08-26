import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine


GOBLIN_DRUID_DRAFT = json.loads(
    (Path(__file__).parent / "fixtures" / "goblin-druid-cr4.json").read_text()
)


def request(request_id, operation, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


class ValidationHardeningTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()

    def assert_source_rule_issue(self, evaluation, code, path):
        issue = next(issue for issue in evaluation["issues"] if issue["code"] == code)
        self.assertEqual(issue["kind"], "source-rule")
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(issue["path"], path)
        return issue

    def test_spellcaster_without_spell_list_or_spells_is_incomplete(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"].pop("spellListId")

        response = self.engine.execute(request(
            "spellcaster-selection-required", "draft.create", {"draft": draft}
        ))

        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "incomplete")
        self.assert_source_rule_issue(
            evaluation, "spells.selection-required", "/selections/spellListId"
        )

    def test_humanoid_without_racial_subtype_is_incomplete_but_valid_subtype_passes(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"].pop("subtypeGraftIds")

        response = self.engine.execute(request(
            "humanoid-subtype-required", "draft.create", {"draft": draft}
        ))

        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "incomplete")
        self.assert_source_rule_issue(
            evaluation, "humanoid.subtype-required", "/selections/subtypeGraftIds"
        )

        valid = self.engine.execute(request(
            "humanoid-subtype-present", "draft.create", {"draft": GOBLIN_DRUID_DRAFT}
        ))
        self.assertTrue(valid["ok"], valid)
        self.assertEqual(valid["result"]["evaluation"]["status"], "valid")

    def test_sneak_attack_reduces_each_base_attack_and_records_bonus_dice(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"]["options"] = [{
            "optionId": "option.sneak-attack",
            "parameters": {},
        }]
        draft["selections"]["attacks"][0].update({
            "attackProfile": "weapon.low",
            "damageDie": "d6",
        })

        response = self.engine.execute(request(
            "sneak-attack-damage", "draft.create", {"draft": draft}
        ))

        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid")
        canonical = evaluation["canonical"]
        self.assertEqual(canonical["sneakAttackDice"], "3d6")
        self.assertTrue(canonical["attacks"])
        for attack in canonical["attacks"]:
            self.assertEqual(attack["averageDamage"], 5)
            self.assertEqual(attack["damageDie"], "d6")
            self.assertEqual(attack["damageExpression"], "1d6+1")

    def test_explicit_spells_receive_cr_band_frequencies_and_list_benefit(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"]["spells"] = [
            {"spellId": "spell.core.call-lightning"},
            {"spellId": "spell.core.entangle"},
        ]

        response = self.engine.execute(request(
            "explicit-spell-frequencies", "draft.create", {"draft": draft}
        ))

        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
        self.assertEqual(
            [(spell["name"], spell["frequency"], spell["sourceBand"]) for spell in evaluation["canonical"]["spells"]],
            [("Call Lightning", "1/day", "4–7"), ("Entangle", "3/day", "0–3")],
        )
        self.assertEqual(evaluation["canonical"]["spellListBenefit"]["spellListId"], "spell-list.nature")

    def test_custom_spells_without_a_list_benefit_are_incomplete(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"].pop("spellListId")
        draft["selections"]["spells"] = [{"spellId": "spell.core.call-lightning"}]

        response = self.engine.execute(request(
            "custom-spell-benefit-required", "draft.create", {"draft": draft}
        ))

        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "incomplete")
        self.assert_source_rule_issue(
            evaluation, "spells.benefit-required", "/selections/spellListId"
        )

    def test_global_spell_level_source_is_a_case_insensitive_preference(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"]["spellLevelSource"] = "Druid"
        draft["selections"]["spells"] = [
            {"spellId": "spell.core.call-lightning"},
            {"spellId": "spell.core.acid-arrow"},
        ]

        response = self.engine.execute(request(
            "global-spell-level-source", "draft.create", {"draft": draft}
        ))

        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
        self.assertEqual(
            [(spell["name"], spell["spellLevelSource"]) for spell in evaluation["canonical"]["spells"]],
            [("Call Lightning", "druid"), ("Acid Arrow", "sorcerer")],
        )

    def test_explicit_spell_level_source_must_cast_the_spell(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"]["spells"] = [{
            "spellId": "spell.core.hideous-laughter",
            "spellLevelSource": "druid",
        }]

        response = self.engine.execute(request(
            "spell-level-source-invalid", "draft.create", {"draft": draft}
        ))

        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "invalid")
        self.assert_source_rule_issue(
            evaluation, "spell.level-source-invalid", "/selections/spells/0"
        )

    def test_sneak_attack_export_includes_its_trigger(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"]["options"] = [{
            "optionId": "option.sneak-attack",
            "parameters": {},
        }]
        draft["selections"]["attacks"][0].update({
            "attackProfile": "weapon.low",
            "damageDie": "d6",
        })
        created = self.engine.execute(request(
            "sneak-export-create", "draft.create", {"draft": draft}
        ))["result"]
        saved = created["draft"]
        finalized = self.engine.execute(request("sneak-export-finalize", "monster.finalize", {
            "draftId": saved["draftId"],
            "baseRevision": saved["revision"],
            "baseFingerprint": saved["fingerprint"],
        }))
        self.assertTrue(finalized["ok"], finalized)
        monster_id = finalized["result"]["monster"]["monsterId"]

        exported = self.engine.execute(request("sneak-export-markdown", "monster.export", {
            "monsterId": monster_id,
            "format": "markdown",
            "profile": "sheet",
        }))

        self.assertTrue(exported["ok"], exported)
        self.assertIn("flanking or attacking a foe denied its Dexterity bonus to AC", exported["result"]["content"])

    def test_canonical_skill_keys_do_not_leak_catalog_prefixes(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"]["skills"]["good"] = ["skill.acrobatics"]
        response = self.engine.execute(request(
            "canonical-skill-ids", "draft.create", {"draft": draft}
        ))

        self.assertTrue(response["ok"], response)
        skills = response["result"]["evaluation"]["canonical"]["skills"]
        self.assertIn("acrobatics", skills)
        self.assertNotIn("skill.acrobatics", skills)

    def test_manufactured_weapon_without_damage_die_is_rejected(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"]["attacks"][0].pop("damageDie")

        response = self.engine.execute(request(
            "weapon-die-required", "draft.create", {"draft": draft}
        ))

        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "invalid")
        self.assert_source_rule_issue(
            evaluation, "damage.weapon-die-required", "/selections/attacks/0/damageDie"
        )


if __name__ == "__main__":
    unittest.main()
