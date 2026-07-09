import json
import unittest

from tests.helpers import TempRepo, load_treemap, run_cli


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tm = load_treemap()
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def test_defaults_when_no_config(self):
        cfg = self.tm.load_config(self.repo.root)
        self.assertEqual(cfg["caps"], {"root": 80, "nested": 60, "hard_max": 200})
        self.assertTrue(cfg["stack_aware"])
        self.assertEqual(cfg["markers"], {"module": "treecode", "root": "treecode:map"})

    def test_partial_config_deep_merges(self):
        self.repo.write("treemap.config.json",
                        json.dumps({"caps": {"root": 50}, "stack_aware": False}))
        cfg = self.tm.load_config(self.repo.root)
        self.assertEqual(cfg["caps"]["root"], 50)
        self.assertEqual(cfg["caps"]["nested"], 60)   # default preserved
        self.assertFalse(cfg["stack_aware"])

    def test_invalid_config_is_usage_error(self):
        self.repo.write("treemap.config.json", "{not json")
        res = run_cli(["scan", "--json"], cwd=self.repo.root)
        self.assertEqual(res.returncode, 2)

    def test_cli_subcommands_exist(self):
        for sub in ("scan", "check", "read-block"):
            res = run_cli([sub], cwd=self.repo.root)
            self.assertNotEqual(res.returncode, 2, msg=f"{sub}: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
