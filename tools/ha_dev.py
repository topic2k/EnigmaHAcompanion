"""Build and start an isolated HA Container with persistent test configuration."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "dev/ha/compose.yaml"
URL = "http://127.0.0.1:18123"
ACCESS = ROOT / ".work/ha-dev-access.json"
DOMAIN = "enigmaha_companion"
# Public fixtures for this loopback-only lab, never production credentials.
TEST_LOGIN = {"username": "enigma2ha", "password": "notsecret"}


class HAClient:
    def __init__(self):
        self.token = None
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, data=None, method=None, form=False):
        headers = {}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        body = None
        if data is not None:
            headers["Content-Type"] = ("application/x-www-form-urlencoded" if form
                                       else "application/json")
            body = (urlencode(data) if form else json.dumps(data)).encode("utf-8")
        request = Request(URL + path, body, headers, method=method)
        with self.opener.open(request, timeout=10) as response:
            return json.load(response)

    def wait(self, path, timeout=180, ready=lambda result: True, missing=None):
        deadline = time.monotonic() + timeout
        while True:
            try:
                result = self.request(path)
                if ready(result):
                    return result
            except HTTPError as error:
                if error.code == 404 and missing is not None:
                    error.close()
                    return missing
                if error.code not in (404, 502, 503):
                    raise
                error.close()
            except (URLError, TimeoutError, ConnectionError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("HA did not become ready at " + path
                                   + "; inspect python tools/ha_dev.py logs")
            time.sleep(2)


def save_access(access):
    ACCESS.parent.mkdir(parents=True, exist_ok=True)
    # Persist immediately after user creation so an interrupted run can resume.
    temporary = ACCESS.with_suffix(".tmp")
    temporary.write_text(json.dumps(access, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(ACCESS)


def login(client, access, code=None):
    if code is None and access.get("refresh_token"):
        try:
            return client.request("/auth/token", {
                "grant_type": "refresh_token", "client_id": URL + "/",
                "refresh_token": access["refresh_token"],
            }, form=True)
        except HTTPError as error:
            if error.code != 400:
                raise
            error.close()
    if code is None:
        flow = client.request("/auth/login_flow", {
            "client_id": URL + "/", "handler": ["homeassistant", None],
            "redirect_uri": URL + "/?auth_callback=1",
        })
        result = client.request("/auth/login_flow/" + flow["flow_id"], {
            "client_id": URL + "/", "username": access["username"],
            "password": access["password"],
        })
        if result.get("type") != "create_entry":
            raise RuntimeError("Lab login failed; check credentials in " + str(ACCESS)
                               + ". Existing users are never reset.")
        code = result["result"]
    return client.request("/auth/token", {
        "grant_type": "authorization_code", "client_id": URL + "/", "code": code,
    }, form=True)


def bootstrap():
    """Complete fresh/partial onboarding and configure the integration via HA APIs."""
    client = HAClient()
    # HA does not register onboarding routes on subsequent, completed starts.
    complete = [{"step": step, "done": True}
                for step in ("user", "core_config", "analytics", "integration")]
    steps = client.wait("/api/onboarding", missing=complete)
    done = {step["step"] for step in steps if step["done"]}
    access = dict(TEST_LOGIN, url=URL)
    code = None
    if "user" not in done:
        # Save the intended login before the mutation, including on a partial failure.
        save_access(access)
        result = client.request("/api/onboarding/users", {
            **TEST_LOGIN, "name": "EnigmaHA Testlabor", "language": "de",
            "client_id": URL + "/",
        })
        code = result["auth_code"]
    elif ACCESS.exists():
        access = json.loads(ACCESS.read_text(encoding="utf-8"))
        if access.get("url") != URL:
            raise RuntimeError("Saved credentials belong to another lab URL")
    tokens = login(client, access, code)
    access.update(tokens)
    client.token = access["access_token"]
    save_access(access)
    for step in ("core_config", "analytics", "integration"):
        if step not in done:
            data = {"client_id": URL + "/", "redirect_uri": URL + "/?auth_callback=1"}
            client.request("/api/onboarding/" + step, data if step == "integration" else {})
    # Config flows require HA to have finished startup, not just an open HTTP port.
    client.wait("/api/config", ready=lambda result: result["state"] == "RUNNING")
    entries = client.request("/api/config/config_entries/entry?domain=" + DOMAIN)
    if not entries:
        flow = client.request("/api/config/config_entries/flow", {
            "handler": DOMAIN, "show_advanced_options": False,
        })
        if flow.get("type") == "form" and flow.get("step_id") == "user":
            flow = client.request("/api/config/config_entries/flow/" + flow["flow_id"], {})
        if flow.get("type") != "create_entry":
            raise RuntimeError("Integration setup failed: " + str(flow.get("type")))
    path = "/api/" + DOMAIN + "/v1/config"
    menu = client.wait(path)
    # Only seed a pristine menu; reruns preserve edited or deliberately emptied menus.
    if menu["revision"] == 1 and not menu["root"]["children"]:
        fixture = json.loads((ROOT / "dev/ha/menu.json").read_text(encoding="utf-8"))
        client.request(path, dict(fixture, revision=menu["revision"]), method="PUT")
    print("HA onboarding and EnigmaHA integration ready; login: " + access["username"])
    print("Local lab credentials: " + str(ACCESS))


def run(*args, capture=False):
    return subprocess.run(args, cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "stop", "logs", "check"))
    args = parser.parse_args()
    compose = ("docker", "compose", "-f", str(COMPOSE))
    if args.command == "stop":
        run(*compose, "stop")
        return
    if args.command == "logs":
        run(*compose, "logs", "--tail", "100")
        return
    if args.command == "check":
        run(*compose, "exec", "-T", "homeassistant", "python", "-m",
            "homeassistant", "--script", "check_config", "--config", "/config")
        return
    run(sys.executable, str(ROOT / "tools/build.py"))
    stage = ROOT / ".work/ha-dev-stage"
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "dev/ha/configuration.yaml", stage / "configuration.yaml")
    component = stage / "custom_components/enigmaha_companion"
    # Replace only generated integration files. Persistent HA data lives in Docker.
    if component.exists():
        if component.is_symlink() or component.resolve() != (stage / "custom_components/enigmaha_companion").absolute():
            raise ValueError("refusing redirected staging directory")
        shutil.rmtree(component)
    shutil.copytree(ROOT / "dist/unpacked/homeassistant/custom_components/enigmaha_companion", component)
    run(*compose, "create")
    container = run(*compose, "ps", "--all", "--quiet", "homeassistant", capture=True).strip()
    if not container or "\n" in container:
        raise RuntimeError("expected one HA development container")
    # Stop before updating Python modules; do not touch .storage or the database.
    run(*compose, "stop")
    run("docker", "cp", str(stage) + "/.", container + ":/config/.enigmaha-dev-stage")
    # A one-shot container shares the volume while HA is stopped. Replace the
    # generated component completely, including files removed in development.
    install = (
        "from pathlib import Path; import shutil; "
        "root=Path('/config'); stage=root/'.enigmaha-dev-stage'; "
        "target=root/'custom_components/enigmaha_companion'; "
        "shutil.rmtree(target) if target.exists() else None; "
        "shutil.copytree(stage/'custom_components/enigmaha_companion',target); "
        "shutil.copyfile(stage/'configuration.yaml',root/'configuration.yaml'); "
        "shutil.rmtree(stage)"
    )
    run(*compose, "run", "--rm", "--no-deps", "--entrypoint", "python",
        "homeassistant", "-c", install)
    run(*compose, "start")
    bootstrap()
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    print("EnigmaHA " + version + " test instance: " + URL)


if __name__ == "__main__":
    main()
