"""Session timer for CKAD-style timed exams.

A ``SessionTimer`` runs on background daemon threads:
- one ``threading.Timer`` per scheduled reminder (e.g. "30 min remaining"), and
- one ``threading.Timer`` for expiry, which sets ``expired = True`` and raises
  SIGINT in the main thread so any blocking ``input()`` call is interrupted.

The CLI distinguishes "user pressed Ctrl+C" from "timer expired" by checking
``timer.expired`` inside the KeyboardInterrupt handler.

Public helpers ``parse_duration`` and ``format_duration_short`` are also
defined here so the CLI can present user-facing durations consistently.
"""

import signal
import sys
import threading
import time
from typing import Callable, Iterable, TextIO


def parse_duration(text: str) -> int:
    """Parse a human duration string into integer seconds.

    Accepts ``120m``, ``2h``, ``7200s``, or a bare integer (interpreted as
    seconds). Raises ``ValueError`` for empty, non-numeric, or non-positive
    inputs.
    """
    if text is None:
        raise ValueError("duration cannot be empty")
    raw = text.strip().lower()
    if not raw:
        raise ValueError("duration cannot be empty")

    multiplier = 1
    number_part = raw
    if raw.endswith("s"):
        number_part = raw[:-1]
        multiplier = 1
    elif raw.endswith("m"):
        number_part = raw[:-1]
        multiplier = 60
    elif raw.endswith("h"):
        number_part = raw[:-1]
        multiplier = 3600

    try:
        value = int(number_part)
    except ValueError as exc:
        raise ValueError(
            f"invalid duration {text!r}; use forms like '120m', '2h', '7200s'."
        ) from exc

    if value <= 0:
        raise ValueError(f"duration must be positive, got {text!r}.")
    return value * multiplier


def format_duration_short(total_seconds: float) -> str:
    """Format a duration as ``1h47m``, ``47m``, ``59s``.

    Anything >= 60s is rendered with hour/minute precision; below a minute we
    fall back to seconds so the renderer can still show a meaningful value.
    """
    total = int(max(0, total_seconds))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours and minutes:
        return f"{hours}h{minutes:02d}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def compute_reminder_schedule(
    total_seconds: int,
    reminder_thresholds_seconds: Iterable[int],
) -> list[tuple[int, int]]:
    """Return [(delay_until_fire, threshold_remaining), ...] sorted by delay.

    A threshold is dropped if it would fire at-or-before t=0 (i.e. it's >=
    total_seconds), since reminders should be in the future.
    """
    schedule: list[tuple[int, int]] = []
    for threshold in reminder_thresholds_seconds:
        if threshold <= 0 or threshold >= total_seconds:
            continue
        delay = total_seconds - threshold
        schedule.append((delay, threshold))
    schedule.sort(key=lambda pair: pair[0])
    return schedule


class SessionTimer:
    """Background timer with reminder banners and SIGINT-on-expiry."""

    def __init__(
        self,
        total_seconds: int,
        *,
        reminder_thresholds_seconds: Iterable[int] = (),
        stderr: TextIO | None = None,
        on_expire: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        timer_factory: Callable[..., threading.Timer] = threading.Timer,
    ) -> None:
        if total_seconds <= 0:
            raise ValueError("total_seconds must be positive")
        self.total_seconds = int(total_seconds)
        self._reminder_thresholds = tuple(reminder_thresholds_seconds)
        self._stderr = stderr if stderr is not None else sys.stderr
        self._on_expire = on_expire or self._default_on_expire
        self._clock = clock
        self._timer_factory = timer_factory
        self._start_time: float | None = None
        self._timers: list[threading.Timer] = []
        self._lock = threading.Lock()
        self._expired = False
        self._cancelled = False

    # ---- public API --------------------------------------------------------
    @property
    def expired(self) -> bool:
        return self._expired

    @property
    def started(self) -> bool:
        return self._start_time is not None

    def elapsed_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return max(0.0, self._clock() - self._start_time)

    def remaining_seconds(self) -> float:
        if self._start_time is None:
            return float(self.total_seconds)
        return max(0.0, self.total_seconds - self.elapsed_seconds())

    def start(self) -> None:
        """Begin counting down. Idempotent: a second call is a no-op."""
        with self._lock:
            if self._start_time is not None or self._cancelled:
                return
            self._start_time = self._clock()
            schedule = compute_reminder_schedule(
                self.total_seconds, self._reminder_thresholds
            )
            for delay, threshold in schedule:
                t = self._timer_factory(delay, self._fire_reminder, args=(threshold,))
                t.daemon = True
                t.start()
                self._timers.append(t)
            expiry = self._timer_factory(self.total_seconds, self._fire_expiry)
            expiry.daemon = True
            expiry.start()
            self._timers.append(expiry)

    def cancel(self) -> None:
        """Stop all pending reminders and the expiry callback."""
        with self._lock:
            self._cancelled = True
            for t in self._timers:
                t.cancel()
            self._timers = []

    # ---- background callbacks ---------------------------------------------
    def _fire_reminder(self, threshold_seconds: int) -> None:
        if self._cancelled or self._expired:
            return
        message = f"\n[exam] {format_duration_short(threshold_seconds)} remaining\n"
        try:
            self._stderr.write(message)
            self._stderr.flush()
        except Exception:
            pass

    def _fire_expiry(self) -> None:
        with self._lock:
            if self._cancelled or self._expired:
                return
            self._expired = True
        try:
            self._stderr.write("\n[exam] TIME'S UP — auto-grading your work now...\n")
            self._stderr.flush()
        except Exception:
            pass
        try:
            self._on_expire()
        except Exception:
            # never let the background thread crash on cleanup
            pass

    # ---- default expiry behavior -----------------------------------------
    @staticmethod
    def _default_on_expire() -> None:
        """Interrupt the main thread's blocking ``input()`` call.

        ``signal.raise_signal`` raises the signal in the *current* process; on
        Unix this wakes up a blocking ``input()`` with KeyboardInterrupt on
        the main thread. Available on Python 3.8+.
        """
        try:
            signal.raise_signal(signal.SIGINT)
        except (AttributeError, OSError, ValueError):
            # Fall back: best-effort, may not interrupt input on some platforms.
            import os

            try:
                os.kill(os.getpid(), signal.SIGINT)
            except Exception:
                pass
