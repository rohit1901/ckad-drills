import argparse
import select
import sys
from dataclasses import dataclass

from ckad_drills.config import (
    CKAD_EXAM_QUESTION_COUNT,
    CKAD_EXAM_TIME_LIMIT_SECONDS,
    CKAD_PASSING_PERCENTAGE,
    CKAD_TIMER_POLL_INTERVAL_SECONDS,
    CLEANUP_MODES,
    DEFAULT_CLEANUP_MODE,
    DEFAULT_COUNT,
    DEFAULT_NAMESPACE,
)
from ckad_drills.exceptions import CleanupConfigurationError, DatasetValidationError
from ckad_drills.models import CleanupSummary, Drill, EnvPhaseSummary, GradeSummary
from ckad_drills.renderer import (
    render_cleanup_summary,
    render_drills,
    render_env_phase_summary,
    render_exam_timer_banner,
    render_results,
)
from ckad_drills.session import (
    cleanup_session,
    evaluate_drills,
    prepare_drills,
    run_setup_phase,
    run_teardown_phase,
    validate_session_cleanup,
)
from ckad_drills.timer import (
    SessionTimer,
    default_reminder_thresholds,
    format_duration_short,
    parse_duration,
)

# Kept as a module-level alias for backwards compatibility with tests/scripts
# that imported it from this module.
PASSING_PERCENTAGE = CKAD_PASSING_PERCENTAGE

# Exit codes
EXIT_OK = 0
EXIT_INFRA_FAILURE = 1
EXIT_EXAM_FAILED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate CKAD practice drills.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  ckad-drills
  ckad-drills help
  ckad-drills run --mode exam --count 10 --namespace drill-02 --seed 42
  ckad-drills run --mode drills --hide-solutions
  ckad-drills run --cleanup namespace --namespace drill-01
  ckad-drills run --cleanup kind-cluster --kind-cluster-name ckad-practice
  ckad-drills cleanup-only --cleanup objects --namespace drill-01
""",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["run", "cleanup-only", "help"],
        default="run",
        help="Command to execute (default: run). Use 'help' to see this message.",
    )
    parser.add_argument(
        "--mode",
        choices=["exam", "drills"],
        default="drills",
        help="'exam' uses the balanced exam CSV.\n'drills' uses the full question bank.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help=(
            f"Number of questions. Default: {CKAD_EXAM_QUESTION_COUNT} in exam mode, "
            f"{DEFAULT_COUNT} in drills mode."
        ),
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help="Namespace to substitute into generated tasks and verify commands.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible drill selection.",
    )
    parser.add_argument(
        "--time-limit",
        default=None,
        help=(
            "Exam time limit. Examples: '120m', '2h', '7200s'. Default: 120m in "
            "exam mode; no limit in drills mode. Use --no-timer to disable."
        ),
    )
    parser.add_argument(
        "--no-timer",
        action="store_true",
        help="Disable the exam timer even in exam mode.",
    )
    parser.add_argument(
        "--cleanup",
        choices=CLEANUP_MODES,
        default=DEFAULT_CLEANUP_MODE,
        help="Cleanup mode to run after grading: objects, namespace, kind-cluster, or none.",
    )
    parser.add_argument(
        "--kind-cluster-name",
        default=None,
        help="Kind cluster name to delete when --cleanup kind-cluster is selected.",
    )
    solutions_group = parser.add_mutually_exclusive_group()
    solutions_group.add_argument(
        "--show-solutions",
        dest="show_solutions",
        action="store_true",
        help="Show solution review with verify commands and hints at the end.",
    )
    solutions_group.add_argument(
        "--hide-solutions",
        dest="show_solutions",
        action="store_false",
        help="Hide the solution review section at the end.",
    )
    parser.set_defaults(show_solutions=True)
    return parser


def wait_for_user_confirmation(timer: SessionTimer | None = None) -> bool:
    """Block until the user confirms or the exam timer expires.

    Returns ``True`` if the timer fired (auto-grade mode) and ``False`` if the
    user pressed Enter. Ctrl+C still exits the session as before.
    """
    prompt = (
        "Press ENTER when you have completed all drills to run the automated "
        "grader (or Ctrl+C to exit)..."
    )
    if timer is not None and timer.started:
        prompt = (
            f"Exam timer running ({format_duration_short(timer.total_seconds)} total). "
            "Press ENTER to grade early, or wait for time to expire (Ctrl+C to exit)..."
        )

    if timer is None:
        try:
            input(prompt)
        except KeyboardInterrupt:
            print("\nExiting without grading.")
            raise SystemExit(0) from None
        return False

    return _wait_with_timer_polling(timer, prompt)


def _wait_with_timer_polling(
    timer: SessionTimer,
    prompt: str,
    poll_interval_seconds: float = CKAD_TIMER_POLL_INTERVAL_SECONDS,
) -> bool:
    """Display ``prompt`` and wait for either ENTER or timer expiry."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    stdin_fd = sys.stdin
    try:
        while True:
            if timer.expired:
                sys.stdout.write("\n")
                sys.stdout.flush()
                return True
            try:
                ready, _, _ = select.select([stdin_fd], [], [], poll_interval_seconds)
            except (OSError, ValueError):
                try:
                    stdin_fd.readline()
                except KeyboardInterrupt:
                    if timer.expired:
                        return True
                    print("\nExiting without grading.")
                    raise SystemExit(0) from None
                return timer.expired
            if ready:
                line = stdin_fd.readline()
                if line == "":
                    return timer.expired
                return False
    except KeyboardInterrupt:
        if timer.expired:
            return True
        print("\nExiting without grading.")
        raise SystemExit(0) from None


def should_use_color() -> bool:
    return sys.stdout.isatty()


def run_cleanup_only(args: argparse.Namespace, *, use_color: bool) -> int:
    if args.cleanup == "none":
        raise CleanupConfigurationError(
            "cleanup-only requires a cleanup mode other than 'none'."
        )

    validate_session_cleanup(
        args.cleanup,
        args.namespace,
        kind_cluster_name=args.kind_cluster_name,
    )
    cleanup_summary = cleanup_session(
        args.cleanup,
        args.namespace,
        kind_cluster_name=args.kind_cluster_name,
    )
    cleanup_output = render_cleanup_summary(cleanup_summary, use_color=use_color)
    if cleanup_output:
        print(cleanup_output)
    return EXIT_OK if cleanup_summary.succeeded else EXIT_INFRA_FAILURE


def _resolve_count(args: argparse.Namespace) -> int:
    if args.count is not None:
        return args.count
    return CKAD_EXAM_QUESTION_COUNT if args.mode == "exam" else DEFAULT_COUNT


def _resolve_time_limit_seconds(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int | None:
    """Return the exam time limit in seconds, or None if disabled."""
    if args.no_timer:
        return None
    if args.time_limit is not None:
        try:
            return parse_duration(args.time_limit)
        except ValueError as exc:
            parser.exit(status=1, message=f"Error: {exc}\n")
    if args.mode == "exam":
        return CKAD_EXAM_TIME_LIMIT_SECONDS
    return None


@dataclass
class _PreparedSession:
    drills: list[Drill]
    time_limit_seconds: int | None
    reminder_thresholds: tuple[int, ...]


class SessionRunner:
    """Owns the per-phase flow for a single ``ckad-drills run`` invocation.

    ``main()`` parses argv and constructs one of these; ``run()`` walks the
    setup → wait → grade → teardown → cleanup pipeline and returns an exit
    code. Splitting the pipeline into named phases makes it possible to test
    them in isolation while preserving stdout/stderr ordering.
    """

    def __init__(self, args: argparse.Namespace, *, use_color: bool) -> None:
        self.args = args
        self.use_color = use_color
        self.timer: SessionTimer | None = None

    # ---- top-level orchestration -----------------------------------------
    def run(self, parser: argparse.ArgumentParser) -> int:
        prepared = self._prepare(parser)
        self._render_drills(prepared)
        self._render_pre_setup_timer_banner(prepared)
        setup_summary = self._render_setup(prepared.drills)
        self._maybe_start_timer(prepared)
        auto_graded, elapsed_seconds = self._wait_for_user()
        results, summary = self._grade(prepared.drills)
        self._render_results(
            results,
            summary,
            elapsed_seconds=elapsed_seconds,
            time_limit_seconds=prepared.time_limit_seconds,
            auto_graded=auto_graded,
        )
        self._teardown(prepared.drills)
        cleanup_summary = self._cleanup()
        return self._exit_code(cleanup_summary, summary)

    # ---- phases ----------------------------------------------------------
    def _prepare(self, parser: argparse.ArgumentParser) -> _PreparedSession:
        validate_session_cleanup(
            self.args.cleanup,
            self.args.namespace,
            kind_cluster_name=self.args.kind_cluster_name,
        )
        self.args.count = _resolve_count(self.args)
        time_limit_seconds = _resolve_time_limit_seconds(self.args, parser)
        drills = prepare_drills(
            self.args.mode,
            self.args.count,
            self.args.namespace,
            seed=self.args.seed,
        )
        reminder_thresholds: tuple[int, ...] = ()
        if time_limit_seconds is not None and drills:
            reminder_thresholds = default_reminder_thresholds(time_limit_seconds)
        return _PreparedSession(
            drills=drills,
            time_limit_seconds=time_limit_seconds,
            reminder_thresholds=reminder_thresholds,
        )

    def _render_drills(self, prepared: _PreparedSession) -> None:
        print(
            render_drills(
                prepared.drills,
                self.args.namespace,
                seed=self.args.seed,
                use_color=self.use_color,
            )
        )
        print()

    def _render_pre_setup_timer_banner(self, prepared: _PreparedSession) -> None:
        if prepared.time_limit_seconds is None or not prepared.drills:
            return
        print(
            render_exam_timer_banner(
                prepared.time_limit_seconds,
                prepared.reminder_thresholds,
                started=False,
                use_color=self.use_color,
            )
        )
        print()

    def _render_setup(self, drills: list[Drill]) -> EnvPhaseSummary | None:
        setup_summary = run_setup_phase(drills)
        setup_output = render_env_phase_summary(setup_summary, use_color=self.use_color)
        if setup_output:
            print(setup_output)
            print()
            if not setup_summary.succeeded:
                print(
                    "Warning: one or more setup steps failed. "
                    "You can still attempt the drills, but verification may not behave as expected.\n"
                )
        return setup_summary

    def _maybe_start_timer(self, prepared: _PreparedSession) -> None:
        if prepared.time_limit_seconds is None or not prepared.drills:
            return
        self.timer = SessionTimer(
            total_seconds=prepared.time_limit_seconds,
            reminder_thresholds_seconds=prepared.reminder_thresholds,
        )
        self.timer.start()
        print(
            render_exam_timer_banner(
                prepared.time_limit_seconds,
                prepared.reminder_thresholds,
                started=True,
                use_color=self.use_color,
            )
        )
        print()

    def _wait_for_user(self) -> tuple[bool, float | None]:
        auto_graded = False
        elapsed_seconds: float | None = None
        try:
            auto_graded = wait_for_user_confirmation(self.timer)
        finally:
            if self.timer is not None:
                elapsed_seconds = self.timer.elapsed_seconds()
                self.timer.cancel()
        return auto_graded, elapsed_seconds

    def _grade(self, drills: list[Drill]):
        return evaluate_drills(drills)

    def _render_results(
        self,
        results,
        summary: GradeSummary,
        *,
        elapsed_seconds: float | None,
        time_limit_seconds: int | None,
        auto_graded: bool,
    ) -> None:
        print()
        print(
            render_results(
                results,
                summary,
                passing_percentage=CKAD_PASSING_PERCENTAGE,
                show_solutions=self.args.show_solutions,
                use_color=self.use_color,
                elapsed_seconds=elapsed_seconds,
                time_limit_seconds=time_limit_seconds,
                auto_graded=auto_graded,
            )
        )

    def _teardown(self, drills: list[Drill]) -> None:
        teardown_summary = run_teardown_phase(drills)
        teardown_output = render_env_phase_summary(
            teardown_summary, use_color=self.use_color
        )
        if teardown_output:
            print()
            print(teardown_output)

    def _cleanup(self) -> CleanupSummary:
        cleanup_summary = cleanup_session(
            self.args.cleanup,
            self.args.namespace,
            kind_cluster_name=self.args.kind_cluster_name,
        )
        cleanup_output = render_cleanup_summary(
            cleanup_summary, use_color=self.use_color
        )
        if cleanup_output:
            print()
            print(cleanup_output)
        return cleanup_summary

    def _exit_code(
        self, cleanup_summary: CleanupSummary, grade_summary: GradeSummary
    ) -> int:
        if not cleanup_summary.succeeded:
            return EXIT_INFRA_FAILURE
        if (
            grade_summary.total > 0
            and grade_summary.percentage < CKAD_PASSING_PERCENTAGE
        ):
            return EXIT_EXAM_FAILED
        return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "help" or (argv is not None and "help" in argv):
        parser.print_help()
        return EXIT_OK

    use_color = should_use_color()

    try:
        if args.command == "cleanup-only":
            return run_cleanup_only(args, use_color=use_color)
        return SessionRunner(args, use_color=use_color).run(parser)
    except (CleanupConfigurationError, DatasetValidationError) as exc:
        parser.exit(status=EXIT_INFRA_FAILURE, message=f"Error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
