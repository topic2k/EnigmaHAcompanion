"""Dynamic graphics from HA frontend files, including bounded caches and failures."""

import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from test_ha_plugin import ICON_GLOBALS

FrontendIconPaths = ICON_GLOBALS["FrontendIconPaths"]
PATH = "M0,0H24V24H0Z"


class FrontendIconTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.mdi = self.root / "static/mdi"
        self.mdi.mkdir(parents=True)
        self.paths = FrontendIconPaths(self.root)

    def chunk(self, name, data):
        file = self.mdi / name
        file.write_text(json.dumps(data), encoding="utf-8")
        if not (self.mdi / "iconMetadata.json").exists():
            self.metadata({"file": file.stem})
        return file

    def metadata(self, *parts):
        (self.mdi / "iconMetadata.json").write_text(json.dumps({"parts": list(parts)}), encoding="utf-8")

    def test_installed_frontend_module_supplies_asset_root(self):
        self.chunk("asset-hash.json", {"new-ha-symbol": PATH})
        paths = FrontendIconPaths()
        with patch.dict("sys.modules", {"hass_frontend": types.SimpleNamespace(where=lambda: self.root)}):
            self.assertEqual(paths.get("new-ha-symbol"), PATH)

    def test_reads_requested_chunks_and_reuses_geometry(self):
        first = self.chunk("a-hash.json", {"lamp": PATH})
        self.chunk("b-hash.json", {"window-open": "M1,1H23V23Z"})
        self.metadata({"file": "a-hash"}, {"start": "window", "file": "b-hash"})
        self.assertEqual(self.paths.get("lamp"), PATH)
        self.assertEqual(len(self.paths.chunks), 1)
        first.unlink()  # Served from the in-memory chunk cache.
        self.assertEqual(self.paths.get("lamp"), PATH)
        self.assertEqual(self.paths.get("window-open"), "M1,1H23V23Z")
        self.assertIsNone(self.paths.get("does-not-exist"))
        self.assertEqual(len(self.paths.chunks), 2)

    def test_cache_eviction_keeps_index_and_reloads_only_needed_chunk(self):
        for index in range(8):
            self.chunk(f"{index}.json", {f"icon-{index}": PATH})
        self.metadata({"file": "0"}, *({"start": f"icon-{index}", "file": str(index)} for index in range(1, 8)))
        for index in range(8):
            self.assertEqual(self.paths.get(f"icon-{index}"), PATH)
            self.assertLessEqual(len(self.paths.chunks), 4)
        self.assertEqual(self.paths.get("icon-0"), PATH)
        self.assertEqual(len(self.paths.chunks), 4)

    def test_missing_assets_recover_when_available(self):
        self.assertIsNone(self.paths.get("lamp"))
        self.chunk("new.json", {"lamp": PATH})
        self.assertEqual(self.paths.get("lamp"), PATH)

    def test_invalid_chunk_is_skipped_and_can_recover(self):
        broken = self.chunk("a-broken.json", [])
        self.chunk("b-valid.json", {"lamp": PATH})
        self.metadata({"file": "b-valid"}, {"start": "repaired", "file": "a-broken"})
        self.assertIsNone(self.paths.get("repaired"))
        self.assertEqual(self.paths.get("lamp"), PATH)
        broken.write_text(json.dumps({"repaired": PATH}), encoding="utf-8")
        self.assertEqual(self.paths.get("repaired"), PATH)

    def test_rejects_active_oversized_or_non_path_geometry(self):
        self.chunk("paths.json", {"script": '<script>alert(1)</script>',
            "xml": '<svg onload="evil()"/>', "url": 'https://example.org/icon.svg',
            "oversized": "M" + "0" * 16384, "object": {"path": PATH}, "valid": PATH})
        for name in ("script", "xml", "url", "oversized", "object", "../../outside"):
            self.assertIsNone(self.paths.get(name))
        self.assertEqual(self.paths.get("valid"), PATH)

    def test_oversized_json_chunk_does_not_hide_valid_chunk(self):
        (self.mdi / "a-large.json").write_bytes(b" " * (1024 * 1024 + 1))
        self.chunk("b-valid.json", {"window": PATH})
        self.metadata({"file": "a-large"}, {"start": "window", "file": "b-valid"})
        self.assertIsNone(self.paths.get("lamp"))
        self.assertEqual(self.paths.get("window"), PATH)

    def test_metadata_cannot_select_paths_outside_mdi_directory(self):
        for filename in ("../outside", "/absolute", "https://example.org/icon", "chunk.json"):
            with self.subTest(filename=filename):
                self.metadata({"file": filename})
                self.assertIsNone(FrontendIconPaths(self.root).get("lamp"))

    def test_rejects_invalid_or_unsorted_metadata_and_retries(self):
        self.chunk("paths.json", {"lamp": PATH})
        for parts in ([], [{"file": "paths", "start": "lamp"}],
                      [{"file": "paths"}, {"file": "paths", "start": "z"}, {"file": "paths", "start": "a"}],
                      [{"file": "paths"}, {"file": "paths", "start": None}]):
            with self.subTest(parts=parts):
                self.metadata(*parts)
                self.assertIsNone(self.paths.get("lamp"))
        self.metadata({"file": "paths"})
        self.assertEqual(self.paths.get("lamp"), PATH)


if __name__ == "__main__":
    unittest.main()
