from ckad_drills.models import (
    CleanupSummary,
    Drill,
    EnvPhaseSummary,
    GradeResult,
    GradeSummary,
)
from ckad_drills.timer import format_duration_short

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"


def colorize(text: str, *styles: str, use_color: bool) -> str:
    if not use_color:
        return text
    prefix = "".join(styles)
    return f"{prefix}{text}{RESET}"


def render_drills(
    drills: list[Drill],
    namespace: str,
    *,
    seed: int | None = None,
    use_color: bool = False,
) -> str:
    lines = [
        colorize("=" * 72, CYAN, use_color=use_color),
        colorize("CKAD DRILL GENERATOR", BOLD, CYAN, use_color=use_color),
        colorize("=" * 72, CYAN, use_color=use_color),
        "",
    ]

    if seed is not None:
        lines.extend(
            [
                colorize(f"Seed: {seed}", MAGENTA, use_color=use_color),
                "",
            ]
        )

    for index, drill in enumerate(drills, start=1):
        lines.extend(
            [
                colorize(
                    f"【Drill {index}】 {drill.domain} - {drill.topic}",
                    BOLD,
                    YELLOW,
                    use_color=use_color,
                ),
                colorize("-" * 72, CYAN, use_color=use_color),
                colorize("SCENARIO:", BOLD, use_color=use_color),
                f"{drill.scenario}\n",
                colorize("TASKS:", BOLD, use_color=use_color),
                f"{drill.tasks}\n",
            ]
        )

    lines.extend(
        [
            colorize("=" * 72, CYAN, use_color=use_color),
            colorize(
                f"Tip: kubectl create ns {namespace} && kubectl config set-context --current --namespace={namespace}",
                GREEN,
                use_color=use_color,
            ),
            colorize("=" * 72, CYAN, use_color=use_color),
        ]
    )
    return "\n".join(lines)


def render_exam_timer_banner(
    total_seconds: int,
    reminder_thresholds_seconds: tuple[int, ...] = (),
    *,
    started: bool = False,
    use_color: bool = False,
) -> str:
    """Render a prominent banner announcing the exam timer.

    Used twice in a session: once up front (``started=False``) so the user
    knows a time limit is in effect before they start solving, and once
    immediately after setup completes (``started=True``) so the user sees
    when the clock actually starts ticking.
    """
    title = "EXAM TIMER STARTED" if started else "EXAM TIMER ENABLED"
    lines = [
        colorize("=" * 72, CYAN, use_color=use_color),
        colorize(title, BOLD, YELLOW, use_color=use_color),
        colorize("=" * 72, CYAN, use_color=use_color),
    ]
    if started:
        lines.append(
            colorize(
                f"⏱  Timer is running. Total: {format_duration_short(total_seconds)}.",
                BOLD,
                YELLOW,
                use_color=use_color,
            )
        )
    else:
        lines.append(
            colorize(
                f"⏱  Time limit: {format_duration_short(total_seconds)} (countdown begins after setup).",
                BOLD,
                YELLOW,
                use_color=use_color,
            )
        )
    if reminder_thresholds_seconds:
        thresholds_text = " / ".join(
            format_duration_short(t) for t in reminder_thresholds_seconds
        )
        lines.append(
            colorize(
                f"   Reminders will print at {thresholds_text} remaining.",
                YELLOW,
                use_color=use_color,
            )
        )
    lines.append(
        colorize(
            "   Press ENTER any time to grade early; Ctrl+C exits without grading.",
            YELLOW,
            use_color=use_color,
        )
    )
    lines.append(colorize("=" * 72, CYAN, use_color=use_color))
    return "\n".join(lines)


def render_results(
    results: list[GradeResult],
    summary: GradeSummary,
    *,
    passing_percentage: int,
    show_solutions: bool = True,
    use_color: bool = False,
    elapsed_seconds: float | None = None,
    time_limit_seconds: int | None = None,
    auto_graded: bool = False,
) -> str:
    lines = [
        colorize("=" * 72, CYAN, use_color=use_color),
        colorize("GRADING RESULTS", BOLD, CYAN, use_color=use_color),
        colorize("=" * 72, CYAN, use_color=use_color),
    ]

    for result in results:
        status = colorize("✅ PASS", GREEN, use_color=use_color)
        if not result.passed:
            status = colorize("❌ FAIL", RED, use_color=use_color)
        lines.append(
            f"Checking Drill {result.drill_number} ({result.domain})... {status}"
        )

    lines.extend(
        [
            "",
            colorize("PER-DOMAIN SCORECARD", BOLD, CYAN, use_color=use_color),
            colorize("=" * 72, CYAN, use_color=use_color),
        ]
    )
    for domain_score in summary.domain_scores:
        score_style = GREEN if domain_score.percentage >= passing_percentage else YELLOW
        lines.append(
            colorize(
                f"- {domain_score.domain}: {domain_score.passed}/{domain_score.total} ({domain_score.percentage:.0f}%)",
                score_style,
                use_color=use_color,
            )
        )

    result_line = "RESULT: 🎉 PASSING SCORE!"
    result_style = GREEN
    if summary.percentage < passing_percentage:
        result_line = "RESULT: 💻 KEEP PRACTICING!"
        result_style = RED

    if elapsed_seconds is not None:
        if time_limit_seconds is not None:
            timing_line = (
                f"TIME USED: {format_duration_short(elapsed_seconds)} / "
                f"{format_duration_short(time_limit_seconds)}"
            )
        else:
            timing_line = f"TIME USED: {format_duration_short(elapsed_seconds)}"
        lines.extend(
            [
                "",
                colorize("EXAM TIMING", BOLD, CYAN, use_color=use_color),
                colorize("=" * 72, CYAN, use_color=use_color),
                timing_line,
            ]
        )
        if auto_graded:
            lines.append(
                colorize(
                    "AUTO-GRADED: time limit reached before user confirmed.",
                    BOLD,
                    YELLOW,
                    use_color=use_color,
                )
            )

    lines.extend(
        [
            "",
            colorize("FINAL SCORE", BOLD, CYAN, use_color=use_color),
            colorize("=" * 72, CYAN, use_color=use_color),
            f"SCORE: {summary.passed} / {summary.total}",
            f"PERCENTAGE: {summary.percentage:.0f}%",
            colorize(result_line, BOLD, result_style, use_color=use_color),
        ]
    )

    if not show_solutions:
        return "\n".join(lines)

    lines.extend(
        [
            "",
            colorize("SOLUTION REVIEW", BOLD, CYAN, use_color=use_color),
            colorize("=" * 72, CYAN, use_color=use_color),
        ]
    )
    for result in results:
        status = colorize("PASS", GREEN, use_color=use_color)
        if not result.passed:
            status = colorize("FAIL", RED, use_color=use_color)
        lines.extend(
            [
                f"[Drill {result.drill_number}] {result.question_id} | {result.domain} | {result.topic} | {status}",
                f"Verify command: {result.verify_command}",
                f"Hints: {result.hints}",
            ]
        )
        if result.check_results:
            lines.append(colorize("Checks:", BOLD, use_color=use_color))
            for check in result.check_results:
                check_status = colorize("PASS", GREEN, use_color=use_color)
                if not check.passed:
                    check_status = colorize("FAIL", RED, use_color=use_color)
                lines.append(f"  - [{check_status}] {check.name}")
                lines.append(f"      run:    {check.run}")
                lines.append(f"      detail: {check.detail}")
        lines.append(colorize("-" * 72, CYAN, use_color=use_color))

    return "\n".join(lines)


def render_env_phase_summary(
    summary: EnvPhaseSummary,
    *,
    use_color: bool = False,
) -> str:
    if not summary.attempted:
        return ""

    heading = "SETUP" if summary.phase == "setup" else "TEARDOWN"
    status_text = colorize("SUCCESS", GREEN, use_color=use_color)
    if not summary.succeeded:
        status_text = colorize("FAILED", RED, use_color=use_color)

    lines = [
        colorize("=" * 72, CYAN, use_color=use_color),
        colorize(heading, BOLD, CYAN, use_color=use_color),
        colorize("=" * 72, CYAN, use_color=use_color),
        f"Status: {status_text}",
        "",
    ]
    for step in summary.steps:
        step_status = colorize("OK", GREEN, use_color=use_color)
        if not step.succeeded:
            step_status = colorize("FAILED", RED, use_color=use_color)
        lines.append(f"- {step.label}: {step_status}")
        lines.append(f"  Command: {step.command.splitlines()[0]}")
        if step.output:
            for output_line in step.output.splitlines():
                lines.append(f"    {output_line}")

    return "\n".join(lines)


def render_cleanup_summary(
    summary: CleanupSummary,
    *,
    use_color: bool = False,
) -> str:
    if not summary.attempted:
        return ""

    status_text = colorize("SUCCESS", GREEN, use_color=use_color)
    if not summary.succeeded:
        status_text = colorize("FAILED", RED, use_color=use_color)

    lines = [
        colorize("=" * 72, CYAN, use_color=use_color),
        colorize("CLEANUP", BOLD, CYAN, use_color=use_color),
        colorize("=" * 72, CYAN, use_color=use_color),
        f"Mode: {summary.mode}",
        f"Target: {summary.target}",
        f"Status: {status_text}",
        "",
    ]

    for step in summary.steps:
        step_status = colorize("OK", GREEN, use_color=use_color)
        if not step.succeeded:
            step_status = colorize("FAILED", RED, use_color=use_color)
        lines.extend(
            [
                f"- {step.label}: {step_status}",
                f"  Command: {step.command}",
            ]
        )

    return "\n".join(lines)
