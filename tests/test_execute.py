import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine


WORG_DRAFT = json.loads((Path(__file__).parent / "fixtures" / "worg-cr2.json").read_text())
GRIFFON_DRAFT = json.loads((Path(__file__).parent / "fixtures" / "griffon-cr4.json").read_text())
MEDUSA_DRAFT = json.loads((Path(__file__).parent / "fixtures" / "medusa-cr7.json").read_text())
GOBLIN_DRUID_DRAFT = json.loads((Path(__file__).parent / "fixtures" / "goblin-druid-cr4.json").read_text())


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
        issue = next(issue for issue in evaluation["issues"] if issue["code"] == "damage.natural-die-unsupported")
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

    def test_medusa_cr7_preserves_the_strict_pre_reality_check_result(self):
        response = self.engine.execute(request("create-medusa", "draft.create", {"draft": MEDUSA_DRAFT}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        canonical = evaluation["canonical"]

        self.assertEqual(evaluation["status"], "valid")
        self.assertEqual(canonical["defenses"], {
            "ac": 22, "touchAC": 13, "flatFootedAC": 16,
            "fortitude": 8, "reflex": 10, "will": 8, "cmd": 24, "hp": 93,
        })
        self.assertEqual(canonical["cmb"], 13)
        self.assertEqual(canonical["skills"], {"perception": 15, "intimidate": 12, "stealth": 12})
        self.assertEqual(canonical["attacks"], [
            {
                "name": "snake bite", "count": 1, "attackBonus": [12, 7], "attackBonusText": "+12/+7",
                "averageDamage": 16, "damageDie": "d4", "damageExpression": "1d4+14",
            },
            {
                "name": "longbow", "count": 1, "attackBonus": [15, 10], "attackBonusText": "+15/+10",
                "averageDamage": 22, "damageDie": "2d8", "damageExpression": "2d8+12",
            },
        ])
        self.assertEqual(canonical["options"], [
            {
                "optionId": "option.gaze",
                "parameters": {"range": "30 ft.", "effect": "turn-to-stone-permanently", "save": "fortitude-negates"},
                "effect": {"type": "gaze", "range": "30 ft.", "effect": "turn-to-stone-permanently", "save": "fortitude-negates", "dc": 15},
            },
            {
                "optionId": "option.poison",
                "parameters": {
                    "attackTypes": ["snake bite", "longbow"], "ability": "strength",
                    "advantages": ["no-onset", "round-frequency", "increase-damage", "two-consecutive-saves"],
                },
                "effect": {
                    "type": "poison", "attackTypes": ["snake bite", "longbow"], "save": "fortitude", "dc": 15,
                    "poisonType": "injury", "onset": "—", "frequency": "1/round for 6 rounds",
                    "ability": "strength", "damage": "1d3", "cure": "2 consecutive saves",
                },
            },
        ])
        self.assertEqual(canonical["senses"], ["darkvision 60 ft."])
        self.assertNotIn("2d8+6", {attack["damageExpression"] for attack in canonical["attacks"]})
        option_trace = next(entry for entry in evaluation["derivationTrace"] if entry["path"] == "/canonical/options")
        self.assertTrue(all(isinstance(ref, dict) for ref in option_trace["sourceRefs"]))
        attack_trace = next(entry for entry in evaluation["derivationTrace"] if entry["path"] == "/canonical/attacks")
        self.assertIn("2d8+12", {ref.get("entry") for ref in attack_trace["sourceRefs"]})

    def test_poison_advantage_budget_is_enforced_at_the_public_boundary(self):
        draft = copy.deepcopy(MEDUSA_DRAFT)
        draft["selections"]["options"][1]["parameters"]["advantages"].pop()
        response = self.engine.execute(request("bad-medusa-poison", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["evaluation"]["status"], "invalid")
        self.assertIn("option.poison-advantage-budget", {
            issue["code"] for issue in response["result"]["evaluation"]["issues"]
        })

    def test_fixed_creature_type_adjustments_share_the_graft_effect_path(self):
        cases = {
            "aberration": ({"fortitude": 3, "reflex": 3, "will": 3}, [4]),
            "animal": ({"fortitude": 5, "reflex": 5, "will": 1}, [4]),
            "construct": ({"fortitude": 1, "reflex": 1, "will": -1}, [6]),
            "fey": ({"fortitude": 3, "reflex": 5, "will": 3}, [2]),
            "ooze": ({"fortitude": 5, "reflex": 1, "will": -1}, [4]),
            "plant": ({"fortitude": 5, "reflex": 3, "will": 1}, [4]),
            "undead": ({"fortitude": 3, "reflex": 3, "will": 3}, [4]),
            "vermin": ({"fortitude": 5, "reflex": 3, "will": 1}, [4]),
        }
        for graft, (saves, attack_bonus) in cases.items():
            with self.subTest(graft=graft):
                draft = copy.deepcopy(WORG_DRAFT)
                draft["selections"]["creatureTypeGraftId"] = f"graft.creature-type.{graft}"
                response = Engine().execute(request(f"graft-{graft}", "draft.create", {"draft": draft}))
                self.assertTrue(response["ok"], response)
                canonical = response["result"]["evaluation"]["canonical"]
                self.assertEqual({key: canonical["defenses"][key] for key in saves}, saves)
                self.assertEqual(canonical["attacks"][0]["attackBonus"], attack_bonus)

    def test_goblin_druid_class_and_subtype_grafts_apply_through_execute(self):
        response = self.engine.execute(request("goblin-druid", "draft.create", {"draft": GOBLIN_DRUID_DRAFT}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        canonical = evaluation["canonical"]

        self.assertEqual(evaluation["status"], "valid")
        self.assertEqual(canonical["classGraftId"], "graft.class.druid")
        self.assertEqual(canonical["subtypeGraftIds"], ["graft.subtype.goblinoid"])
        self.assertEqual(canonical["defenses"], {
            "ac": 15, "touchAC": 9, "flatFootedAC": 12,
            "fortitude": 5, "reflex": 3, "will": 7, "cmd": 15, "hp": 36,
        })
        self.assertEqual(canonical["skills"], {
            "knowledge-nature": 12, "survival": 12, "acrobatics": 9,
            "stealth": 9, "perception": 9,
        })
        self.assertEqual(canonical["initiative"], 4)
        self.assertEqual(canonical["concentration"], 8)
        self.assertEqual(canonical["cmb"], 6)
        self.assertEqual(canonical["attacks"][0]["damageExpression"], "1d6+10")
        self.assertEqual(
            [(spell["name"], spell["spellLevelSource"], spell["spellDC"], spell["frequency"]) for spell in canonical["spells"]],
            [
                ("Call Lightning", "druid", 19, "1/day"),
                ("Sleet Storm", "druid", 19, "1/day"),
                ("Entangle", "druid", 17, "3/day"),
                ("Shillelagh", "druid", 17, "3/day"),
                ("Charm Animal", "druid", 17, "3/day"),
                ("Obscuring Mist", "druid", 17, "3/day"),
            ],
        )
        self.assertEqual([option["optionId"] for option in canonical["options"]], [
            "option.spontaneous-casting", "option.change-shape",
            "option.terrain-stride", "option.improved-initiative",
        ])
        self.assertEqual(canonical["options"][1]["parameters"]["forms"], [
            "Small animal", "Medium animal",
        ])
        self.assertIn("/canonical/classGraftId", {entry["path"] for entry in evaluation["derivationTrace"]})
        self.assertIn("/canonical/subtypeGraftIds", {entry["path"] for entry in evaluation["derivationTrace"]})
        skill_trace = next(entry for entry in evaluation["derivationTrace"] if entry["path"] == "/canonical/skills")
        self.assertIn("Goblinoid", {ref.get("entry") for ref in skill_trace["sourceRefs"]})
        option_trace = next(entry for entry in evaluation["derivationTrace"] if entry["path"] == "/canonical/options")
        self.assertIn("Druid CR 3", {ref.get("entry") for ref in option_trace["sourceRefs"]})
        initiative_trace = next(entry for entry in evaluation["derivationTrace"] if entry["path"] == "/canonical/initiative")
        self.assertIn("Improved Initiative", {ref.get("entry") for ref in initiative_trace["sourceRefs"]})

    def test_class_graft_enforces_its_required_array(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["selections"]["arrayId"] = "array.expert"
        response = self.engine.execute(request("bad-druid-array", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["evaluation"]["status"], "invalid")
        self.assertIn("class-graft.required-array", {
            issue["code"] for issue in response["result"]["evaluation"]["issues"]
        })

        draft["selections"]["arrayId"] = "array.spellcaster"
        draft["selections"]["cr"] = 5
        draft["concept"]["targetCR"] = 5
        response = Engine().execute(request("druid-cr5-gap", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "invalid")
        self.assertIn("class-graft.cr-unsupported", {
            issue["code"] for issue in response["result"]["evaluation"]["issues"]
        })

    def test_lycanthrope_template_enforces_prerequisites_and_consumes_a_slot(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["concept"] = {"name": "Goblin Werewolf Druid", "targetCR": 4}
        draft["selections"].update({
            "subtypeGraftIds": ["graft.subtype.goblinoid", "graft.subtype.shapechanger"],
            "templateGraftId": "graft.template.lycanthrope",
            "options": [],
        })
        response = self.engine.execute(request("lycanthrope", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid")
        self.assertEqual([option["optionId"] for option in evaluation["canonical"]["options"]], [
            "option.spontaneous-casting", "option.change-shape", "option.terrain-stride",
            "option.change-shape", "option.curse-of-lycanthropy",
        ])
        option_trace = next(entry for entry in evaluation["derivationTrace"] if entry["path"] == "/canonical/options")
        self.assertIn("Lycanthrope", {ref.get("entry") for ref in option_trace["sourceRefs"]})

        draft["selections"]["options"] = [{"optionId": "option.improved-initiative", "parameters": {}}]
        response = Engine().execute(request("lycanthrope-extra-option", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "invalid")
        self.assertIn("option-budget.mismatch", {
            issue["code"] for issue in response["result"]["evaluation"]["issues"]
        })
        draft["selections"]["options"] = []

        draft["selections"]["subtypeGraftIds"] = ["graft.subtype.goblinoid"]
        response = Engine().execute(request("lycanthrope-no-shapechanger", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "invalid")
        self.assertIn("template.subtype-required", {
            issue["code"] for issue in response["result"]["evaluation"]["issues"]
        })

        draft["selections"]["subtypeGraftIds"] = ["graft.subtype.shapechanger", "graft.subtype.shapechanger"]
        response = Engine().execute(request("duplicate-subtype", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "invalid")
        self.assertIn("subtype.duplicate", {
            issue["code"] for issue in response["result"]["evaluation"]["issues"]
        })

        draft["selections"]["subtypeGraftIds"] = ["graft.subtype.goblinoid", "graft.subtype.shapechanger"]
        draft["selections"]["cr"] = 0.5
        draft["concept"]["targetCR"] = 0.5
        response = Engine().execute(request("lycanthrope-cr-half", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "invalid")
        self.assertIn("template.cr-too-low", {
            issue["code"] for issue in response["result"]["evaluation"]["issues"]
        })

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
