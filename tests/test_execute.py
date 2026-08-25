import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine


WORG_DRAFT = json.loads((Path(__file__).parent / "fixtures" / "worg-cr2.json").read_text())
GRIFFON_DRAFT = json.loads((Path(__file__).parent / "fixtures" / "griffon-cr4.json").read_text())


def request(request_id, operation, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


class ExecuteVerticalSliceTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()

    def create_worg(self):
        response = self.engine.execute(request("create-worg", "draft.create", {"draft": WORG_DRAFT}))
        self.assertTrue(response["ok"], response)
        return response

    def test_small_natural_attack_fixed_damage_is_explicit_source_gap(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["sizeId"] = "graft.size.diminutive"
        draft["selections"]["options"][0]["parameters"]["attackType"] = "claw"
        draft["selections"]["attacks"] = [{
            "name": "claw",
            "naturalAttackId": "natural-attack.claw",
            "attackProfile": "natural.two",
        }]
        response = self.engine.execute(request("small-natural", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "invalid")
        issue = next(issue for issue in evaluation["issues"] if issue["code"] == "damage.fixed-natural-unsupported")
        self.assertTrue(issue["sourceRefs"])

    def test_tiny_natural_attack_damage_gap_has_source_refs(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["sizeId"] = "graft.size.tiny"
        draft["selections"]["options"][0]["parameters"]["attackType"] = "claw"
        draft["selections"]["attacks"] = [{
            "name": "claw",
            "naturalAttackId": "natural-attack.claw",
            "attackProfile": "natural.two",
        }]
        response = self.engine.execute(request("tiny-natural", "draft.create", {"draft": draft}))
        evaluation = response["result"]["evaluation"]
        issue = next(issue for issue in evaluation["issues"] if issue["code"] == "damage.unresolved")
        self.assertTrue(issue["sourceRefs"])
        self.assertIn("6–8", {ref.get("entry") for ref in issue["sourceRefs"]})

    def test_worg_cr2_is_reproduced_from_public_execute(self):
        response = self.create_worg()
        evaluation = response["result"]["evaluation"]
        canonical = evaluation["canonical"]

        self.assertEqual(evaluation["status"], "valid")
        self.assertEqual(canonical["cr"], 2)
        self.assertEqual(canonical["defenses"], {
            "ac": 16,
            "touchAC": 12,
            "flatFootedAC": 12,
            "fortitude": 5,
            "reflex": 5,
            "will": 1,
            "cmd": 16,
            "hp": 22,
        })
        self.assertEqual(canonical["abilityDC"], 11)
        self.assertEqual(canonical["spellDC"], 11)
        self.assertEqual(canonical["spells"], [])
        self.assertEqual(canonical["skills"], {
            "perception": 10,
            "stealth": 7,
            "survival": 7,
        })
        self.assertEqual(canonical["initiative"], 2)
        self.assertEqual(canonical["cmb"], 4)
        self.assertEqual(canonical["maneuverBonuses"], {
            "trip": {"cmb": 8, "cmd": 20}
        })
        self.assertEqual(canonical["attacks"][0]["attackBonus"], [6])
        self.assertEqual(canonical["attacks"][0]["averageDamage"], 11)
        self.assertEqual(canonical["attacks"][0]["damageExpression"], "1d6+7")
        self.assertEqual(canonical["senses"], ["darkvision 60 ft.", "low-light vision"])
        trace_paths = {entry["path"] for entry in evaluation["derivationTrace"]}
        self.assertTrue({
            "/canonical/defenses", "/canonical/abilityDC", "/canonical/spellDC",
            "/canonical/abilityModifiers", "/canonical/attacks", "/canonical/senses",
            "/canonical/skills", "/canonical/initiative", "/canonical/hitDice",
            "/canonical/speed", "/canonical/options", "/canonical/cmb",
            "/canonical/maneuverBonuses",
        } <= trace_paths)

    def test_griffon_cr4_covers_large_multiattack_and_combat_options(self):
        response = self.engine.execute(request("create-griffon", "draft.create", {"draft": GRIFFON_DRAFT}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]

        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        self.assertEqual(canonical["defenses"], {
            "ac": 19, "touchAC": 11, "flatFootedAC": 15,
            "fortitude": 7, "reflex": 7, "will": 3, "cmd": 21, "hp": 44,
        })
        self.assertEqual(canonical["cmb"], 10)
        self.assertEqual(canonical["skills"], {"perception": 12, "acrobatics": 9, "fly": 9})
        self.assertEqual(canonical["attacks"], [
            {
                "name": "bite", "count": 1, "attackBonus": [10], "attackBonusText": "+10",
                "averageDamage": 12, "damageDie": "d8", "damageExpression": "1d8+9",
                "naturalAttackId": "natural-attack.bite", "damageType": "B/S/P", "classification": "primary",
            },
            {
                "name": "talons", "count": 2, "attackBonus": [5], "attackBonusText": "+5",
                "averageDamage": 6, "damageDie": "d6", "damageExpression": "1d6+4",
                "naturalAttackId": "natural-attack.talons", "damageType": "S", "classification": "primary",
            },
        ])
        self.assertEqual([option["optionId"] for option in canonical["options"]], ["option.pounce", "option.rake"])

    def test_evaluation_is_deterministic_and_does_not_mutate_draft(self):
        created = self.create_worg()
        draft = created["result"]["draft"]
        before = copy.deepcopy(draft)
        first = self.engine.execute(request("eval-1", "draft.evaluate", {"draft": draft}))
        second = self.engine.execute(request("eval-2", "draft.evaluate", {"draft": draft}))
        self.assertEqual(first["result"]["evaluation"], second["result"]["evaluation"])
        self.assertEqual(draft, before)

    def test_apply_changes_requires_current_revision_and_fingerprint(self):
        created = self.create_worg()
        draft = created["result"]["draft"]
        payload = {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
            "changes": [
                {
                    "changeId": "change-speed",
                    "type": "set-selection",
                    "field": "speed",
                    "value": {"land": 60},
                }
            ],
        }
        applied = self.engine.execute(request("apply-1", "draft.applyChanges", payload))
        self.assertTrue(applied["ok"], applied)
        new_draft = applied["result"]["draft"]
        self.assertEqual(new_draft["revision"], 1)
        self.assertEqual(new_draft["selections"]["speed"], {"land": 60})
        self.assertNotEqual(new_draft["fingerprint"], draft["fingerprint"])

        stale = self.engine.execute(request("apply-stale", "draft.applyChanges", payload))
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["error"]["code"], "draft.revision-conflict")

    def test_unknown_catalog_id_is_a_boundary_error(self):
        bad = copy.deepcopy(WORG_DRAFT)
        bad["selections"]["arrayId"] = "array.unknown"
        response = self.engine.execute(request("bad-array", "draft.create", {"draft": bad}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["kind"], "catalog-data")
        self.assertEqual(response["error"]["code"], "catalog.unknown-id")

    def test_typed_but_incompatible_selection_is_stored_as_invalid(self):
        created = self.create_worg()
        draft = created["result"]["draft"]
        response = self.engine.execute(request("invalid-domain", "draft.applyChanges", {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
            "changes": [{
                "changeId": "bad-maneuver",
                "type": "set-selection",
                "field": "options",
                "value": [{"optionId": "option.improved-combat-maneuver", "parameters": {"maneuver": "teleport"}}],
            }],
        }))
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["draft"]["revision"], 1)
        self.assertEqual(response["result"]["evaluation"]["status"], "invalid")
        self.assertEqual(response["result"]["evaluation"]["issues"][0]["code"], "option.parameter-invalid")

    def test_boundary_change_is_atomic(self):
        created = self.create_worg()
        draft = created["result"]["draft"]
        response = self.engine.execute(request("bad-parameter", "draft.applyChanges", {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
            "changes": [{
                "changeId": "wrong-type",
                "type": "set-selection",
                "field": "options",
                "value": [{"optionId": "option.improved-combat-maneuver", "parameters": {"maneuver": 1}}],
            }],
        }))
        self.assertFalse(response["ok"])
        current = self.engine.execute(request("get-after-boundary", "draft.get", {"draftId": draft["draftId"]}))
        self.assertEqual(current["result"]["draft"]["revision"], draft["revision"])

    def test_computed_values_cannot_be_injected_into_selections(self):
        bad = copy.deepcopy(WORG_DRAFT)
        bad["selections"]["ac"] = 999
        response = self.engine.execute(request("computed", "draft.create", {"draft": bad}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "draft.computed-selection")

    def test_empty_draft_is_inspectable_but_incomplete(self):
        response = self.engine.execute(request("empty", "draft.create", {"draft": {}}))
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["evaluation"]["status"], "incomplete")
        self.assertIsNone(response["result"]["evaluation"]["canonical"])

    def test_create_request_is_idempotent(self):
        payload = {"draft": WORG_DRAFT}
        first = self.engine.execute(request("same-request", "draft.create", payload))
        second = self.engine.execute(request("same-request", "draft.create", payload))
        self.assertEqual(first, second)

    def test_fingerprint_is_reproducible_across_fresh_engines(self):
        first = Engine().execute(request("fresh-1", "draft.create", {"draft": WORG_DRAFT}))
        second = Engine().execute(request("fresh-2", "draft.create", {"draft": WORG_DRAFT}))
        self.assertEqual(first["result"]["draft"]["fingerprint"], second["result"]["draft"]["fingerprint"])

    def test_ordered_options_have_distinct_fingerprints_and_evaluations(self):
        base = copy.deepcopy(WORG_DRAFT)
        base["selections"].update({
            "cr": 3,
            "arrayId": "array.expert",
            "skills": {"master": ["perception", "stealth", "survival"], "good": ["climb", "swim"]},
        })
        universal = {"optionId": "option.secondary-magic", "parameters": {"spellListId": "spell-list.water"}}
        maneuver = {"optionId": "option.improved-combat-maneuver", "parameters": {"maneuver": "trip", "attackType": "bite"}}
        first_draft = copy.deepcopy(base)
        first_draft["selections"]["options"] = [universal, maneuver]
        second_draft = copy.deepcopy(base)
        second_draft["selections"]["options"] = [maneuver, universal]
        first = Engine().execute(request("ordered-1", "draft.create", {"draft": first_draft}))
        second = Engine().execute(request("ordered-2", "draft.create", {"draft": second_draft}))
        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        self.assertNotEqual(first["result"]["draft"]["fingerprint"], second["result"]["draft"]["fingerprint"])
        self.assertNotEqual(first["result"]["evaluation"]["canonical"]["options"], second["result"]["evaluation"]["canonical"]["options"])

    def test_universal_option_can_fill_an_any_slot(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"].update({
            "arrayId": "array.expert",
            "options": [{"optionId": "option.secondary-magic", "parameters": {"spellListId": "spell-list.water"}}],
            "skills": {"master": ["perception", "stealth", "survival"], "good": ["climb", "swim"]},
        })
        response = self.engine.execute(request("universal-slot", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")

    def test_step6_spell_list_resolves_cr_bands_frequencies_and_benefit(self):
        spellcaster = copy.deepcopy(WORG_DRAFT)
        spellcaster["concept"] = {"name": "Aberrant Caster", "targetCR": 9}
        spellcaster["selections"].update({
            "cr": 9,
            "arrayId": "array.spellcaster",
            "options": [
                {"optionId": "option.at-will-magic", "parameters": {}},
                {"optionId": "option.secondary-magic", "parameters": {"spellListId": "spell-list.aberrant"}},
            ],
            "skills": {"master": ["perception", "stealth"], "good": ["survival"]},
            "spellListId": "spell-list.aberrant",
            "spells": [],
        })
        response = self.engine.execute(request("aberrant-list", "draft.create", {"draft": spellcaster}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid")
        self.assertEqual(
            [(spell["name"], spell["frequency"], spell["sourceBand"], spell["spellDC"]) for spell in evaluation["canonical"]["spells"]],
            [
                ("Feeblemind", "1/day", "8–11", 22),
                ("Spell Resistance", "1/day", "8–11", 22),
                ("Beast Shape I", "3/day", "4–7", 20),
                ("Major Image", "3/day", "4–7", 20),
                ("Acid Arrow", "3/day", "4–7", 19),
                ("See Invisibility", "3/day", "4–7", 19),
                ("Cause Fear", "at will", "0–3", 18),
                ("Long Arm", "at will", "0–3", 18),
            ],
        )
        self.assertEqual(evaluation["canonical"]["spellListBenefit"], {
            "spellListId": "spell-list.aberrant",
            "name": "Aberrant",
            "text": "The monster gains the benefit of the fortification universal monster rule (Bestiary 4 294).",
        })
        trace_paths = {entry["path"] for entry in evaluation["derivationTrace"]}
        self.assertIn("/canonical/spellListBenefit", trace_paths)

    def test_step6_frequency_rules_hold_at_cr_band_boundaries(self):
        expected = {
            3: {"1/day": 2},
            4: {"1/day": 2, "3/day": 4},
            8: {"1/day": 2, "3/day": 4, "at will": 2},
            12: {"1/day": 2, "3/day": 4, "at will": 2},
            16: {"1/day": 2, "3/day": 4, "at will": 2},
        }
        for cr, frequencies in expected.items():
            with self.subTest(cr=cr):
                draft = copy.deepcopy(WORG_DRAFT)
                draft["concept"]["targetCR"] = cr
                magic_slots = 2 if cr < 12 else 3
                options = [{"optionId": "option.at-will-magic", "parameters": {}} for _ in range(magic_slots - 1)]
                options.append({"optionId": "option.secondary-magic", "parameters": {"spellListId": "spell-list.aberrant"}})
                draft["selections"].update({
                    "cr": cr,
                    "arrayId": "array.spellcaster",
                    "options": options,
                    "skills": {"master": ["perception", "stealth"], "good": ["survival"]},
                    "spellListId": "spell-list.aberrant",
                    "spells": [],
                })
                response = self.engine.execute(request(f"band-{cr}", "draft.create", {"draft": draft}))
                self.assertTrue(response["ok"], response)
                spells = response["result"]["evaluation"]["canonical"]["spells"]
                self.assertEqual({frequency: sum(spell["frequency"] == frequency for spell in spells) for frequency in frequencies}, frequencies)

    def test_step6_choice_and_scaled_numeric_benefit_is_applied(self):
        for cr, resistance in ((11, 5), (12, 10), (16, 20)):
            with self.subTest(cr=cr):
                draft = copy.deepcopy(WORG_DRAFT)
                draft["concept"]["targetCR"] = cr
                option_count = 2 if cr < 12 else 3
                draft["selections"].update({
                    "cr": cr,
                    "arrayId": "array.spellcaster",
                    "options": [{"optionId": "option.at-will-magic", "parameters": {}}] * option_count,
                    "skills": {"master": ["perception", "stealth"], "good": ["survival"]},
                    "spellListId": "spell-list.abjuration",
                    "spellListBenefitChoices": {"energyType": "cold"},
                    "spells": [],
                })
                response = self.engine.execute(request(f"abjuration-{cr}", "draft.create", {"draft": draft}))
                self.assertTrue(response["ok"], response)
                canonical = response["result"]["evaluation"]["canonical"]
                self.assertEqual(canonical["resistances"], {"cold": resistance})
                self.assertEqual(canonical["spellListBenefit"]["effects"], [
                    {"type": "resistance", "energyType": "cold", "value": resistance}
                ])
                self.assertIn("/canonical/resistances", {
                    entry["path"] for entry in response["result"]["evaluation"]["derivationTrace"]
                })

    def test_step6_missing_benefit_choice_keeps_draft_incomplete(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"].update({
            "arrayId": "array.spellcaster",
            "options": [{"optionId": "option.at-will-magic", "parameters": {}}],
            "skills": {"master": ["perception", "stealth"], "good": ["survival"]},
            "spellListId": "spell-list.abjuration",
            "spells": [],
        })
        response = self.engine.execute(request("abjuration-choice", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["evaluation"]["status"], "incomplete")
        self.assertIn("spell-list-benefit.choice-required", {
            issue["code"] for issue in response["result"]["evaluation"]["issues"]
        })

    def test_step6_resolves_class_level_and_metamagic_from_catalog(self):
        spellcaster = copy.deepcopy(WORG_DRAFT)
        spellcaster["concept"] = {"name": "Serenity Caster", "targetCR": 2}
        selections = spellcaster["selections"]
        selections.update({
            "arrayId": "array.spellcaster",
            "options": [{"optionId": "option.at-will-magic", "parameters": {}}],
            "skills": {"master": ["perception", "stealth"], "good": ["survival"]},
            "spells": [{"spellId": "spell.um.serenity", "metamagic": ["empower"]}],
            "spellLevelSource": "cleric",
        })
        response = self.engine.execute(request("spellcaster", "draft.create", {"draft": spellcaster}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid")
        self.assertEqual(evaluation["canonical"]["spells"], [{
            "spellId": "spell.um.serenity",
            "name": "Serenity",
            "spellLevelSource": "cleric",
            "baseLevel": 5,
            "metamagic": ["empower"],
            "effectiveLevel": 7,
            "spellDC": 22,
        }])


if __name__ == "__main__":
    unittest.main()
