"""Evaluate a single declarative VerifyCheck against captured shell output."""

import re

from ckad_drills.models import (
    CHECK_KIND_CONTAINS,
    CHECK_KIND_EQUALS,
    CHECK_KIND_EXIT_CODE,
    CHECK_KIND_NOT_CONTAINS,
    CHECK_KIND_REGEX,
    CheckResult,
    VerifyCheck,
)

_MAX_DETAIL_LEN = 200


def _truncate(text: str, limit: int = _MAX_DETAIL_LEN) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


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

    if check.kind == CHECK_KIND_EXIT_CODE:
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

    expected = check.value
    if check.kind == CHECK_KIND_EQUALS:
        passed = out == expected.strip()
        detail = (
            f"stdout matched '{_truncate(expected)}'"
            if passed
            else f"expected '{_truncate(expected)}', got '{_truncate(out)}'"
        )
    elif check.kind == CHECK_KIND_CONTAINS:
        passed = expected in out
        detail = (
            f"stdout contains '{_truncate(expected)}'"
            if passed
            else f"expected substring '{_truncate(expected)}' not found in '{_truncate(out)}'"
        )
    elif check.kind == CHECK_KIND_NOT_CONTAINS:
        passed = expected not in out
        detail = (
            f"stdout does not contain '{_truncate(expected)}'"
            if passed
            else f"forbidden substring '{_truncate(expected)}' found in '{_truncate(out)}'"
        )
    elif check.kind == CHECK_KIND_REGEX:
        try:
            pattern = re.compile(expected, re.MULTILINE | re.DOTALL)
        except re.error as exc:
            return CheckResult(
                name=check.name,
                run=check.run,
                passed=False,
                detail=f"invalid regex '{_truncate(expected)}': {exc}",
            )
        passed = pattern.search(out) is not None
        detail = (
            f"stdout matched regex '{_truncate(expected)}'"
            if passed
            else f"stdout did not match regex '{_truncate(expected)}'; got '{_truncate(out)}'"
        )
    else:
        passed = False
        detail = f"unknown check kind '{check.kind}'"

    return CheckResult(name=check.name, run=check.run, passed=passed, detail=detail)
