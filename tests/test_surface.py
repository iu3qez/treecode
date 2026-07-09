import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path}: missing frontmatter"
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip().strip('"')
    return fields


class TestSurface(unittest.TestCase):
    def test_skill_frontmatter(self):
        fm = frontmatter(ROOT / "skills/tree-mapper/SKILL.md")
        self.assertEqual(fm["name"], "tree-mapper")
        self.assertTrue(len(fm["description"]) > 20)

    def test_skill_body_contract(self):
        body = (ROOT / "skills/tree-mapper/SKILL.md").read_text()
        for needle in ("scan --json", "write-block", "CLAUDE_PLUGIN_ROOT",
                       "Never commit", "@path"):
            self.assertIn(needle, body)

    def test_commands_exist_with_frontmatter(self):
        for cmd in ("map-tree", "map-drift"):
            fm = frontmatter(ROOT / f"commands/{cmd}.md")
            self.assertIn("description", fm)

    def test_readme_mentions_invariants_and_install(self):
        text = (ROOT / "README.md").read_text()
        for needle in ("plugin marketplace add", "plugin install treecode@iu3qez-tools",
                       "map-tree", "map-drift", "marker", "lazy"):
            self.assertIn(needle, text)

    def test_cartographer_agent(self):
        fm = frontmatter(ROOT / "agents/module-cartographer.md")
        self.assertEqual(fm["name"], "module-cartographer")
        self.assertIn("description", fm)
        body = (ROOT / "agents/module-cartographer.md").read_text()
        self.assertIn("one", body.lower())          # single-module scope
        self.assertIn("do not write files", body.lower())

    def test_skill_and_command_cover_rules(self):
        skill = (ROOT / "skills/tree-mapper/SKILL.md").read_text()
        self.assertIn("--kind rule", skill)
        self.assertIn("module-cartographer", skill)
        cmd = (ROOT / "commands/map-tree.md").read_text()
        self.assertIn("--with-rules", cmd)


if __name__ == "__main__":
    unittest.main()
