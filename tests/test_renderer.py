import unittest

from ckad_drills.grading import grade_drills, summarize_results
from ckad_drills.models import (
    CleanupStepResult,
    CleanupSummary,
    Drill,
    GradeSummary,
)
from ckad_drills.renderer import (
    render_cleanup_summary,
    render_drills,
    render_results,
)


class TestRenderer(unittest.TestCase):
    def test_render_drills_can_include_seed_and_colors(self):
        drills = [
            Drill(
                question_id="Q01",
                domain="Domain A",
                topic="Topic A",
                scenario="Scenario A",
                tasks="Task A",
                verify="pass-command",
                hints="Hint A",
            )
        ]

        drills_text = render_drills(drills, "drill-01", seed=42, use_color=True)

        self.assertIn("Seed: 42", drills_text)
        self.assertIn("\033[", drills_text)

    def test_render_results_can_hide_solutions(self):
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
                domain="Domain B",
                topic="Topic B",
                scenario="Scenario B",
                tasks="Task B",
                verify="fail-command",
                hints="Hint B",
            ),
        ]

        results = grade_drills(drills, lambda command: command == "pass-command")
        summary = summarize_results(results)
        results_text = render_results(
            results,
            summary,
            passing_percentage=66,
            show_solutions=False,
            use_color=False,
        )

        self.assertIn("PER-DOMAIN SCORECARD", results_text)
        self.assertNotIn("SOLUTION REVIEW", results_text)
        self.assertNotIn("Verify command: fail-command", results_text)

    def test_render_results_include_scorecards_and_solutions(self):
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
                domain="Domain B",
                topic="Topic B",
                scenario="Scenario B",
                tasks="Task B",
                verify="fail-command",
                hints="Hint B",
            ),
        ]

        results = grade_drills(drills, lambda command: command == "pass-command")
        summary = summarize_results(results)
        results_text = render_results(
            results,
            summary,
            passing_percentage=66,
            show_solutions=True,
            use_color=False,
        )

        self.assertIn("PER-DOMAIN SCORECARD", results_text)
        self.assertIn("- Domain A: 1/1 (100%)", results_text)
        self.assertIn("- Domain B: 0/1 (0%)", results_text)
        self.assertIn("SOLUTION REVIEW", results_text)
        self.assertIn("Verify command: fail-command", results_text)
        self.assertIn("Hints: Hint B", results_text)

    def test_render_cleanup_summary_includes_commands(self):
        summary = CleanupSummary(
            mode="namespace",
            target="drill-01",
            attempted=True,
            succeeded=True,
            steps=(
                CleanupStepResult(
                    label="Delete practice namespace",
                    command="kubectl delete namespace drill-01 --ignore-not-found --wait=false",
                    succeeded=True,
                ),
            ),
        )

        cleanup_text = render_cleanup_summary(summary, use_color=False)

        self.assertIn("CLEANUP", cleanup_text)
        self.assertIn("Mode: namespace", cleanup_text)
        self.assertIn(
            "Command: kubectl delete namespace drill-01 --ignore-not-found --wait=false",
            cleanup_text,
        )


if __name__ == "__main__":
    unittest.main()
