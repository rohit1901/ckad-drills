"""Evaluate a single declarative VerifyCheck against captured shell output."""

import re
from collections.abc import Callable

from ckad_drills.models import CheckKind, CheckResult, VerifyCheck

_MAX_DETAIL_LEN = 200


def _truncate(text: str, limit: int = _MAX_DETAIL_LEN) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


# A check evaluator inspects already-captured stdout (stripped) and returns
# a (passed, detail_message) pair. Exit-code-aware checks have their own
# evaluator that runs before this dispatch table.
_StdoutEvaluator = Callable[[VerifyCheck, str], tuple[bool, str]]


def _eval_equals(check: VerifyCheck, out: str) -> tuple[bool, str]:
    expected = check.value
    passed = out == expected.strip()
    detail = (
        f"stdout matched '{_truncate(expected)}'"
        if passed
        else f"expected '{_truncate(expected)}', got '{_truncate(out)}'"
    )
    return passed, detail


def _eval_contains(check: VerifyCheck, out: str) -> tuple[bool, str]:
    expected = check.value
    passed = expected in out
    detail = (
        f"stdout contains '{_truncate(expected)}'"
        if passed
        else f"expected substring '{_truncate(expected)}' not found in '{_truncate(out)}'"
    )
    return passed, detail


def _eval_not_contains(check: VerifyCheck, out: str) -> tuple[bool, str]:
    expected = check.value
    passed = expected not in out
    detail = (
        f"stdout does not contain '{_truncate(expected)}'"
        if passed
        else f"forbidden substring '{_truncate(expected)}' found in '{_truncate(out)}'"
    )
    return passed, detail


def _eval_regex(check: VerifyCheck, out: str) -> tuple[bool, str]:
    expected = check.value
    try:
        pattern = re.compile(expected, re.MULTILINE | re.DOTALL)
    except re.error as exc:
        return False, f"invalid regex '{_truncate(expected)}': {exc}"
    passed = pattern.search(out) is not None
    detail = (
        f"stdout matched regex '{_truncate(expected)}'"
        if passed
        else f"stdout did not match regex '{_truncate(expected)}'; got '{_truncate(out)}'"
    )
    return passed, detail


# Adding a new check kind is now "write an evaluator, register it here, add
# the enum member to ``CheckKind`` and a parser in ``yaml_datasets``."
_STDOUT_EVALUATORS: dict[str, _StdoutEvaluator] = {
    CheckKind.EQUALS.value: _eval_equals,
    CheckKind.CONTAINS.value: _eval_contains,
    CheckKind.NOT_CONTAINS.value: _eval_not_contains,
    CheckKind.REGEX.value: _eval_regex,
}


def evaluate_check(
    check: VerifyCheck,
    exit_code: int,
    stdout: str,
    stderr: str,
) -> CheckResult:
    """Decide pass/fail for one VerifyCheck given captured output.

    Convention:
    - ``equals`` / ``contains`` / ``not_contains`` / ``regex`` are evaluated
      against stdout. The command must also exit 0 for those kinds; a non-zero
      exit code surfaces as a failure with the stderr snippet in the detail.
    - ``exit_code`` only inspects the process exit code.
    """
    out = stdout.strip()
    err = stderr.strip()

    if check.kind == CheckKind.EXIT_CODE.value:
        expected_rc = int(check.value)
        passed = exit_code == expected_rc
        if passed:
            detail = f"exit_code={exit_code} (matched)"
        else:
            detail = f"expected exit_code={expected_rc}, got {exit_code}"
            if err:
                detail += f"; stderr: {_truncate(err)}"
        return CheckResult(name=check.name, run=check.run, passed=passed, detail=detail)

    if exit_code != 0:
        detail = f"command failed with exit_code={exit_code}"
        if err:
            detail += f"; stderr: {_truncate(err)}"
        return CheckResult(name=check.name, run=check.run, passed=False, detail=detail)

    evaluator = _STDOUT_EVALUATORS.get(check.kind)
    if evaluator is None:
        return CheckResult(
            name=check.name,
            run=check.run,
            passed=False,
            detail=f"unknown check kind '{check.kind}'",
        )

    passed, detail = evaluator(check, out)
    return CheckResult(name=check.name, run=check.run, passed=passed, detail=detail)
