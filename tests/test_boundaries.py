import unittest

from tests.helpers import TempRepo, load_treemap

PY = "x = 1\n"


class TestBoundaries(unittest.TestCase):
    def setUp(self):
        self.tm = load_treemap()
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def build_fixture(self):
        r = self.repo
        # python backend: src/api (3 sources), src/core (3 sources)
        for i in range(3):
            r.write(f"src/api/m{i}.py", "from src.core import util\n" if i == 0 else PY)
            r.write(f"src/core/m{i}.py", PY)
        # tiny dir under src: below min_sources, must merge away
        r.write("src/tiny/one.py", PY)
        # sveltekit-style frontend package
        r.write("frontend/package.json", "{}")
        for i in range(3):
            r.write(f"frontend/src/routes/p{i}.svelte", "<div/>")
        # monorepo member
        r.write("packages/shared/index.ts", "export const a = 1\n")
        r.write("packages/shared/b.ts", "import { a } from './index'\n")
        r.write("packages/shared/c.ts", PY)

    def modules(self, **kw):
        cfg = self.tm.load_config(self.repo.root)
        files = self.tm.list_files(self.repo.root, cfg)
        return self.tm.find_modules(self.repo.root, files, cfg, **kw)

    def test_expected_modules(self):
        self.build_fixture()
        paths = {m.path: m.kind for m in self.modules()}
        self.assertEqual(paths.get("src/api"), "framework-dir")
        self.assertEqual(paths.get("src/core"), "framework-dir")
        self.assertEqual(paths.get("frontend"), "package")
        self.assertEqual(paths.get("packages/shared"), "monorepo-member")
        self.assertNotIn("src/tiny", paths)      # merged away (< min_sources)
        self.assertNotIn(".", paths)              # repo root never a module
        self.assertNotIn("frontend/src/routes", paths)  # absorbed by frontend

    def test_generic_disables_framework_dirs(self):
        self.build_fixture()
        paths = {m.path for m in self.modules(stack_aware=False)}
        self.assertNotIn("src/api", paths)
        self.assertIn("frontend", paths)          # package markers still apply

    def test_dep_graph_python_and_js(self):
        self.build_fixture()
        cfg = self.tm.load_config(self.repo.root)
        files = self.tm.list_files(self.repo.root, cfg)
        mods = self.tm.find_modules(self.repo.root, files, cfg)
        self.tm.build_dep_graph(self.repo.root, mods, files)
        by_path = {m.path: m for m in mods}
        self.assertIn("src/core", by_path["src/api"].depends_on)
        self.assertIn("src/api", by_path["src/core"].used_by)

    def test_parse_errors_never_raise(self):
        self.build_fixture()
        self.repo.write("src/api/broken.py", "def broken(:\n")
        cfg = self.tm.load_config(self.repo.root)
        files = self.tm.list_files(self.repo.root, cfg)
        mods = self.tm.find_modules(self.repo.root, files, cfg)
        self.tm.build_dep_graph(self.repo.root, mods, files)  # must not raise


if __name__ == "__main__":
    unittest.main()
