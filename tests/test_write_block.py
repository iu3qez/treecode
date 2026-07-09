import unittest

from tests.helpers import TempRepo, run_cli

BODY = "# api — HTTP handlers\n\nResponsibility: routing only\n"


class TestWriteBlock(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        (self.repo.root / "src" / "api").mkdir(parents=True)

    def write_block(self, path="src/api", kind="module", body=BODY):
        f = self.repo.write("_body.md", body)
        return run_cli(["write-block", "--path", path, "--kind", kind,
                        "--content-file", str(f)], cwd=self.repo.root)

    def test_creates_file_with_block(self):
        res = self.write_block()
        self.assertEqual(res.returncode, 0, res.stderr)
        text = (self.repo.root / "src/api/CLAUDE.md").read_text()
        self.assertIn("<!-- BEGIN treecode (auto)", text)
        self.assertIn("Responsibility: routing only", text)

    def test_idempotent_rerun_zero_diff(self):
        self.write_block()
        first = (self.repo.root / "src/api/CLAUDE.md").read_text()
        self.write_block()
        self.assertEqual(first, (self.repo.root / "src/api/CLAUDE.md").read_text())

    def test_preserves_human_text(self):
        self.repo.write("src/api/CLAUDE.md", "MY NOTES — do not lose\n")
        self.write_block()
        text = (self.repo.root / "src/api/CLAUDE.md").read_text()
        self.assertTrue(text.startswith("MY NOTES — do not lose\n"))

    def test_read_block_roundtrip(self):
        self.write_block()
        res = run_cli(["read-block", "--path", "src/api"], cwd=self.repo.root)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Responsibility: routing only", res.stdout)

    def test_corrupted_block_refused(self):
        self.repo.write("src/api/CLAUDE.md",
                        "<!-- BEGIN treecode (auto) -->\nno end marker\n")
        res = self.write_block()
        self.assertEqual(res.returncode, 2)
        self.assertIn("no end marker",
                      (self.repo.root / "src/api/CLAUDE.md").read_text())

    def test_root_map_kind(self):
        res = self.write_block(path=".", kind="root-map",
                               body="## Codebase map\n- `src/api/` — handlers → src/api/CLAUDE.md\n")
        self.assertEqual(res.returncode, 0, res.stderr)
        text = (self.repo.root / "CLAUDE.md").read_text()
        self.assertIn("<!-- BEGIN treecode:map (auto) -->", text)

    def test_cap_warning_on_stderr(self):
        res = self.write_block(body="\n".join(f"line {i}" for i in range(70)))
        self.assertEqual(res.returncode, 0)
        self.assertIn("warning", res.stderr.lower())


if __name__ == "__main__":
    unittest.main()
