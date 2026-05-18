import random

from ckad_drills.cleanup import cleanup_environment, validate_cleanup_settings
from ckad_drills.config import (
    resolve_base_question_bank_path,
    resolve_exam_blueprint_path,
    resolve_question_bank_extension_paths,
)
from ckad_drills.datasets import (
    load_question_bank,
    load_questions,
    validate_exam_blueprint_references,
)
from ckad_drills.generator import build_drills, select_exam_questions, select_questions
from ckad_drills.grading import CommandRunner, grade_drills, summarize_results
from ckad_drills.kubectl_runner import run_command, run_verification
from ckad_drills.models import (
    CleanupSummary,
    Drill,
    GradeResult,
    GradeSummary,
    Question,
)


def load_base_question_bank() -> list[Question]:
    return load_question_bank([resolve_base_question_bank_path()])


def load_configured_question_bank() -> list[Question]:
    question_bank_paths = [
        resolve_base_question_bank_path(),
        *resolve_question_bank_extension_paths(),
    ]
    return load_question_bank(question_bank_paths)


def prepare_drills(
    mode: str,
    count: int,
    namespace: str,
    *,
    seed: int | None = None,
) -> list[Drill]:
    rng = random.Random(seed) if seed is not None else None
    question_bank = load_configured_question_bank()

    if mode == "exam":
        base_question_bank = load_base_question_bank()
        blueprint_path = resolve_exam_blueprint_path()
        blueprint_questions = load_questions(blueprint_path)
        validate_exam_blueprint_references(
            blueprint_questions,
            base_question_bank,
            blueprint_path=blueprint_path,
        )
        selected_questions = select_exam_questions(
            question_bank,
            blueprint_questions,
            count,
            rng=rng,
        )
    else:
        selected_questions = select_questions(question_bank, count, rng=rng)

    return build_drills(selected_questions, namespace)


def validate_session_cleanup(
    cleanup_mode: str,
    namespace: str,
    *,
    kind_cluster_name: str | None = None,
) -> None:
    validate_cleanup_settings(cleanup_mode, namespace, kind_cluster_name)


def evaluate_drills(
    drills: list[Drill],
    runner: CommandRunner = run_verification,
) -> tuple[list[GradeResult], GradeSummary]:
    results = grade_drills(drills, runner)
    return results, summarize_results(results)


def cleanup_session(
    cleanup_mode: str,
    namespace: str,
    *,
    kind_cluster_name: str | None = None,
    runner: CommandRunner = run_command,
) -> CleanupSummary:
    return cleanup_environment(
        cleanup_mode,
        namespace,
        kind_cluster_name=kind_cluster_name,
        runner=runner,
    )
