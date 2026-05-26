import argparse
import sys

from ckad_drills.config import (
    CLEANUP_MODES,
    DEFAULT_CLEANUP_MODE,
    DEFAULT_COUNT,
    DEFAULT_NAMESPACE,
)
from ckad_drills.exceptions import CleanupConfigurationError, DatasetValidationError
from ckad_drills.renderer import (
    render_cleanup_summary,
    render_drills,
    render_env_phase_summary,
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

PASSING_PERCENTAGE = 66


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
        default=DEFAULT_COUNT,
        help="Number of questions to generate.",
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


def wait_for_user_confirmation() -> None:
    try:
        input(
            "Press ENTER when you have completed all drills to run the automated grader (or Ctrl+C to exit)..."
        )
    except KeyboardInterrupt:
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
    return 0 if cleanup_summary.succeeded else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "help" or (argv is not None and "help" in argv):
        parser.print_help()
        return 0

    use_color = should_use_color()

    try:
        if args.command == "cleanup-only":
            return run_cleanup_only(args, use_color=use_color)

        validate_session_cleanup(
            args.cleanup,
            args.namespace,
            kind_cluster_name=args.kind_cluster_name,
        )
        drills = prepare_drills(args.mode, args.count, args.namespace, seed=args.seed)
    except (CleanupConfigurationError, DatasetValidationError) as exc:
        parser.exit(status=1, message=f"Error: {exc}\n")

    print(render_drills(drills, args.namespace, seed=args.seed, use_color=use_color))
    print()

    setup_summary = run_setup_phase(drills)
    setup_output = render_env_phase_summary(setup_summary, use_color=use_color)
    if setup_output:
        print(setup_output)
        print()
        if not setup_summary.succeeded:
            print(
                "Warning: one or more setup steps failed. "
                "You can still attempt the drills, but verification may not behave as expected.\n"
            )

    wait_for_user_confirmation()
    results, summary = evaluate_drills(drills)
    print()
    print(
        render_results(
            results,
            summary,
            passing_percentage=PASSING_PERCENTAGE,
            show_solutions=args.show_solutions,
            use_color=use_color,
        )
    )

    teardown_summary = run_teardown_phase(drills)
    teardown_output = render_env_phase_summary(teardown_summary, use_color=use_color)
    if teardown_output:
        print()
        print(teardown_output)

    cleanup_summary = cleanup_session(
        args.cleanup,
        args.namespace,
        kind_cluster_name=args.kind_cluster_name,
    )
    cleanup_output = render_cleanup_summary(cleanup_summary, use_color=use_color)
    if cleanup_output:
        print()
        print(cleanup_output)

    return 0 if cleanup_summary.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
