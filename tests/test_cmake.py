import unittest

from tests.helpers import TempRepo, load_treemap

C = "int x;\n"
H = "#pragma once\n"


class TestCMakeDiscovery(unittest.TestCase):
    def setUp(self):
        self.tm = load_treemap()
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def modules(self, **kw):
        cfg = self.tm.load_config(self.repo.root)
        files = self.tm.list_files(self.repo.root, cfg)
        return self.tm.find_modules(self.repo.root, files, cfg, **kw)

    def _esp_idf_repo(self):
        r = self.repo
        r.write("CMakeLists.txt", "project(app)\n")           # root project file
        for name in ("keyer_core", "esp_wireguard", "keyer_webui"):
            r.write(f"components/{name}/CMakeLists.txt", "idf_component_register()\n")
            r.write(f"components/{name}/src/{name}.c", C)
            r.write(f"components/{name}/include/{name}.h", H)
        # a component that nests a source subdir (the old false-positive trigger)
        r.write("components/esp_wireguard/src/crypto/aead.c", C)
        r.write("main/CMakeLists.txt", "idf_component_register()\n")
        r.write("main/main.c", C)

    def test_esp_idf_components_and_main_detected(self):
        self._esp_idf_repo()
        paths = {m.path for m in self.modules()}
        for name in ("keyer_core", "esp_wireguard", "keyer_webui"):
            self.assertIn(f"components/{name}", paths)
        self.assertIn("main", paths)

    def test_no_false_positive_from_nested_src(self):
        self._esp_idf_repo()
        paths = {m.path for m in self.modules()}
        self.assertNotIn("components/esp_wireguard/src/crypto", paths)
        self.assertNotIn("components/esp_wireguard/src", paths)

    def test_cmake_marker_gated_on_root_project_file(self):
        # a dir with CMakeLists.txt but NO root CMakeLists.txt is not promoted
        for i in range(2):
            self.repo.write(f"widget/a{i}.c", C)
        self.repo.write("widget/CMakeLists.txt", "add_library(widget)\n")
        self.assertNotIn("widget", {m.path for m in self.modules()})
        # add the root project file -> now it is promoted
        self.repo.write("CMakeLists.txt", "project(app)\n")
        self.assertIn("widget", {m.path for m in self.modules()})

    def test_components_glob_without_cmake(self):
        # components/* is a recognized convention even without CMake files
        for i in range(3):
            self.repo.write(f"components/sensor/s{i}.c", C)
        self.assertIn("components/sensor", {m.path for m in self.modules()})

    def test_src_child_only_top_level(self):
        # top-level src/ children remain modules; a deep <pkg>/src/<x> does not
        self.repo.write("pyproject.toml", "[project]\nname = \"app\"\n")
        for i in range(3):
            self.repo.write(f"src/api/m{i}.py", "x=1\n")
            self.repo.write(f"lib/thing/src/deep/d{i}.py", "x=1\n")
        paths = {m.path for m in self.modules()}
        self.assertIn("src/api", paths)
        self.assertNotIn("lib/thing/src/deep", paths)


if __name__ == "__main__":
    unittest.main()
