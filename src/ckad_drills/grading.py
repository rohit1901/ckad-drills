from collections.abc import Callable, Sequence

from ckad_drills.models import DomainScore, Drill, GradeResult, GradeSummary

CommandRunner = Callable[[str], bool]


def grade_drills(
    drills: Sequence[Drill],
    runner: CommandRunner,
) -> list[GradeResult]:
    results = []
    for index, drill in enumerate(drills, start=1):
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
