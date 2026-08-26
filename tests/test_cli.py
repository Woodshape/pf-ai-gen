import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "goblin-druid-cr4.json").read_text())


class ValidateCLI(unittest.TestCase):
    def run_validate(self, value, suffix=".json"):
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as file:
            file.write(value if isinstance(value, str) else json.dumps(value))
            path = file.name
        self.addCleanup(Path(path).unlink, missing_ok=True)
        return subprocess.run(
            [sys.executable, "-m", "monster_builder", "validate", path],
            text=True,
            capture_output=True,
            cwd=Path(__file__).parents[1],
        )

    def test_validates_draft_or_finished_monster_json(self):
        for value in (FIXTURE, {"monster": {"concept": FIXTURE["concept"], "selections": FIXTURE["selections"]}}):
            with self.subTest(wrapper="monster" in value):
                result = self.run_validate(value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "valid")

    def test_invalid_rules_exit_two_with_issues(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"].pop("spellListId")
        result = self.run_validate(draft)
        self.assertEqual(result.returncode, 2, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "incomplete")
        self.assertIn("spells.selection-required", {issue["code"] for issue in output["issues"]})

    def test_rendered_sheet_is_rejected_as_lossy(self):
        result = self.run_validate("# Gobak CR 4\n", ".md")
        self.assertEqual(result.returncode, 4)
        self.assertIn("JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
