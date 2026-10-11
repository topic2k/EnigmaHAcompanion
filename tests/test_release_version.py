import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.release_version import VERSION_FILES, select_version, update_versions

ROOT = Path(__file__).resolve().parents[1]


class ReleaseVersionTests(unittest.TestCase):
    def test_semantic_bumps_reset_lower_components(self):
        for bump, expected in (("patch", "2.3.10"), ("minor", "2.4.0"), ("major", "3.0.0")):
            with self.subTest(bump=bump):
                self.assertEqual(select_version("2.3.9", [], bump), expected)

    def test_highest_tag_is_compared_numerically_across_branches_and_prereleases(self):
        tags = ["v0.1.9", "v0.1.10", "v0.2.0", "unrelated", "v5.0.0-beta", "v01.0.0"]
        self.assertEqual(select_version("0.1.6", tags), "0.2.1")
        self.assertEqual(select_version("0.3.0", tags), "0.3.1")

    def test_explicit_version_overrides_bump_and_can_publish_current_unreleased_version(self):
        self.assertEqual(select_version("0.1.6", ["v0.1.5"], "major", " 0.1.6 "), "0.1.6")
        self.assertEqual(select_version("0.1.6", [], "patch", "1.0.0"), "1.0.0")

    def test_reject_invalid_duplicate_and_lower_versions(self):
        for explicit in ("v1.0.0", "01.0.0", "1.0", "1.0.0-beta", "1.0.0\ninvalid", "0.1.5", "0.2.0"):
            with self.subTest(explicit=explicit), self.assertRaises(ValueError):
                select_version("0.1.6", ["v0.2.0"], explicit=explicit)

    def fixture(self, root):
        for name in VERSION_FILES:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def test_all_metadata_updated_without_changing_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            before = json.loads((root / "package-lock.json").read_text())
            update_versions(root, "3.0.0")
            for name in VERSION_FILES[:3]:
                self.assertEqual(json.loads((root / name).read_text())["version"], "3.0.0")
            after = json.loads((root / "package-lock.json").read_text())
            self.assertEqual(after["packages"][""]["version"], "3.0.0")
            self.assertEqual({k: v for k, v in before["packages"].items() if k},
                             {k: v for k, v in after["packages"].items() if k})
            for name in VERSION_FILES[3:]:
                self.assertIn('VERSION = "3.0.0"', (root / name).read_text())

    def test_invalid_metadata_does_not_partially_update_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / VERSION_FILES[3]).write_text("unexpected format\n")
            before = {name: (root / name).read_bytes() for name in VERSION_FILES}
            with self.assertRaises(ValueError):
                update_versions(root, "3.0.0")
            self.assertEqual(before, {name: (root / name).read_bytes() for name in VERSION_FILES})

    def test_cli_uses_git_tags_and_exports_version_without_mutating_git_refs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            update_versions(root, "0.1.6")
            (root / "tools").mkdir()
            shutil.copyfile(ROOT / "tools/release_version.py", root / "tools/release_version.py")
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.STDOUT)
            git("init")
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "Initial")
            git("tag", "v0.4.9")
            refs = git("show-ref")
            output = root / "outputs.txt"
            result = subprocess.run([os.sys.executable, "tools/release_version.py", "--bump", "minor"],
                                    cwd=root, env={**os.environ, "GITHUB_OUTPUT": str(output)},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), "version=0.5.0\n")
            self.assertEqual(git("show-ref"), refs)
            before = {name: (root / name).read_bytes() for name in VERSION_FILES}
            rejected = subprocess.run([os.sys.executable, "tools/release_version.py", "--version", "0.4.9"],
                                      cwd=root, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in VERSION_FILES})


if __name__ == "__main__":
    unittest.main()
