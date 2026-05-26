from collections.abc import Callable, Sequence

from ckad_drills.check_evaluator import evaluate_check
from ckad_drills.models import (
    CheckResult,
    DomainScore,
    Drill,
    GradeResult,
    GradeSummary,
)

CommandRunner = Callable[[str], bool]
CaptureRunner = Callable[[str], tuple[int, str, str]]


def grade_drills(
    drills: Sequence[Drill],
    runner: CommandRunner,
    *,
    capture_runner: CaptureRunner | None = None,
) -> list[GradeResult]:
    """Grade each drill.

    If a drill carries structured ``checks`` (from a YAML bank), each check is
    evaluated individually against captured shell output via ``capture_runner``
    and the drill passes only when every check passes. Otherwise we fall back
    to the legacy single-command boolean ``runner``.
    """
    results: list[GradeResult] = []
    for index, drill in enumerate(drills, start=1):
        if drill.checks and capture_runner is not None:
            check_results = _evaluate_structured_checks(drill, capture_runner)
            passed = all(cr.passed for cr in check_results)
            results.append(
                GradeResult(
                    drill_number=index,
                    question_id=drill.question_id,
                    domain=drill.domain,
                    topic=drill.topic,
                    passed=passed,
                    verify_command=drill.verify,
                    hints=drill.hints,
                    check_results=tuple(check_results),
                )
            )
            continue

        passed = runner(drill.verify)
        results.append(
            GradeResult(
                drill_number=index,
                question_id=drill.question_id,
                domain=drill.domain,
                topic=drill.topic,
                passed=passed,
                verify_command=drill.verify,
                hints=drill.hints,
            )
        )
    return results


def _evaluate_structured_checks(
    drill: Drill, capture_runner: CaptureRunner
) -> list[CheckResult]:
    results: list[CheckResult] = []
    for check in drill.checks:
        exit_code, stdout, stderr = capture_runner(check.run)
        results.append(evaluate_check(check, exit_code, stdout, stderr))
    return results


def summarize_results(results: Sequence[GradeResult]) -> GradeSummary:
    domain_totals: dict[str, dict[str, int]] = {}
    failed_results = []

    for result in results:
        counters = domain_totals.setdefault(result.domain, {"passed": 0, "total": 0})
        counters["total"] += 1
        counters["passed"] += int(result.passed)
        if not result.passed:
            failed_results.append(result)

    domain_scores = tuple(
        DomainScore(
            domain=domain,
            passed=counters["passed"],
            total=counters["total"],
        )
        for domain, counters in domain_totals.items()
    )
    passed = sum(result.passed for result in results)
    return GradeSummary(
        passed=passed,
        total=len(results),
        domain_scores=domain_scores,
        failed_results=tuple(failed_results),
    )
