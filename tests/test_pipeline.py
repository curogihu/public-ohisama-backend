import copy
import json
from pathlib import Path
import tempfile
import unittest

from pipeline import ROOT, build_payloads, run


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads((ROOT / "samples/input.json").read_text(encoding="utf-8"))

    def test_duplicate_collapse_and_repeatable_output(self):
        payloads, stats = build_payloads(self.raw)
        self.assertGreater(stats["duplicates"], 0)
        self.assertEqual(stats["input"] - stats["duplicates"], stats["output"])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            run(ROOT / "samples/input.json", output)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            run(ROOT / "samples/input.json", output)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
            self.assertEqual(set(payloads), set(before))

    def test_reject_unknown_fields_real_urls_members_and_bad_dates(self):
        mutations = [
            ("url", "https://outside.invalid/item"), ("members", ["unknown"]),
            ("publishDate", "2026/02/30"), ("expiresAt", "2026-11-19T00:00:00"),
            ("privateExtra", "must not be exported"),
        ]
        for key, value in mutations:
            with self.subTest(key=key):
                raw = copy.deepcopy(self.raw)
                raw["content"][0][key] = value
                with self.assertRaises(ValueError):
                    build_payloads(raw)

    def test_conflicting_duplicates_are_rejected(self):
        self.raw["content"].append({**self.raw["content"][0], "title": "Conflicting title"})
        with self.assertRaises(ValueError):
            build_payloads(self.raw)

    def test_failed_validation_does_not_modify_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data"
            run(ROOT / "samples/input.json", output)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            self.raw["fictional"] = False
            invalid = Path(directory) / "invalid.json"
            invalid.write_text(json.dumps(self.raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                run(invalid, output)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_refuse_existing_non_demo_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            existing = output / "members.json"
            existing.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                run(ROOT / "samples/input.json", output)
            self.assertEqual(existing.read_text(encoding="utf-8"), "[]")


if __name__ == "__main__":
    unittest.main()
