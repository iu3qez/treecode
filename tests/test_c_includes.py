import json
import unittest

from tests.helpers import TempRepo, load_treemap, run_cli


class TestCIncludeFallback(unittest.TestCase):
    """Quoted #include dependency graph for non-CMake C/C++ projects."""

    def setUp(self):
        self.tm = load_treemap()
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def _module(self, name, *files):
        # three sources so the dir clears min_sources without a build marker.
        for i in range(3):
            self.repo.write(f"components/{name}/pad{i}.c", "int pad;\n")
        for rel, content in files:
            self.repo.write(f"components/{name}/{rel}", content)

    def graph(self, **cfg_over):
        if cfg_over:
            self.repo.write("treemap.config.json", json.dumps(cfg_over))
        cfg = self.tm.load_config(self.repo.root)
        files = self.tm.list_files(self.repo.root, cfg)
        mods = self.tm.find_modules(self.repo.root, files, cfg)
        self.tm.build_dep_graph(self.repo.root, mods, files, cfg)
        return {m.path: m for m in mods}

    def test_include_relative_to_repo_root(self):
        self._module("core", ("core.h", "#pragma once\n"))
        self._module("net", ("net.c", '#include "components/core/core.h"\nint n;\n'))
        g = self.graph()
        self.assertIn("components/core", g["components/net"].depends_on)
        self.assertIn("components/net", g["components/core"].used_by)

    def test_include_relative_to_including_file(self):
        self._module("core", ("core.h", "#pragma once\n"))
        self._module("net", ("net.c", '#include "../core/core.h"\nint n;\n'))
        g = self.graph()
        self.assertIn("components/core", g["components/net"].depends_on)

    def test_include_by_unique_basename(self):
        # header reached via an -I include dir we can't see; basename is unique.
        self._module("core", ("core.h", "#pragma once\n"))
        self._module("net", ("net.c", '#include "core.h"\nint n;\n'))
        g = self.graph()
        self.assertIn("components/core", g["components/net"].depends_on)

    def test_ambiguous_basename_no_edge(self):
        # two headers share a basename -> refuse to guess.
        self._module("core", ("util.h", "#pragma once\n"))
        self._module("aux", ("util.h", "#pragma once\n"))
        self._module("net", ("net.c", '#include "util.h"\nint n;\n'))
        g = self.graph()
        self.assertEqual(g["components/net"].depends_on, [])

    def test_angle_bracket_include_ignored(self):
        self._module("core", ("core.h", "#pragma once\n"))
        self._module("net", ("net.c", "#include <core.h>\n#include <stdio.h>\nint n;\n"))
        g = self.graph()
        self.assertEqual(g["components/net"].depends_on, [])

    def test_no_self_edge_within_module(self):
        self._module("net", ("net.h", "#pragma once\n"),
                     ("net.c", '#include "net.h"\nint n;\n'))
        g = self.graph()
        self.assertEqual(g["components/net"].depends_on, [])

    def test_cmake_module_uses_requires_not_includes(self):
        # a module WITH CMakeLists.txt is authoritative via REQUIRES; a stray
        # #include that REQUIRES doesn't declare must not create an edge.
        self.repo.write("CMakeLists.txt", "project(app)\n")
        self.repo.write("components/core/CMakeLists.txt",
                        'idf_component_register(SRCS "core.c")\n')
        self.repo.write("components/core/core.h", "#pragma once\n")
        self.repo.write("components/core/core.c", "int c;\n")
        self.repo.write("components/net/CMakeLists.txt",
                        'idf_component_register(SRCS "net.c")\n')  # no REQUIRES core
        self.repo.write("components/net/net.c", '#include "core.h"\nint n;\n')
        g = self.graph()
        self.assertEqual(g["components/net"].depends_on, [])

    def test_surfaces_in_scan_json(self):
        self._module("core", ("core.h", "#pragma once\n"))
        self._module("net", ("net.c", '#include "../core/core.h"\nint n;\n'))
        data = json.loads(run_cli(["scan", "--json"], cwd=self.repo.root).stdout)
        net = next(m for m in data["modules"] if m["path"] == "components/net")
        self.assertIn("components/core", net["depends_on"])


if __name__ == "__main__":
    unittest.main()
