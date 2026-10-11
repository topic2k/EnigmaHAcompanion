import ast
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def read_ar(data):
    assert data[:8] == b"!<arch>\n"
    result = {}
    position = 8
    while position < len(data):
        header = data[position:position + 60]
        assert header[58:] == b"`\n"
        length = int(header[48:58])
        result[header[:16].decode().strip().rstrip("/")] = data[position+60:position+60+length]
        position += 60 + length + length % 2
    assert position == len(data)
    return result


class PackageTests(unittest.TestCase):
    def test_ha_and_receiver_ship_the_same_release_identity(self):
        relative = "enigmaha_protocol/compatibility.py"
        root = DIST / "unpacked"
        ha = root / "homeassistant/custom_components/enigmaha_companion" / relative
        receiver = root / "enigma2/usr/lib/enigma2/python/Plugins/Extensions/EnigmaHACompanion" / relative
        self.assertEqual(ha.read_bytes(), receiver.read_bytes())
        constants = ast.parse(receiver.read_text(encoding="utf-8"))
        version = next(ast.literal_eval(node.value) for node in constants.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets))
        self.assertEqual(version, VERSION)
        protocol = next(ast.literal_eval(node.value) for node in constants.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "PROTOCOL_VERSION" for target in node.targets))
        self.assertIs(type(protocol), int)
        self.assertGreater(protocol, 0)

    def test_hacs_release_installs_complete_component_without_extra_directory(self):
        hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
        self.assertTrue(hacs["zip_release"])
        self.assertTrue(hacs["hide_default_branch"])
        source = ROOT / "custom_components/enigmaha_companion"
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["domain"], source.name)
        self.assertEqual(manifest["codeowners"], ["@topic2k"])
        for key in ("documentation", "issue_tracker"):
            self.assertTrue(manifest[key].startswith("https://github.com/topic2k/EnigmaHAcompanion"))
        with zipfile.ZipFile(DIST / hacs["filename"]) as hacs_zip, zipfile.ZipFile(
                DIST / ("enigmaha-companion-ha-" + VERSION + ".zip")) as manual_zip:
            prefix = "custom_components/enigmaha_companion/"
            self.assertIn("manifest.json", hacs_zip.namelist())
            self.assertIn("enigmaha_protocol/menu.py", hacs_zip.namelist())
            self.assertEqual(hacs_zip.read("brand/icon.png")[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(set(hacs_zip.namelist()), {
                name.removeprefix(prefix) for name in manual_zip.namelist()})
            for name in hacs_zip.namelist():
                self.assertFalse(name.startswith(("/", "custom_components/")))
                self.assertNotIn("..", name.split("/"))
                self.assertEqual(hacs_zip.read(name), manual_zip.read(prefix + name))

    def test_checksums_cover_only_current_release_assets(self):
        sums = (DIST / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines()
        expected = {
            "enigmaha_companion.zip",
            "enigmaha-companion-ha-" + VERSION + ".zip",
            "enigmaha-companion-enigma2-" + VERSION + ".tar.gz",
            "enigma2-plugin-extensions-enigmahacompanion_" + VERSION + "_all.ipk",
        }
        self.assertEqual({line.split("  ")[1] for line in sums}, expected)
        for line in sums:
            checksum, filename = line.split("  ")
            self.assertEqual(hashlib.sha256((DIST / filename).read_bytes()).hexdigest(), checksum)

    def test_ha_zip_complete_without_caches_or_credentials(self):
        with zipfile.ZipFile(DIST / ("enigmaha-companion-ha-" + VERSION + ".zip")) as archive:
            names = archive.namelist()
            prefix = "custom_components/enigmaha_companion/"
            for filename in ("__init__.py", "manifest.json", "config_flow.py", "api.py", "panel.js",
                             "icons.py", "update.py", "updates.py", "repairs.py", "repair_issues.py", "enigmaha_protocol/releases.py",
                             "translations/de.json", "translations/en.json", "enigmaha_protocol/menu.py", "enigmaha_protocol/icons.py"):
                self.assertIn(prefix + filename, names)
            self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
            self.assertEqual(json.loads(archive.read(prefix + "manifest.json"))["version"], VERSION)
            constants = ast.parse(archive.read(prefix + "const.py").decode("utf-8"))
            panel_version = next(ast.literal_eval(node.value) for node in constants.body
                                 if isinstance(node, ast.Assign)
                                 and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets))
            self.assertEqual(panel_version, VERSION)
            self.assertFalse(any(name.startswith(prefix + "mdi/") for name in names))

    def test_ipk_ar_control_payload_and_paths(self):
        data = (DIST / ("enigma2-plugin-extensions-enigmahacompanion_" + VERSION + "_all.ipk")).read_bytes()
        members = read_ar(data)
        self.assertEqual(members["debian-binary"], b"2.0\n")
        with tarfile.open(fileobj=io.BytesIO(members["control.tar.gz"]), mode="r:gz") as archive:
            control = archive.extractfile("control").read().decode()
            self.assertIn("Version: " + VERSION + "\n", control)
            self.assertIn("Architecture: all\n", control)
            dependencies = next(line[len("Depends: "):] for line in control.splitlines()
                                if line.startswith("Depends: ")).split(", ")
            # OpenEmbedded: urllib/http -> netclient, ssl/_ssl/tempfile -> io.
            self.assertEqual(set(dependencies), {
                "enigma2", "python3-core (>= 3.13)", "python3-json", "python3-netclient",
                "python3-io", "python3-twisted-core",
            })
            self.assertTrue({"python3-urllib", "python3-ssl"}.isdisjoint(dependencies))
        with tarfile.open(fileobj=io.BytesIO(members["data.tar.gz"]), mode="r:gz") as archive:
            names = archive.getnames()
            prefix = "usr/lib/enigma2/python/Plugins/Extensions/EnigmaHACompanion/"
            for filename in ("plugin.py", "setup.py", "keymap.xml", "settings.py", "state_icons.py",
                             "skin/__init__.py", "skin/base.py",
                             "skin/native/__init__.py", "skin/GradientFHD/__init__.py",
                             "companion/client.py", "companion/updater.py", "companion/i18n.py",
                             "enigmaha_protocol/releases.py", "enigmaha_protocol/menu.py", "enigmaha_protocol/icons.py"):
                self.assertIn(prefix + filename, names)
            self.assertTrue(all(name.startswith(prefix) and ".." not in name.split("/") for name in names))
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertEqual(members["data.tar.gz"], (DIST / ("enigmaha-companion-enigma2-" + VERSION + ".tar.gz")).read_bytes())

    def test_receiver_is_self_contained_and_python313_syntax(self):
        bundle = DIST / "unpacked/enigma2"
        for file in bundle.rglob("*.py"):
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file), feature_version=(3, 13))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("enigmaha_protocol"):
                    self.assertGreater(node.level, 0, str(file))

    def test_ipk_postinst_refreshes_same_size_same_timestamp_bytecode(self):
        members = read_ar((DIST / ("enigma2-plugin-extensions-enigmahacompanion_" + VERSION + "_all.ipk")).read_bytes())
        with tarfile.open(fileobj=io.BytesIO(members["control.tar.gz"]), mode="r:gz") as archive:
            self.assertEqual(archive.getmember("postinst").mode, 0o755)
            script = archive.extractfile("postinst").read().decode()
        self.assertTrue(script.startswith("#!/bin/sh\nset -e\n"))
        command = script.splitlines()[2].split()
        self.assertEqual(command[0], "python3")
        self.assertEqual(command[-1], "/usr/lib/enigma2/python/Plugins/Extensions/EnigmaHACompanion")
        with tempfile.TemporaryDirectory() as directory:
            module = Path(directory) / "release_identity.py"
            def write(version):
                module.write_text('VERSION = "' + version + '"\n', encoding="ascii")
                os.utime(module, (0, 0))
            def running():
                return subprocess.check_output([sys.executable, "-c",
                    "import release_identity; print(release_identity.VERSION)"], cwd=directory, text=True).strip()
            write("1.0.0")
            self.assertEqual(running(), "1.0.0")
            write("1.0.1")
            self.assertEqual(running(), "1.0.0")  # Reproduce the actual OpenATV failure.
            subprocess.run([sys.executable, *command[1:-1], directory], check=True)
            self.assertEqual(running(), "1.0.1")
            write("1.0.2")
            self.assertEqual(running(), "1.0.2")  # Checked hashes also reject later stale caches.


if __name__ == "__main__":
    unittest.main()
