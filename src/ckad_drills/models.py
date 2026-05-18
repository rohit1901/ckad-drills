from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Question:
    question_id: str
    domain: str
    topic: str
    scenario: str
    tasks: str
    verify: str
    hints: str

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

    @classmethod
    def from_question(
        cls,
        question: Question,
        *,
        tasks: str | None = None,
        verify: str | None = None,
    ) -> "Drill":
        return cls(
            question_id=question.question_id,
            domain=question.domain,
            topic=question.topic,
            scenario=question.scenario,
            tasks=question.tasks if tasks is None else tasks,
            verify=question.verify if verify is None else verify,
            hints=question.hints,
        )


@dataclass(frozen=True)
class GradeResult:
    drill_number: int
    question_id: str
    domain: str
    topic: str
    passed: bool
    verify_command: str
    hints: str


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
