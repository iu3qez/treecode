import unittest

from tests.helpers import TempRepo, load_treemap

PY = "x = 1\n"


class TestRootPackageDiscovery(unittest.TestCase):
    def setUp(self):
        self.tm = load_treemap()
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def modules(self, **kw):
        cfg = self.tm.load_config(self.repo.root)
        files = self.tm.list_files(self.repo.root, cfg)
        return self.tm.find_modules(self.repo.root, files, cfg, **kw)

    def test_report_case_backend_detected_without_config(self):
        # pyproject at root + all code under backend/ -> the de-facto layout for
        # monolithic Python apps. backend/ must be detected with no config.
        self.repo.write("pyproject.toml", "[project]\nname = \"app\"\n")
        for i in range(54):
            self.repo.write(f"backend/mod{i}.py", PY)
        self.repo.write("frontend/package.json", "{}")
        for i in range(3):
            self.repo.write(f"frontend/src/routes/p{i}.svelte", "<div/>")
        paths = {m.path for m in self.modules()}
        self.assertIn("backend", paths)
        self.assertIn("frontend", paths)

    def test_tier_a_declared_poetry_package(self):
        # explicit poetry package declaration -> adopted as a package module
        self.repo.write("pyproject.toml",
                        "[tool.poetry]\nname = \"svc\"\n"
                        "packages = [{ include = \"svc\" }]\n")
        for i in range(3):
            self.repo.write(f"svc/m{i}.py", PY)
        mods = {m.path: m.kind for m in self.modules()}
        self.assertEqual(mods.get("svc"), "package")

    def test_tier_a_setuptools_packages(self):
        self.repo.write("pyproject.toml",
                        "[tool.setuptools]\npackages = [\"myapp\"]\n")
        for i in range(3):
            self.repo.write(f"myapp/m{i}.py", PY)
        self.assertIn("myapp", {m.path for m in self.modules()})

    def test_fallback_excludes_tests_and_docs(self):
        self.repo.write("pyproject.toml", "[project]\nname = \"app\"\n")
        for i in range(5):
            self.repo.write(f"backend/m{i}.py", PY)
            self.repo.write(f"tests/test_{i}.py", PY)
        for i in range(5):
            self.repo.write(f"docs/gen{i}.py", PY)
        paths = {m.path for m in self.modules()}
        self.assertIn("backend", paths)
        self.assertNotIn("tests", paths)
        self.assertNotIn("docs", paths)

    def test_fallback_keeps_migrations(self):
        # PRD treats migrations/ as a legitimate module -> not excluded
        self.repo.write("pyproject.toml", "[project]\nname = \"app\"\n")
        for i in range(4):
            self.repo.write(f"migrations/rev{i}.py", PY)
        self.assertIn("migrations", {m.path for m in self.modules()})

    def test_no_marker_no_fallback(self):
        # without any root package marker the fallback must NOT fire
        for i in range(5):
            self.repo.write(f"backend/m{i}.py", PY)
        self.assertNotIn("backend", {m.path for m in self.modules()})

    def test_src_layout_not_broken(self):
        # a normal src/ layout must keep detecting sub-dirs, not promote src/
        self.repo.write("pyproject.toml", "[project]\nname = \"app\"\n")
        for i in range(3):
            self.repo.write(f"src/api/m{i}.py", PY)
            self.repo.write(f"src/core/m{i}.py", PY)
        paths = {m.path for m in self.modules()}
        self.assertIn("src/api", paths)
        self.assertIn("src/core", paths)
        self.assertNotIn("src", paths)

    def test_generic_disables_fallback(self):
        self.repo.write("pyproject.toml", "[project]\nname = \"app\"\n")
        for i in range(5):
            self.repo.write(f"backend/m{i}.py", PY)
        self.assertNotIn("backend", {m.path for m in self.modules(stack_aware=False)})


if __name__ == "__main__":
    unittest.main()
