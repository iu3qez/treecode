import json
import subprocess
import unittest
from pathlib import Path

from tests.helpers import TempRepo

HOOKS = Path(__file__).resolve().parent.parent / "hooks"


def run_hook(script, payload, cwd):
    return subprocess.run(["bash", str(HOOKS / script)], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=cwd,
                          env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                               "CLAUDE_PLUGIN_ROOT": str(HOOKS.parent),
                               "CLAUDE_PROJECT_DIR": str(cwd)})


class TestHooks(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def test_hooks_json_shape(self):
        data = json.loads((HOOKS / "hooks.json").read_text())
        events = data["hooks"]
        self.assertIn("PostToolUse", events)
        self.assertIn("InstructionsLoaded", events)
        self.assertEqual(events["PostToolUse"][0]["matcher"], "Write|Edit")

    def test_cap_guard_warns_over_cap_but_exits_0(self):
        big = self.repo.write("src/CLAUDE.md",
                              "\n".join(f"l{i}" for i in range(120)) + "\n")
        res = run_hook("cap-guard.sh",
                       {"tool_input": {"file_path": str(big)}}, self.repo.root)
        self.assertEqual(res.returncode, 0)
        self.assertIn("cap", (res.stdout + res.stderr).lower())

    def test_cap_guard_silent_under_cap(self):
        ok = self.repo.write("src/CLAUDE.md", "short\n")
        res = run_hook("cap-guard.sh",
                       {"tool_input": {"file_path": str(ok)}}, self.repo.root)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip() + res.stderr.strip(), "")

    def test_cap_guard_ignores_other_files(self):
        f = self.repo.write("src/notes.md", "\n".join("x" * 300))
        res = run_hook("cap-guard.sh",
                       {"tool_input": {"file_path": str(f)}}, self.repo.root)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip() + res.stderr.strip(), "")

    def test_instructions_log_off_by_default(self):
        res = run_hook("instructions-log.sh",
                       {"file_path": "CLAUDE.md", "load_reason": "startup"},
                       self.repo.root)
        self.assertEqual(res.returncode, 0)
        self.assertFalse((self.repo.root / ".claude/treecode-instructions.log").exists())

    def test_instructions_log_opt_in(self):
        self.repo.write("treemap.config.json",
                        json.dumps({"hooks": {"instructions_loaded_log": True}}))
        res = run_hook("instructions-log.sh",
                       {"file_path": "CLAUDE.md", "load_reason": "startup"},
                       self.repo.root)
        self.assertEqual(res.returncode, 0)
        log = self.repo.root / ".claude/treecode-instructions.log"
        self.assertIn("CLAUDE.md", log.read_text())


if __name__ == "__main__":
    unittest.main()
