"""Lab bootstrap recovery and preservation guarantees, without a Docker daemon."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ha_dev


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        access = patch.object(ha_dev, "ACCESS", Path(self.directory.name) / "access.json")
        access.start()
        self.addCleanup(access.stop)
        self.client = Mock()
        client = patch.object(ha_dev, "HAClient", return_value=self.client)
        client.start()
        self.addCleanup(client.stop)
        self.fixture = json.loads((ROOT / "dev/ha/menu.json").read_text(encoding="utf-8"))
        self.empty = copy.deepcopy(self.fixture)
        self.empty["root"]["children"] = []
        self.tokens = {"access_token": "test-access", "refresh_token": "test-refresh"}

    def prepare(self, done=(), menu=None, entries=None):
        self.client.wait.side_effect = [
            [{"step": step, "done": step in done}
             for step in ("user", "core_config", "analytics", "integration")],
            {"state": "RUNNING"}, menu or self.empty,
        ]

        def request(path, data=None, **kwargs):
            if path == "/api/onboarding/users":
                # Login is recoverable even if user creation's response is lost.
                self.assertEqual(json.loads(ha_dev.ACCESS.read_text())["password"],
                                 ha_dev.TEST_LOGIN["password"])
                return {"auth_code": "test-code"}
            if path == "/auth/token":
                return self.tokens
            if path.endswith("/entry?domain=enigmaha_companion"):
                return [] if entries is None else entries
            if path == "/api/config/config_entries/flow":
                return {"type": "form", "step_id": "user", "flow_id": "test-flow"}
            if path.endswith("/flow/test-flow"):
                return {"type": "create_entry"}
            return {}

        self.client.request.side_effect = request

    def paths(self):
        return [call.args[0] for call in self.client.request.call_args_list]

    def test_fresh_lab_onboards_installs_and_seeds_menu(self):
        self.prepare()
        ha_dev.bootstrap()
        self.assertEqual(json.loads(ha_dev.ACCESS.read_text())["refresh_token"], "test-refresh")
        for step in ("users", "core_config", "analytics", "integration"):
            self.assertIn("/api/onboarding/" + step, self.paths())
        self.client.request.assert_any_call("/api/enigmaha_companion/v1/config",
                                            self.fixture, method="PUT")

    def test_rerun_preserves_existing_login_integration_and_edited_menu(self):
        access = dict(ha_dev.TEST_LOGIN, url=ha_dev.URL, username="existing-owner",
                      refresh_token="saved-refresh")
        ha_dev.save_access(access)
        menu = dict(self.empty, revision=5)  # Deliberately emptied by the user.
        self.prepare(done=("user", "core_config", "analytics", "integration"),
                     menu=menu, entries=[{"domain": ha_dev.DOMAIN}])
        ha_dev.bootstrap()
        self.assertEqual(self.paths(), ["/auth/token",
                                       "/api/config/config_entries/entry?domain=" + ha_dev.DOMAIN])
        self.assertEqual(json.loads(ha_dev.ACCESS.read_text())["username"], "existing-owner")
        self.client.request.assert_any_call("/auth/token", {
            "grant_type": "refresh_token", "client_id": ha_dev.URL + "/",
            "refresh_token": "saved-refresh",
        }, form=True)

    def test_partial_onboarding_resumes_only_missing_steps(self):
        self.prepare(done=("user", "core_config"))
        # No saved token: recover by logging in with the intended test credentials.
        with patch.object(ha_dev, "login", return_value=self.tokens) as login:
            ha_dev.bootstrap()
        self.assertEqual(login.call_args.args[1]["username"], "enigma2ha")
        self.assertNotIn("/api/onboarding/users", self.paths())
        self.assertNotIn("/api/onboarding/core_config", self.paths())
        self.assertIn("/api/onboarding/analytics", self.paths())
        self.assertIn("/api/onboarding/integration", self.paths())

    def test_new_integration_does_not_overwrite_existing_menu(self):
        self.prepare(menu=self.fixture)
        ha_dev.bootstrap()
        self.assertNotIn("/api/enigmaha_companion/v1/config", self.paths())

    def test_rejects_credentials_from_another_url(self):
        ha_dev.save_access(dict(ha_dev.TEST_LOGIN, url="http://another-instance"))
        self.prepare(done=("user",))
        with self.assertRaisesRegex(RuntimeError, "another lab URL"):
            ha_dev.bootstrap()
        self.client.request.assert_not_called()

    def test_fixture_validates_against_protocol(self):
        sys.path.insert(0, str(ROOT / "protocol"))
        from enigmaha_protocol import validate_menu
        self.assertEqual(validate_menu(self.fixture), self.fixture)


class ClientTests(unittest.TestCase):
    def test_expired_refresh_token_falls_back_to_password_login(self):
        client = Mock()
        client.request.side_effect = [
            HTTPError("url", 400, "expired", {}, None), {"flow_id": "flow"},
            {"type": "create_entry", "result": "code"}, {"access_token": "access"},
        ]
        self.assertEqual(ha_dev.login(client, dict(ha_dev.TEST_LOGIN, refresh_token="expired")),
                         {"access_token": "access"})
        self.assertEqual(client.request.call_args.args[1]["grant_type"], "authorization_code")

    def test_wrong_password_fails_without_disclosing_password(self):
        client = Mock()
        client.request.side_effect = [{"flow_id": "flow"}, {"type": "form"}]
        with self.assertRaisesRegex(RuntimeError, "Existing users are never reset") as error:
            ha_dev.login(client, ha_dev.TEST_LOGIN)
        self.assertNotIn(ha_dev.TEST_LOGIN["password"], str(error.exception))

    def test_readiness_retries_connection_and_starting_state(self):
        client = ha_dev.HAClient()
        with patch.object(client, "request", side_effect=[
                URLError("starting"), {"state": "STARTING"}, {"state": "RUNNING"}]), \
                patch.object(ha_dev.time, "sleep"):
            self.assertEqual(client.wait("/api/config", ready=lambda x: x["state"] == "RUNNING"),
                             {"state": "RUNNING"})

    def test_readiness_does_not_retry_permission_errors(self):
        client = ha_dev.HAClient()
        with patch.object(client, "request", side_effect=HTTPError("url", 401, "auth", {}, None)), \
                patch.object(ha_dev.time, "sleep") as sleep:
            with self.assertRaises(HTTPError) as error:
                client.wait("/api/config")
            error.exception.close()
        sleep.assert_not_called()

    def test_completed_onboarding_has_no_status_route_after_restart(self):
        client = ha_dev.HAClient()
        complete = [{"step": "user", "done": True}]
        with patch.object(client, "request", side_effect=HTTPError("url", 404, "done", {}, None)):
            self.assertEqual(client.wait("/api/onboarding", missing=complete), complete)

    def test_readiness_timeout_is_actionable(self):
        client = ha_dev.HAClient()
        with patch.object(client, "request", side_effect=URLError("starting")):
            with self.assertRaisesRegex(RuntimeError, "ha_dev.py logs"):
                client.wait("/api/onboarding", timeout=0)


if __name__ == "__main__":
    unittest.main()
