"""YAML-based question bank loader.

A YAML bank file lives in ``question_banks/`` and looks like:

    questions:
      - id: YQ01
        domain: Application Design and Build (20%)
        topic: Define, build, and modify container images
        scenario: |
          ...
        tasks: |
          1. ...
          2. ...
        setup:           # optional
          - run: kubectl create namespace workloads --dry-run=client -o yaml | kubectl apply -f -
          - apply: |
              apiVersion: v1
              kind: ConfigMap
              ...
        verify:          # list of named checks OR a single shell-pipeline string
          - name: pod is Running
            run: kubectl get pod demo -n workloads -o jsonpath='{.status.phase}'
            expect:
              equals: Running
        teardown:        # optional
          - run: kubectl delete pod demo -n workloads --ignore-not-found
        hints: |
          ...

Each ``expect`` block accepts exactly one of: ``equals``, ``contains``,
``not_contains``, ``regex``, ``exit_code``. If ``expect`` is omitted, the
check passes when the command exits 0.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

from ckad_drills.exceptions import DatasetValidationError
from ckad_drills.models import (
    CHECK_KINDS,
    CheckKind,
    EnvStep,
    Question,
    VerifyCheck,
)

REQUIRED_QUESTION_FIELDS = ("id", "domain", "topic", "scenario", "tasks")


def _require_yaml_module():
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - hard to hit in CI
        raise DatasetValidationError(
            "PyYAML is required to load YAML question banks. "
            "Install it with: pip install PyYAML  (or rerun 'make install')."
        ) from exc
    return yaml


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _short_label(command: str) -> str:
    snippet = command.strip().splitlines()[0]
    return snippet if len(snippet) <= 60 else snippet[:57] + "..."


def _parse_apply_to_run(manifest_text: str) -> str:
    """Convert an ``apply:`` manifest into an equivalent shell command."""
    return (
        "kubectl apply -f - <<'__CKAD_YAML_EOF__'\n"
        f"{manifest_text.rstrip()}\n"
        "__CKAD_YAML_EOF__"
    )


# Dispatch table for ``expect`` parsing. Each entry returns the string-encoded
# value used by the runtime check evaluator. Adding a new check kind is now
# "add an enum member, register a parser here, register an evaluator in
# check_evaluator._STDOUT_EVALUATORS."
def _parse_expect_exit_code(
    parser: "YamlBankParser", qid: str, index: int, raw: Any
) -> str:
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        parser._bail(
            f"question '{qid}' verify[{index}].expect.exit_code must be an integer."
        )


def _parse_expect_string(
    parser: "YamlBankParser", qid: str, index: int, raw: Any, kind: str
) -> str:
    value = _as_str(raw)
    if value == "":
        parser._bail(
            f"question '{qid}' verify[{index}].expect.{kind} must be a non-empty string."
        )
    return value


_EXPECT_PARSERS = {
    CheckKind.EQUALS.value: lambda p, q, i, r: _parse_expect_string(
        p, q, i, r, CheckKind.EQUALS.value
    ),
    CheckKind.CONTAINS.value: lambda p, q, i, r: _parse_expect_string(
        p, q, i, r, CheckKind.CONTAINS.value
    ),
    CheckKind.NOT_CONTAINS.value: lambda p, q, i, r: _parse_expect_string(
        p, q, i, r, CheckKind.NOT_CONTAINS.value
    ),
    CheckKind.REGEX.value: lambda p, q, i, r: _parse_expect_string(
        p, q, i, r, CheckKind.REGEX.value
    ),
    CheckKind.EXIT_CODE.value: _parse_expect_exit_code,
}


class YamlBankParser:
    """Parse a single YAML question-bank file into :class:`Question` objects.

    State that every helper needs (the source ``path`` for error messages)
    lives on ``self``, so individual parsing helpers can be simple methods
    instead of threading ``path``, ``qid``, ``index`` through every call.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    # ---- public API ------------------------------------------------------
    def parse(self) -> list[Question]:
        yaml = _require_yaml_module()
        with self.path.open(mode="r", encoding="utf-8") as handle:
            try:
                document = yaml.safe_load(handle)
            except yaml.YAMLError as exc:
                raise DatasetValidationError(
                    f"Failed to parse YAML bank '{self.path.name}': {exc}"
                ) from exc

        if document is None:
            return []

        if isinstance(document, list):
            questions_raw = document
        elif isinstance(document, dict):
            questions_raw = document.get("questions")
            if questions_raw is None:
                self._bail("top-level mapping must contain a 'questions' list.")
        else:
            self._bail("top-level document must be a list or a mapping.")

        if not isinstance(questions_raw, list):
            self._bail("'questions' must be a list.")

        return [
            self._parse_question(index, raw) for index, raw in enumerate(questions_raw)
        ]

    # ---- internals -------------------------------------------------------
    def _bail(self, message: str) -> NoReturn:
        raise DatasetValidationError(f"Invalid YAML bank '{self.path.name}': {message}")

    def _parse_question(self, index: int, raw: Any) -> Question:
        if not isinstance(raw, dict):
            self._bail(f"questions[{index}] must be a mapping.")

        qid = _as_str(raw.get("id")).strip()
        if not qid:
            self._bail(f"questions[{index}] is missing a non-empty 'id'.")

        missing = [
            field_name
            for field_name in REQUIRED_QUESTION_FIELDS
            if not _as_str(raw.get(field_name)).strip()
        ]
        if missing:
            self._bail(
                f"question '{qid}' is missing required field(s): {', '.join(missing)}."
            )

        verify_fallback, checks = self._parse_verify(qid, raw.get("verify"))
        setup_steps = self._parse_env_phase(qid, "setup", raw.get("setup"))
        teardown_steps = self._parse_env_phase(qid, "teardown", raw.get("teardown"))

        return Question(
            question_id=qid,
            domain=_as_str(raw.get("domain")).strip(),
            topic=_as_str(raw.get("topic")).strip(),
            scenario=_as_str(raw.get("scenario")),
            tasks=_as_str(raw.get("tasks")),
            verify=verify_fallback,
            hints=_as_str(raw.get("hints")),
            checks=checks,
            setup_steps=setup_steps,
            teardown_steps=teardown_steps,
        )

    def _parse_verify(self, qid: str, raw: Any) -> tuple[str, tuple[VerifyCheck, ...]]:
        if raw is None:
            self._bail(f"question '{qid}' is missing 'verify'.")

        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                self._bail(f"question '{qid}' has an empty 'verify' string.")
            return text, ()

        if not isinstance(raw, list) or len(raw) == 0:
            self._bail(
                f"question '{qid}' 'verify' must be a non-empty list of checks "
                f"or a non-empty shell-pipeline string."
            )

        checks: list[VerifyCheck] = []
        for index, entry in enumerate(raw):
            if not isinstance(entry, dict):
                self._bail(f"question '{qid}' verify[{index}] must be a mapping.")
            run_value = _as_str(entry.get("run")).strip()
            if not run_value:
                self._bail(
                    f"question '{qid}' verify[{index}] is missing a non-empty 'run' command."
                )
            name = _as_str(entry.get("name")).strip() or f"check {index + 1}"
            kind, value = self._parse_expect(qid, index, entry.get("expect"))
            checks.append(VerifyCheck(name=name, run=run_value, kind=kind, value=value))

        fallback = "; ".join(check.run for check in checks)
        return fallback, tuple(checks)

    def _parse_expect(self, qid: str, index: int, expect_raw: Any) -> tuple[str, str]:
        if expect_raw is None:
            return CheckKind.EXIT_CODE.value, "0"

        if not isinstance(expect_raw, dict):
            self._bail(
                f"question '{qid}' verify[{index}].expect must be a mapping "
                f"(one of: {', '.join(CHECK_KINDS)})."
            )

        present = [key for key in CHECK_KINDS if key in expect_raw]
        if len(present) == 0:
            self._bail(
                f"question '{qid}' verify[{index}].expect must contain exactly one of: "
                f"{', '.join(CHECK_KINDS)}."
            )
        if len(present) > 1:
            self._bail(
                f"question '{qid}' verify[{index}].expect has multiple expectations "
                f"({', '.join(present)}); please use exactly one."
            )

        kind = present[0]
        encoded_value = _EXPECT_PARSERS[kind](self, qid, index, expect_raw[kind])
        return kind, encoded_value

    def _parse_env_phase(self, qid: str, phase: str, raw: Any) -> tuple[EnvStep, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, list):
            self._bail(f"question '{qid}' '{phase}' must be a list of steps.")
        return tuple(
            self._parse_env_step(qid, phase, index, entry)
            for index, entry in enumerate(raw)
        )

    def _parse_env_step(self, qid: str, phase: str, index: int, raw: Any) -> EnvStep:
        location = f"question '{qid}' {phase}[{index}]"
        if not isinstance(raw, dict):
            self._bail(f"{location} must be a mapping with 'run' or 'apply'.")

        label_raw = raw.get("name") or raw.get("label")
        run_value = raw.get("run")
        apply_value = raw.get("apply")

        if run_value and apply_value:
            self._bail(f"{location} cannot set both 'run' and 'apply'.")
        if not run_value and not apply_value:
            self._bail(f"{location} must set either 'run' or 'apply'.")

        if run_value is not None:
            run_str = _as_str(run_value).strip()
            if not run_str:
                self._bail(f"{location} 'run' must be a non-empty string.")
            label = _as_str(label_raw).strip() or _short_label(run_str)
            return EnvStep(label=label, run=run_str)

        manifest = _as_str(apply_value)
        if not manifest.strip():
            self._bail(f"{location} 'apply' must be a non-empty manifest string.")
        label = _as_str(label_raw).strip() or "kubectl apply (inline manifest)"
        return EnvStep(label=label, run=_parse_apply_to_run(manifest))


def load_yaml_questions(yaml_path: str | Path) -> list[Question]:
    """Load a single YAML question bank file."""
    return YamlBankParser(Path(yaml_path)).parse()


def load_yaml_question_bank(yaml_paths: Sequence[str | Path]) -> list[Question]:
    """Load and merge multiple YAML banks, enforcing id uniqueness."""
    questions: list[Question] = []
    seen_ids: dict[str, str] = {}

    for yaml_path in yaml_paths:
        path = Path(yaml_path)
        for question in load_yaml_questions(path):
            existing = seen_ids.get(question.question_id)
            if existing is not None:
                raise DatasetValidationError(
                    f"Duplicate question id '{question.question_id}' found in "
                    f"'{path.name}'. Already defined in '{existing}'."
                )
            seen_ids[question.question_id] = path.name
            questions.append(question)

    return questions
