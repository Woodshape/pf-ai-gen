import copy
import unittest

from monster_builder import CatalogRegistry, Engine
from monster_builder.exports import render_html, render_markdown, structured_sheet
from tests.test_npc_vertical_slice import ResolvedNpcCatalog, request, valid_test_draft


class NpcExportTests(unittest.TestCase):
    def snapshot(self):
        catalog = ResolvedNpcCatalog()
        engine = Engine(catalogs=CatalogRegistry(loaders={"npc": lambda: catalog}))
        created = engine.execute(request("export-create", "draft.create", {"draft": valid_test_draft()}))
        self.assertTrue(created["ok"], created)
        draft = created["result"]["draft"]
        finalized = engine.execute(request("export-finalize", "monster.finalize", {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
        }))
        self.assertTrue(finalized["ok"], finalized)
        snapshot = finalized["result"]["monster"]
        snapshot.pop("status")
        return snapshot

    def test_npc_projection_arranges_canonical_values_without_recalculation(self):
        snapshot = self.snapshot()
        original = copy.deepcopy(snapshot)
        model = structured_sheet(snapshot)

        self.assertEqual(model["creationSystem"], "npc")
        self.assertEqual(model["header"]["label"], "Human Warrior 3 Level 3")
        fields = {field["key"]: field for field in model["statistics"]["fields"]}
        self.assertEqual(fields["abilityScores"]["value"], snapshot["result"]["abilityScores"])
        self.assertEqual(fields["bab"]["value"], snapshot["result"]["bab"])
        self.assertEqual(fields["classProgression"]["value"], snapshot["result"]["classProgression"])
        self.assertEqual(fields["feats"]["value"], snapshot["result"]["feats"])
        self.assertEqual(fields["gear"]["value"], snapshot["result"]["gear"])
        self.assertEqual(fields["languages"]["value"], snapshot["result"]["languages"])
        self.assertEqual(model["statistics"]["spells"], snapshot["result"]["spells"])
        self.assertEqual(snapshot, original)

        markdown = render_markdown(snapshot, "audit")
        html = render_html(snapshot, "audit")
        for expected in ("Ability Scores Str 13", "BAB +3", "Class Progression Warrior 3", "Gear Longsword"):
            self.assertIn(expected, markdown)
            self.assertIn(expected, html)
        self.assertIn("CREATION DECISIONS: STEPS 1–8", markdown)
        self.assertIn("CREATION DECISIONS: STEPS 1–8", html)


if __name__ == "__main__":
    unittest.main()
