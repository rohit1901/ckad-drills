# Refactoring TODO

This document tracks clean-code refactors for the CKAD drill generator.

## Completion status

All items below have been executed in the suggested order. `make test`
(77 tests) still passes after each phase.

| # | Description                                                                    | Status |
| - | ------------------------------------------------------------------------------ | ------ |
| 1 | Delete dead `core.py` and `grader.py` compatibility shims                       | ✅     |
| 2 | Move `PASSING_PERCENTAGE` and timer poll interval into `config.py`              | ✅     |
| 3 | Drop `importlib.import_module(...)` boilerplate in tests                        | ✅     |
| 4 | Replace `CHECK_KIND_*` string constants with a `CheckKind` `str` enum           | ✅     |
| 5 | Split `cli.main()` into a `SessionRunner` with per-phase methods                | ✅     |
| 6 | Split monolithic `tests/test_ckad.py` into per-module test files                | ✅     |
| 7 | Split `tests/test_timer.py` into pure-timer vs. CLI-wiring tests                | ✅     |
| 8 | Replace the `if/elif` ladder in `check_evaluator.py` with a dispatch table      | ✅     |
| 9 | Turn `yaml_datasets` helpers into a `YamlBankParser` class                      | ✅     |
| 10 | Promote `CommandRunner` / `CaptureRunner` aliases into `models.py`             | ✅     |
| 11 | Reduce `Question` / `Drill` duplication in `Drill.from_question`               | ✅     |
| 12 | Extract a `Style` / theme abstraction and `_section_header` helper in renderer | ✅     |
| 13 | Use `logging` (NullHandler) for diagnostic output in `timer.py`                | ✅     |
| 14 | Compile the namespace-rewrite regex once at module import                      | ✅     |
| 15 | Co-locate `KNOWN_NAMESPACES` / `PROTECTED_NAMESPACES` with their consumers     | ✅     |
| 16 | Rename `DEFAULT_COUNT` / `DEFAULT_NAMESPACE` → `DRILLS_*` (with back-compat)   | ✅     |
| 17 | Update `start_ckad_exam.command` to use the real CKAD exam shape               | ✅     |
| 18 | Distinct exit code (2) when the exam runs to completion but fails the cut     | ✅     |
| 19 | Document the blueprint's "`verify:` is metadata only" rule in `question_banks/README.md` | ✅     |

---

## Notes per item

### 1. Delete `src/ckad_drills/core.py` and `src/ckad_drills/grader.py`
Both were unused re-export shims. Deleted; nothing in the tree imported
them.

### 2. Domain constants moved to `config.py`
`CKAD_PASSING_PERCENTAGE = 66` and `CKAD_TIMER_POLL_INTERVAL_SECONDS =
0.5` now live in `config.py`. `cli.PASSING_PERCENTAGE` is preserved as a
back-compat alias.

### 3. Test imports cleaned up
The `importlib.import_module(...)` indirection was removed. Tests now use
ordinary `from ckad_drills.cli import main, build_parser` imports. A
small `tests/_fixtures.py` module holds shared fixture-path constants and
the `sys.path.insert(SRC_ROOT)` bootstrap so each test file is short and
focused.

### 4. `CheckKind` enum
`CheckKind` is a `str` Enum, so existing comparisons (`check.kind ==
"equals"`, YAML I/O, tuple iteration via `CHECK_KINDS`) keep working.
`CHECK_KIND_*` aliases are still exported.

### 5. `SessionRunner`
`cli.main()` is now a thin dispatcher: parse argv → `cleanup-only` or
`SessionRunner(args).run(parser)`. The runner has named phase methods
(`_prepare`, `_render_drills`, `_render_setup`, `_maybe_start_timer`,
`_wait_for_user`, `_grade`, `_render_results`, `_teardown`, `_cleanup`,
`_exit_code`). stdout/stderr ordering is preserved; the existing
`TestCliExamRunIntegration` tests still cover the contract.

### 6 & 7. Test split
The 715-line `tests/test_ckad.py` is now seven files:
`test_datasets.py`, `test_generator.py`, `test_cleanup.py`,
`test_session.py`, `test_grading.py`, `test_renderer.py`,
`test_yaml_bank.py`, plus the CLI tests in `test_cli.py`.
`tests/test_timer.py` now only holds pure-timer concerns
(`TestParseDuration`, `TestFormatDurationShort`,
`TestDefaultReminderThresholds`, `TestReminderSchedule`,
`TestSessionTimer`); CLI-side tests moved into `test_cli.py`.

### 8. Dispatch table in `check_evaluator.py`
The `if/elif` ladder is replaced with a `_STDOUT_EVALUATORS: dict[str,
_StdoutEvaluator]` registry. Adding a new check kind is now "write an
evaluator function, register it, add the enum member, register a parser
in `yaml_datasets._EXPECT_PARSERS`."

### 9. `YamlBankParser`
All `_parse_*` helpers became methods on a single parser class that owns
the file path. The public `load_yaml_questions(path)` is a one-liner over
the parser. Error message wording is preserved.

### 10. Runner aliases in `models.py`
`CommandRunner` and `CaptureRunner` `Callable` aliases now live in
`models.py` next to the data classes they consume. `grading.py`,
`environment.py`, `session.py` import from there.

### 11. `Drill` / `Question` overlap
`Drill.from_question` now builds an `overrides` map and falls back to the
question's existing field values, which makes the override semantics
slightly clearer when new fields are added. Bigger structural changes
(`Drill` holding a `Question` overlay) were deemed out of scope for this
pass.

### 12. `Style` / `render_section`
A frozen `Style` dataclass holds the ANSI escapes (or empty strings for
`Style.plain()`). The repeated `= * 72 / title / = * 72` banner is now a
single `_section_header(title, style)` helper used by every renderer. The
old `colorize(use_color=...)` helper is preserved as a thin shim for any
external caller.

### 13. `logging` in `timer.py`
`timer.py` now owns a `logging.getLogger(__name__)` with a
`NullHandler()` attached at import time. Reminder fires and expiry now
also emit `logger.info(...)` records, while the existing stderr writes
remain so the user-facing banners are unchanged. Hosts that want
structured logs can configure the `ckad_drills.timer` logger.

### 14. Compiled namespace-rewrite regex
`generator.rewrite_namespace` now uses a single `_NAMESPACE_PATTERN =
re.compile(...)` built at import time and a single `pattern.sub(...)`
call per text.

### 15 & 16. Config moves
`KNOWN_NAMESPACES` and `PROTECTED_NAMESPACES` now live in
`ckad_drills/_namespaces.py`; `config.py` re-exports them at the bottom
so any external import still works. `DEFAULT_COUNT` and
`DEFAULT_NAMESPACE` were renamed to `DRILLS_DEFAULT_COUNT` /
`DRILLS_DEFAULT_NAMESPACE` and grouped parallel to the `CKAD_EXAM_*`
block, with back-compat aliases under the old names.

### 17. `start_ckad_exam.command`
Dropped the explicit `--count 5` so the launcher falls through to the
real CKAD defaults (22 questions / 2h, defined in `config.py`).

### 18. Exit codes
`cli.main()` now exits `0` on a pass, `1` on infrastructure failure
(invalid args, cleanup failures), and `2` when the exam ran but the
final score is below `CKAD_PASSING_PERCENTAGE`. Documented in
`README.md`.

### 19. Blueprint `verify:` field doc
`question_banks/README.md` now carries a callout explaining that
`balanced_exam.yaml`'s placeholder `verify:` blocks are required by the
schema but are never executed at runtime.

---

## Out of scope (recorded so we don't forget)

- **Operator-style drill orchestration.** Per-drill ephemeral namespaces
  pushed into Kubernetes would be a bigger architectural change worth a
  separate design doc.
- **Asynchronous setup/verify.** Drill setup runs sequentially; the
  user-perceived bottleneck is `kubectl` round trips, which already
  block per-call.
- **Web UI.** Out of scope for this codebase.
