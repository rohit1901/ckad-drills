"""Execute drill setup and teardown phases.

Drills loaded from YAML banks may include ``setup`` steps (to prepare the
cluster before the user starts) and ``teardown`` steps (to clean up after
grading). Both are run as shell commands; failures are captured in an
``EnvPhaseSummary`` rather than raised, so a flaky teardown never blocks the
session.
"""

from collections.abc import Callable, Sequence

from ckad_drills.models import Drill, EnvPhaseSummary, EnvStep, EnvStepResult

CaptureRunner = Callable[[str], tuple[int, str, str]]

_OUTPUT_LIMIT = 400


def _truncate(text: str, limit: int = _OUTPUT_LIMIT) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _collect_steps(drills: Sequence[Drill], phase: str) -> list[tuple[int, EnvStep]]:
    """Return [(drill_number, step), ...] for the requested phase."""
    pairs: list[tuple[int, EnvStep]] = []
    for index, drill in enumerate(drills, start=1):
        steps = drill.setup_steps if phase == "setup" else drill.teardown_steps
        for step in steps:
            pairs.append((index, step))
    return pairs


def execute_phase(
    drills: Sequence[Drill],
    phase: str,
    runner: CaptureRunner,
) -> EnvPhaseSummary:
    if phase not in ("setup", "teardown"):
        raise ValueError(f"Unknown env phase '{phase}'.")

    pairs = _collect_steps(drills, phase)
    results: list[EnvStepResult] = []
    for drill_number, step in pairs:
        exit_code, stdout, stderr = runner(step.run)
        succeeded = exit_code == 0
        output_pieces = []
        if stdout.strip():
            output_pieces.append(_truncate(stdout))
        if stderr.strip():
            output_pieces.append(f"stderr: {_truncate(stderr)}")
        if not succeeded:
            output_pieces.append(f"exit_code={exit_code}")
        results.append(
            EnvStepResult(
                label=f"Drill {drill_number}: {step.label}",
                command=step.run,
                succeeded=succeeded,
                output="\n".join(output_pieces),
            )
        )
    return EnvPhaseSummary(phase=phase, steps=tuple(results))
