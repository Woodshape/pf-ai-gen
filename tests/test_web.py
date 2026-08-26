import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from monster_builder.web import CATALOG_PATH, INDEX_PATH, make_server


class WebTransportTests(unittest.TestCase):
    def start_server(self, root: str, *, body_limit: int = 1 << 20):
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

    def test_checked_in_ui_is_a_built_typescript_app_with_structured_editors(self):
        source_root = Path(__file__).parents[1] / "monster_builder" / "web"
        html = (source_root / "index.html").read_text(encoding="utf-8")
        options = (source_root / "src" / "steps" / "options.tsx").read_text(encoding="utf-8")
        damage = (source_root / "src" / "steps" / "finish.tsx").read_text(encoding="utf-8")
        built = INDEX_PATH.read_text(encoding="utf-8")
        self.assertLess(len(html), 1000)
        self.assertIn('/src/main.tsx', html)
        self.assertIn("Add option", options)
        self.assertIn("OptionParameter", options)
        self.assertIn("Add attack", damage)
        self.assertIn("Natural attack", damage)
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

            status, _, body = self.request(server, "POST", "/api/execute", b"x" * 17)
            self.assertEqual(status, 413)
            self.assertEqual(json.loads(body)["error"]["code"], "protocol.body-too-large")


if __name__ == "__main__":
    unittest.main()
