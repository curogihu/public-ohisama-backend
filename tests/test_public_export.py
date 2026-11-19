import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_public import export
from verify_public import verify


class ExportTests(unittest.TestCase):
    def sample(self, root):
        root.mkdir()
        (root / "README.md").write_text("Synthetic demo", encoding="utf-8")
        (root / "public-files.json").write_text(json.dumps(["README.md", "public-files.json"]), encoding="utf-8")

    def test_unknown_file_stops_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            self.sample(root)
            (root / ".env").write_text("local configuration", encoding="utf-8")
            self.assertTrue(verify(root))
            destination = Path(directory) / "export"
            with self.assertRaises(ValueError):
                export(root, destination)
            self.assertFalse(destination.exists())

    def test_clean_export_drops_history_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            self.sample(root)
            (root / ".git").mkdir()
            (root / ".git/config").write_text("local metadata", encoding="utf-8")
            destination = Path(directory) / "export"
            export(root, destination)
            self.assertFalse((destination / ".git").exists())
            self.assertEqual(verify(destination), [])
            with self.assertRaises(ValueError):
                export(root, destination)

    def test_credential_pattern_in_document_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            self.sample(root)
            (root / "README.md").write_text("ghp_" + "a" * 30, encoding="utf-8")
            self.assertTrue(verify(root))

    def test_non_example_url_in_fixture_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            self.sample(root)
            (root / "data").mkdir()
            (root / "data/item.json").write_text(json.dumps({"url": "https://outside.invalid/item"}), encoding="utf-8")
            (root / "public-files.json").write_text(json.dumps(["README.md", "public-files.json", "data/item.json"]), encoding="utf-8")
            self.assertTrue(verify(root))
