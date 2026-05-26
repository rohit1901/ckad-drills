# Refactoring TODO

This document tracks clean-code refactors for the CKAD drill generator.
Items are grounded in concrete observations from the current tree, not
generic clean-code advice. Each item has a priority (P1 = high payoff,
low risk; P2 = nice cleanup; P3 = aspirational), the symptom that
motivates it, and a sketched-out approach.

The non-negotiable invariant for every refactor: **`make test` must still
pass and no observable CLI behavior may change unless explicitly called
out.**

---

## Quick wins (P1)

### 1. Delete `src/ckad_drills/core.py` and `src/ckad_drills/grader.py`
- **Symptom**: both modules are thin compatibility shims with **zero
  importers** in the codebase (`grep -RIn 'from ckad_drills.core\|from
  ckad_drills.grader'` returns nothing). `core.py` re-exports
  `load_questions`/`rewrite_namespace`/`select_questions` via aliases;
  `grader.py` is a one-line wrapper around `run_verification`.
- **Action**: delete both files. Run `make test` to confirm.
- **Risk**: none — dead code.

### 2. Move `PASSING_PERCENTAGE = 66` from `cli.py` to `config.py`
- **Symptom**: a domain constant (CKAD pass mark) lives in the CLI
  module, next to argument parsing.
- **Action**: move into `config.py` as `CKAD_PASSING_PERCENTAGE`, import
  in `cli.py`. Same treatment for the `0.5 s` polling interval in
  `_wait_with_timer_polling` → `CKAD_TIMER_POLL_INTERVAL_SECONDS`.
- **Risk**: trivial.

### 3. Drop `importlib.import_module(...)` boilerplate in tests
- **Symptom**: `tests/test_ckad.py` and `tests/test_timer.py` both open
  with ~30 lines of `_cli = importlib.import_module("ckad_drills.cli")`
  / `main = _cli.main` style indirection. No test in the suite actually
  needs lazy/dynamic imports.
- **Action**: replace with normal `from ckad_drills.cli import main,
  build_parser` etc. Drop the `_module` aliases. `patch.object(_cli,
  ...)` calls become `patch("ckad_drills.cli....")`.
- **Risk**: low — straight syntactic substitution.

### 4. Replace the `CHECK_KIND_*` constants with a `StrEnum`
- **Symptom**: `models.py` exports five string constants plus a
  `CHECK_KINDS` tuple. `check_evaluator.py` and `yaml_datasets.py` both
  import and `if/elif`-ladder over them. No type checker can spot a
  typo.
- **Action**: introduce `class CheckKind(StrEnum): EQUALS = "equals";
  …`. Keep the string values identical for YAML compatibility. Update
  `VerifyCheck.kind` to `CheckKind`. Replace `CHECK_KINDS` tuple usage
  with `CheckKind` iteration.
- **Risk**: small. Tests that pass literal strings keep working because
  `StrEnum == str`. YAML loader needs to coerce.

---

## Module decomposition (P1)

### 5. Split `cli.main()` into a session orchestrator
- **Symptom**: `main()` is **115 lines** doing argv parsing, cleanup
  validation, drill prep, env-phase rendering, timer construction,
  user-wait, grading, results rendering, teardown, and final cleanup —
  all inline with bare `print()` calls between each phase.
- **Action**: introduce a `SessionRunner` (or a `run_drill_session(args,
  *, use_color) -> int` free function) that owns the per-phase flow.
  `main()` becomes: parse argv → dispatch to `run_cleanup_only` or
  `SessionRunner(args).run()` → return exit code. Each phase becomes a
  method (`_render_setup`, `_wait_for_user`, `_grade`, `_teardown`,
  `_cleanup`) returning a small typed result. Easier to test phases in
  isolation.
- **Risk**: moderate — needs careful preservation of stdout/stderr
  ordering. The `TestCliExamRunIntegration` tests in `test_timer.py`
  already cover the contract.

### 6. Split `tests/test_ckad.py` (715 lines) along module lines
- **Symptom**: a single 715-line test file holds `TestDatasets`,
  `TestGenerator`, `TestCleanup`, `TestSession`, `TestGrading`,
  `TestRenderer`, `TestCli`, `TestYAMLBank`, `TestStructuredGrading`.
  `tests/test_timer.py` was already split out and is much easier to
  navigate.
- **Action**: split into one file per module under test:
  `test_datasets.py`, `test_generator.py`, `test_cleanup.py`,
  `test_session.py`, `test_grading.py`, `test_renderer.py`,
  `test_cli.py`, `test_yaml_bank.py`. Shared fixture-path constants go
  into a `tests/_fixtures.py` helper.
- **Risk**: low. `unittest discover` already globs `test_*.py`.

### 7. Split `tests/test_timer.py` into pure-timer and CLI-wiring tests
- **Symptom**: the file mixes `TestParseDuration` / `TestSessionTimer`
  (pure timer concerns) with `TestCliTimerWiring` /
  `TestCliExamRunIntegration` (CLI plumbing). 606 lines.
- **Action**: keep timer-internals in `tests/test_timer.py`; move the
  CLI-side tests into the new `tests/test_cli.py` from item 6.
- **Risk**: low.

---

## Domain modeling (P2)

### 8. Replace the `if/elif` ladder in `check_evaluator.py` with dispatch
- **Symptom**: `evaluate_check` has a chain of `if check.kind ==
  CHECK_KIND_EQUALS: … elif … elif …`. Adding a new check kind means
  editing the ladder, `models.CHECK_KINDS`, and the YAML loader in
  three places.
- **Action**: define a `dict[CheckKind, Callable[[VerifyCheck,
  CapturedOutput], CheckResult]]` so adding a kind is "write a
  function, register it in the dict, add the enum member." Same
  treatment for `yaml_datasets._parse_expect`.
- **Risk**: low. Existing `test_check_evaluator`/structured-grading
  tests cover the contract.

### 9. Turn `yaml_datasets` helpers into a `YamlBankParser` class
- **Symptom**: every private helper threads `path` (for error
  messages), `qid` (for the current question), and `index`. Functions
  like `_parse_env_step(path, qid, phase, index, raw)` would be
  `self._parse_env_step(phase, index, raw)` with state on `self`.
- **Action**: introduce `class YamlBankParser` whose ctor takes `path`,
  whose `parse() -> list[Question]` is the public entry point, and
  whose `_bail`, `_parse_question`, `_parse_verify`, `_parse_env_step`,
  `_parse_expect` are methods. `load_yaml_questions` becomes a
  one-liner that constructs the parser. Keep error-message wording
  identical so user-facing failures don't change.
- **Risk**: low–moderate. There's a parser test in the suite; keep
  message formats.

### 10. Promote `CommandRunner` / `CaptureRunner` aliases to a single home
- **Symptom**: the typed aliases for verification runners (`Callable[[str],
  bool]`) and capture runners (`Callable[[str], CapturedOutput]`) are
  imported from `grading.py` into `session.py` and `environment.py`,
  but the names are defined in `grading.py` because that's "where they
  were first needed."
- **Action**: move the two aliases into `models.py` (or a new
  `protocols.py`) next to the data classes they consume. Update three
  importers.
- **Risk**: trivial.

### 11. Reconsider `Question` vs `Drill` duplication
- **Symptom**: `Drill.from_question` copies almost every field of
  `Question` and then re-wraps `tasks`, `verify`, `checks`,
  `setup_steps`, `teardown_steps` with namespace-rewritten versions.
  The two dataclasses are 80% the same.
- **Action**: either (a) make `Drill` hold a `Question` and a
  `rewritten` overlay, or (b) generate `Drill` as a frozen dataclass
  with `dataclasses.replace(question, …)` calls. Reduces ~30 lines and
  prevents drift when one dataclass gets a new field.
- **Risk**: moderate — touches `generator.py`, `models.py`, and
  several tests. Defer until item 5 lands.

---

## Rendering & I/O (P2)

### 12. Extract an ANSI `Style` / theme abstraction in `renderer.py`
- **Symptom**: `renderer.py` defines `RESET`, `BOLD`, `CYAN`, `GREEN`,
  `RED`, `YELLOW`, `MAGENTA` as raw ANSI escape strings and threads
  `use_color: bool` through ~10 functions. Section-header rendering
  (`= * 72`, title, `= * 72`) is duplicated in `render_drills`,
  `render_results`, `render_cleanup_summary`,
  `render_env_phase_summary`, and (after the recent timer banner work)
  `render_exam_timer_banner`.
- **Action**:
  1. Introduce a `Style` (or small `Theme`) dataclass holding the
     escape strings, with a `Style.plain()` factory for the no-color
     case.
  2. Extract a `render_section(title, body_lines, *, style)` helper
     that owns the `===` box.
  3. Pass a single `style` object instead of `use_color: bool`.
- **Risk**: moderate. Lots of tests assert on rendered strings; doable
  but mechanical.

### 13. Use `logging` for diagnostic output instead of bare `print` /
  `sys.stderr.write`
- **Symptom**: `cli.py` uses `print()` for user-facing output and
  `sys.stderr.write()` (in `timer.py`) for reminders. There's no way
  to silence or redirect just the verbose parts (e.g. setup-phase
  output) for non-interactive runs.
- **Action**: introduce a single `logger` (`logging.getLogger(__name__)`)
  for diagnostic and reminder output; keep user-facing rendering on
  stdout via `print`. Add a `--quiet` flag later if useful.
- **Risk**: low, but verify the existing tests that capture stderr
  (timer reminders) still see the messages.

### 14. Compile the namespace-rewrite regex once
- **Symptom**: `generator.rewrite_namespace` calls `re.sub` inside a
  loop over `KNOWN_NAMESPACES` for every drill, every render pass. The
  pattern is built fresh on each call via `rf"(?<![/\w]){…}\b"`.
- **Action**: cache a `re.compile`'d alternation
  (`(?<![/\w])(team-alpha|team-beta|…)\b`) at module import time and
  substitute with a single `sub(..., text)` call using a function
  replacement.
- **Risk**: trivial. Existing path-preservation tests cover edges.

---

## Configuration & namespacing (P3)

### 15. Co-locate per-feature constants with their consumer
- **Symptom**: `KNOWN_NAMESPACES` is used only in `generator.py`,
  `PROTECTED_NAMESPACES` only in `cleanup.py`, but both live in the
  shared `config.py`. Mixed concerns make `config.py` look bigger than
  it really is.
- **Action**: either move each constant to the module that owns it, or
  keep `config.py` but group constants by feature with comments and a
  `# fmt: off` block. Mild preference for the move.
- **Risk**: trivial.

### 16. Add `CKAD_EXAM_*` sibling for drills-mode defaults
- **Symptom**: `DEFAULT_COUNT = 5` and `DEFAULT_NAMESPACE = "drill-01"`
  sit at the top of `config.py` as bare strings while `CKAD_EXAM_*`
  constants are grouped a few lines below. Asymmetric.
- **Action**: rename to `DRILLS_DEFAULT_COUNT`, `DRILLS_DEFAULT_NAMESPACE`
  and group them in their own block parallel to the `CKAD_EXAM_*`
  block. Or introduce a small `DrillsDefaults` / `ExamDefaults`
  namedtuple if the count of constants grows.
- **Risk**: small; touches a handful of imports.

---

## Documentation & UX (P3)

### 17. Update `start_ckad_exam.command` to the real CKAD exam shape
- **Symptom**: the macOS one-click launcher still runs `ckad-drills run
  --mode exam --count 5 --namespace drill-01`. The real CKAD exam is 15
  questions / 2h, which the project now defaults to.
- **Action**: change to `ckad-drills run --mode exam --namespace
  drill-01` (or explicitly `--count 15 --time-limit 2h`) so a
  double-click gives a realistic exam.
- **Risk**: behavior change, but the right one.

### 18. Make exam exit code reflect pass/fail
- **Symptom**: the CLI exits 0 as long as cleanup succeeds, even if
  the student failed the exam or got auto-graded with a sub-passing
  score.
- **Action**: introduce a non-zero exit code (e.g. 2) when the final
  percentage is below `CKAD_PASSING_PERCENTAGE`, so CI / shell
  pipelines can detect a failed practice run. Document in README. Keep
  exit code 1 reserved for infrastructure failures (cleanup, bad
  args).
- **Risk**: small behavior change. Update one CLI test.

### 19. Document the exam blueprint's "verify is metadata only" rule
- **Symptom**: `balanced_exam.yaml` carries placeholder `verify: |
  true` for every slot because the YAML loader currently requires the
  field, but the runtime never executes it. New maintainers will
  wonder.
- **Action** (one of):
  - relax the YAML schema so `verify` is optional when the file is
    consumed as a blueprint (introduce a `blueprint: true` marker), or
  - keep the current shape but document the convention in
    `question_banks/README.md` with a callout that blueprint files
    must still satisfy the schema.
- **Risk**: schema change is a real change; the doc-only path is the
  safer first step.

---

## Out of scope (recorded so we don't forget)

- **Operator-style drill orchestration.** The current "rewrite known
  namespaces" approach is fine. Pushing per-drill namespace isolation
  into Kubernetes (one ephemeral namespace per drill, deleted on
  teardown) would be a bigger architectural change worth a separate
  design doc.
- **Asynchronous setup/verify.** Drill setup runs sequentially. Could
  parallelize, but the user-perceived bottleneck is `kubectl` round
  trips, which already block per-call.
- **Web UI.** Out of scope for this codebase.

---

## Suggested ordering

A reasonable sequence that keeps each PR small and reviewable:

1. Items 1, 2, 3, 4 — pure cleanups, no behavior change.
2. Item 6 then 7 — re-organize tests before refactoring code so the
   safety net is easy to read.
3. Item 5 — the big `main()` decomposition. Land it standalone.
4. Items 8, 9, 10 — domain-model tidying, one PR each.
5. Items 12, 13, 14 — rendering / logging.
6. Items 11, 15, 16 — broader model + config moves once the rest is
   stable.
7. Items 17, 18, 19 — UX / docs polish.
