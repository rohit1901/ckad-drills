import unittest

from ckad_drills.cleanup import (
    build_cleanup_plan,
    cleanup_environment,
    validate_cleanup_settings,
)
from ckad_drills.exceptions import CleanupConfigurationError


class TestCleanup(unittest.TestCase):
    def test_build_cleanup_plan_for_objects(self):
        target, steps = build_cleanup_plan("objects", "drill-01")

        self.assertEqual(target, "drill-01")
        self.assertEqual(len(steps), 1)
        self.assertIn("kubectl delete", steps[0][1])
        self.assertIn("-n drill-01", steps[0][1])

    def test_build_cleanup_plan_for_kind_cluster(self):
        target, steps = build_cleanup_plan(
            "kind-cluster",
            "drill-01",
            kind_cluster_name="ckad-practice",
        )

        self.assertEqual(target, "ckad-practice")
        self.assertEqual(steps[0][1], "kind delete cluster --name ckad-practice")

    def test_validate_cleanup_settings_rejects_protected_namespace(self):
        with self.assertRaises(CleanupConfigurationError):
            validate_cleanup_settings("namespace", "default")

    def test_validate_cleanup_settings_requires_kind_cluster_name(self):
        with self.assertRaises(CleanupConfigurationError):
            validate_cleanup_settings("kind-cluster", "drill-01")

    def test_cleanup_environment_reports_failed_step(self):
        summary = cleanup_environment(
            "namespace",
            "drill-01",
            runner=lambda command: False,
        )

        self.assertTrue(summary.attempted)
        self.assertFalse(summary.succeeded)
        self.assertEqual(len(summary.steps), 1)
        self.assertFalse(summary.steps[0].succeeded)


if __name__ == "__main__":
    unittest.main()
