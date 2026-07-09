import ast as ast_mod
import json
import sys
import unittest
from pathlib import Path

from tests.helpers import TempRepo, run_cli

PY = "x = 1\n"


def build_mixed_repo(repo):
    for i in range(3):
        repo.write(f"src/api/m{i}.py", PY)
        repo.write(f"src/core/m{i}.py", PY)
    repo.write("frontend/package.json", "{}")
    for i in range(3):
        repo.write(f"frontend/src/routes/p{i}.svelte", "<div/>")
    repo.write("node_modules/junk/x.js", "junk")
    repo.git_init()


def write_all_blocks(repo):
    """Simulate what the skill does: one block per module + root map."""
    scan = json.loads(run_cli(["scan", "--json"], cwd=repo.root).stdout)
    map_lines = ["## Codebase map"]
    for mod in scan["modules"]:
        body = repo.write("_b.md", f"# {mod['path']} — module\n\nResponsibility: demo\n")
        res = run_cli(["write-block", "--path", mod["path"],
                       "--content-file", str(body)], cwd=repo.root)
        assert res.returncode == 0, res.stderr
        map_lines.append(f"- `{mod['path']}/` — module → {mod['path']}/CLAUDE.md")
    body = repo.write("_m.md", "\n".join(map_lines) + "\n")
    res = run_cli(["write-block", "--path", ".", "--kind", "root-map",
                   "--content-file", str(body)], cwd=repo.root)
    assert res.returncode == 0, res.stderr
    (repo.root / "_b.md").unlink()
    (repo.root / "_m.md").unlink()


class TestAcceptance(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        build_mixed_repo(self.repo)

    def test_ac1_ac2_ac3_ac4_ac8(self):
        write_all_blocks(self.repo)
        # AC1: nested files exist, plus root map, and a clean check
        for mod in ("src/api", "src/core", "frontend"):
            self.assertTrue((self.repo.root / mod / "CLAUDE.md").is_file())
        self.assertIn("treecode:map", (self.repo.root / "CLAUDE.md").read_text())
        self.assertEqual(run_cli(["check"], cwd=self.repo.root).returncode, 0)
        # AC3: human text outside markers
        root_md = self.repo.root / "CLAUDE.md"
        root_md.write_text("HUMAN HEADER\n" + root_md.read_text())
        # AC2: re-run -> zero diff (human header included)
        watched = ("src/api", "src/core", "frontend")
        before = {p: (self.repo.root / p / "CLAUDE.md").read_text() for p in watched}
        before["."] = root_md.read_text()
        write_all_blocks(self.repo)
        after = {p: (self.repo.root / p / "CLAUDE.md").read_text() for p in watched}
        after["."] = root_md.read_text()
        self.assertEqual(before, after)
        self.assertTrue(after["."].startswith("HUMAN HEADER\n"))
        # AC4: no @path imports anywhere in generated files
        for text in after.values():
            for line in text.splitlines():
                self.assertFalse(line.startswith("@"), "no @path imports allowed")
        # AC8: ignored dirs untouched
        self.assertFalse((self.repo.root / "node_modules/junk/CLAUDE.md").exists())

    def test_ac5_renamed_directory_flags_drift(self):
        # A full directory rename moves CLAUDE.md too, so the live signal is a
        # dead root-map pointer + removed entry (pure content-rename is pinned
        # in tests/test_check.py::test_renamed_module_detected).
        write_all_blocks(self.repo)
        (self.repo.root / "src/core").rename(self.repo.root / "src/domain")
        res = run_cli(["check", "--json"], cwd=self.repo.root)
        self.assertEqual(res.returncode, 1)
        drift = json.loads(res.stdout)["drift"]
        dead = [d["path"] for d in drift["dead_pointers"]]
        removed = [r["path"] for r in drift["removed"]]
        self.assertIn("src/core", dead, drift)
        self.assertIn("src/core", removed, drift)

    def test_ac7_stdlib_only(self):
        script = Path(__file__).resolve().parent.parent / "scripts/treemap.py"
        tree = ast_mod.parse(script.read_text())
        imported = set()
        for node in ast_mod.walk(tree):
            if isinstance(node, ast_mod.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast_mod.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported, set(sys.stdlib_module_names))


if __name__ == "__main__":
    unittest.main()
