from dataclasses import dataclass
from typing import Iterable

from ckad_drills.models import (
    CleanupSummary,
    Drill,
    EnvPhaseSummary,
    GradeResult,
    GradeSummary,
)
from ckad_drills.timer import format_duration_short

# Raw ANSI escape strings; kept at module level for backwards compatibility
# with any caller that imports them by name.
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"


@dataclass(frozen=True)
class Style:
    """ANSI palette used by the renderer.

    Pass ``Style.plain()`` to disable all escape sequences (for piped output
    or non-TTY contexts). Pass ``Style.ansi()`` for a coloured terminal.
    """

    reset: str = ""
    bold: str = ""
    cyan: str = ""
    green: str = ""
    red: str = ""
    yellow: str = ""
    magenta: str = ""

    @classmethod
    def plain(cls) -> "Style":
        return cls()

    @classmethod
    def ansi(cls) -> "Style":
        return cls(
            reset=RESET,
            bold=BOLD,
            cyan=CYAN,
            green=GREEN,
            red=RED,
            yellow=YELLOW,
            magenta=MAGENTA,
        )

    @classmethod
    def for_color(cls, use_color: bool) -> "Style":
        return cls.ansi() if use_color else cls.plain()

    def paint(self, text: str, *styles: str) -> str:
        prefix = "".join(s for s in styles if s)
        if not prefix:
            return text
        return f"{prefix}{text}{self.reset}"


# Kept for back-compat with any caller still importing ``colorize``.
def colorize(text: str, *styles: str, use_color: bool) -> str:
    style = Style.for_color(use_color)
    if not use_color:
        return text
    return style.paint(text, *styles)


_DIVIDER_WIDTH = 72


def _divider(style: Style) -> str:
    return style.paint("=" * _DIVIDER_WIDTH, style.cyan)


def _subdivider(style: Style) -> str:
    return style.paint("-" * _DIVIDER_WIDTH, style.cyan)


def _section_header(title: str, style: Style) -> list[str]:
    """The ``= * 72 / title / = * 72`` banner used across the renderer."""
    return [
        _divider(style),
        style.paint(title, style.bold, style.cyan),
        _divider(style),
    ]


def render_section(title: str, body_lines: Iterable[str], *, style: Style) -> str:
    """Render a titled section with the standard divider box."""
    return "\n".join([*_section_header(title, style), *body_lines])


def render_drills(
    drills: list[Drill],
    namespace: str,
    *,
    seed: int | None = None,
    use_color: bool = False,
) -> str:
    style = Style.for_color(use_color)
    lines = [
        _divider(style),
        style.paint("CKAD DRILL GENERATOR", style.bold, style.cyan),
        _divider(style),
        "",
    ]

    if seed is not None:
        lines.extend([style.paint(f"Seed: {seed}", style.magenta), ""])

    for index, drill in enumerate(drills, start=1):
        lines.extend(
            [
                style.paint(
                    f"【Drill {index}】 {drill.domain} - {drill.topic}",
                    style.bold,
                    style.yellow,
                ),
                _subdivider(style),
                style.paint("SCENARIO:", style.bold),
                f"{drill.scenario}\n",
                style.paint("TASKS:", style.bold),
                f"{drill.tasks}\n",
            ]
        )

    lines.extend(
        [
            _divider(style),
            style.paint(
                f"Tip: kubectl create ns {namespace} && kubectl config set-context --current --namespace={namespace}",
                style.green,
            ),
            _divider(style),
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
    style = Style.for_color(use_color)
    title = "EXAM TIMER STARTED" if started else "EXAM TIMER ENABLED"
    lines = [
        _divider(style),
        style.paint(title, style.bold, style.yellow),
        _divider(style),
    ]
    if started:
        lines.append(
            style.paint(
                f"⏱  Timer is running. Total: {format_duration_short(total_seconds)}.",
                style.bold,
                style.yellow,
            )
        )
    else:
        lines.append(
            style.paint(
                f"⏱  Time limit: {format_duration_short(total_seconds)} (countdown begins after setup).",
                style.bold,
                style.yellow,
            )
        )
    if reminder_thresholds_seconds:
        thresholds_text = " / ".join(
            format_duration_short(t) for t in reminder_thresholds_seconds
        )
        lines.append(
            style.paint(
                f"   Reminders will print at {thresholds_text} remaining.",
                style.yellow,
            )
        )
    lines.append(
        style.paint(
            "   Press ENTER any time to grade early; Ctrl+C exits without grading.",
            style.yellow,
        )
    )
    lines.append(_divider(style))
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
    style = Style.for_color(use_color)
    lines = _section_header("GRADING RESULTS", style)

    for result in results:
        status = style.paint("✅ PASS", style.green)
        if not result.passed:
            status = style.paint("❌ FAIL", style.red)
        lines.append(
            f"Checking Drill {result.drill_number} ({result.domain})... {status}"
        )

    lines.extend(
        [
            "",
            style.paint("PER-DOMAIN SCORECARD", style.bold, style.cyan),
            _divider(style),
        ]
    )
    for domain_score in summary.domain_scores:
        score_color = (
            style.green
            if domain_score.percentage >= passing_percentage
            else style.yellow
        )
        lines.append(
            style.paint(
                f"- {domain_score.domain}: {domain_score.passed}/{domain_score.total} ({domain_score.percentage:.0f}%)",
                score_color,
            )
        )

    result_line = "RESULT: 🎉 PASSING SCORE!"
    result_color = style.green
    if summary.percentage < passing_percentage:
        result_line = "RESULT: 💻 KEEP PRACTICING!"
        result_color = style.red

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
                style.paint("EXAM TIMING", style.bold, style.cyan),
                _divider(style),
                timing_line,
            ]
        )
        if auto_graded:
            lines.append(
                style.paint(
                    "AUTO-GRADED: time limit reached before user confirmed.",
                    style.bold,
                    style.yellow,
                )
            )

    lines.extend(
        [
            "",
            style.paint("FINAL SCORE", style.bold, style.cyan),
            _divider(style),
            f"SCORE: {summary.passed} / {summary.total}",
            f"PERCENTAGE: {summary.percentage:.0f}%",
            style.paint(result_line, style.bold, result_color),
        ]
    )

    if not show_solutions:
        return "\n".join(lines)

    lines.extend(
        ["", style.paint("SOLUTION REVIEW", style.bold, style.cyan), _divider(style)]
    )
    for result in results:
        status = style.paint("PASS", style.green)
        if not result.passed:
            status = style.paint("FAIL", style.red)
        lines.extend(
            [
                f"[Drill {result.drill_number}] {result.question_id} | {result.domain} | {result.topic} | {status}",
                f"Verify command: {result.verify_command}",
                f"Hints: {result.hints}",
            ]
        )
        if result.check_results:
            lines.append(style.paint("Checks:", style.bold))
            for check in result.check_results:
                check_status = style.paint("PASS", style.green)
                if not check.passed:
                    check_status = style.paint("FAIL", style.red)
                lines.append(f"  - [{check_status}] {check.name}")
                lines.append(f"      run:    {check.run}")
                lines.append(f"      detail: {check.detail}")
        lines.append(_subdivider(style))

    return "\n".join(lines)


def render_env_phase_summary(
    summary: EnvPhaseSummary,
    *,
    use_color: bool = False,
) -> str:
    if not summary.attempted:
        return ""

    style = Style.for_color(use_color)
    heading = "SETUP" if summary.phase == "setup" else "TEARDOWN"
    status_text = style.paint("SUCCESS", style.green)
    if not summary.succeeded:
        status_text = style.paint("FAILED", style.red)

    lines = [
        *_section_header(heading, style),
        f"Status: {status_text}",
        "",
    ]
    for step in summary.steps:
        step_status = style.paint("OK", style.green)
        if not step.succeeded:
            step_status = style.paint("FAILED", style.red)
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

    style = Style.for_color(use_color)
    status_text = style.paint("SUCCESS", style.green)
    if not summary.succeeded:
        status_text = style.paint("FAILED", style.red)

    lines = [
        *_section_header("CLEANUP", style),
        f"Mode: {summary.mode}",
        f"Target: {summary.target}",
        f"Status: {status_text}",
        "",
    ]

    for step in summary.steps:
        step_status = style.paint("OK", style.green)
        if not step.succeeded:
            step_status = style.paint("FAILED", style.red)
        lines.extend(
            [
                f"- {step.label}: {step_status}",
                f"  Command: {step.command}",
            ]
        )

    return "\n".join(lines)
