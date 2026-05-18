from collections.abc import Mapping, Sequence
from pathlib import Path

from ckad_drills.datasets import load_questions as load_question_bank
from ckad_drills.generator import build_drill, rewrite_namespace, select_questions
from ckad_drills.models import Question


def load_questions(csv_file_path: str | Path):
    return load_question_bank(csv_file_path)


def replace_namespaces(text: str, new_namespace: str | None) -> str:
    return rewrite_namespace(text, new_namespace)


def format_drill(
    drill: Question | Mapping[str, str],
    new_namespace: str | None = None,
) -> dict[str, str]:
    question = drill if isinstance(drill, Question) else Question.from_row(drill)
    formatted = build_drill(question, new_namespace)
    return {
        "id": formatted.question_id,
        "domain": formatted.domain,
        "topic": formatted.topic,
        "scenario": formatted.scenario,
        "tasks": formatted.tasks,
        "verify": formatted.verify,
        "hints": formatted.hints,
    }


def select_drills(
    questions: Sequence[Question],
    count: int = 5,
):
    return select_questions(questions, count)
