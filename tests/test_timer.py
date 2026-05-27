import io
import threading
import unittest

from ckad_drills.timer import (
    SessionTimer,
    compute_reminder_schedule,
    default_reminder_thresholds,
    format_duration_short,
    parse_duration,
)


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
            parse_duration(None)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


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
        self.assertEqual(
            default_reminder_thresholds(3 * 3600),
            (60 * 60, 30 * 60, 10 * 60, 5 * 60),
        )

    def test_thirty_minute_exam_scales_down(self):
        thresholds = default_reminder_thresholds(30 * 60)
        self.assertEqual(thresholds, (15 * 60, 10 * 60, 5 * 60, 60))
        self.assertTrue(all(t < 30 * 60 for t in thresholds))

    def test_ten_minute_exam_uses_sub_minute_thresholds(self):
        thresholds = default_reminder_thresholds(10 * 60)
        self.assertEqual(thresholds, (5 * 60, 2 * 60, 60, 30))

    def test_short_exam_still_produces_reminders(self):
        thresholds = default_reminder_thresholds(2 * 60)
        self.assertEqual(thresholds, (60, 30, 15))
        thresholds = default_reminder_thresholds(60)
        self.assertTrue(len(thresholds) >= 1)
        self.assertTrue(all(t < 60 for t in thresholds))

    def test_degenerate_inputs(self):
        self.assertEqual(default_reminder_thresholds(0), ())
        self.assertEqual(default_reminder_thresholds(-5), ())
        self.assertEqual(default_reminder_thresholds(10), ())

    def test_thresholds_produce_a_real_schedule(self):
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
        self.assertEqual(
            schedule,
            [(3600, 3600), (5400, 1800), (6600, 600), (6900, 300)],
        )

    def test_empty_when_no_valid_thresholds(self):
        self.assertEqual(compute_reminder_schedule(120, [120, 300, 0]), [])


class _FakeTimer:
    """Stand-in for ``threading.Timer`` that fires synchronously on ``start()``."""

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
            timer_factory=_FakeTimer,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
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
        self.assertEqual(len(_FakeTimer.instances), 5)
        self.assertTrue(all(t.started and t.daemon for t in _FakeTimer.instances))
        delays = [t.interval for t in _FakeTimer.instances]
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
        _FakeTimer.instances = []
        timer.start()
        self.assertEqual(_FakeTimer.instances, [])

    def test_reminder_writes_to_stderr(self):
        timer, stderr = self._make()
        timer.start()
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
        expiry.fire()
        self.assertFalse(timer.expired)
        self.assertEqual(calls, [])

    def test_elapsed_and_remaining_use_injected_clock(self):
        now = [1000.0]
        timer = SessionTimer(
            total_seconds=600,
            reminder_thresholds_seconds=(),
            stderr=io.StringIO(),
            clock=lambda: now[0],
            timer_factory=_FakeTimer,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        )
        self.assertEqual(timer.elapsed_seconds(), 0.0)
        self.assertEqual(timer.remaining_seconds(), 600.0)
        timer.start()
        now[0] = 1075.0
        self.assertAlmostEqual(timer.elapsed_seconds(), 75.0)
        self.assertAlmostEqual(timer.remaining_seconds(), 525.0)
        now[0] = 5000.0
        self.assertEqual(timer.remaining_seconds(), 0.0)

    def test_real_threading_timer_fires_expiry(self):
        """Smoke test with the real threading.Timer to catch wiring regressions."""
        done = threading.Event()
        timer = SessionTimer(
            total_seconds=1,
            reminder_thresholds_seconds=(),
            stderr=io.StringIO(),
            on_expire=done.set,
        )
        timer.total_seconds = 1
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


if __name__ == "__main__":
    unittest.main()
