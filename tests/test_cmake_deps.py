import json
import unittest

from tests.helpers import TempRepo, load_treemap, run_cli

C = "int x;\n"


class TestCMakeDeps(unittest.TestCase):
    def setUp(self):
        self.tm = load_treemap()
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("CMakeLists.txt", "project(app)\n")

    def _component(self, name, register):
        self.repo.write(f"components/{name}/CMakeLists.txt", register)
        self.repo.write(f"components/{name}/{name}.c", C)

    def graph(self):
        cfg = self.tm.load_config(self.repo.root)
        files = self.tm.list_files(self.repo.root, cfg)
        mods = self.tm.find_modules(self.repo.root, files, cfg)
        self.tm.build_dep_graph(self.repo.root, mods, files, cfg)
        return {m.path: m for m in mods}

    def test_requires_and_priv_requires(self):
        self._component("core", 'idf_component_register(SRCS "core.c" REQUIRES "")\n')
        self._component("net",
                        'idf_component_register(SRCS "net.c"\n'
                        '  REQUIRES core esp_netif)\n')
        self._component("app",
                        'idf_component_register(SRCS "app.c"\n'
                        '  REQUIRES net\n  PRIV_REQUIRES core)\n')
        g = self.graph()
        self.assertIn("components/core", g["components/net"].depends_on)
        self.assertCountEqual(g["components/app"].depends_on,
                              ["components/net", "components/core"])
        self.assertIn("components/app", g["components/core"].used_by)
        self.assertIn("components/net", g["components/core"].used_by)

    def test_builtin_requires_ignored(self):
        # esp_netif / nvs_flash are ESP-IDF builtins, not repo modules -> no edge
        self._component("core", 'idf_component_register(SRCS "core.c" REQUIRES "")\n')
        self._component("net",
                        'idf_component_register(SRCS "net.c" REQUIRES esp_netif nvs_flash core)\n')
        g = self.graph()
        self.assertEqual(g["components/net"].depends_on, ["components/core"])

    def test_target_link_libraries_plain_cmake(self):
        self._component("core", 'idf_component_register(SRCS "core.c")\n')
        self._component("net",
                        'idf_component_register(SRCS "net.c")\n'
                        'target_link_libraries(net PRIVATE core)\n')
        g = self.graph()
        self.assertIn("components/core", g["components/net"].depends_on)

    def test_no_self_edge_and_surfaces_in_scan(self):
        self._component("core",
                        'idf_component_register(SRCS "core.c" REQUIRES core)\n')  # self
        self._component("net",
                        'idf_component_register(SRCS "net.c" REQUIRES core)\n')
        data = json.loads(run_cli(["scan", "--json"], cwd=self.repo.root).stdout)
        core = next(m for m in data["modules"] if m["path"] == "components/core")
        net = next(m for m in data["modules"] if m["path"] == "components/net")
        self.assertEqual(core["depends_on"], [])          # no self-edge
        self.assertIn("components/core", net["depends_on"])

    def test_config_edges_still_merge(self):
        self._component("core", 'idf_component_register(SRCS "core.c")\n')
        self._component("net", 'idf_component_register(SRCS "net.c")\n')
        self.repo.write("treemap.config.json",
                        json.dumps({"edges": {"components/net": ["components/core"]}}))
        g = self.graph()
        self.assertIn("components/core", g["components/net"].depends_on)


if __name__ == "__main__":
    unittest.main()
