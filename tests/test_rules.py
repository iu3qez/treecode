import unittest

from tests.helpers import TempRepo, run_cli

RULE = "When editing this module, run the API contract tests first.\n"


class TestRuleBlock(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def write_rule(self, path="src/api", body=RULE):
        f = self.repo.write("_r.md", body)
        return run_cli(["write-block", "--path", path, "--kind", "rule",
                        "--content-file", str(f)], cwd=self.repo.root)

    def rule_file(self, slug="src-api"):
        return self.repo.root / ".claude" / "rules" / f"{slug}.md"

    def test_creates_rule_file_with_block(self):
        res = self.write_rule()
        self.assertEqual(res.returncode, 0, res.stderr)
        text = self.rule_file().read_text()
        self.assertIn("<!-- BEGIN treecode:rule (auto)", text)
        self.assertIn("contract tests first", text)

    def test_slug_from_nested_path(self):
        res = self.write_rule(path="packages/shared")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(self.rule_file("packages-shared").is_file())

    def test_idempotent(self):
        self.write_rule()
        first = self.rule_file().read_text()
        self.write_rule()
        self.assertEqual(first, self.rule_file().read_text())

    def test_preserves_human_text(self):
        self.rule_file().parent.mkdir(parents=True)
        self.rule_file().write_text("MY MANUAL RULE\n")
        self.write_rule()
        text = self.rule_file().read_text()
        self.assertTrue(text.startswith("MY MANUAL RULE\n"))
        self.assertIn("contract tests first", text)

    def test_read_block_rule_roundtrip(self):
        self.write_rule()
        res = run_cli(["read-block", "--path", "src/api", "--kind", "rule"],
                      cwd=self.repo.root)
        self.assertEqual(res.returncode, 0)
        self.assertIn("contract tests first", res.stdout)

    def test_long_rule_no_cap_warning(self):
        res = self.write_rule(body="\n".join(f"rule line {i}" for i in range(90)))
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stderr.strip(), "")   # rules are not cap-checked


if __name__ == "__main__":
    unittest.main()
