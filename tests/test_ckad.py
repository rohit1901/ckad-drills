import importlib
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from random import Random
from unittest.mock import patch

TESTS_ROOT = Path(__file__).resolve().parent
SRC_ROOT = TESTS_ROOT.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

_cli = importlib.import_module("ckad_drills.cli")
main = _cli.main
build_parser = _cli.build_parser
_datasets = importlib.import_module("ckad_drills.datasets")
load_question_bank = _datasets.load_question_bank
load_questions = _datasets.load_questions
validate_exam_blueprint_references = _datasets.validate_exam_blueprint_references
_exceptions = importlib.import_module("ckad_drills.exceptions")
CleanupConfigurationError = _exceptions.CleanupConfigurationError
DatasetValidationError = _exceptions.DatasetValidationError
_generator = importlib.import_module("ckad_drills.generator")
build_drills = _generator.build_drills
rewrite_namespace = _generator.rewrite_namespace
select_exam_questions = _generator.select_exam_questions
select_questions = _generator.select_questions
_grading = importlib.import_module("ckad_drills.grading")
grade_drills = _grading.grade_drills
summarize_results = _grading.summarize_results
_renderer = importlib.import_module("ckad_drills.renderer")
render_cleanup_summary = _renderer.render_cleanup_summary
render_drills = _renderer.render_drills
render_results = _renderer.render_results
_session = importlib.import_module("ckad_drills.session")
cleanup_session = _session.cleanup_session
load_configured_question_bank = _session.load_configured_question_bank
prepare_drills = _session.prepare_drills
_cleanup = importlib.import_module("ckad_drills.cleanup")
build_cleanup_plan = _cleanup.build_cleanup_plan
cleanup_environment = _cleanup.cleanup_environment
validate_cleanup_settings = _cleanup.validate_cleanup_settings
_models = importlib.import_module("ckad_drills.models")
CleanupStepResult = _models.CleanupStepResult
CleanupSummary = _models.CleanupSummary
Drill = _models.Drill
GradeSummary = _models.GradeSummary

FIXTURE_PATH = TESTS_ROOT / "fixtures" / "sample_questions.csv"
EXTRA_BANK_FIXTURE = TESTS_ROOT / "fixtures" / "sample_questions_extra.csv"
SAMPLE_EXAM_BLUEPRINT_FIXTURE = TESTS_ROOT / "fixtures" / "sample_exam_blueprint.csv"
INVALID_EXAM_BLUEPRINT_FIXTURE = (
    TESTS_ROOT / "fixtures" / "invalid_exam_blueprint_unknown_id.csv"
)
INVALID_SCHEMA_FIXTURE = (
    TESTS_ROOT / "fixtures" / "invalid_questions_missing_verify.csv"
)
INVALID_ROW_FIXTURE = TESTS_ROOT / "fixtures" / "invalid_questions_empty_verify.csv"


class TestDatasets(unittest.TestCase):
    def test_load_questions_returns_typed_questions(self):
        questions = load_questions(FIXTURE_PATH)

        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0].question_id, "Q01")
        self.assertEqual(questions[1].verify, "kubectl get svc -n team-alpha")

    def test_load_question_bank_merges_base_and_extension_files(self):
        questions = load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE])

        self.assertEqual(len(questions), 3)
        self.assertEqual(
            [question.question_id for question in questions], ["Q01", "Q02", "Q03"]
        )

    def test_load_question_bank_rejects_duplicate_ids(self):
        with self.assertRaises(DatasetValidationError) as context:
            load_question_bank([FIXTURE_PATH, FIXTURE_PATH])

        self.assertIn("Duplicate question id 'Q01'", str(context.exception))

    def test_validate_exam_blueprint_references_rejects_unknown_ids(self):
        question_bank = load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE])
        blueprint_questions = load_questions(INVALID_EXAM_BLUEPRINT_FIXTURE)

        with self.assertRaises(DatasetValidationError) as context:
            validate_exam_blueprint_references(
                blueprint_questions,
                question_bank,
                blueprint_path=INVALID_EXAM_BLUEPRINT_FIXTURE,
            )

        self.assertIn("invalid_exam_blueprint_unknown_id.csv", str(context.exception))
        self.assertIn("Q99", str(context.exception))

    def test_load_questions_rejects_missing_required_columns(self):
        with self.assertRaises(DatasetValidationError) as context:
            load_questions(INVALID_SCHEMA_FIXTURE)

        self.assertIn("invalid_questions_missing_verify.csv", str(context.exception))
        self.assertIn("verify", str(context.exception))

    def test_load_questions_rejects_missing_required_row_values(self):
        with self.assertRaises(DatasetValidationError) as context:
            load_questions(INVALID_ROW_FIXTURE)

        self.assertIn("invalid_questions_empty_verify.csv", str(context.exception))
        self.assertIn("missing value(s) for verify", str(context.exception))


class TestGenerator(unittest.TestCase):
    def test_select_questions_uses_bounded_sample(self):
        questions = load_questions(FIXTURE_PATH)

        selected = select_questions(questions, 5, rng=Random(7))

        self.assertEqual(len(selected), 2)

    def test_select_questions_rejects_negative_count(self):
        questions = load_questions(FIXTURE_PATH)

        with self.assertRaises(ValueError):
            select_questions(questions, -1)

    def test_select_questions_is_reproducible_with_same_seed(self):
        questions = load_questions(FIXTURE_PATH)

        first = select_questions(questions, 2, rng=Random(11))
        second = select_questions(questions, 2, rng=Random(11))

        self.assertEqual(
            [question.question_id for question in first],
            [question.question_id for question in second],
        )

    def test_select_exam_questions_uses_full_bank_for_dynamic_variation(self):
        question_bank = load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE])
        blueprint_slot = [load_questions(SAMPLE_EXAM_BLUEPRINT_FIXTURE)[0]]

        picked_ids = {
            select_exam_questions(question_bank, blueprint_slot, 1, rng=Random(seed))[
                0
            ].question_id
            for seed in range(10)
        }

        self.assertIn("Q01", picked_ids)
        self.assertIn("Q03", picked_ids)

    def test_rewrite_namespace_updates_kubectl_and_dns_references(self):
        text = "kubectl get pod -n default && nslookup db-service.default.svc.cluster.local"

        rewritten = rewrite_namespace(text, "drill-01")

        self.assertEqual(
            rewritten,
            "kubectl get pod -n drill-01 && nslookup db-service.drill-01.svc.cluster.local",
        )

    def test_build_drills_returns_drill_models(self):
        questions = load_questions(FIXTURE_PATH)

        drills = build_drills(questions, "drill-01")

        self.assertEqual(len(drills), 2)
        self.assertIsInstance(drills[0], Drill)
        self.assertIn("drill-01", drills[0].tasks)
        self.assertIn("drill-01", drills[1].verify)


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


class TestSession(unittest.TestCase):
    def test_load_configured_question_bank_includes_extensions(self):
        with (
            patch.object(
                _session, "resolve_base_question_bank_path", return_value=FIXTURE_PATH
            ),
            patch.object(
                _session,
                "resolve_question_bank_extension_paths",
                return_value=[EXTRA_BANK_FIXTURE],
            ),
        ):
            questions = load_configured_question_bank()

        self.assertEqual(
            [question.question_id for question in questions], ["Q01", "Q02", "Q03"]
        )

    def test_prepare_drills_is_reproducible_with_seed(self):
        with patch.object(
            _session,
            "load_configured_question_bank",
            return_value=load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE]),
        ):
            first = prepare_drills("drills", 2, "drill-01", seed=5)
            second = prepare_drills("drills", 2, "drill-01", seed=5)

        self.assertEqual(
            [drill.question_id for drill in first],
            [drill.question_id for drill in second],
        )

    def test_prepare_exam_drills_uses_blueprint_and_full_bank(self):
        with (
            patch.object(
                _session,
                "load_base_question_bank",
                return_value=load_question_bank([FIXTURE_PATH]),
            ),
            patch.object(
                _session,
                "load_configured_question_bank",
                return_value=load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE]),
            ),
            patch.object(
                _session,
                "resolve_exam_blueprint_path",
                return_value=SAMPLE_EXAM_BLUEPRINT_FIXTURE,
            ),
        ):
            drills = prepare_drills("exam", 2, "drill-01", seed=7)

        self.assertEqual(len(drills), 2)
        self.assertTrue(
            all(drill.question_id in {"Q01", "Q02", "Q03"} for drill in drills)
        )

    def test_cleanup_session_uses_cleanup_module(self):
        summary = cleanup_session("objects", "drill-01", runner=lambda command: True)

        self.assertTrue(summary.attempted)
        self.assertTrue(summary.succeeded)


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


class TestCli(unittest.TestCase):
    def test_help_command_returns_zero(self):
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            result = main(["help"])

        self.assertEqual(result, 0)
        self.assertIn("Generate CKAD practice drills.", buffer.getvalue())

    def test_parser_supports_seed_solution_and_cleanup_flags(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "cleanup-only",
                "--seed",
                "99",
                "--hide-solutions",
                "--cleanup",
                "kind-cluster",
                "--kind-cluster-name",
                "ckad-practice",
            ]
        )

        self.assertEqual(args.command, "cleanup-only")
        self.assertEqual(args.seed, 99)
        self.assertFalse(args.show_solutions)
        self.assertEqual(args.cleanup, "kind-cluster")
        self.assertEqual(args.kind_cluster_name, "ckad-practice")

    def test_main_prints_friendly_dataset_validation_error(self):
        stderr_buffer = io.StringIO()

        with patch.object(
            _cli, "prepare_drills", side_effect=DatasetValidationError("bad csv")
        ):
            with redirect_stderr(stderr_buffer):
                with self.assertRaises(SystemExit) as context:
                    main(["run"])

        self.assertEqual(context.exception.code, 1)
        self.assertIn("Error: bad csv", stderr_buffer.getvalue())

    def test_main_returns_one_when_cleanup_fails(self):
        results = []
        summary = GradeSummary(
            passed=0,
            total=0,
            domain_scores=(),
            failed_results=(),
        )
        cleanup_summary = CleanupSummary(
            mode="namespace",
            target="drill-01",
            attempted=True,
            succeeded=False,
            steps=(
                CleanupStepResult(
                    label="Delete practice namespace",
                    command="kubectl delete namespace drill-01 --ignore-not-found --wait=false",
                    succeeded=False,
                ),
            ),
        )

        with (
            patch.object(_cli, "prepare_drills", return_value=[]),
            patch.object(_cli, "wait_for_user_confirmation", return_value=None),
            patch.object(_cli, "evaluate_drills", return_value=(results, summary)),
            patch.object(_cli, "cleanup_session", return_value=cleanup_summary),
            patch.object(_cli, "should_use_color", return_value=False),
        ):
            result = main(["run", "--cleanup", "namespace"])

        self.assertEqual(result, 1)

    def test_cleanup_only_command_runs_without_session(self):
        cleanup_summary = CleanupSummary(
            mode="objects",
            target="drill-01",
            attempted=True,
            succeeded=True,
            steps=(
                CleanupStepResult(
                    label="Delete common namespaced resources",
                    command="kubectl delete deployments -n drill-01 --all --ignore-not-found",
                    succeeded=True,
                ),
            ),
        )

        with (
            patch.object(_cli, "cleanup_session", return_value=cleanup_summary),
            patch.object(_cli, "should_use_color", return_value=False),
        ):
            result = main(
                ["cleanup-only", "--cleanup", "objects", "--namespace", "drill-01"]
            )

        self.assertEqual(result, 0)

    def test_cleanup_only_rejects_none_cleanup_mode(self):
        stderr_buffer = io.StringIO()

        with redirect_stderr(stderr_buffer):
            with self.assertRaises(SystemExit) as context:
                main(["cleanup-only", "--cleanup", "none"])

        self.assertEqual(context.exception.code, 1)
        self.assertIn(
            "cleanup-only requires a cleanup mode other than 'none'",
            stderr_buffer.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
