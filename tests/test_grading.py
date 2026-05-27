import unittest

from ckad_drills.grading import grade_drills, summarize_results
from ckad_drills.models import Drill, VerifyCheck


class TestGrading(unittest.TestCase):
    def test_grade_drills_and_summarize_results(self):
        drills = [
            Drill(
                question_id="Q01",
                domain="Domain A",
                topic="Topic A",
                scenario="Scenario A",
                tasks="Task A",
                verify="pass-command",
                hints="Hint A",
            ),
            Drill(
                question_id="Q02",
                domain="Domain A",
                topic="Topic B",
                scenario="Scenario B",
                tasks="Task B",
                verify="fail-command",
                hints="Hint B",
            ),
            Drill(
                question_id="Q03",
                domain="Domain B",
                topic="Topic C",
                scenario="Scenario C",
                tasks="Task C",
                verify="pass-command-2",
                hints="Hint C",
            ),
        ]

        def fake_runner(command: str) -> bool:
            return command != "fail-command"

        results = grade_drills(drills, fake_runner)
        summary = summarize_results(results)

        self.assertEqual(len(results), 3)
        self.assertTrue(results[0].passed)
        self.assertFalse(results[1].passed)
        self.assertEqual(summary.passed, 2)
        self.assertEqual(summary.total, 3)
        self.assertAlmostEqual(summary.percentage, 66.6666666667)
        self.assertEqual(len(summary.domain_scores), 2)
        self.assertEqual(summary.domain_scores[0].domain, "Domain A")
        self.assertEqual(summary.domain_scores[0].passed, 1)
        self.assertEqual(summary.domain_scores[0].total, 2)
        self.assertEqual(len(summary.failed_results), 1)
        self.assertEqual(summary.failed_results[0].question_id, "Q02")


class TestStructuredGrading(unittest.TestCase):
    def _build_drill(self, checks):
        return Drill(
            question_id="Y01",
            domain="Domain X",
            topic="Topic X",
            scenario="...",
            tasks="...",
            verify="fallback",
            hints="",
            checks=tuple(checks),
        )

    def test_drill_passes_when_all_checks_pass(self):
        captures = {
            "echo hello": (0, "hello\n", ""),
            "echo world": (0, "world\n", ""),
        }
        drill = self._build_drill(
            [
                VerifyCheck(name="a", run="echo hello", kind="equals", value="hello"),
                VerifyCheck(name="b", run="echo world", kind="contains", value="orl"),
            ]
        )

        results = grade_drills(
            [drill],
            runner=lambda _command: False,
            capture_runner=lambda command: captures[command],
        )

        self.assertTrue(results[0].passed)
        self.assertEqual(len(results[0].check_results), 2)
        self.assertTrue(all(cr.passed for cr in results[0].check_results))

    def test_drill_fails_when_any_check_fails(self):
        captures = {
            "echo hello": (0, "hello\n", ""),
            "echo nope": (0, "nope\n", ""),
        }
        drill = self._build_drill(
            [
                VerifyCheck(name="a", run="echo hello", kind="equals", value="hello"),
                VerifyCheck(name="b", run="echo nope", kind="equals", value="yep"),
            ]
        )

        results = grade_drills(
            [drill],
            runner=lambda _command: True,
            capture_runner=lambda command: captures[command],
        )

        self.assertFalse(results[0].passed)
        self.assertTrue(results[0].check_results[0].passed)
        self.assertFalse(results[0].check_results[1].passed)
        self.assertIn("yep", results[0].check_results[1].detail)

    def test_non_zero_exit_fails_non_exit_code_checks(self):
        captures = {
            "kubectl get pod missing": (1, "", "Error from server (NotFound)"),
        }
        drill = self._build_drill(
            [
                VerifyCheck(
                    name="pod exists",
                    run="kubectl get pod missing",
                    kind="contains",
                    value="missing",
                ),
            ]
        )

        results = grade_drills(
            [drill],
            runner=lambda _command: True,
            capture_runner=lambda command: captures[command],
        )

        self.assertFalse(results[0].passed)
        self.assertIn("exit_code=1", results[0].check_results[0].detail)

    def test_fallback_to_bool_runner_when_no_checks(self):
        drill = Drill(
            question_id="Q01",
            domain="Domain X",
            topic="Topic X",
            scenario="...",
            tasks="...",
            verify="some-command",
            hints="",
        )

        results = grade_drills(
            [drill],
            runner=lambda command: command == "some-command",
            capture_runner=lambda command: (99, "", ""),
        )

        self.assertTrue(results[0].passed)
        self.assertEqual(results[0].check_results, ())


if __name__ == "__main__":
    unittest.main()
