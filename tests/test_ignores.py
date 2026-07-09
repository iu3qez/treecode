import os
import unittest

from tests.helpers import TempRepo, load_treemap


class TestIgnores(unittest.TestCase):
    def setUp(self):
        self.tm = load_treemap()
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("src/api/app.py", "x = 1\n")
        self.repo.write("node_modules/pkg/index.js", "junk")
        self.repo.write("dist/out.js", "junk")
        self.repo.write("secret/keys.py", "k = 1\n")
        self.repo.write(".gitignore", "dist/\n")
        self.repo.write(".claudeignore", "secret/*\n")
        self.cfg = self.tm.load_config(self.repo.root)

    def rels(self):
        return {p.as_posix() for p in self.tm.list_files(self.repo.root, self.cfg)}

    def check_common(self):
        rels = self.rels()
        self.assertIn("src/api/app.py", rels)
        self.assertNotIn("node_modules/pkg/index.js", rels)   # ignore_globs
        self.assertNotIn("dist/out.js", rels)                  # .gitignore
        self.assertNotIn("secret/keys.py", rels)               # .claudeignore

    def test_with_git(self):
        self.repo.git_init()
        self.check_common()

    def test_without_git_fallback(self):
        self.check_common()  # no .git dir → os.walk fallback

    def test_symlink_outside_root_dropped(self):
        outside = TempRepo()
        self.addCleanup(outside.cleanup)
        outside.write("evil.py", "x = 1\n")
        os.symlink(outside.root / "evil.py", self.repo.root / "link.py")
        self.assertNotIn("link.py", self.rels())

    def test_match_any_glob_variants(self):
        self.assertTrue(self.tm.match_any("a/node_modules/b.js",
                                          ["**/node_modules/**"]))
        self.assertTrue(self.tm.match_any("node_modules/b.js",
                                          ["**/node_modules/**"]))
        self.assertFalse(self.tm.match_any("src/app.py", ["**/node_modules/**"]))


if __name__ == "__main__":
    unittest.main()
