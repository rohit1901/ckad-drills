import importlib
import io
import sys
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

TESTS_ROOT = Path(__file__).resolve().parent
SRC_ROOT = TESTS_ROOT.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

_timer = importlib.import_module("ckad_drills.timer")
SessionTimer = _timer.SessionTimer
parse_duration = _timer.parse_duration
format_duration_short = _timer.format_duration_short
compute_reminder_schedule = _timer.compute_reminder_schedule
default_reminder_thresholds = _timer.default_reminder_thresholds

_cli = importlib.import_module("ckad_drills.cli")
main = _cli.main
build_parser = _cli.build_parser
wait_for_user_confirmation = _cli.wait_for_user_confirmation
_resolve_time_limit_seconds = _cli._resolve_time_limit_seconds

_config = importlib.import_module("ckad_drills.config")
CKAD_EXAM_TIME_LIMIT_SECONDS = _config.CKAD_EXAM_TIME_LIMIT_SECONDS

_renderer = importlib.import_module("ckad_drills.renderer")
render_results = _renderer.render_results

_models = importlib.import_module("ckad_drills.models")
CleanupStepResult = _models.CleanupStepResult
CleanupSummary = _models.CleanupSummary
GradeSummary = _models.GradeSummary


class TestParseDuration(unittest.TestCase):
    def test_parses_minutes_hours_seconds_and_bare_int(self):
        self.assertEqual(parse_duration("120m"), 120 * 60)
        self.assertEqual(parse_duration("2h"), 2 * 3600)
        self.assertEqual(parse_duration("7200s"), 7200)
        self.assertEqual(parse_duration("45"), 45)

    def test_is_case_insensitive_and_strips_whitespace(self):
        self.assertEqual(parse_duration("  30M "), 30 * 60)
        self.assertEqual(parse_duration("1H"), 3600)

    def test_rejects_invalid_inputs(self):
        for bad in ["", "   ", "abc", "1.5h", "-5m", "0", "0s"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_duration(bad)

        with self.assertRaises(ValueError):
            parse_duration(None)  # type: ignore[arg-type]


class TestFormatDurationShort(unittest.TestCase):
    def test_renders_hours_minutes_seconds(self):
        self.assertEqual(format_duration_short(0), "0s")
        self.assertEqual(format_duration_short(45), "45s")
        self.assertEqual(format_duration_short(60), "1m")
        self.assertEqual(format_duration_short(125), "2m")
        self.assertEqual(format_duration_short(3600), "1h")
        self.assertEqual(format_duration_short(3700), "1h01m")
        self.assertEqual(format_duration_short(2 * 3600 + 30 * 60), "2h30m")

    def test_clamps_negative(self):
        self.assertEqual(format_duration_short(-10), "0s")


class TestDefaultReminderThresholds(unittest.TestCase):
    def test_two_hour_exam_uses_canonical_ckad_thresholds(self):
        self.assertEqual(
            default_reminder_thresholds(2 * 3600),
            (60 * 60, 30 * 60, 10 * 60, 5 * 60),
        )
        # Also for longer time limits.
        self.assertEqual(
            default_reminder_thresholds(3 * 3600),
            (60 * 60, 30 * 60, 10 * 60, 5 * 60),
        )

    def test_thirty_minute_exam_scales_down(self):
        thresholds = default_reminder_thresholds(30 * 60)
        # Must give multiple reminders inside the 30m window.
        self.assertEqual(thresholds, (15 * 60, 10 * 60, 5 * 60, 60))
        # And every threshold must be strictly less than the total time so
        # they actually fire (compute_reminder_schedule drops >= total).
        self.assertTrue(all(t < 30 * 60 for t in thresholds))

    def test_ten_minute_exam_uses_sub_minute_thresholds(self):
        thresholds = default_reminder_thresholds(10 * 60)
        self.assertEqual(thresholds, (5 * 60, 2 * 60, 60, 30))

    def test_short_exam_still_produces_reminders(self):
        thresholds = default_reminder_thresholds(2 * 60)
        self.assertEqual(thresholds, (60, 30, 15))
        # ...and a ridiculously short session (1 minute) still gets at least one.
        thresholds = default_reminder_thresholds(60)
        self.assertTrue(len(thresholds) >= 1)
        self.assertTrue(all(t < 60 for t in thresholds))

    def test_degenerate_inputs(self):
        self.assertEqual(default_reminder_thresholds(0), ())
        self.assertEqual(default_reminder_thresholds(-5), ())
        # Sessions shorter than 30s get no reminders (no useful threshold).
        self.assertEqual(default_reminder_thresholds(10), ())

    def test_thresholds_produce_a_real_schedule(self):
        # Round-trip: every chosen threshold should survive the
        # compute_reminder_schedule filter for its total.
        for total in (60, 5 * 60, 30 * 60, 2 * 3600):
            with self.subTest(total=total):
                thresholds = default_reminder_thresholds(total)
                schedule = compute_reminder_schedule(total, thresholds)
                self.assertEqual(len(schedule), len(thresholds))


class TestReminderSchedule(unittest.TestCase):
    def test_drops_thresholds_outside_range_and_sorts(self):
        schedule = compute_reminder_schedule(
            7200, [3600, 1800, 600, 300, 7200, 9999, 0, -1]
        )
        # delay = total - threshold; sorted ascending by delay.
        self.assertEqual(
            schedule,
            [(3600, 3600), (5400, 1800), (6600, 600), (6900, 300)],
        )

    def test_empty_when_no_valid_thresholds(self):
        self.assertEqual(compute_reminder_schedule(120, [120, 300, 0]), [])


class _FakeTimer:
    """Stand-in for ``threading.Timer`` that fires synchronously on ``start()``.

    This lets us assert reminder/expiry behavior without sleeping.
    """

    instances: list["_FakeTimer"] = []

    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval = interval
        self.function = function
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.cancelled = False
        self.started = False
        self.daemon = False
        _FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.function(*self.args, **self.kwargs)


class TestSessionTimer(unittest.TestCase):
    def setUp(self):
        _FakeTimer.instances = []

    def _make(self, total=7200, thresholds=(3600, 1800, 600, 300), **kw):
        stderr = io.StringIO()
        timer = SessionTimer(
            total_seconds=total,
            reminder_thresholds_seconds=thresholds,
            stderr=stderr,
            timer_factory=_FakeTimer,
            **kw,
        )
        return timer, stderr

    def test_rejects_non_positive_total(self):
        with self.assertRaises(ValueError):
            SessionTimer(total_seconds=0)
        with self.assertRaises(ValueError):
            SessionTimer(total_seconds=-5)

    def test_start_schedules_reminders_and_expiry(self):
        timer, _ = self._make()
        timer.start()
        # 4 reminders + 1 expiry
        self.assertEqual(len(_FakeTimer.instances), 5)
        self.assertTrue(all(t.started and t.daemon for t in _FakeTimer.instances))
        delays = [t.interval for t in _FakeTimer.instances]
        # Reminders sorted ascending, then expiry last.
        self.assertEqual(delays, [3600, 5400, 6600, 6900, 7200])

    def test_start_is_idempotent(self):
        timer, _ = self._make()
        timer.start()
        timer.start()
        self.assertEqual(len(_FakeTimer.instances), 5)

    def test_cancel_stops_pending_timers_and_blocks_restart(self):
        timer, _ = self._make()
        timer.start()
        timer.cancel()
        self.assertTrue(all(t.cancelled for t in _FakeTimer.instances))
        # cancelled timer cannot be re-armed
        _FakeTimer.instances = []
        timer.start()
        self.assertEqual(_FakeTimer.instances, [])

    def test_reminder_writes_to_stderr(self):
        timer, stderr = self._make()
        timer.start()
        # first scheduled timer is the 1h-remaining reminder
        _FakeTimer.instances[0].fire()
        self.assertIn("1h remaining", stderr.getvalue())

    def test_expiry_sets_expired_and_invokes_on_expire(self):
        calls = []
        timer, stderr = self._make(on_expire=lambda: calls.append("fired"))
        timer.start()
        expiry = _FakeTimer.instances[-1]
        expiry.fire()
        self.assertTrue(timer.expired)
        self.assertEqual(calls, ["fired"])
        self.assertIn("TIME'S UP", stderr.getvalue())

    def test_expiry_after_cancel_is_no_op(self):
        calls = []
        timer, _ = self._make(on_expire=lambda: calls.append("fired"))
        timer.start()
        expiry = _FakeTimer.instances[-1]
        timer.cancel()
        expiry.fire()  # cancelled flag is set, fire() returns early
        self.assertFalse(timer.expired)
        self.assertEqual(calls, [])

    def test_elapsed_and_remaining_use_injected_clock(self):
        now = [1000.0]
        timer = SessionTimer(
            total_seconds=600,
            reminder_thresholds_seconds=(),
            stderr=io.StringIO(),
            clock=lambda: now[0],
            timer_factory=_FakeTimer,
        )
        self.assertEqual(timer.elapsed_seconds(), 0.0)
        self.assertEqual(timer.remaining_seconds(), 600.0)
        timer.start()
        now[0] = 1075.0
        self.assertAlmostEqual(timer.elapsed_seconds(), 75.0)
        self.assertAlmostEqual(timer.remaining_seconds(), 525.0)
        # Clamps to zero past the end.
        now[0] = 5000.0
        self.assertEqual(timer.remaining_seconds(), 0.0)

    def test_real_threading_timer_fires_expiry(self):
        """Smoke test with the real threading.Timer to catch wiring regressions."""
        done = threading.Event()
        timer = SessionTimer(
            total_seconds=1,  # parse_duration disallows sub-second, ctor accepts int
            reminder_thresholds_seconds=(),
            stderr=io.StringIO(),
            on_expire=done.set,
        )
        # Patch total_seconds to a very short delay without going through __init__.
        timer.total_seconds = 1
        # Replace the expiry-scheduling delay using a custom factory that
        # forwards to threading.Timer with a 50ms interval instead of 1s, so
        # the test stays fast.
        original_factory = timer._timer_factory

        def fast_factory(interval, function, args=None, kwargs=None):
            return threading.Timer(0.05, function, args=args or (), kwargs=kwargs or {})

        timer._timer_factory = fast_factory
        try:
            timer.start()
            self.assertTrue(done.wait(timeout=2.0), "expiry callback never fired")
            self.assertTrue(timer.expired)
        finally:
            timer.cancel()
            timer._timer_factory = original_factory


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
        # Polling loop sees timer.expired=True on its first iteration and
        # returns True without ever consulting stdin.
        class _FakeTimer:
            started = True
            expired = True
            total_seconds = 60

        with patch("sys.stdout.write"), patch("sys.stdout.flush"):
            self.assertTrue(wait_for_user_confirmation(_FakeTimer()))

    def test_wait_for_user_confirmation_returns_true_when_timer_expires_during_poll(
        self,
    ):
        # Simulate timer expiring on the second poll iteration. select.select
        # returns no ready fds (timeout), then the loop checks timer.expired
        # again and returns True.
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
            self.assertTrue(wait_for_user_confirmation(_FakeTimer()))

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
            self.assertFalse(wait_for_user_confirmation(_FakeTimer()))

    def test_wait_for_user_confirmation_exits_on_user_ctrl_c(self):
        # Ctrl+C during the polling loop while the timer hasn't expired
        # should exit cleanly with status 0 (unchanged contract).
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
                wait_for_user_confirmation(_FakeTimer())
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

        # A single sentinel "drill" so the timer branch is entered.
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
            # No-op setup/teardown summaries are fine.
            run_setup.return_value = None
            run_teardown.return_value = None
            rc = main(["run", "--mode", "exam", "--no-timer"])

        # With --no-timer, no timer is constructed.
        self.assertEqual(rc, 0)
        self.assertNotIn("timer", captured)
        self.assertIn("ELAPSED=None", stdout_buffer.getvalue())
        self.assertIn(f"LIMIT=None", stdout_buffer.getvalue())

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
