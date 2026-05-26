# Extendable question banks

Drop additional question bank files in this directory to extend the CKAD drill pool. **Both YAML and CSV formats are supported and loaded together**; question ids must be unique across every file (CSV base bank + CSV extensions + YAML banks).

The recommended format for new content is YAML — it supports declarative verification (per-check pass/fail) and optional `setup` / `teardown` phases. See [`yaml_demo.yaml`](./yaml_demo.yaml) for a complete, working example.

## YAML schema

```yaml
questions:
  - id: <unique id>
    domain: <CKAD domain, e.g. "Application Design and Build (20%)">
    topic: <CKAD topic name>
    scenario: |
      <Multi-line narrative shown to the user.>
    tasks: |
      1. <Multi-line list of what the user must do.>
      2. ...

    # Optional. Runs BEFORE the drill is shown so the user starts from a
    # known-good state (e.g. namespaces and prerequisite objects exist).
    setup:
      - name: <human readable label>          # optional
        run: <shell command>                  # OR
      - name: <label>
        apply: |                              # inline kubernetes manifest
          apiVersion: v1
          kind: Namespace
          metadata: { name: workloads }

    # Required. Two shapes:
    #   (a) a single shell pipeline string — passes when exit code is 0
    #   (b) a list of named checks with declarative expectations (preferred)
    verify:
      - name: <label>
        run: <shell command>
        expect:
          # exactly one of:
          equals:       <exact stdout, leading/trailing whitespace stripped>
          contains:     <substring of stdout>
          not_contains: <substring that must NOT appear in stdout>
          regex:        <python regex matched against stdout>
          exit_code:    <integer; default behavior when 'expect:' is omitted is exit_code 0>

    # Optional. Runs AFTER grading regardless of pass/fail. Mirror of `setup`.
    teardown:
      - run: kubectl delete pod demo-pod -n workloads --ignore-not-found

    hints: |
      <Free-text hints shown in the solution review.>
```

### Verification semantics

- For `equals` / `contains` / `not_contains` / `regex`, the command **must also exit 0**. A non-zero exit reports the failing exit code (and stderr snippet) in the per-check detail, regardless of the expectation kind.
- `exit_code` only inspects the process exit code and ignores stdout/stderr content.
- `equals` compares trimmed stdout to a trimmed expected string.
- `regex` uses Python regex semantics with `MULTILINE | DOTALL`.
- A drill passes only when **every** verify check passes.

### Setup vs teardown

- `setup` is run for **every** drill in the current session, in order, before the user is prompted. Failures are reported but do not block the session — the warning is printed and the user can still attempt the drills.
- `teardown` is run after grading, regardless of whether the drill passed or failed. Failures are reported but do not change the grading outcome.

### Namespace rewriting

The runtime rewrites well-known namespaces (`workloads`, `team-alpha`, `team-beta`, `ckad-practice`, `dev`, `staging`, `prod`, etc.) inside `scenario`, `tasks`, `verify.*.run`, `setup.*.run`, `setup.*.apply`, and `teardown.*.run` to whatever you pass via `--namespace`. Author YAML drills against one of those well-known namespaces and they'll automatically migrate.

## CSV (legacy)

The existing `ckad_full_question_bank.csv` and `ckad_balanced_exam.csv` continue to work unchanged. To extend via CSV, drop a `*.csv` file here matching the same header schema (`id,domain,topic,scenario,tasks,verify,hints`) and a single shell pipeline in the `verify` column.

## Rules

- Every question id must be unique across all CSV + YAML banks.
- YAML files use the `.yaml` or `.yml` extension. CSV files use `.csv`.
- Top-level YAML may be either `questions: [...]` (recommended) or a bare list of question mappings.
