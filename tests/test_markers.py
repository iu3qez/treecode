import unittest

from tests.helpers import load_treemap

BLOCK = ("<!-- BEGIN treecode (auto) — do not edit inside this block -->\n"
         "old body\n"
         "<!-- END treecode (auto) -->\n")


class TestMarkers(unittest.TestCase):
    def setUp(self):
        self.tm = load_treemap()

    def test_lines_exact(self):
        self.assertEqual(
            self.tm.begin_line("treecode", "module"),
            "<!-- BEGIN treecode (auto) — do not edit inside this block -->")
        self.assertEqual(self.tm.begin_line("treecode:map", "root-map"),
                         "<!-- BEGIN treecode:map (auto) -->")
        self.assertEqual(self.tm.end_line("treecode"), "<!-- END treecode (auto) -->")

    def test_replace_preserves_outside_text(self):
        text = "human intro\n\n" + BLOCK + "\nhuman outro\n"
        out = self.tm.replace_block(text, "treecode", "module", "new body")
        self.assertIn("human intro", out)
        self.assertIn("human outro", out)
        self.assertIn("new body", out)
        self.assertNotIn("old body", out)

    def test_replace_is_idempotent(self):
        once = self.tm.replace_block("", "treecode", "module", "body")
        twice = self.tm.replace_block(once, "treecode", "module", "body")
        self.assertEqual(once, twice)

    def test_append_when_no_block(self):
        out = self.tm.replace_block("existing text\n", "treecode", "module", "body")
        self.assertTrue(out.startswith("existing text\n"))
        self.assertIn("<!-- BEGIN treecode (auto)", out)

    def test_names_do_not_collide(self):
        # a treecode:map block must not be seen as a treecode block
        text = ("<!-- BEGIN treecode:map (auto) -->\nmap\n"
                "<!-- END treecode:map (auto) -->\n")
        self.assertIsNone(self.tm.find_block(text, "treecode"))
        self.assertIsNotNone(self.tm.find_block(text, "treecode:map"))

    def test_corrupted_markers_raise(self):
        for bad in (
            "<!-- BEGIN treecode (auto) -->\nno end\n",
            "text\n<!-- END treecode (auto) -->\n",
            BLOCK + "\n" + BLOCK,  # duplicate
        ):
            with self.assertRaises(self.tm.MarkerError):
                self.tm.find_block(bad, "treecode")


if __name__ == "__main__":
    unittest.main()
