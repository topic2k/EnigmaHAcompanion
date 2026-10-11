import json
import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "protocol"), str(ROOT / "enigma2")]

from companion.client import API_PATH, ClientError, CompanionClient, MAX_RESPONSE_BYTES
from companion.navigation import Navigator
from enigmaha_protocol import ActionError, prepare_action


class FakeHA(BaseHTTPRequestHandler):
    """Contract test server; intentionally not a Home Assistant emulator."""

    def log_message(self, *args):
        pass

    def reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def do_GET(self):
        self.server.requests.append((self.command, self.path))
        if self.headers.get("Authorization") != "Bearer test-token":
            self.reply(401, {"error": "unauthorized"})
        elif self.server.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "/redirect-target")
            self.end_headers()
        elif self.server.mode == "oversized":
            self.reply(200, {"padding": "a" * MAX_RESPONSE_BYTES})
        elif self.server.mode == "malformed":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"not json")
        elif self.path == API_PATH + "/menu":
            self.reply(200, self.server.menu)
        elif self.path == API_PATH + "/states":
            self.reply(200, self.server.snapshot)
        else:
            self.reply(404, {"error": "not_found"})

    def do_POST(self):
        self.server.requests.append((self.command, self.path))
        if self.headers.get("Authorization") != "Bearer test-token":
            self.reply(401, {"error": "unauthorized"})
            return
        if self.path != API_PATH + "/actions":
            self.reply(404, {"error": "not_found"})
            return
        command = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        states = self.server.snapshot["states"]
        try:
            plan = prepare_action(self.server.menu, command,
                                  lambda entity: states.get(entity, {}).get("state"),
                                  lambda entity: True)
        except ActionError as error:
            self.reply(error.status, {"error": error.code})
            return
        self.server.plans.append(plan)
        entity = plan["data"]["entity_id"]
        states[entity]["state"] = "on" if states[entity]["state"] == "off" else "off"
        if self.server.mode == "lost_reply":
            # The service ran, but the client cannot know it from this response.
            self.close_connection = True
        else:
            self.reply(200, {"accepted": True})


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeHA)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.server.menu = json.loads((ROOT / "protocol/menu.example.json").read_text(encoding="utf-8"))
        self.server.snapshot = json.loads((ROOT / "protocol/states.example.json").read_text(encoding="utf-8"))
        self.server.mode = "normal"
        self.server.requests = []
        self.server.plans = []
        self.url = "http://127.0.0.1:" + str(self.server.server_port)
        self.client = CompanionClient(self.url, "test-token")

    def command(self):
        menu = self.client.get_menu()
        nav = Navigator(menu)
        states = self.client.get_states(menu)
        nav.activate(states)
        return nav.activate(states)

    def test_full_menu_to_service_roundtrip(self):
        self.assertEqual(self.client.execute(self.command()), {"accepted": True})
        states = self.client.get_states(self.server.menu)
        self.assertEqual(states["light.wohnzimmer"]["state"], "on")
        self.assertEqual(self.server.plans[0]["data"], {"entity_id": "light.wohnzimmer"})

    def test_auth_error_does_not_expose_token(self):
        with self.assertRaises(ClientError) as caught:
            CompanionClient(self.url, "secret-invalid-token").get_menu()
        self.assertEqual(caught.exception.code, "unauthorized")
        self.assertNotIn("secret", str(caught.exception))

    def test_redirect_not_followed(self):
        self.server.mode = "redirect"
        with self.assertRaises(ClientError):
            self.client.get_menu()
        self.assertEqual(self.server.requests, [("GET", API_PATH + "/menu")])

    def test_large_and_malformed_responses(self):
        for mode, code in [("oversized", "response_too_large"), ("malformed", "invalid_response")]:
            self.server.mode = mode
            with self.subTest(mode=mode), self.assertRaises(ClientError) as caught:
                self.client.get_menu()
            self.assertEqual(caught.exception.code, code)

    def test_snapshot_revision_and_entity_scope(self):
        self.server.snapshot["revision"] = 2
        with self.assertRaises(ClientError) as caught:
            self.client.get_states(self.server.menu)
        self.assertEqual(caught.exception.code, "stale_menu")
        self.server.snapshot["revision"] = 1
        self.server.snapshot["states"]["sensor.private"] = {"state": "42", "unit_of_measurement": None}
        with self.assertRaises(ClientError):
            self.client.get_states(self.server.menu)

    def test_failed_reply_never_repeats_toggle(self):
        command = self.command()
        self.server.mode = "lost_reply"
        with self.assertRaises(ClientError):
            self.client.execute(command)
        self.assertEqual(len(self.server.plans), 1)
        self.assertEqual(self.server.snapshot["states"]["light.wohnzimmer"]["state"], "on")
        self.assertEqual(sum(method == "POST" for method, _ in self.server.requests), 1)

    def test_disallowed_urls_and_tokens(self):
        for url in ["file:///etc/passwd", "http://user:pass@host", "https://host/?token=x", "http://host/path"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                CompanionClient(url, "token")
        with self.assertRaises(ValueError):
            CompanionClient(self.url, "token\r\nInjected: header")

    def test_state_icons_resolve_and_reject_external_or_invalid_geometry(self):
        snapshot = self.server.snapshot
        path = "M0,0H24V24H0Z"
        snapshot["states"]["light.wohnzimmer"]["icon"] = "mdi:lightbulb-off"
        snapshot["icons"] = {"mdi:lightbulb-off": path}
        states = self.client.get_states(self.server.menu)
        self.assertEqual(states["light.wohnzimmer"]["icon"], {"name": "mdi:lightbulb-off", "path": path})
        self.assertIsNone(states["sensor.wohnzimmer_temperatur"]["icon"])
        for invalid in ("<svg onload='evil()'/>", 'M0,0\"/><image href="http://other/"/>', "M" * 16385, None):
            with self.subTest(invalid=invalid):
                self.server.snapshot = copy.deepcopy(snapshot)
                self.server.snapshot["icons"]["mdi:lightbulb-off"] = invalid
                with self.assertRaises(ClientError):
                    self.client.get_states(self.server.menu)
        for name, state in (("mdi:missing", "off"), ([], "off"), ("mdi:lightbulb-off", "unavailable")):
            self.server.snapshot = copy.deepcopy(snapshot)
            self.server.snapshot["states"]["light.wohnzimmer"].update(icon=name, state=state)
            with self.assertRaises(ClientError):
                self.client.get_states(self.server.menu)


if __name__ == "__main__":
    unittest.main()
