import json
import unittest

from tests.helpers import TempRepo, run_cli

PY = "x = 1\n"
BLOCK_BODY = ("# api — HTTP handlers\n\nResponsibility: routing\n"
              "Key abstractions: Router\nGotchas: none\n")


def block(body):
    return ("<!-- BEGIN treecode (auto) — do not edit inside this block -->\n"
            f"{body}<!-- END treecode (auto) -->\n")


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        for i in range(3):
            self.repo.write(f"src/api/m{i}.py", PY)

    def check(self, *extra):
        res = run_cli(["check", "--json", *extra], cwd=self.repo.root)
        return res.returncode, json.loads(res.stdout) if res.stdout else {}

    def test_new_module_is_drift(self):
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(data["drift"]["new"][0]["path"], "src/api")

    def test_clean_repo_exits_0(self):
        self.repo.write("src/api/CLAUDE.md", block(BLOCK_BODY))
        self.repo.write("CLAUDE.md",
                        "<!-- BEGIN treecode:map (auto) -->\n## Codebase map\n"
                        "- `src/api/` — handlers → src/api/CLAUDE.md\n"
                        "<!-- END treecode:map (auto) -->\n")
        code, data = self.check()
        self.assertEqual(code, 0, data)

    def test_renamed_module_detected(self):
        # src/api is a live module WITH a block; src/old holds a near-identical
        # stale block but no sources -> orphan paired to src/api by content.
        self.repo.write("src/api/CLAUDE.md", block(BLOCK_BODY))
        self.repo.write("src/old/CLAUDE.md", block(BLOCK_BODY))
        code, data = self.check()
        self.assertEqual(code, 1)
        renamed = data["drift"]["renamed"]
        self.assertTrue(renamed, data["drift"])
        self.assertEqual(renamed[0]["from"], "src/old")
        self.assertEqual(renamed[0]["to"], "src/api")
        # a paired orphan must leave the orphan bucket
        self.assertEqual(data["drift"]["orphan_nested"], [])

    def test_orphan_without_match_stays_orphan(self):
        self.repo.write("src/api/CLAUDE.md", block(BLOCK_BODY))
        self.repo.write("src/gone/CLAUDE.md",
                        block("# gone — totally unrelated\n\nNothing in common here.\n"))
        code, data = self.check()
        self.assertEqual(code, 1)
        orphans = [o["path"] for o in data["drift"]["orphan_nested"]]
        self.assertIn("src/gone", orphans)

    def test_dead_pointer(self):
        self.repo.write("src/api/CLAUDE.md", block(BLOCK_BODY))
        self.repo.write("CLAUDE.md",
                        "<!-- BEGIN treecode:map (auto) -->\n"
                        "- `gone/` — vanished → gone/CLAUDE.md\n"
                        "- `src/api/` — handlers → src/api/CLAUDE.md\n"
                        "<!-- END treecode:map (auto) -->\n")
        code, data = self.check()
        self.assertEqual(code, 1)
        dead = [d["path"] for d in data["drift"]["dead_pointers"]]
        self.assertIn("gone", dead)

    def test_cap_violation_and_cap_only(self):
        self.repo.write("src/api/CLAUDE.md",
                        block(BLOCK_BODY) + "\n".join(f"l{i}" for i in range(80)) + "\n")
        code, data = self.check("--cap-only")
        self.assertEqual(code, 1)
        self.assertEqual(data["drift"]["cap_violations"][0]["path"],
                         "src/api/CLAUDE.md")
        for bucket in ("new", "renamed", "removed", "dead_pointers", "orphan_nested"):
            self.assertEqual(data["drift"][bucket], [])

    def test_cap_only_single_path(self):
        self.repo.write("src/api/CLAUDE.md", block(BLOCK_BODY))
        code, _ = self.check("--cap-only", "--path", "src/api/CLAUDE.md")
        self.assertEqual(code, 0)

    def test_table_output(self):
        res = run_cli(["check"], cwd=self.repo.root)
        self.assertEqual(res.returncode, 1)
        self.assertIn("new", res.stdout)
        self.assertIn("src/api", res.stdout)
        self.assertIn("suggested-action", res.stdout)


if __name__ == "__main__":
    unittest.main()
