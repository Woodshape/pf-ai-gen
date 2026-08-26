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


def boundary_draft(cr, array="combatant"):
    """A complete public-interface draft using source-literal slot counts."""
    ability_values = {
        0.5: [3, 2, 1], 1: [3, 2, 1], 2: [3, 2, 1], 3: [4, 2, 1],
        4: [4, 3, 1], 5: [5, 3, 2], 6: [5, 4, 2], 7: [6, 4, 2],
        8: [6, 4, 2], 10: [7, 5, 3], 11: [7, 5, 4], 12: [8, 5, 4],
        15: [10, 7, 5], 16: [11, 7, 5], 20: [13, 9, 6], 21: [14, 10, 7],
        27: [17, 13, 9], 30: [18, 15, 10],
    }[cr]
    option_count = 1 if cr < 3 else 2 if cr < 12 else 3 if cr < 20 else 4
    if array == "combatant":
        options = [{"optionId": "option.blind-fight", "parameters": {}}] * option_count
        skills = {"master": ["perception"], "good": ["survival", "climb"]}
    elif array == "expert":
        options = [{"optionId": "option.alertness", "parameters": {}}] + [
            {"optionId": "option.blind-fight", "parameters": {}}
        ] * (option_count - 1)
        skills = {
            "master": ["perception", "stealth", "survival"],
            "good": ["climb", "swim"],
        }
    else:
        options = [{"optionId": "option.combat-casting", "parameters": {}}] * (
            option_count if cr < 3 else option_count - 1
        )
        if cr >= 3:
            options.append({"optionId": "option.blind-fight", "parameters": {}})
        skills = {"master": ["perception", "stealth"], "good": ["survival"]}
    attack = {"name": "weapon", "attackProfile": "weapon.high", "damageDie": "d6"}
    if cr == 30:
        attack.update({"attackProfile": "natural.three", "profileEntry": 1})
    return {
        "concept": {"name": "Boundary", "targetCR": cr},
        "selections": {
            "cr": cr,
            "arrayId": f"array.{array}",
            "creatureTypeGraftId": "graft.creature-type.humanoid",
            "classGraftId": None,
            "subtypeGraftIds": [],
            "templateGraftId": None,
            "sizeId": "graft.size.medium",
            "abilityModifiers": dict(zip(("strength", "dexterity", "constitution"), ability_values)),
            "options": options,
            "skills": skills,
            "attacks": [attack],
            "speed": {"land": 30},
            "spells": [],
        },
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
        draft["selections"]["options"] = [
            {"optionId": "option.improved-initiative", "parameters": {}},
            {"optionId": "option.at-will-magic", "parameters": {"spellId": "spell.core.detect-magic"}},
        ]
        response = Engine().execute(request("druid-cr5", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        self.assertIn("Tiny, Small, Medium", next(
            option["sourceText"] for option in response["result"]["evaluation"]["canonical"]["options"]
            if option["optionId"] == "option.change-shape"
        ))

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

    def test_bard_spellcasting_uses_bard_spell_levels(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Bard", "targetCR": 6}
        draft["selections"].update({
            "cr": 6,
            "arrayId": "array.expert",
            "classGraftId": "graft.class.bard",
            "spellListId": "spell-list.enchantment",
            "spellListBenefitChoices": {"skillId": "skill.bluff"},
            "options": [
                {"optionId": "option.alertness", "parameters": {}},
                {"optionId": "option.blind-fight", "parameters": {}},
            ],
            "skills": {
                "master": ["perception", "stealth", "knowledge-arcana"],
                "good": ["survival", "climb"],
            },
        })
        response = self.engine.execute(request("bard-levels", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        spell = next(spell for spell in response["result"]["evaluation"]["canonical"]["spells"] if spell["spellId"] == "spell.core.hideous-laughter")
        self.assertEqual((spell["spellLevelSource"], spell["baseLevel"]), ("bard", 1))

    def test_alchemist_requires_alchemy_list_and_extract_mode(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Alchemist", "targetCR": 3}
        draft["selections"].update({
            "cr": 3,
            "arrayId": "array.expert",
            "classGraftId": "graft.class.alchemist",
            "graftOptionChoices": {"graft.class.alchemist": {
                "option.mutagen": {"package": "strength"},
                "option.energy-infusion": {"energyType": "acid"},
            }},
            "options": [{"optionId": "option.blind-fight", "parameters": {}}],
            "skills": {"master": ["perception", "knowledge-arcana"], "good": ["stealth", "survival"]},
        })
        response = self.engine.execute(request("alchemist-missing-list", "draft.create", {"draft": draft}))
        self.assertIn("class-graft.spell-list-required", {issue["code"] for issue in response["result"]["evaluation"]["issues"]})

        draft["selections"]["spellListId"] = "alchemy"
        response = Engine().execute(request("alchemist-list", "draft.create", {"draft": draft}))
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(canonical["spellcastingClassId"], "alchemist")
        self.assertEqual(canonical["spellcastingMode"], "supernatural-extracts")
        self.assertTrue(canonical["spells"])

    def test_monk_unarmed_damage_uses_highest_cr_progression(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Monk", "targetCR": 7}
        draft["selections"].update({
            "cr": 7,
            "classGraftId": "graft.class.monk",
            "graftOptionChoices": {"graft.class.monk": {
                "option.extra-attack": {"attackMode": "melee"},
                "option.stun-attack": {"attackType": "unarmed strike"},
            }},
            "options": [
                {"optionId": "option.blind-fight", "parameters": {}},
                {"optionId": "option.accuracy", "parameters": {}},
            ],
            "skills": {"master": [], "good": ["stealth", "survival"]},
            "attacks": [{"name": "unarmed strike", "attackProfile": "weapon.high"}],
        })
        response = self.engine.execute(request("monk", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(canonical["classAttackDamage"], "1d10")
        self.assertEqual(canonical["attacks"][0]["damageDie"], "d10")

        draft["selections"]["attacks"] = copy.deepcopy(WORG_DRAFT["selections"]["attacks"])
        draft["selections"]["graftOptionChoices"]["graft.class.monk"]["option.stun-attack"] = {"attackType": "bite"}
        response = Engine().execute(request("armed-monk", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(canonical["classAttackDamage"], "1d10")
        self.assertEqual(canonical["attacks"][0]["damageDie"], "d6")

    def test_fighter_uses_base_plus_highest_cr_option_slots(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Fighter", "targetCR": 3}
        draft["selections"].update({
            "cr": 3,
            "classGraftId": "graft.class.fighter",
            "options": [
                {"optionId": "option.blind-fight", "parameters": {}},
                {"optionId": "option.accuracy", "parameters": {}},
                {"optionId": "option.power-attack", "parameters": {"attackType": "bite"}},
            ],
        })
        response = self.engine.execute(request("fighter", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        self.assertEqual(len(canonical["options"]), 3)
        self.assertEqual(canonical["classGraftId"], "graft.class.fighter")
        self.assertIn("Fighter", {ability["name"] for ability in canonical["graftAbilities"]})

    def test_cleric_requires_source_defined_spontaneous_casting_choice(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["concept"]["name"] = "Goblin Cleric"
        draft["selections"]["classGraftId"] = "graft.class.cleric"
        draft["selections"]["skills"]["master"] = ["survival"]
        draft["selections"].pop("spellListId")
        response = self.engine.execute(request("cleric-choice", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "incomplete")
        self.assertIn("class-graft.choice-required", {issue["code"] for issue in response["result"]["evaluation"]["issues"]})

        draft["selections"]["classGraftChoices"] = {"spontaneousCasting": "inflict"}
        draft["selections"]["graftOptionChoices"] = {"graft.class.cleric": {
            "option.channel-energy": {"energy": "negative", "targets": "living"},
        }}
        response = Engine().execute(request("cleric-choice-set", "draft.create", {"draft": draft}))
        spontaneous = next(
            option for option in response["result"]["evaluation"]["canonical"]["options"]
            if option["optionId"] == "option.spontaneous-casting"
        )
        self.assertEqual(spontaneous["parameters"], {"spellType": "inflict"})

    def test_oracle_lame_curse_applies_cumulative_cr_effects(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["concept"]["name"] = "Lame Oracle"
        draft["selections"].update({
            "classGraftId": "graft.class.oracle",
            "classGraftChoices": {"curse": "lame", "mystery": "battle"},
            "options": [
                {"optionId": "option.improved-initiative", "parameters": {}},
                {"optionId": "option.combat-casting", "parameters": {}},
            ],
            "skills": {"master": ["knowledge-arcana", "perception"], "good": ["acrobatics"]},
        })
        draft["selections"].pop("spellListId")
        response = self.engine.execute(request("oracle-lame", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(canonical["speed"]["land"], 10)
        self.assertIn("fatigued", canonical["immunities"])
        self.assertNotIn("exhausted", canonical["immunities"])
        self.assertIn({"ability": "mystery", "value": "battle", "sourceText": self.engine.catalog.data["grafts"]["classGrafts"]["graft.class.oracle"]["ruleText"]}, canonical["classAbilities"])

    def test_summoner_requires_and_describes_its_eidolon(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["concept"]["name"] = "Goblin Summoner"
        draft["selections"].update({
            "classGraftId": "graft.class.summoner",
            "options": [
                {"optionId": "option.improved-initiative", "parameters": {}},
                {"optionId": "option.combat-casting", "parameters": {}},
            ],
            "skills": {"master": ["knowledge-arcana"], "good": ["acrobatics"]},
        })
        draft["selections"].pop("spellListId")
        response = self.engine.execute(request("summoner-no-eidolon", "draft.create", {"draft": draft}))
        self.assertIn("class-graft.choice-required", {issue["code"] for issue in response["result"]["evaluation"]["issues"]})

        draft["selections"]["classGraftChoices"] = {"eidolonName": "Ash"}
        response = Engine().execute(request("summoner-eidolon", "draft.create", {"draft": draft}))
        companion = response["result"]["evaluation"]["canonical"]["companion"]
        self.assertEqual(companion, {
            "name": "Ash", "cr": 4, "arrayId": "array.combatant",
            "creatureTypeGraftId": "graft.creature-type.outsider",
            "combinedEncounterCR": 6, "awardsIndependentXP": True,
        })

    def test_class_save_choice_is_incomplete_until_selected(self):
        draft = copy.deepcopy(GOBLIN_DRUID_DRAFT)
        draft["concept"] = {"name": "Sorcerer", "targetCR": 4}
        draft["selections"].update({
            "creatureTypeGraftId": "graft.creature-type.humanoid",
            "classGraftId": "graft.class.sorcerer",
            "subtypeGraftIds": [],
            "sizeId": "graft.size.medium",
            "options": [
                {"optionId": "option.at-will-magic", "parameters": {"spellId": "spell.core.detect-magic"}},
                {"optionId": "option.blind-fight", "parameters": {}},
            ],
            "skills": {"master": ["perception"], "good": ["acrobatics"]},
            "spellListId": None,
            "spells": [],
        })
        response = self.engine.execute(request("sorcerer-choice", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "incomplete")
        draft["selections"]["classGraftChoices"] = {"save": "reflex"}
        response = Engine().execute(request("sorcerer-choice-set", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(canonical["defenses"]["reflex"], 4)
        self.assertEqual([(spell["name"], spell["frequency"]) for spell in canonical["spells"]], [("Detect Magic", "at will")])

    def test_ranger_additional_skill_and_secondary_magic_use_source_cr(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Ranger", "targetCR": 7}
        draft["selections"].update({
            "cr": 7,
            "classGraftId": "graft.class.ranger",
            "classGraftChoices": {"favoredEnemyTargets": ["graft.creature-type.undead", "humanoid:orc"]},
            "options": [
                {"optionId": "option.blind-fight", "parameters": {}},
                {"optionId": "option.accuracy", "parameters": {}},
            ],
            "skills": {"master": ["stealth"], "good": ["survival", "climb"]},
            "spellListId": "spell-list.water",
            "spells": [],
        })
        response = self.engine.execute(request("ranger", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        self.assertEqual({spell["sourceBand"] for spell in canonical["spells"]}, {"0–3"})
        self.assertTrue(all(spell["secondaryMagic"] for spell in canonical["spells"]))
        self.assertEqual(canonical["skills"]["stealth"], 15)
        favored_enemy = next(option for option in canonical["options"] if option["optionId"] == "option.favored-enemy")
        self.assertEqual(favored_enemy["parameters"]["targets"], ["graft.creature-type.undead", "humanoid:orc"])

    def test_elf_subtype_requires_and_applies_its_master_skill_choice(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["subtypeGraftIds"] = ["graft.subtype.elf"]
        response = self.engine.execute(request("elf-choice", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "incomplete")
        draft["selections"]["subtypeGraftChoices"] = {
            "graft.subtype.elf": {"masterSkill": "skill.spellcraft"},
        }
        response = Engine().execute(request("elf-choice-set", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        self.assertEqual(response["result"]["evaluation"]["canonical"]["skills"]["spellcraft"], 10)

    def test_gnome_subtype_requires_a_cr_appropriate_illusion_spell(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"].update({
            "creatureTypeGraftId": "graft.creature-type.humanoid",
            "subtypeGraftIds": ["graft.subtype.gnome"],
            "sizeId": "graft.size.small",
        })
        response = self.engine.execute(request("gnome-no-spell", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "incomplete")
        draft["selections"]["subtypeGraftChoices"] = {
            "graft.subtype.gnome": {"spellId": "spell.core.color-spray"},
        }
        response = Engine().execute(request("gnome-spell", "draft.create", {"draft": draft}))
        spell = next(spell for spell in response["result"]["evaluation"]["canonical"]["spells"] if spell["spellId"] == "spell.core.color-spray")
        self.assertEqual((spell["frequency"], spell["role"], spell["sourceBand"]), ("1/day", "subtype-graft", "0–3"))

    def test_inevitable_uses_source_fixed_regeneration_bypass(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["subtypeGraftIds"] = ["graft.subtype.inevitable"]
        response = self.engine.execute(request("inevitable", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        self.assertEqual(response["result"]["evaluation"]["canonical"]["regeneration"], [{
            "value": 2, "bypass": ["chaotic"], "suppression": "1 round",
        }])

    def test_orc_subtype_exposes_darkvision_and_light_sensitivity(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["creatureTypeGraftId"] = "graft.creature-type.humanoid"
        draft["selections"]["subtypeGraftIds"] = ["graft.subtype.orc"]
        response = self.engine.execute(request("orc", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertIn("darkvision 60 ft.", canonical["senses"])
        self.assertIn("light sensitivity", canonical["graftTraits"])

    def test_dwarf_subtype_exposes_sense_and_conditional_save_bonus(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["creatureTypeGraftId"] = "graft.creature-type.humanoid"
        draft["selections"]["subtypeGraftIds"] = ["graft.subtype.dwarf"]
        response = self.engine.execute(request("dwarf", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertIn("darkvision 60 ft.", canonical["senses"])
        self.assertEqual(canonical["conditionalSaveBonuses"], [{
            "bonus": 2,
            "against": ["poison", "spells", "spell-like abilities"],
        }])

    def test_clockwork_subtype_applies_free_numeric_and_option_grants(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["subtypeGraftIds"] = ["graft.subtype.clockwork"]
        response = self.engine.execute(request("clockwork", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        self.assertEqual(canonical["defenses"], {
            "ac": 18, "touchAC": 14, "flatFootedAC": 12,
            "fortitude": 5, "reflex": 7, "will": 1, "cmd": 16, "hp": 22,
        })
        self.assertEqual(canonical["initiative"], 6)
        self.assertIn("option.improved-initiative", {option["optionId"] for option in canonical["options"]})
        self.assertIn("Clockwork", {ability["name"] for ability in canonical["graftAbilities"]})

    def test_ghost_at_will_choice_grants_source_mandated_telekinesis(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Ghost", "targetCR": 6}
        draft["selections"].update({
            "cr": 6,
            "creatureTypeGraftId": "graft.creature-type.undead",
            "subtypeGraftIds": ["graft.subtype.incorporeal"],
            "templateGraftId": "graft.template.ghost",
            "templateGraftChoices": {"optionIds": ["option.at-will-magic"]},
            "options": [],
            "skills": {"master": [], "good": ["survival", "climb"]},
        })
        response = self.engine.execute(request("ghost", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(canonical["movementManeuverability"], {"fly": "perfect"})
        at_will = next(option for option in canonical["options"] if option["optionId"] == "option.at-will-magic")
        self.assertEqual(at_will["parameters"], {
            "spellId": "spell.core.telekinesis", "maxSpellLevel": 5,
        })
        telekinesis = next(spell for spell in canonical["spells"] if spell["spellId"] == "spell.core.telekinesis")
        self.assertEqual(telekinesis["frequency"], "at will")
        self.assertEqual(telekinesis["role"], "option")

        draft["selections"]["graftOptionChoices"] = {"graft.template.ghost": {
            "option.at-will-magic": {"maxSpellLevel": 5},
        }}
        response = Engine().execute(request("ghost-internal", "draft.create", {"draft": draft}))
        self.assertIn("graft-option.choice-invalid", {issue["code"] for issue in response["result"]["evaluation"]["issues"]})

    def test_zombie_template_applies_staggered_and_fixed_damage_reduction(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"].update({
            "creatureTypeGraftId": "graft.creature-type.undead",
            "templateGraftId": "graft.template.zombie",
            "options": [],
            "skills": {"master": [], "good": []},
        })
        response = self.engine.execute(request("zombie", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertIn("staggered", canonical["conditions"])
        self.assertIn("can perform only a single move action or standard action each round", canonical["graftTraits"])
        damage_reduction = next(option for option in canonical["options"] if option["optionId"] == "option.damage-reduction")
        self.assertEqual(damage_reduction["parameters"], {"bypass": ["slashing"]})
        self.assertEqual(damage_reduction["value"], 5)

    def test_graveknight_locks_cone_and_links_energy_options(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Graveknight", "targetCR": 5}
        draft["selections"].update({
            "cr": 5,
            "creatureTypeGraftId": "graft.creature-type.undead",
            "templateGraftId": "graft.template.graveknight",
            "templateGraftChoices": {"energyType": "acid"},
            "options": [{"optionId": "option.blind-fight", "parameters": {}}],
            "skills": {"master": [], "good": ["stealth", "survival"]},
        })
        response = self.engine.execute(request("graveknight", "draft.create", {"draft": draft}))
        canonical = response["result"]["evaluation"]["canonical"]
        breath = next(option for option in canonical["options"] if option["optionId"] == "option.breath-weapon")
        channel = next(option for option in canonical["options"] if option["optionId"] == "option.channel-destruction")
        self.assertEqual(breath["parameters"], {"shape": "cone", "damageType": "acid"})
        self.assertEqual(channel["parameters"], {"energyType": "acid"})

        draft["selections"]["graftOptionChoices"] = {"graft.template.graveknight": {
            "option.breath-weapon": {"shape": "line", "damageType": "force"},
        }}
        response = Engine().execute(request("graveknight-invalid", "draft.create", {"draft": draft}))
        self.assertIn("graft-option.choice-invalid", {issue["code"] for issue in response["result"]["evaluation"]["issues"]})

    def test_vampire_exposes_constant_spider_climb_and_weaknesses(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Vampire", "targetCR": 5}
        draft["selections"].update({
            "cr": 5,
            "creatureTypeGraftId": "graft.creature-type.undead",
            "templateGraftId": "graft.template.vampire",
            "options": [],
            "skills": {"master": [], "good": ["stealth", "survival"]},
            "graftOptionChoices": {"graft.template.vampire": {
                "option.energy-drain": {"attackType": "bite"},
            }},
        })
        response = self.engine.execute(request("vampire", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        self.assertEqual(response["result"]["evaluation"]["canonical"]["graftTraits"], [
            "spider climb (constant)", "vampire weaknesses",
        ])

    def test_half_celestial_applies_scaled_damage_reduction(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"].update({
            "creatureTypeGraftId": "graft.creature-type.outsider",
            "templateGraftId": "graft.template.half-celestial",
            "options": [],
            "skills": {"master": ["perception", "intimidate"], "good": ["stealth", "survival"]},
            "spellListId": "spell-list.good",
        })
        response = self.engine.execute(request("half-celestial", "draft.create", {"draft": draft}))
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(canonical["damageReduction"], [{"value": 5, "bypass": ["magic"]}])
        self.assertEqual(canonical["movementManeuverability"], {"fly": "good"})

    def test_half_dragon_links_breath_and_immunity_energy_choices(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Half-Dragon", "targetCR": 3}
        draft["selections"].update({
            "cr": 3,
            "creatureTypeGraftId": "graft.creature-type.dragon",
            "templateGraftId": "graft.template.half-dragon",
            "options": [],
            "skills": {"master": ["perception", "intimidate"], "good": ["stealth", "survival"]},
        })
        response = self.engine.execute(request("half-dragon-no-choice", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "incomplete")
        draft["selections"]["templateGraftChoices"] = {"energyType": "fire", "breathShape": "cone"}
        response = Engine().execute(request("half-dragon-choice", "draft.create", {"draft": draft}))
        canonical = response["result"]["evaluation"]["canonical"]
        breath = next(option for option in canonical["options"] if option["optionId"] == "option.breath-weapon")
        immunity = next(option for option in canonical["options"] if option["optionId"] == "option.immunity")
        self.assertEqual(breath["parameters"], {"shape": "cone", "damageType": "fire"})
        self.assertEqual(breath["frequency"], "1/day")
        self.assertEqual(immunity["parameters"], {"immunities": ["sleep", "paralysis", "fire"]})

    def test_paladin_automatic_option_choices_are_required_and_applied(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Paladin", "targetCR": 7}
        draft["selections"].update({
            "cr": 7,
            "classGraftId": "graft.class.paladin",
            "spellListId": "spell-list.good",
        })
        response = self.engine.execute(request("paladin-no-choices", "draft.create", {"draft": draft}))
        self.assertIn("graft-option.choice-required", {issue["code"] for issue in response["result"]["evaluation"]["issues"]})
        draft["selections"]["graftOptionChoices"] = {"graft.class.paladin": {
            "option.channel-energy": {"energy": "positive", "targets": "undead"},
            "option.save-boost": {"save": "all"},
        }}
        response = Engine().execute(request("paladin-choices", "draft.create", {"draft": draft}))
        canonical = response["result"]["evaluation"]["canonical"]
        main = self.engine.catalog.data["arrays"]["combatant"]["mainStatistics"]["7"]
        self.assertEqual(canonical["defenses"]["fortitude"], main["fortitude"] + 3)
        self.assertEqual(canonical["defenses"]["reflex"], main["reflex"] + 1)
        self.assertEqual(canonical["defenses"]["will"], main["will"] + 4)

        draft["selections"]["graftOptionChoices"]["graft.class.paladin"].update({
            "option.smite": {"alignment": "good"},
            "option.alertness": {},
        })
        response = Engine().execute(request("paladin-locked-choice", "draft.create", {"draft": draft}))
        invalid_paths = {issue["path"] for issue in response["result"]["evaluation"]["issues"] if issue["code"] == "graft-option.choice-invalid"}
        self.assertIn("/selections/graftOptionChoices/graft.class.paladin/option.smite/alignment", invalid_paths)
        self.assertIn("/selections/graftOptionChoices/graft.class.paladin/option.alertness", invalid_paths)

    def test_skeleton_template_applies_all_automatic_traits_even_over_budget(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["concept"] = {"name": "Skeleton", "targetCR": 2}
        draft["selections"].update({
            "creatureTypeGraftId": "graft.creature-type.undead",
            "templateGraftId": "graft.template.skeleton",
            "options": [],
        })
        response = self.engine.execute(request("skeleton", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        self.assertIsNone(canonical["abilityModifiers"]["intelligence"])
        self.assertEqual(canonical["initiative"], 6)
        self.assertEqual({option["optionId"] for option in canonical["options"]}, {
            "option.damage-reduction", "option.immunity", "option.improved-initiative",
        })
        self.assertIn("cold", canonical["immunities"])
        self.assertIn({"value": 5, "bypass": ["bludgeoning"]}, canonical["damageReduction"])
        self.assertIn("DR 5/bludgeoning", canonical["damageRules"])
        self.assertIn("Skeleton", {ability["name"] for ability in canonical["graftAbilities"]})

    def test_option_prerequisites_are_enforced(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["options"] = [{"optionId": "option.snatch", "parameters": {}}]
        response = self.engine.execute(request("snatch-without-grab", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["status"], "invalid")
        self.assertIn("option.prerequisite-missing", {
            issue["code"] for issue in response["result"]["evaluation"]["issues"]
        })

    def test_array_rows_hold_at_source_cr_boundaries(self):
        # ac, Fort, Will, hp, ability DC, spell DC, selected average damage;
        # literals transcribed from Tables 5-1 through 5-6.
        expected = {
            "combatant": {
                0.5: (13, 1, 0, 11, 9, 9, 5), 1: (14, 2, 1, 16, 10, 10, 8),
                3: (17, 4, 2, 33, 12, 11, 14),
                4: (19, 5, 3, 44, 13, 12, 17), 7: (22, 8, 6, 93, 15, 12, 22),
                8: (23, 9, 7, 110, 16, 13, 26), 11: (27, 12, 10, 159, 18, 13, 32),
                12: (29, 13, 11, 176, 19, 14, 35), 15: (32, 16, 13, 242, 21, 14, 41),
                16: (33, 17, 14, 264, 22, 15, 47), 20: (38, 20, 17, 407, 25, 17, 70),
                21: (39, 21, 18, 440, 25, 17, 76), 30: (50, 29, 26, 836, 33, 25, 94),
            },
            "expert": {
                0.5: (11, 0, 3, 10, 11, 11, 4), 1: (12, 1, 4, 15, 12, 12, 7),
                3: (15, 2, 6, 30, 14, 13, 13),
                4: (17, 3, 7, 40, 15, 14, 16), 7: (20, 6, 10, 85, 17, 14, 20),
                8: (21, 7, 11, 100, 18, 15, 23), 11: (25, 10, 14, 145, 20, 15, 33),
                12: (27, 11, 15, 160, 21, 16, 36), 15: (30, 13, 18, 220, 23, 16, 40),
                16: (31, 14, 19, 240, 24, 17, 46), 20: (36, 17, 22, 370, 27, 19, 68),
                21: (37, 18, 23, 400, 27, 19, 69), 30: (48, 26, 31, 760, 35, 27, 85),
            },
            "spellcaster": {
                0.5: (9, 0, 3, 9, 11, 13, 4), 1: (10, 1, 4, 13, 12, 14, 6),
                3: (13, 2, 6, 27, 14, 15, 12),
                4: (15, 3, 7, 36, 15, 16, 14), 7: (18, 6, 10, 76, 17, 16, 18),
                8: (19, 7, 11, 90, 18, 17, 21), 11: (23, 10, 14, 130, 20, 17, 30),
                12: (25, 11, 15, 144, 21, 18, 33), 15: (28, 13, 18, 198, 23, 18, 36),
                16: (29, 14, 19, 216, 24, 19, 41), 20: (34, 17, 22, 333, 27, 21, 61),
                21: (35, 18, 23, 360, 27, 21, 63), 30: (46, 26, 31, 684, 35, 29, 77),
            },
        }
        for array, rows in expected.items():
            for cr, values in rows.items():
                with self.subTest(array=array, cr=cr):
                    response = self.engine.execute(request(f"array-{array}-{cr}", "draft.create", {"draft": boundary_draft(cr, array)}))
                    self.assertTrue(response["ok"], response)
                    evaluation = response["result"]["evaluation"]
                    self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
                    canonical = evaluation["canonical"]
                    defenses = canonical["defenses"]
                    actual = (
                        defenses["ac"], defenses["fortitude"], defenses["will"], defenses["hp"],
                        canonical["abilityDC"], canonical["spellDC"], canonical["attacks"][0]["averageDamage"],
                    )
                    self.assertEqual(actual, values)

    def test_damage_table_lower_and_upper_boundaries_use_source_literals(self):
        expected = {
            0.5: {
                "profile": "weapon.high",
                "array": "expert",
                "expressions": {
                    "d4": "1d4+2", "d6": "1d6+1", "d8": "1d8+0", "d10": "1d10",
                    "d12": "1d12", "2d6": "2d6", "3d6": "3d6",
                },
            },
            27: {
                "profile": "weapon.high",
                "array": "spellcaster",
                "expressions": {
                    "d4": "1d4+98", "d6": "1d6+97", "d8": "1d8+96", "d10": "1d10+95",
                    "d12": "1d12+94", "2d6": "2d6+93", "3d6": "3d6+91",
                },
            },
        }
        for cr, case in expected.items():
            for die, expression in case["expressions"].items():
                with self.subTest(cr=cr, die=die):
                    draft = boundary_draft(cr, case["array"])
                    draft["selections"]["attacks"] = [{
                        "name": "weapon", "attackProfile": case["profile"], "damageDie": die,
                    }]
                    response = self.engine.execute(request(f"damage-{cr}-{die}", "draft.create", {"draft": draft}))
                    self.assertEqual(response["result"]["evaluation"]["canonical"]["attacks"][0]["damageExpression"], expression)

        above_table = boundary_draft(30)
        above_table["selections"]["attacks"] = [{
            "name": "weapon", "attackProfile": "weapon.high", "damageDie": "d6",
        }]
        evaluation = self.engine.execute(request("damage-above-table", "draft.create", {"draft": above_table}))["result"]["evaluation"]
        issue = next(issue for issue in evaluation["issues"] if issue["code"] == "damage.unresolved")
        self.assertTrue(issue["sourceRefs"])

    def test_cr_outside_the_published_array_is_a_catalog_boundary_error(self):
        for cr in (0, 31):
            with self.subTest(cr=cr):
                draft = copy.deepcopy(WORG_DRAFT)
                draft["concept"]["targetCR"] = cr
                draft["selections"]["cr"] = cr
                response = self.engine.execute(request(f"unsupported-cr-{cr}", "draft.create", {"draft": draft}))
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "catalog.cr-unsupported")

    def test_size_graft_cr_boundaries_are_inclusive(self):
        cases = [
            ("fine", 2, 3, "size.cr-too-high"),
            ("diminutive", 4, 5, "size.cr-too-high"),
            ("tiny", 6, 7, "size.cr-too-high"),
            ("large", 2, 1, "size.cr-too-low"),
            ("huge", 4, 3, "size.cr-too-low"),
            ("gargantuan", 6, 5, "size.cr-too-low"),
            ("colossal", 8, 7, "size.cr-too-low"),
        ]
        for size, allowed_cr, rejected_cr, code in cases:
            with self.subTest(size=size):
                allowed = boundary_draft(allowed_cr)
                allowed["selections"]["sizeId"] = f"graft.size.{size}"
                response = self.engine.execute(request(f"size-{size}-allowed", "draft.create", {"draft": allowed}))
                self.assertNotIn(code, {issue["code"] for issue in response["result"]["evaluation"]["issues"]})

                rejected = boundary_draft(rejected_cr)
                rejected["selections"]["sizeId"] = f"graft.size.{size}"
                response = self.engine.execute(request(f"size-{size}-rejected", "draft.create", {"draft": rejected}))
                self.assertIn(code, {issue["code"] for issue in response["result"]["evaluation"]["issues"]})

        for cr in (0.5, 30):
            small = boundary_draft(cr)
            small["selections"]["sizeId"] = "graft.size.small"
            response = self.engine.execute(request(f"size-small-{cr}", "draft.create", {"draft": small}))
            self.assertFalse({"size.cr-too-low", "size.cr-too-high"} & {
                issue["code"] for issue in response["result"]["evaluation"]["issues"]
            })

        fine = boundary_draft(2)
        fine["selections"]["sizeId"] = "graft.size.fine"
        canonical = self.engine.execute(request("size-fine-cap", "draft.create", {"draft": fine}))["result"]["evaluation"]["canonical"]
        self.assertEqual(canonical["defenses"]["touchAC"], canonical["defenses"]["ac"])

    def test_direct_numeric_option_effects_share_the_catalog_effect_path(self):
        cases = {
            "option.accuracy": ("attacks", [8]),
            "option.dodge-expert": ("defenses", {"ac": 18, "touchAC": 16, "flatFootedAC": 6}),
            "option.spell-resistance": ("spellResistance", 13),
        }
        for option_id, (field, expected) in cases.items():
            with self.subTest(option_id=option_id):
                draft = copy.deepcopy(WORG_DRAFT)
                draft["selections"]["options"] = [{"optionId": option_id, "parameters": {}}]
                response = Engine().execute(request(option_id, "draft.create", {"draft": draft}))
                self.assertEqual(response["result"]["evaluation"]["status"], "valid")
                canonical = response["result"]["evaluation"]["canonical"]
                if field == "attacks":
                    self.assertEqual(canonical["attacks"][0]["attackBonus"], expected)
                    self.assertEqual(canonical["cmb"], 6)
                elif field == "defenses":
                    self.assertEqual({key: canonical["defenses"][key] for key in expected}, expected)
                else:
                    self.assertEqual(canonical[field], expected)

    def test_sheet_changing_options_are_typed_and_scaled_at_boundaries(self):
        for cr, expected in ((3, 2), (4, 5), (10, 5), (11, 10), (15, 10), (16, 15), (20, 15), (21, 20)):
            with self.subTest(option="fast-healing", cr=cr):
                draft = boundary_draft(cr)
                draft["selections"]["options"][0] = {"optionId": "option.fast-healing", "parameters": {}}
                response = self.engine.execute(request(f"fast-healing-{cr}", "draft.create", {"draft": draft}))
                self.assertEqual(response["result"]["evaluation"]["canonical"]["fastHealing"], expected)

        draft = boundary_draft(2)
        draft["selections"]["options"][0] = {"optionId": "option.flying-acumen", "parameters": {}}
        response = self.engine.execute(request("flying-acumen", "draft.create", {"draft": draft}))
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertEqual(canonical["skills"]["fly"], 10)
        option = next(option for option in canonical["options"] if option["optionId"] == "option.flying-acumen")
        self.assertEqual(option["effect"], {"type": "additionalMasterSkills", "skillIds": ["skill.fly"]})

        draft = boundary_draft(11, "spellcaster")
        draft["selections"]["options"][0] = {"optionId": "option.spell-penetration", "parameters": {}}
        response = self.engine.execute(request("spell-penetration-11", "draft.create", {"draft": draft}))
        self.assertEqual(response["result"]["evaluation"]["canonical"]["casterLevelCheckBonuses"], [
            {"value": 4, "against": "spell resistance"},
        ])

    def test_tough_options_apply_source_cr_formulas(self):
        cases = [
            ("option.damage-reduction", {"bypass": ["magic"]}, "damageReduction", [{"value": 5, "bypass": ["magic"]}]),
            ("option.energy-resistance", {"energyTypes": ["acid", "cold"], "resistanceValue": 10}, "resistances", {"acid": 10, "cold": 10}),
            ("option.fast-healing", {}, "fastHealing", 2),
        ]
        for option_id, parameters, field, expected in cases:
            with self.subTest(option_id=option_id):
                draft = copy.deepcopy(WORG_DRAFT)
                draft["selections"]["options"] = [{"optionId": option_id, "parameters": parameters}]
                response = Engine().execute(request(option_id, "draft.create", {"draft": draft}))
                self.assertEqual(response["result"]["evaluation"]["canonical"][field], expected)

        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["options"] = [{"optionId": "option.extra-hit-points", "parameters": {}}]
        response = Engine().execute(request("extra-hp", "draft.create", {"draft": draft}))
        base_hp = self.engine.catalog.data["arrays"]["combatant"]["mainStatistics"]["2"]["hp"]
        self.assertEqual(response["result"]["evaluation"]["canonical"]["defenses"]["hp"], base_hp + int(base_hp * 0.2))

    def test_catalogued_source_rule_option_is_exposed_without_hidden_derivation(self):
        draft = copy.deepcopy(WORG_DRAFT)
        draft["selections"]["options"] = [{"optionId": "option.blind-fight", "parameters": {}}]
        response = self.engine.execute(request("blind-fight", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        option = response["result"]["evaluation"]["canonical"]["options"][0]
        self.assertEqual(option["effect"]["type"], "source-rule")
        self.assertIn("concealment", option["effect"]["text"])

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
        spells = response["result"]["evaluation"]["canonical"]["spells"]
        self.assertEqual(len(spells), 2)
        self.assertTrue(all(spell["frequency"] == "1/day" and spell["secondaryMagic"] for spell in spells))

    def test_step6_spell_list_resolves_cr_bands_frequencies_and_benefit(self):
        spellcaster = copy.deepcopy(WORG_DRAFT)
        spellcaster["concept"] = {"name": "Aberrant Caster", "targetCR": 9}
        spellcaster["selections"].update({
            "cr": 9,
            "arrayId": "array.spellcaster",
            "options": [
                {"optionId": "option.combat-casting", "parameters": {}},
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
            7: {"1/day": 2, "3/day": 4},
            8: {"1/day": 2, "3/day": 4, "at will": 2},
            11: {"1/day": 2, "3/day": 4, "at will": 2},
            12: {"1/day": 2, "3/day": 4, "at will": 2},
            15: {"1/day": 2, "3/day": 4, "at will": 2},
            16: {"1/day": 2, "3/day": 4, "at will": 2},
        }
        for cr, frequencies in expected.items():
            with self.subTest(cr=cr):
                draft = copy.deepcopy(WORG_DRAFT)
                draft["concept"]["targetCR"] = cr
                magic_slots = 2 if cr < 12 else 3
                options = [{"optionId": "option.combat-casting", "parameters": {}} for _ in range(magic_slots - 1)]
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
                    "options": [{"optionId": "option.combat-casting", "parameters": {}}] * option_count,
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
            "options": [{"optionId": "option.combat-casting", "parameters": {}}],
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
            "options": [{"optionId": "option.combat-casting", "parameters": {}}],
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
