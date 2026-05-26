import random

from ckad_drills.cleanup import cleanup_environment, validate_cleanup_settings
from ckad_drills.config import (
    resolve_exam_blueprint_path,
    resolve_question_bank_extension_paths,
    resolve_yaml_question_bank_paths,
)
from ckad_drills.datasets import load_question_bank
from ckad_drills.environment import execute_phase
from ckad_drills.exceptions import DatasetValidationError
from ckad_drills.generator import build_drills, select_exam_questions, select_questions
from ckad_drills.grading import (
    CaptureRunner,
    CommandRunner,
    grade_drills,
    summarize_results,
)
from ckad_drills.kubectl_runner import (
    run_command,
    run_command_capture,
    run_verification,
)
from ckad_drills.models import (
    CleanupSummary,
    Drill,
    EnvPhaseSummary,
    GradeResult,
    GradeSummary,
    Question,
)
from ckad_drills.yaml_datasets import load_yaml_question_bank, load_yaml_questions


def _merge_question_sources(
    csv_questions: list[Question],
    yaml_questions: list[Question],
) -> list[Question]:
    seen: dict[str, str] = {q.question_id: "CSV extension bank" for q in csv_questions}
    merged = list(csv_questions)
    for question in yaml_questions:
        if question.question_id in seen:
            raise DatasetValidationError(
                f"Duplicate question id '{question.question_id}' found in YAML "
                f"banks. Already defined in {seen[question.question_id]}."
            )
        seen[question.question_id] = "YAML bank"
        merged.append(question)
    return merged


def load_configured_question_bank() -> list[Question]:
    """Return the full question pool used for drills mode and exam-mode sampling.

    The pool is composed of:
      - every ``*.yaml`` / ``*.yml`` file under ``question_banks/`` except the
        exam-blueprint file, and
      - any optional ``*.csv`` extension banks under ``question_banks/``.

    Question ids must be unique across all of those sources.
    """
    csv_questions = load_question_bank(resolve_question_bank_extension_paths())
    yaml_questions = load_yaml_question_bank(resolve_yaml_question_bank_paths())
    return _merge_question_sources(csv_questions, yaml_questions)


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
        blueprint_path = resolve_exam_blueprint_path()
        # The blueprint is a curated YAML file: 15 questions whose (domain, topic)
        # pairs define the slots for a balanced exam. The runtime samples real
        # questions from the full bank by matching domain + topic; question ids
        # in the blueprint are intentionally independent of the bank.
        blueprint_questions = load_yaml_questions(blueprint_path)
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
    *,
    capture_runner: CaptureRunner = run_command_capture,
) -> tuple[list[GradeResult], GradeSummary]:
    results = grade_drills(drills, runner, capture_runner=capture_runner)
    return results, summarize_results(results)


def run_setup_phase(
    drills: list[Drill],
    *,
    runner: CaptureRunner = run_command_capture,
) -> EnvPhaseSummary:
    return execute_phase(drills, "setup", runner)


def run_teardown_phase(
    drills: list[Drill],
    *,
    runner: CaptureRunner = run_command_capture,
) -> EnvPhaseSummary:
    return execute_phase(drills, "teardown", runner)


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
