import json
import unittest

from tests.helpers import TempRepo, run_cli


class TestCapMessage(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def cap_rows(self):
        res = run_cli(["check", "--cap-only", "--json"], cwd=self.repo.root)
        return json.loads(res.stdout)["drift"]["cap_violations"]

    def test_root_message_splits_generated_vs_human(self):
        human = "\n".join(f"vital project note {i}" for i in range(100))
        block = ("<!-- BEGIN treecode:map (auto) -->\n## Codebase map\n"
                 "- `src/` — code → src/CLAUDE.md\n"
                 "<!-- END treecode:map (auto) -->\n")
        self.repo.write("CLAUDE.md", human + "\n\n" + block)
        rows = self.cap_rows()
        self.assertEqual(rows[0]["path"], "CLAUDE.md")
        detail = rows[0]["detail"]
        self.assertIn("human", detail.lower())        # attributes the bulk to human text
        self.assertIn("generated", detail.lower())     # names the small owned block
        # the generated block is a handful of lines, the human bulk is ~100
        self.assertIn("distribute", rows[0]["suggested_action"].lower())

    def test_file_without_block_reports_all_human(self):
        self.repo.write("CLAUDE.md", "\n".join(f"line {i}" for i in range(120)))
        detail = self.cap_rows()[0]["detail"]
        self.assertIn("120", detail)
        self.assertIn("human", detail.lower())

    def test_detail_still_names_total_and_cap(self):
        self.repo.write("CLAUDE.md", "\n".join(f"l{i}" for i in range(90)))
        detail = self.cap_rows()[0]["detail"]
        self.assertIn("90", detail)
        self.assertIn("cap 80", detail)


if __name__ == "__main__":
    unittest.main()
