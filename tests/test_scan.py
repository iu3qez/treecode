import json
import unittest

from tests.helpers import TempRepo, load_treemap, run_cli

PY = "x = 1\n"


class TestScan(unittest.TestCase):
    def setUp(self):
        self.tm = load_treemap()
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        for i in range(3):
            self.repo.write(f"src/api/m{i}.py", PY)

    def scan(self):
        res = run_cli(["scan", "--json"], cwd=self.repo.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    def test_scan_shape(self):
        data = self.scan()
        self.assertIn("modules", data)
        mod = next(m for m in data["modules"] if m["path"] == "src/api")
        for key in ("kind", "source_count", "depends_on", "used_by",
                    "has_manual_content", "block_present", "over_cap"):
            self.assertIn(key, mod)
        self.assertFalse(mod["block_present"])

    def test_block_and_manual_content_detected(self):
        self.repo.write(
            "src/api/CLAUDE.md",
            "human note\n\n<!-- BEGIN treecode (auto) — do not edit inside this block -->\n"
            "# api\n<!-- END treecode (auto) -->\n")
        mod = next(m for m in self.scan()["modules"] if m["path"] == "src/api")
        self.assertTrue(mod["block_present"])
        self.assertTrue(mod["has_manual_content"])

    def test_root_map_parsed(self):
        self.repo.write(
            "CLAUDE.md",
            "<!-- BEGIN treecode:map (auto) -->\n## Codebase map\n"
            "- `src/api/` — handlers → src/api/CLAUDE.md\n"
            "<!-- END treecode:map (auto) -->\n")
        rm = self.scan()["root_map"]
        self.assertTrue(rm["present"])
        self.assertEqual(rm["entries"],
                         [{"path": "src/api", "pointer": "src/api/CLAUDE.md"}])

    def test_corrupted_block_exits_2(self):
        self.repo.write("src/api/CLAUDE.md", "<!-- BEGIN treecode (auto) -->\n")
        res = run_cli(["scan", "--json"], cwd=self.repo.root)
        self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main()
