# CKAD question banks

This directory holds the **canonical question pool** for the CKAD drill
generator. YAML is the primary format — it supports per-check verification
(`equals` / `contains` / `not_contains` / `regex` / `exit_code`) plus
optional `setup` and `teardown` phases. CSV is still supported as a legacy
extension surface, but the project no longer ships a CSV base bank.

```
question_banks/
├── README.md
├── balanced_exam.yaml                          ← exam-mode blueprint (slots only)
├── application_design_and_build.yaml           ← Q01–Q11
├── application_deployment.yaml                 ← Q12–Q17
├── application_observability_and_maintenance.yaml ← Q18–Q24
├── application_environment_configuration_and_security.yaml ← Q25–Q33
├── services_and_networking.yaml                ← Q34–Q38
└── yaml_demo.yaml                              ← runnable example (YQ01–YQ02)
```

Question ids must be unique across **every** file in this directory
(`*.yaml`, `*.yml`, and any optional `*.csv` extension banks you drop in).

## How the runtime consumes these files

- **Drills mode** (`ckad-drills run --mode drills`) loads every `*.yaml`,
  `*.yml`, and `*.csv` file in this directory — *except* `balanced_exam.yaml`
  — into a single pool and samples `--count` questions from it.
- **Exam mode** (`ckad-drills run --mode exam`) reads `balanced_exam.yaml`
  as a list of `(domain, topic)` slots, then samples one real question per
  slot from the same pool. Only the slot metadata in `balanced_exam.yaml`
  matters — its scenario / tasks / verify fields are intentionally minimal.

> **Note on the blueprint's `verify:` field.** Every slot in
> `balanced_exam.yaml` carries a placeholder `verify: |\n  true` block.
> The YAML schema requires the field to be present and non-empty, but the
> runtime **never executes it** in exam mode — it only reads the slot's
> `domain` and `topic` to pick a real question from the pool. Keep the
> placeholder as-is when adding or editing slots; do not write real verify
> commands in `balanced_exam.yaml`.

To change the shape of the exam, edit `balanced_exam.yaml` and add/remove
slot entries. The default 15-slot mix tracks the published CKAD weighting:

| Domain                                            | Weight | Slots |
| ------------------------------------------------- | -----: | ----: |
| Application Design and Build                      |    20% |     3 |
| Application Deployment                            |    20% |     3 |
| Application Observability and Maintenance         |    15% |     2 |
| Application Environment, Configuration & Security |    25% |     4 |
| Services and Networking                           |    20% |     3 |
| **Total**                                         |   100% |    15 |

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

See [`yaml_demo.yaml`](./yaml_demo.yaml) for a complete, runnable example.

### Verification semantics

- For `equals` / `contains` / `not_contains` / `regex`, the command **must
  also exit 0**. A non-zero exit reports the failing exit code (and stderr
  snippet) in the per-check detail, regardless of the expectation kind.
- `exit_code` only inspects the process exit code and ignores stdout/stderr
  content. This is the right tool for "I just want to know if the command
  succeeded".
- `equals` compares trimmed stdout to a trimmed expected string. Quote
  numeric values (`equals: "3"`, not `equals: 3`) so YAML doesn't coerce
  them to int.
- `regex` uses Python regex semantics with `MULTILINE | DOTALL`.
- A drill passes only when **every** verify check passes.

### Tip: `kubectl auth can-i` and "expected denied"

`kubectl auth can-i` exits 0 for "yes" and 1 for "no", and prints the literal
words `yes` / `no` to stdout. To assert a permission is **denied**, run the
command with stderr suppressed and force the pipeline exit to 0, then check
the stdout text:

```yaml
- name: "RBAC: developer CANNOT delete pods (denied)"
  run: kubectl auth can-i delete pods --as=developer -n ckad-practice 2>/dev/null; true
  expect:
    contains: "no"
```

### Setup vs teardown

- `setup` is run for **every** drill in the current session, in order,
  before the user is prompted. Failures are reported but do not block the
  session — the warning is printed and the user can still attempt the
  drills.
- `teardown` is run after grading, regardless of whether the drill passed or
  failed. Failures are reported but do not change the grading outcome.

### Namespace rewriting

The runtime rewrites well-known namespaces (`workloads`, `team-alpha`,
`team-beta`, `ckad-practice`, `dev`, `staging`, `prod`, etc.) inside
`scenario`, `tasks`, `verify.*.run`, `setup.*.run`, `setup.*.apply`, and
`teardown.*.run` to whatever you pass via `--namespace`. Author YAML drills
against one of those well-known namespaces and they'll automatically
migrate.

## External tool requirements

Several drills exercise tooling that is not part of base Kubernetes; the
drill's `setup` will fail loudly if the binary is missing.

| Drill          | Requires                                   |
| -------------- | ------------------------------------------ |
| Q15, Q16       | `helm` CLI                                 |
| Q17            | `kubectl` 1.14+ (built-in kustomize) or `kustomize` CLI |
| Q21            | metrics-server (for `kubectl top`)         |
| Q25            | RBAC permission to create CRDs             |
| Q35            | A CNI that enforces NetworkPolicies (Calico/Cilium); the in-tree kindnet does **not** |
| Q38            | An Ingress controller (e.g. NGINX Ingress) |

## Legacy CSV format

CSV is still loaded for any `*.csv` file dropped in this directory. Header:

```
id,domain,topic,scenario,tasks,verify,hints
```

`verify` is a single shell pipeline; the drill passes when the pipeline
exits 0. For richer per-check assertions or `setup`/`teardown` steps, use
the YAML format above.

## Rules

- Every question id must be unique across all CSV + YAML banks.
- YAML files use the `.yaml` or `.yml` extension. CSV files use `.csv`.
- Top-level YAML may be either `questions: [...]` (recommended) or a bare
  list of question mappings.
- `balanced_exam.yaml` is treated specially as the exam-mode blueprint and
  is **excluded** from the drills-mode pool.
