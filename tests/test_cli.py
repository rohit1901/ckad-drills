import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from ckad_drills import cli as _cli
from ckad_drills.cli import (
    _resolve_time_limit_seconds,
    build_parser,
    main,
    wait_for_user_confirmation,
)
from ckad_drills.config import CKAD_EXAM_TIME_LIMIT_SECONDS
from ckad_drills.exceptions import DatasetValidationError
from ckad_drills.models import (
    CleanupStepResult,
    CleanupSummary,
    GradeSummary,
)
from ckad_drills.renderer import render_results


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


class TestResolveTimeLimit(unittest.TestCase):
    def _args(self, **kw):
        parser = build_parser()
        argv = ["run"]
        if "time_limit" in kw:
            argv += ["--time-limit", kw.pop("time_limit")]
        if kw.pop("no_timer", False):
            argv.append("--no-timer")
        if "mode" in kw:
            argv += ["--mode", kw.pop("mode")]
        return parser, parser.parse_args(argv)

    def test_exam_mode_default_uses_config_constant(self):
        parser, args = self._args(mode="exam")
        self.assertEqual(
            _resolve_time_limit_seconds(args, parser),
            CKAD_EXAM_TIME_LIMIT_SECONDS,
        )

    def test_drills_mode_default_is_untimed(self):
        parser, args = self._args(mode="drills")
        self.assertIsNone(_resolve_time_limit_seconds(args, parser))

    def test_no_timer_beats_explicit_time_limit(self):
        parser, args = self._args(mode="exam", time_limit="30m", no_timer=True)
        self.assertIsNone(_resolve_time_limit_seconds(args, parser))

    def test_explicit_time_limit_used_in_drills_mode(self):
        parser, args = self._args(mode="drills", time_limit="45m")
        self.assertEqual(_resolve_time_limit_seconds(args, parser), 45 * 60)

    def test_invalid_time_limit_exits_with_friendly_error(self):
        parser, args = self._args(mode="exam", time_limit="not-a-duration")
        stderr_buffer = io.StringIO()
        with redirect_stderr(stderr_buffer):
            with self.assertRaises(SystemExit) as ctx:
                _resolve_time_limit_seconds(args, parser)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("Error:", stderr_buffer.getvalue())


class TestCliTimerWiring(unittest.TestCase):
    def test_parser_exposes_time_limit_and_no_timer_flags(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--time-limit", "90m", "--no-timer"])
        self.assertEqual(args.time_limit, "90m")
        self.assertTrue(args.no_timer)

    def test_wait_for_user_confirmation_returns_true_when_timer_already_expired(self):
        class _FakeTimer:
            started = True
            expired = True
            total_seconds = 60

        with patch("sys.stdout.write"), patch("sys.stdout.flush"):
            self.assertTrue(wait_for_user_confirmation(_FakeTimer()))  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    def test_wait_for_user_confirmation_returns_true_when_timer_expires_during_poll(
        self,
    ):
        class _FakeTimer:
            started = True
            total_seconds = 60
            _polls = 0

            @property
            def expired(self):
                self.__class__._polls += 1
                return self.__class__._polls >= 2

        _FakeTimer._polls = 0
        with (
            patch("sys.stdout.write"),
            patch("sys.stdout.flush"),
            patch("ckad_drills.cli.select.select", return_value=([], [], [])),
        ):
            self.assertTrue(wait_for_user_confirmation(_FakeTimer()))  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    def test_wait_for_user_confirmation_returns_false_when_user_presses_enter(self):
        class _FakeTimer:
            started = True
            expired = False
            total_seconds = 60

        fake_stdin = io.StringIO("\n")
        with (
            patch("sys.stdout.write"),
            patch("sys.stdout.flush"),
            patch("sys.stdin", fake_stdin),
            patch(
                "ckad_drills.cli.select.select",
                return_value=([fake_stdin], [], []),
            ),
        ):
            self.assertFalse(wait_for_user_confirmation(_FakeTimer()))  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    def test_wait_for_user_confirmation_exits_on_user_ctrl_c(self):
        class _FakeTimer:
            started = True
            expired = False
            total_seconds = 60

        with (
            patch("sys.stdout.write"),
            patch("sys.stdout.flush"),
            patch(
                "ckad_drills.cli.select.select",
                side_effect=KeyboardInterrupt,
            ),
        ):
            with self.assertRaises(SystemExit) as ctx:
                wait_for_user_confirmation(_FakeTimer())  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        self.assertEqual(ctx.exception.code, 0)

    def test_wait_for_user_confirmation_returns_false_on_enter(self):
        with patch("builtins.input", return_value=""):
            self.assertFalse(wait_for_user_confirmation(None))


class TestRenderResultsTiming(unittest.TestCase):
    def _summary(self):
        return GradeSummary(passed=0, total=0, domain_scores=(), failed_results=())

    def test_timing_line_renders_when_elapsed_provided(self):
        out = render_results(
            [],
            self._summary(),
            passing_percentage=66,
            show_solutions=False,
            elapsed_seconds=75 * 60,
            time_limit_seconds=120 * 60,
        )
        self.assertIn("EXAM TIMING", out)
        self.assertIn("TIME USED: 1h15m / 2h", out)
        self.assertNotIn("AUTO-GRADED", out)

    def test_auto_graded_banner_included(self):
        out = render_results(
            [],
            self._summary(),
            passing_percentage=66,
            show_solutions=False,
            elapsed_seconds=120 * 60,
            time_limit_seconds=120 * 60,
            auto_graded=True,
        )
        self.assertIn("AUTO-GRADED", out)

    def test_timing_omitted_when_no_elapsed(self):
        out = render_results(
            [],
            self._summary(),
            passing_percentage=66,
            show_solutions=False,
        )
        self.assertNotIn("EXAM TIMING", out)
        self.assertNotIn("TIME USED", out)


class TestCliExamRunIntegration(unittest.TestCase):
    """End-to-end-ish test that exam mode constructs and cancels a timer."""

    def test_run_exam_mode_starts_timer_and_cancels_it(self):
        from ckad_drills import cli as cli_module

        captured = {}

        class _SpyTimer:
            def __init__(self, *, total_seconds, reminder_thresholds_seconds):
                self.total_seconds = total_seconds
                self.started = False
                self.cancelled = False
                self.expired = False
                captured["timer"] = self

            def start(self):
                self.started = True

            def cancel(self):
                self.cancelled = True

            def elapsed_seconds(self):
                return 42.0

        cleanup_summary = CleanupSummary(
            mode="none",
            target="drill-01",
            attempted=False,
            succeeded=True,
            steps=(),
        )
        grade_summary = GradeSummary(
            passed=0, total=0, domain_scores=(), failed_results=()
        )

        sentinel_drills = [object()]

        stdout_buffer = io.StringIO()
        with (
            patch.object(cli_module, "SessionTimer", _SpyTimer),
            patch.object(cli_module, "prepare_drills", return_value=sentinel_drills),
            patch.object(cli_module, "run_setup_phase") as run_setup,
            patch.object(cli_module, "run_teardown_phase") as run_teardown,
            patch.object(cli_module, "render_drills", return_value=""),
            patch.object(cli_module, "render_env_phase_summary", return_value=""),
            patch.object(cli_module, "render_cleanup_summary", return_value=""),
            patch.object(cli_module, "wait_for_user_confirmation", return_value=False),
            patch.object(
                cli_module,
                "evaluate_drills",
                return_value=([], grade_summary),
            ),
            patch.object(cli_module, "cleanup_session", return_value=cleanup_summary),
            patch.object(cli_module, "should_use_color", return_value=False),
            patch.object(
                cli_module,
                "render_results",
                side_effect=lambda *a, **kw: (
                    f"ELAPSED={kw.get('elapsed_seconds')};LIMIT={kw.get('time_limit_seconds')};AUTO={kw.get('auto_graded')}"
                ),
            ),
            redirect_stdout(stdout_buffer),
        ):
            run_setup.return_value = None
            run_teardown.return_value = None
            rc = main(["run", "--mode", "exam", "--no-timer"])

        self.assertEqual(rc, 0)
        self.assertNotIn("timer", captured)
        self.assertIn("ELAPSED=None", stdout_buffer.getvalue())
        self.assertIn("LIMIT=None", stdout_buffer.getvalue())

    def test_run_exam_mode_with_timer_passes_elapsed_to_renderer(self):
        from ckad_drills import cli as cli_module

        captured = {}

        class _SpyTimer:
            def __init__(self, *, total_seconds, reminder_thresholds_seconds):
                self.total_seconds = total_seconds
                self.started = False
                self.cancelled = False
                self.expired = False
                captured["timer"] = self

            def start(self):
                self.started = True

            def cancel(self):
                self.cancelled = True

            def elapsed_seconds(self):
                return 42.0

        cleanup_summary = CleanupSummary(
            mode="none",
            target="drill-01",
            attempted=False,
            succeeded=True,
            steps=(),
        )
        grade_summary = GradeSummary(
            passed=0, total=0, domain_scores=(), failed_results=()
        )
        sentinel_drills = [object()]

        stdout_buffer = io.StringIO()
        with (
            patch.object(cli_module, "SessionTimer", _SpyTimer),
            patch.object(cli_module, "prepare_drills", return_value=sentinel_drills),
            patch.object(cli_module, "run_setup_phase"),
            patch.object(cli_module, "run_teardown_phase"),
            patch.object(cli_module, "render_drills", return_value=""),
            patch.object(cli_module, "render_env_phase_summary", return_value=""),
            patch.object(cli_module, "render_cleanup_summary", return_value=""),
            patch.object(cli_module, "wait_for_user_confirmation", return_value=True),
            patch.object(
                cli_module,
                "evaluate_drills",
                return_value=([], grade_summary),
            ),
            patch.object(cli_module, "cleanup_session", return_value=cleanup_summary),
            patch.object(cli_module, "should_use_color", return_value=False),
            patch.object(
                cli_module,
                "render_results",
                side_effect=lambda *a, **kw: (
                    f"ELAPSED={kw.get('elapsed_seconds')};LIMIT={kw.get('time_limit_seconds')};AUTO={kw.get('auto_graded')}"
                ),
            ),
            redirect_stdout(stdout_buffer),
        ):
            rc = main(["run", "--mode", "exam", "--time-limit", "30m"])

        self.assertEqual(rc, 0)
        timer = captured["timer"]
        self.assertTrue(timer.started)
        self.assertTrue(timer.cancelled)
        self.assertEqual(timer.total_seconds, 30 * 60)
        output = stdout_buffer.getvalue()
        self.assertIn("ELAPSED=42.0", output)
        self.assertIn(f"LIMIT={30 * 60}", output)
        self.assertIn("AUTO=True", output)


if __name__ == "__main__":
    unittest.main()
