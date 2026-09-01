import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from monster_builder import Catalog, CatalogRegistry, Engine
from monster_builder.ai import PiProposalAdapter


FIXTURES = Path(__file__).parent / "fixtures"
SIMPLE_MONSTER_FIXTURES = (
    "worg-cr2.json",
    "griffon-cr4.json",
    "medusa-cr7.json",
    "goblin-druid-cr4.json",
)

# These hashes characterize the exact compact JSON byte stream produced before
# creation-system dispatch was introduced. Dictionary and trace-list order are
# intentional parts of this contract.
GOLDENS = {
    "worg-cr2.json": {
        "legacyFingerprint": "509ee3dbcf287d0177639792e5d5e7abadf85ac82604da10095bdb6457855d0f",
        "canonical": "917dacbee4198740ac739f69e29ec1f9522fdfd08abff7ef2630692617cc7db4",
        "trace": "5285ae041bccc2715e00ba0e7b819020dbdffb0f0c2b69a488c5a6efdf6a3ac1",
        "markdown": "714ebe5f1240a321f74c697cbf47e99d9db86ee6b07f828ce4d1245b90df06af",
        "html": "ab73c1d4d4f38dd168fb894f5121fec9e48195739b76189c9b6a8ef5e70ea5ec",
    },
    "griffon-cr4.json": {
        "legacyFingerprint": "3a0384f80a2977ef8a9986ac9e7f3dfedb01779c5f966432e45b94ecb4ee7a23",
        "canonical": "0909f8236250d12346daef1638d86d484e54a8c561b7be3396a6a734a90ff46c",
        "trace": "96731a70ae35ab2718d685d75ff9d4e31dd8494fbc8d78ad7c8c19841b374b0e",
        "markdown": "c12f41ad30cf9a6d74ebaa40c5ad39f71fb899f43ff2d23a9eb4d41b855d5131",
        "html": "a967eaced831a31c254ff74166931ee94205ecad3a40d3ea0230877274cdc561",
    },
    "medusa-cr7.json": {
        "legacyFingerprint": "b849afbd0196844a2d96fd3c63fbd56fee039de97a4c9ea2630ae50bf7fc405e",
        "canonical": "2c49e97071ac8cc29b9c787ec46aa17a632d134fbc541c725ce07272458d40ec",
        "trace": "41488a46ee0e6057efae0e4fb0ed83e0cce6b2e9b21bbc2f9cabc415a4c3c509",
        "markdown": "e041ff6bb7e6f469b28bdc3985ec1e4e3eaa0430ca6ce63d8d2f9f4f65ccebac",
        "html": "34f99707cb4a3f5a70aef35be535e9175e49acd0f213a3b789feb02106861ae3",
    },
    "goblin-druid-cr4.json": {
        "legacyFingerprint": "8c72c71a679b0d3bc6c50d0fc6b2bfd486d716ae7b98d07d7fb42e6a3149f26c",
        "canonical": "0b32eedcb574567e4ee462b858c5df7e5c76ad13c5d122914372bc34a34d6b4d",
        "trace": "e7d60019a5ae267558b0ae7215a6fc816b21d34f3c1ab5de881903ab11fa7457",
        "markdown": "304a6be53344dc056b578501f339f83adb673d5e9922d8b1830b3451ea5f7757",
        "html": "59ccc3d11e3d0ac8fd67e04481aa767bec2c380dc4f17f7c07c680a5f0873d1c",
    },
}


def request(request_id, operation, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def exact_json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest_json(value):
    return digest_bytes(exact_json_bytes(value))


def legacy_draft_fingerprint(raw):
    selections = copy.deepcopy(raw["selections"])
    if isinstance(selections.get("subtypeGraftIds"), list):
        selections["subtypeGraftIds"] = sorted(selections["subtypeGraftIds"])
    if isinstance(selections.get("skills"), dict):
        for rank in ("master", "good"):
            if isinstance(selections["skills"].get(rank), list):
                selections["skills"][rank] = sorted(selections["skills"][rank])
    value = {
        "schemaVersion": "1",
        "catalogVersion": Catalog.load().version,
        "concept": raw["concept"],
        "selections": selections,
    }
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class StubCatalog:
    version = "npc-catalog-test"


class StubNpcCreation:
    key = "npc"
    selection_fields = frozenset({"choice"})

    def validate_input(self, draft):
        unknown = set(draft["selections"]) - self.selection_fields
        if unknown:
            raise AssertionError(f"unexpected NPC selection: {sorted(unknown)[0]}")

    def choice_requirements(self, draft):
        return {
            "requirements": [{
                "path": "/selections/choice",
                "label": "Choice",
                "type": "string",
                "required": True,
            }],
            "automaticSelections": {},
            "selectionBudgets": {},
        }

    def evaluate(self, draft):
        canonical = {
            "level": 1,
            "defenses": {"hp": 1},
            "attacks": [],
            "skills": {},
            "spells": [],
            "abilityModifiers": {},
        }
        return {
            "status": "valid",
            "mode": "strict",
            "canonical": canonical,
            "effective": copy.deepcopy(canonical),
            "issues": [],
            "derivationTrace": [],
        }

    def creation_decisions(self, selections, trace):
        return [{"step": 1, "selections": copy.deepcopy(selections), "sourceRefs": []}]


def finished_fingerprint(snapshot):
    value = copy.deepcopy(snapshot)
    value.pop("fingerprint", None)
    value.pop("status", None)
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CreationSystemCompatibilityTests(unittest.TestCase):
    def create(self, engine, fixture_name, suffix):
        response = engine.execute(request(
            f"create-{suffix}", "draft.create", {"draft": fixture(fixture_name)}
        ))
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["evaluation"]["status"], "valid")
        return response["result"]

    def finalize(self, engine, draft, suffix):
        response = engine.execute(request(f"finalize-{suffix}", "monster.finalize", {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
        }))
        self.assertTrue(response["ok"], response)
        return response["result"]["monster"]

    def test_simple_monster_evaluations_traces_and_rendered_sheets_are_exact(self):
        for index, fixture_name in enumerate(SIMPLE_MONSTER_FIXTURES):
            with self.subTest(fixture=fixture_name):
                engine = Engine()
                created = self.create(engine, fixture_name, str(index))
                evaluation = created["evaluation"]
                expected = GOLDENS[fixture_name]

                self.assertEqual(digest_json(evaluation["canonical"]), expected["canonical"])
                self.assertEqual(digest_json(evaluation["derivationTrace"]), expected["trace"])
                monster = self.finalize(engine, created["draft"], str(index))
                for format_name in ("markdown", "html"):
                    exported = engine.execute(request(
                        f"export-{index}-{format_name}", "monster.export", {
                            "monsterId": monster["monsterId"],
                            "format": format_name,
                            "profile": "sheet",
                        },
                    ))
                    self.assertTrue(exported["ok"], exported)
                    content = exported["result"]["content"].encode("utf-8")
                    self.assertEqual(digest_bytes(content), expected[format_name])

    def test_legacy_fingerprints_for_all_current_fixtures_remain_characterized(self):
        for fixture_name in SIMPLE_MONSTER_FIXTURES:
            with self.subTest(fixture=fixture_name):
                self.assertEqual(
                    legacy_draft_fingerprint(fixture(fixture_name)),
                    GOLDENS[fixture_name]["legacyFingerprint"],
                )

    def test_current_fixtures_persist_and_reload_without_semantic_drift(self):
        for index, fixture_name in enumerate(SIMPLE_MONSTER_FIXTURES):
            with self.subTest(fixture=fixture_name), tempfile.TemporaryDirectory() as directory:
                created = self.create(Engine(workspace=directory), fixture_name, f"persist-{index}")
                loaded = Engine(workspace=directory).execute(request(
                    f"reload-{index}", "draft.get", {"draftId": created["draft"]["draftId"]}
                ))
                self.assertTrue(loaded["ok"], loaded)
                # JSONWorkspace writes sorted object keys. Reloading may change
                # dictionary insertion order, but not persisted semantic data.
                self.assertEqual(loaded["result"]["draft"], created["draft"])
                self.assertEqual(
                    loaded["result"]["evaluation"]["canonical"],
                    created["evaluation"]["canonical"],
                )
                self.assertEqual(
                    loaded["result"]["evaluation"]["derivationTrace"],
                    created["evaluation"]["derivationTrace"],
                )
                document = json.loads(next((Path(directory) / "drafts").glob("*.json")).read_text())
                self.assertEqual(document["current"]["fingerprint"], created["draft"]["fingerprint"])
                self.assertEqual(document["current"]["draft"]["fingerprint"], created["draft"]["fingerprint"])

    def test_legacy_draft_loads_without_injecting_a_default_before_fingerprint_validation(self):
        legacy = fixture("legacy-simple-monster-draft.json")
        self.assertNotIn("creationSystem", legacy)
        self.assertEqual(legacy_draft_fingerprint(legacy), legacy["fingerprint"])

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            drafts = workspace / "drafts"
            drafts.mkdir()
            stored = copy.deepcopy(legacy)
            stored.pop("status", None)
            document = {
                "schemaVersion": "1",
                "status": "active",
                "previousStatus": None,
                "monsterId": None,
                "savedAt": "2026-01-01T00:00:00.000Z",
                "current": {
                    "revision": legacy["revision"],
                    "fingerprint": legacy["fingerprint"],
                    "draft": stored,
                },
                "history": [],
            }
            path = drafts / f"{legacy['draftId']}.json"
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            before = path.read_bytes()

            response = Engine(workspace=workspace).execute(request(
                "get-legacy-draft", "draft.get", {"draftId": legacy["draftId"]}
            ))
            self.assertTrue(response["ok"], response)
            self.assertEqual(response["result"]["draft"], legacy)
            self.assertNotIn("creationSystem", response["result"]["draft"])
            legacy_finished = fixture("legacy-finished-monster.json")
            self.assertEqual(
                response["result"]["evaluation"]["canonical"],
                legacy_finished["result"],
            )
            self.assertEqual(path.read_bytes(), before)

    def test_existing_catalog_constructors_and_lazy_registry_remain_supported(self):
        calls = []
        npc_catalog = StubCatalog()
        registry = CatalogRegistry(
            Catalog.load(), loaders={"npc": lambda: calls.append("npc") or npc_catalog}
        )
        self.assertEqual(calls, [])
        self.assertIs(registry.for_system("npc"), npc_catalog)
        self.assertEqual(calls, ["npc"])
        self.assertIs(registry.for_system("npc"), npc_catalog)
        self.assertEqual(calls, ["npc"])

        engines = (
            Engine(Catalog.load()),
            Engine.from_catalog(Path(__file__).parents[1] / "catalog" / "catalog.json"),
        )
        for index, engine in enumerate(engines):
            created = self.create(engine, "worg-cr2.json", f"catalog-constructor-{index}")
            self.assertEqual(
                digest_json(created["evaluation"]["canonical"]),
                GOLDENS["worg-cr2.json"]["canonical"],
            )

    def test_registry_and_shared_lifecycle_dispatch_through_creation_system_adapter(self):
        npc_catalog = StubCatalog()
        catalogs = CatalogRegistry(Catalog.load())
        catalogs.register("npc", npc_catalog)
        engine = Engine(
            catalogs=catalogs,
            creation_systems={"npc": StubNpcCreation()},
        )
        created = engine.execute(request("create-stub-npc", "draft.create", {
            "draft": {
                "creationSystem": "npc",
                "concept": {"name": "Stub NPC"},
                "selections": {"choice": "manual"},
            },
        }))
        self.assertTrue(created["ok"], created)
        draft = created["result"]["draft"]
        self.assertEqual(draft["creationSystem"], "npc")
        self.assertEqual(draft["catalogVersion"], npc_catalog.version)
        self.assertEqual(created["result"]["evaluation"]["canonical"]["level"], 1)

        requirements = engine.execute(request(
            "stub-npc-requirements", "draft.choiceRequirements", {"draftId": draft["draftId"]}
        ))
        self.assertTrue(requirements["ok"], requirements)
        self.assertEqual(
            requirements["result"]["requirements"][0]["path"],
            "/selections/choice",
        )

        library = engine.execute(request("stub-npc-library", "library.search", {}))
        self.assertEqual(library["result"]["drafts"][0]["creationSystem"], "npc")
        finalized = engine.execute(request("finalize-stub-npc", "monster.finalize", {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
        }))
        self.assertTrue(finalized["ok"], finalized)
        monster = finalized["result"]["monster"]
        self.assertEqual(monster["creationSystem"], "npc")
        self.assertEqual(monster["audit"]["creationDecisions"][0]["selections"], {"choice": "manual"})

    def test_new_simple_monster_snapshots_are_explicit_but_legacy_snapshots_stay_implicit(self):
        engine = Engine()
        created = self.create(engine, "worg-cr2.json", "explicit-system")
        draft = created["draft"]
        self.assertEqual(draft["creationSystem"], "simple-monster")
        self.assertNotEqual(
            draft["fingerprint"],
            GOLDENS["worg-cr2.json"]["legacyFingerprint"],
        )
        attempted_change = engine.execute(request("change-system", "draft.applyChanges", {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
            "changes": [{
                "changeId": "system",
                "type": "set-selection",
                "field": "creationSystem",
                "value": "npc",
            }],
        }))
        self.assertFalse(attempted_change["ok"])
        self.assertEqual(attempted_change["error"]["code"], "change.field-invalid")

        monster = self.finalize(engine, draft, "explicit-system")
        self.assertEqual(monster["creationSystem"], "simple-monster")

        legacy = fixture("legacy-simple-monster-draft.json")
        self.assertNotIn("creationSystem", legacy)
        self.assertEqual(
            legacy["fingerprint"],
            GOLDENS["worg-cr2.json"]["legacyFingerprint"],
        )

    def test_explicit_creation_system_is_covered_by_the_persisted_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            created = self.create(
                Engine(workspace=directory), "worg-cr2.json", "system-fingerprint"
            )["draft"]
            path = Path(directory) / "drafts" / f"{created['draftId']}.json"
            document = json.loads(path.read_text())
            document["current"]["draft"]["creationSystem"] = "npc"
            path.write_text(json.dumps(document))

            loaded = Engine(workspace=directory).execute(request(
                "get-system-tamper", "draft.get", {"draftId": created["draftId"]}
            ))
            self.assertFalse(loaded["ok"])
            self.assertEqual(loaded["error"]["code"], "draft.fingerprint-invalid")

    def test_duplicate_of_legacy_draft_writes_the_explicit_default(self):
        legacy = fixture("legacy-simple-monster-draft.json")
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            drafts = workspace / "drafts"
            drafts.mkdir()
            stored = copy.deepcopy(legacy)
            stored.pop("status", None)
            document = {
                "schemaVersion": "1",
                "status": "active",
                "previousStatus": None,
                "monsterId": None,
                "savedAt": "2026-01-01T00:00:00.000Z",
                "current": {
                    "revision": legacy["revision"],
                    "fingerprint": legacy["fingerprint"],
                    "draft": stored,
                },
                "history": [],
            }
            (drafts / f"{legacy['draftId']}.json").write_text(json.dumps(document))
            duplicated = Engine(workspace=workspace).execute(request(
                "duplicate-legacy", "draft.duplicate", {
                    "draftId": legacy["draftId"],
                    "baseRevision": legacy["revision"],
                    "baseFingerprint": legacy["fingerprint"],
                },
            ))
            self.assertTrue(duplicated["ok"], duplicated)
            duplicate = duplicated["result"]["draft"]
            self.assertEqual(duplicate["creationSystem"], "simple-monster")
            self.assertNotEqual(duplicate["fingerprint"], legacy["fingerprint"])

    def test_ai_adapter_rejects_npc_before_invoking_a_runner(self):
        class NpcDraftEngine:
            def __init__(self):
                self.operations = []

            def execute(self, value):
                self.operations.append(value["operation"])
                return {
                    "ok": True,
                    "result": {"draft": {
                        "draftId": "draft-npc",
                        "revision": 0,
                        "fingerprint": "npc-fingerprint",
                        "catalogVersion": "npc-catalog",
                        "creationSystem": "npc",
                        "concept": {},
                        "selections": {},
                    }},
                }

        fake_engine = NpcDraftEngine()
        invoked = []
        adapter = PiProposalAdapter(fake_engine, runner=lambda value: invoked.append(value))
        response = adapter.execute(request("generate-npc", "proposal.generate", {
            "draftId": "draft-npc",
            "concept": "Human warrior",
        }))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "AI_CREATION_SYSTEM_UNSUPPORTED")
        self.assertEqual(fake_engine.operations, ["draft.get"])
        self.assertEqual(invoked, [])

    def test_legacy_finished_snapshot_loads_and_exports_without_default_injection(self):
        legacy = fixture("legacy-finished-monster.json")
        self.assertNotIn("creationSystem", legacy)
        self.assertEqual(finished_fingerprint(legacy), legacy["fingerprint"])

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            monsters = workspace / "monsters"
            monsters.mkdir()
            document = {
                "schemaVersion": "1",
                "status": "active",
                "savedAt": "2026-01-01T00:00:00.000Z",
                "monster": legacy,
            }
            path = monsters / f"{legacy['monsterId']}.json"
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            before = path.read_bytes()
            engine = Engine(workspace=workspace)

            loaded = engine.execute(request(
                "get-legacy-monster", "monster.get", {"monsterId": legacy["monsterId"]}
            ))
            self.assertTrue(loaded["ok"], loaded)
            loaded_snapshot = copy.deepcopy(loaded["result"]["monster"])
            self.assertEqual(loaded_snapshot.pop("status"), "active")
            self.assertEqual(loaded_snapshot, legacy)
            self.assertNotIn("creationSystem", loaded_snapshot)

            exported = engine.execute(request(
                "export-legacy-monster", "monster.export", {
                    "monsterId": legacy["monsterId"],
                    "format": "json",
                    "profile": "audit",
                },
            ))
            self.assertTrue(exported["ok"], exported)
            self.assertEqual(exported["result"]["content"], legacy)
            self.assertNotIn("creationSystem", exported["result"]["content"])
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
