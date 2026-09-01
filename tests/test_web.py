import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from monster_builder.web import CATALOG_PATH, INDEX_PATH, NPC_CATALOG_PATH, make_server


class WebTransportTests(unittest.TestCase):
    def start_server(self, root: str, *, body_limit: int = 1 << 20, proposal_adapter=None):
        index = Path(root) / "index.html"
        index.write_text("<h1>Guided Rail</h1>", encoding="utf-8")
        assets = Path(root) / "assets"
        assets.mkdir()
        (assets / "app.js").write_text("console.log('guided rail')", encoding="utf-8")
        server = make_server(
            "127.0.0.1",
            0,
            Path(root) / "workspace",
            index_path=index,
            asset_path=assets,
            max_body_bytes=body_limit,
            proposal_adapter=proposal_adapter,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    @staticmethod
    def request(server, method: str, path: str, body: bytes | None = None):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response.status, response.getheader("Content-Type"), payload

    def test_get_serves_ui_and_checked_in_catalog(self):
        with tempfile.TemporaryDirectory() as root:
            server = self.start_server(root)
            status, content_type, body = self.request(server, "GET", "/")
            self.assertEqual(status, 200)
            self.assertTrue(content_type.startswith("text/html"))
            self.assertEqual(body, b"<h1>Guided Rail</h1>")

            status, content_type, body = self.request(server, "GET", "/assets/app.js")
            self.assertEqual(status, 200)
            self.assertTrue(content_type.startswith("text/javascript"))
            self.assertEqual(body, b"console.log('guided rail')")

            status, content_type, body = self.request(server, "GET", "/catalog.json")
            self.assertEqual(status, 200)
            self.assertTrue(content_type.startswith("application/json"))
            self.assertEqual(json.loads(body), json.loads(CATALOG_PATH.read_text(encoding="utf-8")))

            status, content_type, body = self.request(server, "GET", "/npc.json")
            self.assertEqual(status, 200)
            self.assertTrue(content_type.startswith("application/json"))
            self.assertEqual(json.loads(body), json.loads(NPC_CATALOG_PATH.read_text(encoding="utf-8")))

    def test_checked_in_ui_is_a_built_typescript_app_with_structured_editors(self):
        source_root = Path(__file__).parents[1] / "monster_builder" / "web"
        html = (source_root / "index.html").read_text(encoding="utf-8")
        options = (source_root / "src" / "steps" / "options.tsx").read_text(encoding="utf-8")
        damage = (source_root / "src" / "steps" / "finish.tsx").read_text(encoding="utf-8")
        grafts = (source_root / "src" / "steps" / "grafts.tsx").read_text(encoding="utf-8")
        npc_steps = (source_root / "src" / "steps" / "npc.tsx").read_text(encoding="utf-8")
        choices = (source_root / "src" / "choice-fields.tsx").read_text(encoding="utf-8")
        components = (source_root / "src" / "components.tsx").read_text(encoding="utf-8")
        proposal_panel = (source_root / "src" / "proposal-panel.tsx").read_text(encoding="utf-8")
        app = (source_root / "src" / "app.tsx").read_text(encoding="utf-8")
        built = INDEX_PATH.read_text(encoding="utf-8")
        self.assertLess(len(html), 1000)
        self.assertIn('/src/main.tsx', html)
        self.assertIn("Add option", options)
        self.assertIn("ChoiceFields", options)
        self.assertIn("Add attack", damage)
        self.assertIn("Natural attack", damage)
        self.assertIn("SkillPicker", damage)
        self.assertIn("automaticSelections", damage)
        self.assertIn("selectionBudgets", damage)
        self.assertIn("of ${props.required} required", damage)
        self.assertIn("Automatic", damage)
        self.assertIn("Add skill", damage)
        self.assertIn("Remove", damage)
        self.assertIn("ChoiceSection", grafts)
        self.assertIn("ChoiceGroups", grafts)
        self.assertIn("choiceRequirements", grafts)
        self.assertIn("onPreview", grafts)
        self.assertIn("useEffect", grafts)
        self.assertNotIn("JsonField", grafts)
        self.assertIn("ChoiceField", choices)
        self.assertIn("ChoiceGroups", choices)
        self.assertIn("ChoiceRequirement", choices)
        self.assertIn("pathPrefix", choices)
        self.assertNotIn("classChoiceSchemas", choices)
        self.assertNotIn("templateChoiceSchemas", choices)
        self.assertNotIn("controlledOptionParameters", choices)
        self.assertNotIn('<JsonField label="Class graft choices"', grafts)
        self.assertNotIn('<JsonField label="Automatic graft-option choices"', grafts)
        self.assertNotIn('<JsonField label="Template choices"', grafts)
        self.assertIn("Template graft choices", grafts)
        self.assertIn("SpellPicker", grafts)
        self.assertIn("Add spell", grafts)
        self.assertIn("Resolved spell loadout", grafts)
        self.assertIn("Customize loadout", grafts)
        self.assertIn("using the", grafts)
        self.assertIn("keeps its generated spells", grafts)
        self.assertIn("NpcWorkflow", npc_steps)
        self.assertIn("classProgression", npc_steps)
        self.assertIn("Canonical NPC preview", npc_steps)
        self.assertIn("loadNpcCatalog", app)
        self.assertIn('creationSystem: "npc"', app)
        self.assertNotIn('<JsonField label="Explicit spell selections"', grafts)
        self.assertNotIn('type="checkbox"', components)
        self.assertNotIn("function JsonField", components)
        self.assertIn("choiceRequirements", app)
        self.assertIn("previewChoiceRequirements", app)
        self.assertIn("selectionOverrides", app)
        self.assertIn('draft.choiceRequirements', app)
        self.assertNotIn("OptionParameter", options)
        self.assertIn("Add subtype graft", components)
        self.assertIn("Remove", components)
        self.assertIn('execute("draft.duplicate"', app)
        self.assertIn("Editable copy created", app)
        self.assertIn('execute("library.search"', app)
        self.assertIn('execute("proposal.generate"', app)
        self.assertIn('execute("proposal.accept"', app)
        self.assertIn("confirmation: { actor: \"user\", confirmed: true }", app)
        self.assertIn("Generate proposal", proposal_panel)
        self.assertIn("Generating with one Pi session", proposal_panel)
        self.assertIn("AI request failed", proposal_panel)
        self.assertIn("nonCanonicalSuggestions", proposal_panel)
        self.assertIn('type="checkbox"', proposal_panel)
        self.assertIn('role="dialog"', app)
        self.assertNotIn("window.prompt", app)
        self.assertIn('/assets/', built)
        self.assertNotIn('<script>', built)

    def test_post_forwards_engine_response_and_reuses_workspace(self):
        with tempfile.TemporaryDirectory() as root:
            server = self.start_server(root)
            request = {
                "protocolVersion": "1",
                "requestId": "create-1",
                "operation": "draft.create",
                "payload": {"draft": {}},
            }
            expected = server.engine.execute(request)
            status, content_type, body = self.request(
                server, "POST", "/api/execute", json.dumps(request).encode("utf-8")
            )
            self.assertEqual(status, 200)
            self.assertTrue(content_type.startswith("application/json"))
            self.assertEqual(json.loads(body), expected)

            draft_id = expected["result"]["draft"]["draftId"]
            get_request = {
                "protocolVersion": "1",
                "requestId": "get-1",
                "operation": "draft.get",
                "payload": {"draftId": draft_id},
            }
            status, _, body = self.request(
                server, "POST", "/api/execute", json.dumps(get_request).encode("utf-8")
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["result"]["draft"]["draftId"], draft_id)

    def test_proposal_generate_uses_the_optional_pi_adapter(self):
        class FakeAdapter:
            def __init__(self):
                self.requests = []

            def execute(self, request):
                self.requests.append(request)
                return {"ok": True, "requestId": request["requestId"], "result": {"proposal": {"proposalId": "proposal-test"}}}

        with tempfile.TemporaryDirectory() as root:
            adapter = FakeAdapter()
            server = self.start_server(root, proposal_adapter=adapter)
            request = {"protocolVersion": "1", "requestId": "ai-1", "operation": "proposal.generate", "payload": {"draftId": "draft-test", "concept": "Goblin"}}
            status, _, body = self.request(server, "POST", "/api/execute", json.dumps(request).encode("utf-8"))
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["result"]["proposal"]["proposalId"], "proposal-test")
            self.assertEqual(adapter.requests, [request])

    def test_bad_json_oversized_body_and_traversal_are_boundary_errors(self):
        with tempfile.TemporaryDirectory() as root:
            server = self.start_server(root, body_limit=16)
            status, content_type, body = self.request(server, "GET", "/../catalog/catalog.json")
            self.assertEqual(status, 404)
            self.assertTrue(content_type.startswith("application/json"))
            self.assertEqual(json.loads(body)["error"]["code"], "protocol.not-found")

            status, _, body = self.request(server, "POST", "/api/execute", b"{")
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)["error"]["code"], "protocol.invalid-json")

            status, _, body = self.request(server, "POST", "/api/execute", b"[]")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["error"]["code"], "request.invalid")

            status, _, body = self.request(server, "POST", "/api/execute", b"x" * 17)
            self.assertEqual(status, 413)
            self.assertEqual(json.loads(body)["error"]["code"], "protocol.body-too-large")


if __name__ == "__main__":
    unittest.main()
