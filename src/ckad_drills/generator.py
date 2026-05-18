import random
import re
from collections.abc import Sequence

from ckad_drills.config import KNOWN_NAMESPACES
from ckad_drills.exceptions import DatasetValidationError
from ckad_drills.models import Drill, Question


def select_questions(
    questions: Sequence[Question],
    count: int,
    *,
    rng: random.Random | None = None,
) -> list[Question]:
    if count < 0:
        raise ValueError("count must be non-negative")
    if count == 0 or not questions:
        return []

    picker = rng.sample if rng is not None else random.sample
    return picker(list(questions), min(count, len(questions)))


def select_exam_questions(
    question_bank: Sequence[Question],
    blueprint_questions: Sequence[Question],
    count: int,
    *,
    rng: random.Random | None = None,
) -> list[Question]:
    selected_slots = select_questions(blueprint_questions, count, rng=rng)
    if not selected_slots:
        return []

    chooser = rng.choice if rng is not None else random.choice
    used_ids: set[str] = set()
    selected_questions = []

    for slot in selected_slots:
        exact_candidates = [
            question
            for question in question_bank
            if question.question_id not in used_ids
            and question.domain == slot.domain
            and question.topic == slot.topic
        ]
        domain_candidates = [
            question
            for question in question_bank
            if question.question_id not in used_ids and question.domain == slot.domain
        ]
        candidates = exact_candidates or domain_candidates
        if not candidates:
            raise DatasetValidationError(
                "Could not build a balanced exam from the current question bank. "
                f"No unused question matched blueprint slot '{slot.question_id}' "
                f"for domain '{slot.domain}' and topic '{slot.topic}'."
            )

        chosen_question = chooser(candidates)
        used_ids.add(chosen_question.question_id)
        selected_questions.append(chosen_question)

    return selected_questions


def rewrite_namespace(text: str, target_namespace: str | None) -> str:
    if not text or not target_namespace:
        return text

    updated_text = text
    for namespace in KNOWN_NAMESPACES:
        updated_text = re.sub(
            rf"\b{re.escape(namespace)}\b",
            target_namespace,
            updated_text,
        )
    return updated_text


def build_drill(question: Question, target_namespace: str | None) -> Drill:
    return Drill.from_question(
        question,
        tasks=rewrite_namespace(question.tasks, target_namespace),
        verify=rewrite_namespace(question.verify, target_namespace),
    )


def build_drills(
    questions: Sequence[Question], target_namespace: str | None
) -> list[Drill]:
    return [build_drill(question, target_namespace) for question in questions]
