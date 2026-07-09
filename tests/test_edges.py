import json
import unittest

from tests.helpers import TempRepo, load_treemap, run_cli

PY = "x = 1\n"


class TestDeclaredEdges(unittest.TestCase):
    def setUp(self):
        self.tm = load_treemap()
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        # two modules that never import each other (client/server over HTTP)
        self.repo.write("backend/pyproject.toml", "[project]\nname = \"backend\"\n")
        for i in range(3):
            self.repo.write(f"backend/m{i}.py", PY)
        self.repo.write("frontend/package.json", "{}")
        for i in range(3):
            self.repo.write(f"frontend/src/routes/p{i}.svelte", "<div/>")

    def modules(self):
        cfg = self.tm.load_config(self.repo.root)
        files = self.tm.list_files(self.repo.root, cfg)
        mods = self.tm.find_modules(self.repo.root, files, cfg)
        self.tm.build_dep_graph(self.repo.root, mods, files, cfg)
        return {m.path: m for m in mods}

    def test_no_edges_without_config(self):
        by_path = self.modules()
        self.assertEqual(by_path["frontend"].depends_on, [])
        self.assertEqual(by_path["backend"].used_by, [])

    def test_declared_edge_merged_both_directions(self):
        self.repo.write("treemap.config.json",
                        json.dumps({"edges": {"frontend": ["backend"]}}))
        by_path = self.modules()
        self.assertIn("backend", by_path["frontend"].depends_on)
        self.assertIn("frontend", by_path["backend"].used_by)

    def test_unknown_endpoint_ignored(self):
        self.repo.write("treemap.config.json",
                        json.dumps({"edges": {"frontend": ["nonexistent"]}}))
        by_path = self.modules()   # must not raise
        self.assertEqual(by_path["frontend"].depends_on, [])

    def test_declared_edge_not_duplicated(self):
        # even if declared twice, the edge appears once
        self.repo.write("treemap.config.json",
                        json.dumps({"edges": {"frontend": ["backend", "backend"]}}))
        by_path = self.modules()
        self.assertEqual(by_path["frontend"].depends_on.count("backend"), 1)

    def test_edges_surface_in_scan_json(self):
        self.repo.write("treemap.config.json",
                        json.dumps({"edges": {"frontend": ["backend"]}}))
        data = json.loads(run_cli(["scan", "--json"], cwd=self.repo.root).stdout)
        fe = next(m for m in data["modules"] if m["path"] == "frontend")
        self.assertIn("backend", fe["depends_on"])


if __name__ == "__main__":
    unittest.main()
