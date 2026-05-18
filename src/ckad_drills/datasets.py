import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

from ckad_drills.exceptions import DatasetValidationError
from ckad_drills.models import Question

REQUIRED_COLUMNS = ("domain", "topic", "scenario", "tasks", "verify", "hints")
REQUIRED_ROW_VALUES = ("domain", "topic", "scenario", "tasks", "verify")
QUESTION_ID_COLUMNS = ("id", "exam_id")


def _missing_columns(fieldnames: Iterable[str] | None) -> list[str]:
    if fieldnames is None:
        return [*QUESTION_ID_COLUMNS, *REQUIRED_COLUMNS]

    available = set(fieldnames)
    missing = [column for column in REQUIRED_COLUMNS if column not in available]
    if not any(column in available for column in QUESTION_ID_COLUMNS):
        missing.append("id or exam_id")
    return missing


def _validate_headers(csv_file_path: Path, fieldnames: Iterable[str] | None) -> None:
    missing = _missing_columns(fieldnames)
    if not missing:
        return

    missing_text = ", ".join(missing)
    raise DatasetValidationError(
        f"Invalid CSV schema in '{csv_file_path.name}'. Missing required column(s): {missing_text}."
    )


def _validate_row(path: Path, row_number: int, row: dict[str, str]) -> None:
    missing_values = []
    if not any((row.get(column) or "").strip() for column in QUESTION_ID_COLUMNS):
        missing_values.append("id/exam_id")

    for column in REQUIRED_ROW_VALUES:
        if not (row.get(column) or "").strip():
            missing_values.append(column)

    if missing_values:
        missing_text = ", ".join(missing_values)
        raise DatasetValidationError(
            f"Invalid CSV row in '{path.name}' at line {row_number}: missing value(s) for {missing_text}."
        )


def load_questions(csv_file_path: str | Path) -> list[Question]:
    path = Path(csv_file_path)
    with path.open(mode="r", encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle)
        _validate_headers(path, reader.fieldnames)

        questions = []
        for row_number, row in enumerate(reader, start=2):
            _validate_row(path, row_number, row)
            questions.append(Question.from_row(row))
        return questions


def load_question_bank(csv_paths: Sequence[str | Path]) -> list[Question]:
    questions = []
    seen_ids: dict[str, str] = {}

    for csv_path in csv_paths:
        path = Path(csv_path)
        for question in load_questions(path):
            existing_source = seen_ids.get(question.question_id)
            if existing_source is not None:
                raise DatasetValidationError(
                    f"Duplicate question id '{question.question_id}' found in '{path.name}'. Already defined in '{existing_source}'."
                )
            seen_ids[question.question_id] = path.name
            questions.append(question)

    return questions


def validate_exam_blueprint_references(
    blueprint_questions: Sequence[Question],
    question_bank: Sequence[Question],
    *,
    blueprint_path: str | Path,
) -> None:
    bank_ids = {question.question_id for question in question_bank}
    missing_ids = sorted(
        {
            question.question_id
            for question in blueprint_questions
            if question.question_id not in bank_ids
        }
    )
    if not missing_ids:
        return

    missing_text = ", ".join(missing_ids)
    path = Path(blueprint_path)
    raise DatasetValidationError(
        f"Invalid exam blueprint in '{path.name}'. The following id value(s) do not exist in the full question bank: {missing_text}."
    )
