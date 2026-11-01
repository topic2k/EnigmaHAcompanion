"""Regression checks for removal of the integration-owned update entity."""

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist/unpacked/homeassistant/custom_components/enigmaha_companion"


class UpdateEntityRemovalTests(unittest.TestCase):
    def test_package_has_no_integration_update_platform_or_release_entity(self):
        source = (BUNDLE / "update.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        definitions = {node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                                                                            ast.AsyncFunctionDef))}
        self.assertNotIn("CompanionUpdateEntity", definitions)
        self.assertNotIn("ReleaseCoordinator", definitions)
        self.assertNotIn("async_setup_entry", definitions)

