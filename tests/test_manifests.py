import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestManifests(unittest.TestCase):
    def test_plugin_json(self):
        data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(data["name"], "treecode")
        self.assertEqual(data["version"], "0.2.1")
        for key in ("description", "author", "license"):
            self.assertIn(key, data)

    def test_marketplace_json(self):
        data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(data["name"], "iu3qez-tools")
        entry = data["plugins"][0]
        self.assertEqual(entry["name"], "treecode")
        self.assertEqual(entry["source"], "./")
        self.assertEqual(entry["version"], "0.2.1")


if __name__ == "__main__":
    unittest.main()
