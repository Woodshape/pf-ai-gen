import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine
from monster_builder.exports import render_html, render_markdown, structured_sheet


FIXTURES = Path(__file__).parent / "fixtures"


def _request(request_id, operation, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


def _snapshot(fixture_name, monster_id):
    draft_input = json.loads((FIXTURES / fixture_name).read_text())
    response = Engine().execute(_request(monster_id, "draft.create", {"draft": draft_input}))
    assert response["ok"], response
    draft = response["result"]["draft"]
    evaluation = response["result"]["evaluation"]
    return {
        "schemaVersion": "1",
        "kind": "FinishedMonster",
        "monsterId": monster_id,
        "sourceDraft": {
            "draftId": draft["draftId"],
            "revision": draft["revision"],
            "fingerprint": draft["fingerprint"],
        },
        "catalogVersion": draft["catalogVersion"],
        "mode": "strict",
        "concept": copy.deepcopy(draft["concept"]),
        "selections": copy.deepcopy(draft["selections"]),
        "result": copy.deepcopy(evaluation["effective"]),
        "fieldAnnotations": {},
        "derivationTrace": copy.deepcopy(evaluation["derivationTrace"]),
        "audit": {
            "acceptedAIRationale": "Use the source array and preserve the selected role.",
            "creationDecisions": [
                {"step": 1, "sourceId": "array.combatant", "printedPages": [198], "viewerPages": [5], "txtLines": [374, 374]},
                {"step": 9, "sourceId": "pathfinder-unchained-txt", "printedPages": [241], "viewerPages": [48], "txtLines": [4444, 4444]},
            ],
            "validationFindings": [],
            "sources": [{"sourceId": "pathfinder-unchained-txt", "printedPages": [198], "viewerPages": [5]}],
        },
    }


class ExportTests(unittest.TestCase):
    def test_worg_structured_sheet_preserves_order_and_sections(self):
        snapshot = _snapshot("worg-cr2.json", "monster-worg")
        model = structured_sheet(snapshot)

        self.assertEqual(model["header"]["label"], "Worg CR/HD 2")
        self.assertEqual(
            [section["id"] for section in model["sections"]],
            ["basics", "defenses", "attacks", "statistics"],
        )
        self.assertEqual(model["defenses"]["ac"], 16)
        self.assertEqual(model["attacks"][0]["damageExpression"], "1d6+7")
        self.assertEqual(model["attackOptions"][0]["optionId"], "option.improved-combat-maneuver")

        markdown = render_markdown(snapshot)
        positions = [markdown.index(heading) for heading in ("## DEFENSES", "## ATTACKS", "## STATISTICS")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Init +2; Perception +10 (darkvision 60 ft.; low-light vision)", markdown)
        self.assertIn("Attack Options:", markdown)
        self.assertNotIn("Spellcasting", markdown)

    def test_medusa_keeps_strict_pre_reality_check_damage(self):
        snapshot = _snapshot("medusa-cr7.json", "monster-medusa")
        markdown = render_markdown(snapshot)
        html = render_html(snapshot)

        self.assertIn("1d4+14", markdown)
        self.assertIn("2d8+12", markdown)
        self.assertIn("1d4+14", html)
        self.assertIn("2d8+12", html)
        self.assertNotIn("1d4+12", markdown)
        self.assertNotIn("2d8+10", markdown)
        self.assertIn("Gaze", markdown)
        self.assertIn("Poison", markdown)

    def test_audit_profile_appends_concept_decisions_findings_sources_and_trace(self):
        snapshot = _snapshot("worg-cr2.json", "monster-worg-audit")
        snapshot["audit"]["validationFindings"] = [{"code": "reality-check.pending", "message": "Review benchmark damage."}]

        sheet = render_markdown(snapshot, profile="sheet")
        audit = render_markdown(snapshot, profile="audit")
        self.assertNotIn("MONSTER CONCEPT", sheet)
        for heading in (
            "MONSTER CONCEPT",
            "ACCEPTED AI RATIONALE",
            "CREATION DECISIONS: STEPS 1–9",
            "VALIDATION FINDINGS",
            "SOURCES",
            "DERIVATION TRACE",
        ):
            self.assertIn(heading, audit)
        self.assertIn("reality-check.pending", audit)
        self.assertIn("sourceId", audit)
        self.assertIn("/canonical/attacks", audit)

    def test_outputs_are_deterministic_and_do_not_mutate_snapshot(self):
        snapshot = _snapshot("medusa-cr7.json", "monster-medusa-deterministic")
        original = copy.deepcopy(snapshot)

        first_model = structured_sheet(snapshot, "audit")
        second_model = structured_sheet(snapshot, "audit")
        self.assertEqual(first_model, second_model)
        self.assertEqual(render_markdown(snapshot, "audit"), render_markdown(snapshot, "audit"))
        self.assertEqual(render_html(snapshot, "audit"), render_html(snapshot, "audit"))
        self.assertEqual(snapshot, original)

    def test_html_is_standalone_semantic_print_document_and_escapes_text(self):
        snapshot = _snapshot("worg-cr2.json", "monster-<script>")
        unsafe = '<script>alert("x")</script> & "quoted"'
        snapshot["concept"]["name"] = unsafe
        snapshot["concept"]["description"] = unsafe
        snapshot["audit"]["acceptedAIRationale"] = unsafe
        snapshot["result"]["attacks"][0]["name"] = unsafe

        output = render_html(snapshot, profile="audit")
        self.assertTrue(output.startswith("<!doctype html>"))
        self.assertIn("<main", output)
        self.assertIn("<section", output)
        self.assertIn("@media print", output)
        self.assertIn("@page", output)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &quot;quoted&quot;", output)
        self.assertNotIn("<script>", output)
        self.assertNotIn(unsafe, output)

    def test_redundant_explicit_graft_options_are_rendered_once(self):
        snapshot = _snapshot("worg-cr2.json", "monster-ranger-duplicate-options")
        snapshot["result"]["options"] = [
            {
                "optionId": "option.secondary-magic",
                "parameters": {"spellListId": "spell-list.nature"},
                "graftId": "graft.class.ranger",
            },
            {
                "optionId": "option.terrain-stride",
                "parameters": {"terrain": "undergrowth"},
                "graftId": "graft.class.ranger",
            },
            {
                "optionId": "option.secondary-magic",
                "parameters": {"spellListId": "spell-list.nature"},
            },
            {
                "optionId": "option.terrain-stride",
                "parameters": {"terrain": "undergrowth"},
            },
            {"optionId": "option.extra-attack", "parameters": {"attackMode": "melee"}},
        ]

        model = structured_sheet(snapshot)
        utility = model["statistics"]["options"]
        self.assertEqual([option["optionId"] for option in utility], [
            "option.secondary-magic", "option.terrain-stride",
        ])
        self.assertEqual([option["optionId"] for option in model["attackOptions"]], ["option.extra-attack"])
        markdown = render_markdown(snapshot)
        utility_line = next(line for line in markdown.splitlines() if line.startswith("Utility Options:"))
        self.assertEqual(utility_line.count("Secondary Magic"), 1)
        self.assertEqual(utility_line.count("Terrain Stride"), 1)

        # Extra Attack is explicitly repeatable, even when one copy is grafted.
        snapshot["result"]["options"] = [
            {"optionId": "option.extra-attack", "parameters": {"attackMode": "melee"}, "graftId": "graft.class.monk"},
            {"optionId": "option.extra-attack", "parameters": {"attackMode": "melee"}},
            {"optionId": "option.extra-attack", "parameters": {"attackMode": "melee"}},
        ]
        model = structured_sheet(snapshot)
        rendered_options = [
            *model["defenses"]["options"], *model["attackOptions"], *model["statistics"]["options"],
            *(option for option in model["specialAbilities"] if option.get("optionId")),
        ]
        self.assertEqual(sum(option["optionId"] == "option.extra-attack" for option in rendered_options), 3)

    def test_modeled_defenses_counts_and_mapping_order_are_preserved(self):
        snapshot = _snapshot("worg-cr2.json", "monster-defense-details")
        snapshot["result"].update({
            "immunities": ["poison"],
            "damageReduction": {"value": 5, "bypass": ["silver"]},
            "spellResistance": 18,
            "speed": {"fly": 60, "land": 50},
        })
        snapshot["result"]["abilityModifiers"] = {"intelligence": -2, "constitution": 1, "dexterity": 2, "strength": 3}
        snapshot["result"]["attacks"][0]["count"] = 2
        snapshot["result"]["options"].extend([
            {
                "optionId": "option.extra-armor",
                "name": "Extra Armor",
                "parameters": {"armorSource": "natural"},
                "effect": {"type": "defenseBonuses", "ac": 2},
            },
            {
                "optionId": "option.damage-reduction",
                "parameters": {"bypass": ["silver"]},
                "effect": {"type": "damage-reduction", "value": 5},
            },
            {"optionId": "option.extra-attack", "parameters": {"attackMode": "melee"}},
            {"optionId": "option.accuracy", "category": "combat", "name": "Accuracy", "parameters": {}},
        ])
        reordered = copy.deepcopy(snapshot)
        reordered["result"]["speed"] = {"land": 50, "fly": 60}
        reordered["result"]["abilityModifiers"] = {"strength": 3, "dexterity": 2, "constitution": 1, "intelligence": -2}

        model = structured_sheet(snapshot)
        self.assertEqual(model["defenses"]["spellResistance"], 18)
        markdown = render_markdown(snapshot)
        self.assertEqual(markdown, render_markdown(reordered))
        self.assertIn("Fort +5", markdown)
        self.assertIn("Ref +5", markdown)
        self.assertIn("Will +1", markdown)
        self.assertIn("Immunities poison", markdown)
        self.assertIn("Damage Reduction", markdown)
        self.assertIn("SR 18", markdown)
        self.assertIn("Defense Options: Extra Armor", markdown)
        self.assertIn("Damage Reduction (bypass: silver; value: 5)", markdown)
        self.assertIn("Attack Options: Improved Combat Maneuver", markdown)
        self.assertIn("Extra Attack (attackMode: melee)", markdown)
        self.assertIn("Accuracy", markdown)
        self.assertIn("bite ×2", markdown)

    def test_spell_frequency_and_caster_metadata_are_rendered_without_derivation(self):
        snapshot = _snapshot("worg-cr2.json", "monster-spell")
        snapshot["result"]["spellcastingClassId"] = "druid"
        snapshot["result"]["spellcastingMode"] = "spell-like"
        snapshot["result"]["casterLevel"] = 5
        snapshot["result"]["spells"] = [{
            "spellId": "spell.example",
            "name": "Call <wind>",
            "frequency": "1/day",
            "role": "primary",
            "effectiveLevel": 2,
            "spellDC": 14,
            "spellLevelSource": "druid",
        }]

        markdown = render_markdown(snapshot)
        html = render_html(snapshot)
        for output in (markdown, html):
            self.assertIn("Caster Level 5", output)
            self.assertRegex(output.lower(), r"\bdruid\b")
            self.assertIn("1/day", output)
            self.assertIn("Call", output)
        self.assertIn("&lt;wind&gt;", html)

        snapshot["result"]["spells"] = []
        snapshot["result"]["spellListBenefit"] = {"name": "Silent casting"}
        self.assertIn("Spell List Benefit: name: Silent casting", render_markdown(snapshot))


if __name__ == "__main__":
    unittest.main()
