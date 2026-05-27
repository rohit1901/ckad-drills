from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class CheckKind(str, Enum):
    """Kind tag for a verify-check expectation.

    Inheriting from ``str`` keeps backwards compatibility with code (and
    tests) that compares ``check.kind == "equals"`` or uses the raw string
    in YAML I/O.
    """

    EQUALS = "equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    REGEX = "regex"
    EXIT_CODE = "exit_code"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# Backwards-compatible aliases used across the codebase.
CHECK_KIND_EQUALS = CheckKind.EQUALS
CHECK_KIND_CONTAINS = CheckKind.CONTAINS
CHECK_KIND_NOT_CONTAINS = CheckKind.NOT_CONTAINS
CHECK_KIND_REGEX = CheckKind.REGEX
CHECK_KIND_EXIT_CODE = CheckKind.EXIT_CODE

CHECK_KINDS = tuple(kind.value for kind in CheckKind)

# Type aliases for shell runners injected into session, grading, and
# environment-phase code paths. Kept here next to the data classes they
# consume so the rest of the codebase doesn't have to import them from a
# specific feature module.
CommandRunner = Callable[[str], bool]
CaptureRunner = Callable[[str], tuple[int, str, str]]


@dataclass(frozen=True)
class VerifyCheck:
    """A single declarative verification step for a YAML-based drill."""

    name: str
    run: str
    kind: str  # CheckKind value (str subclass) for YAML compatibility
    value: str  # for exit_code, the integer encoded as string


@dataclass(frozen=True)
class EnvStep:
    """A single setup or teardown step executed as a shell command."""

    label: str
    run: str


@dataclass(frozen=True)
class Question:
    question_id: str
    domain: str
    topic: str
    scenario: str
    tasks: str
    verify: str
    hints: str
    checks: tuple[VerifyCheck, ...] = field(default_factory=tuple)
    setup_steps: tuple[EnvStep, ...] = field(default_factory=tuple)
    teardown_steps: tuple[EnvStep, ...] = field(default_factory=tuple)

    @classmethod
    def from_row(cls, row: Mapping[str, str]) -> "Question":
        return cls(
            question_id=row.get("id") or row.get("exam_id") or "",
            domain=row.get("domain", ""),
            topic=row.get("topic", ""),
            scenario=row.get("scenario", ""),
            tasks=row.get("tasks", ""),
            verify=row.get("verify", ""),
            hints=row.get("hints", ""),
        )


@dataclass(frozen=True)
class Drill:
    question_id: str
    domain: str
    topic: str
    scenario: str
    tasks: str
    verify: str
    hints: str
    checks: tuple[VerifyCheck, ...] = field(default_factory=tuple)
    setup_steps: tuple[EnvStep, ...] = field(default_factory=tuple)
    teardown_steps: tuple[EnvStep, ...] = field(default_factory=tuple)

    @classmethod
    def from_question(
        cls,
        question: Question,
        *,
        tasks: str | None = None,
        verify: str | None = None,
        checks: tuple[VerifyCheck, ...] | None = None,
        setup_steps: tuple[EnvStep, ...] | None = None,
        teardown_steps: tuple[EnvStep, ...] | None = None,
    ) -> "Drill":
        # Copy every field from ``question`` and only override the ones the
        # caller actually wants to rewrite (typically namespace substitutions).
        return cls(
            question_id=question.question_id,
            domain=question.domain,
            topic=question.topic,
            scenario=question.scenario,
            tasks=question.tasks if tasks is None else tasks,
            verify=question.verify if verify is None else verify,
            hints=question.hints,
            checks=question.checks if checks is None else checks,
            setup_steps=question.setup_steps if setup_steps is None else setup_steps,
            teardown_steps=(
                question.teardown_steps if teardown_steps is None else teardown_steps
            ),
        )


@dataclass(frozen=True)
class CheckResult:
    """Per-check outcome captured during structured grading."""

    name: str
    run: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GradeResult:
    drill_number: int
    question_id: str
    domain: str
    topic: str
    passed: bool
    verify_command: str
    hints: str
    check_results: tuple[CheckResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DomainScore:
    domain: str
    passed: int
    total: int

    @property
    def percentage(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100


@dataclass(frozen=True)
class GradeSummary:
    passed: int
    total: int
    domain_scores: tuple[DomainScore, ...]
    failed_results: tuple[GradeResult, ...]

    @property
    def percentage(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100


@dataclass(frozen=True)
class CleanupStepResult:
    label: str
    command: str
    succeeded: bool


@dataclass(frozen=True)
class CleanupSummary:
    mode: str
    target: str
    attempted: bool
    succeeded: bool
    steps: tuple[CleanupStepResult, ...]


@dataclass(frozen=True)
class EnvStepResult:
    """Outcome of executing a single setup or teardown step."""

    label: str
    command: str
    succeeded: bool
    output: str


@dataclass(frozen=True)
class EnvPhaseSummary:
    """Aggregate result for a setup or teardown phase."""

    phase: str  # "setup" or "teardown"
    steps: tuple[EnvStepResult, ...]

    @property
    def attempted(self) -> bool:
        return len(self.steps) > 0

    @property
    def succeeded(self) -> bool:
        return all(step.succeeded for step in self.steps)
