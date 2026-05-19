# CKAD Drills

A local CLI tool for generating CKAD-style Kubernetes drills from CSV question banks, running an interactive practice session, and grading your work against `kubectl` verification commands.

## How to use the CKAD tests

### Prerequisites
- Python 3.10+
- [Docker](https://docs.docker.com/get-docker/) running locally
- [`kind`](https://kind.sigs.k8s.io/docs/user/quick-start/#installation) for spinning up the local cluster
- [`kubectl`](https://kubernetes.io/docs/tasks/tools/) on your `PATH`

You do not need a pre-existing remote cluster. The repo ships a `kind-config.yaml` and helper scripts that build a local 1 control-plane + 2 worker cluster for you.

### Set up the local kind cluster
Before running any drills, bring up the local Kubernetes cluster:

- `make kind-up`

This runs `scripts/kind-setup.sh`, which:
- verifies `docker`, `kind`, and `kubectl` are installed and on your `PATH`
- verifies the Docker daemon is reachable
- creates a kind cluster named `ckad-practice` from `kind-config.yaml` (skips creation if it already exists)
- switches your `kubectl` context to `kind-ckad-practice`
- waits for all nodes to become `Ready`

If any preflight check fails, the script exits with a clear error message and a hint telling you what to fix (missing tool, Docker not running, missing config file, cluster unhealthy, etc.).

You can override the defaults:

- `make kind-up KIND_CLUSTER_NAME=my-cluster KIND_CONFIG=./kind-config.yaml`
- `./scripts/kind-setup.sh my-cluster ./kind-config.yaml`

### Tear down the local kind cluster
When you are done practicing, remove the local cluster and its `kubectl` context:

- `make kind-down`

This runs `scripts/kind-cleanup.sh`, which:
- deletes the named kind cluster (if it exists)
- removes the matching `kubectl` context, cluster, and user entries
- removes any stray kind containers left behind by a crashed run
- **lists any *other* kind clusters still present on your machine** so leftovers don't go unnoticed

Override the cluster name the same way:

- `make kind-down KIND_CLUSTER_NAME=my-cluster`
- `./scripts/kind-cleanup.sh my-cluster`

#### Wiping every kind cluster
If the cleanup script reports leftover clusters (for example a cluster literally named `kind`, which is what `kind create cluster` produces when no `--name` is given), you have two options:

- delete them one by one: `make kind-down KIND_CLUSTER_NAME=<name>`
- wipe them all at once: `make kind-nuke` (equivalent to `./scripts/kind-cleanup.sh --all`)

`make kind-nuke` will iterate over every cluster reported by `kind get clusters` and delete it, along with its kubectl context and any stray containers.

### Install
You can set up the Python project with:

- `make install`

This creates a local virtual environment in `.venv` and installs the package in editable mode.

After installation, you can use the CLI in either of these ways:

- `source .venv/bin/activate` and then run `ckad-drills ...`
- run the local executable directly with `.venv/bin/ckad-drills ...`

If you skip installation, `ckad-drills` will not exist on your shell `PATH`. In that case, use `python ckad_gen.py ...` instead.

### Run practice drills
To start a general drill session from the full question bank:

- `make run`

To start a balanced exam-style session:

- `make exam`

Both targets depend on `make kind-up`, so the local cluster is created automatically (or reused if already up) before drills start.

Exam mode is dynamic: it uses `ckad_balanced_exam.csv` as a blueprint for balanced coverage, then selects matching questions from the full question bank. That means you can get a different exam set on different runs while keeping the intended balance.

You can also run the CLI directly:

- `ckad-drills run --mode drills --count 5 --namespace drill-01`
- `.venv/bin/ckad-drills run --mode drills --count 5 --namespace drill-01`
- `.venv/bin/ckad-drills run --mode exam --count 10 --namespace drill-02`
- `python ckad_gen.py help`

### Useful CLI options
- `--seed 42`
  - uses a fixed random seed so you can reproduce the same drill selection later
- `--show-solutions`
  - explicitly show the solution review section at the end of the session
- `--hide-solutions`
  - hide the solution review section and only show scoring output
- `--namespace drill-01`
  - rewrites supported namespaces in the drills so you can practice in a controlled namespace
- `--cleanup objects`
  - deletes common namespaced Kubernetes resources in your practice namespace after grading
- `--cleanup namespace`
  - deletes the entire practice namespace after grading
- `--cleanup kind-cluster --kind-cluster-name ckad-practice`
  - deletes the full local kind cluster after grading
- `cleanup-only`
  - runs cleanup without generating or grading a session

Example:

- `ckad-drills run --mode exam --count 5 --namespace drill-01 --seed 42 --hide-solutions`
- `.venv/bin/ckad-drills run --mode drills --namespace drill-01 --cleanup objects`
- `.venv/bin/ckad-drills run --mode exam --cleanup kind-cluster --kind-cluster-name ckad-practice`
- `.venv/bin/ckad-drills cleanup-only --cleanup namespace --namespace drill-01`

### Colored terminal output
When you run the tool in an interactive terminal, it uses colored output for:

- section headers
- drill labels
- pass/fail status lines
- final result summary

This makes it easier to scan the results during a practice session.

### One-click start on macOS
If you want a double-click launcher, use:

- `start_ckad_exam.command`

This bootstraps the virtual environment, installs the package, and starts an exam session.

### Test the project itself
To run the automated unit test suite:

- `make test`

Cleanup is tiered, from least to most destructive. Pick the one that matches what you want gone:

- `make cleanup-objects` — delete drill resources inside the practice namespace (keeps the namespace and the cluster).
- `make cleanup-namespace` — delete the entire practice namespace (keeps the kind cluster).
- `make kind-cleanup` (alias for `make kind-down`) — delete the local kind cluster and its kubectl context. Also reports any other leftover kind clusters.
- `make kind-nuke` — delete **every** kind cluster on the machine. Use this if `make kind-down` warns about leftovers (e.g. a default-named `kind` cluster from a previous `kind create cluster`).
- `make cleanup-all` — namespace cleanup + `kind-down`, in order. This is the full teardown for the cluster `make kind-up` created.
- `make cleanup` — friendly alias for `make cleanup-all`.

All cleanup targets honor the `NAMESPACE` variable, which defaults to `drill-01`. If you ran a session in a different namespace, pass it explicitly:

- `make cleanup-objects NAMESPACE=drill-02`
- `make cleanup-namespace NAMESPACE=drill-02`
- `make cleanup NAMESPACE=drill-02`

Likewise, `make kind-cleanup` honors `KIND_CLUSTER_NAME`:

- `make kind-cleanup KIND_CLUSTER_NAME=my-cluster`

### What happens during a session
1. The tool loads drills from one of the CSV files:
   - `ckad_full_question_bank.csv`
   - `ckad_balanced_exam.csv`
2. It rewrites the drill namespaces to your chosen practice namespace.
3. It shows the scenario and tasks, but hides grading internals until the end.
4. After you press Enter, it runs the `verify` commands from the CSV against your cluster.
5. It prints:
   - pass/fail per drill
   - per-domain score breakdown
   - overall score and percentage
   - optional solution review with verification commands and hints
6. If cleanup is enabled, it runs the requested cleanup workflow and prints the cleanup status and commands used.

### Question bank structure
The project now uses two concepts:

- `ckad_full_question_bank.csv`
  - the canonical base question bank
- `ckad_balanced_exam.csv`
  - an exam blueprint, not a fixed exam output list

In exam mode, the CLI validates that every `id` in `ckad_balanced_exam.csv` exists in `ckad_full_question_bank.csv`, then builds a balanced exam dynamically from the full bank.

### Extend the question bank
If you want to add more questions in the future, place additional CSV files in:

- `question_banks/`

Rules:
- use the same CSV schema as the base question bank
- every question must have a unique `id`
- do not reuse an `id` from the base bank or another extension file

These extension files are loaded automatically in both drill mode and exam mode.

### Guide: maintain the question bank and exam blueprint
Use this workflow when you want to add new questions or evolve the exam over time.

#### 1. Understand the roles of the files
- `ckad_full_question_bank.csv`
  - the canonical base bank
  - blueprint ids are validated against this file
- `ckad_balanced_exam.csv`
  - a blueprint describing the balanced exam slots
  - it is not the final exam output anymore
- `question_banks/*.csv`
  - optional extension banks for new questions
  - loaded automatically in drill mode and exam mode

#### 2. Add new questions safely
You have two options:
- add them directly to `ckad_full_question_bank.csv`
- or add them as new CSV files under `question_banks/`

For each new question:
- keep the same CSV schema
- assign a unique `id`
- make sure `domain` and `topic` are set consistently so exam mode can match blueprint slots well
- provide a usable `verify` command and a meaningful `hints` value

#### 3. Example: add one new question step by step
A simple way to add one new question without touching the base bank is:

1. create a new CSV file under `question_banks/`, for example `question_banks/networking_extra.csv`
2. add the standard header row:
   - `id,domain,topic,scenario,tasks,verify,hints`
3. add your new question row with:
   - a brand new unique `id`
   - a valid `domain`
   - a useful `topic`
   - a scenario, tasks, verify command, and hint
4. run `make test` to make sure the project still passes validation
5. run a drill or exam session and confirm the new question can be selected

If the new question should help exam mode produce more variety, make its `domain` and `topic` align with one of the blueprint slots in `ckad_balanced_exam.csv`.

#### 4. How dynamic exam generation works now
When you run exam mode:
1. the app loads the base question bank
2. it loads any extension banks from `question_banks/`
3. it loads `ckad_balanced_exam.csv` as a blueprint
4. it validates that every blueprint `id` exists in `ckad_full_question_bank.csv`
5. it randomly selects blueprint slots
6. for each slot, it picks a matching question from the merged question bank

This means the exam can vary between runs while still staying balanced by domain and topic.

#### 5. When to update `ckad_balanced_exam.csv`
Update the blueprint when you want to change:
- the balance across domains
- the balance across topics
- the number or style of exam slots

You do not need to add every new question to the blueprint. The blueprint defines the exam shape, while the full bank and extension banks provide the actual selectable questions.

#### 6. Best practice for future growth
A good pattern is:
- keep `ckad_full_question_bank.csv` as the stable canonical bank
- add new batches of questions in separate files under `question_banks/`
- only change `ckad_balanced_exam.csv` when you want to change exam composition rules

That keeps the system easy to extend without turning the exam file into a hard-coded static list.

### Cleanup modes
The CLI supports opt-in cleanup after grading, and also as a standalone command:

- `--cleanup none`
  - do nothing after the session ends
- `--cleanup objects`
  - delete a broad set of namespaced resources in the target namespace
- `--cleanup namespace`
  - delete the target namespace itself
- `--cleanup kind-cluster --kind-cluster-name <name>`
  - delete a local kind cluster by name

You can also run cleanup without starting a session:

- `.venv/bin/ckad-drills cleanup-only --cleanup objects --namespace drill-01`
- `.venv/bin/ckad-drills cleanup-only --cleanup namespace --namespace drill-01`
- `.venv/bin/ckad-drills cleanup-only --cleanup kind-cluster --kind-cluster-name ckad-practice`

### Cleanup safety rules
To reduce accidental damage:

- cleanup is disabled by default
- protected namespaces such as `default` and `kube-system` are blocked for destructive namespace or object cleanup
- `kind-cluster` cleanup requires an explicit `--kind-cluster-name`

### CSV validation behavior
The loader validates the CSV question banks before starting a session.

It checks for:
- required headers such as `scenario`, `tasks`, and `verify`
- at least one identifier column: `id` or `exam_id`
- required row values for the fields used by the drill engine

If the CSV is invalid, the CLI exits with a friendly error message that includes the file name and the missing columns or missing row values.

## Technical details of this project

### Project structure
This project uses the Python `src` layout:

- `src/ckad_drills/cli.py` — CLI entrypoint, session flow, and cleanup-only command
- `src/ckad_drills/session.py` — session orchestration
- `src/ckad_drills/renderer.py` — terminal output rendering and ANSI colors
- `src/ckad_drills/datasets.py` — CSV loading, schema validation, bank merging, and blueprint validation
- `src/ckad_drills/generator.py` — drill selection, dynamic exam generation, and namespace rewriting
- `src/ckad_drills/grading.py` — grading and score summarization
- `src/ckad_drills/cleanup.py` — cleanup planning, safety checks, and post-session execution
- `src/ckad_drills/kubectl_runner.py` — shell execution of verification and cleanup commands
- `src/ckad_drills/models.py` — typed domain models and summaries
- `src/ckad_drills/exceptions.py` — custom exceptions for user-facing validation errors
- `tests/` — unit tests and fixtures

### Design approach
The code is intentionally split into small modules:

- **CLI layer** handles argument parsing, error handling, and interactive prompts.
- **Session layer** prepares drills, loads merged question banks, and evaluates them.
- **Rendering layer** formats drill output, grading reports, and cleanup summaries.
- **Grading layer** converts verification outcomes into structured score summaries.
- **Cleanup layer** validates destructive cleanup options and builds cleanup commands safely.
- **Dataset layer** validates and loads CSV content before the session starts.

This keeps the business logic easier to test and change independently from terminal I/O.

### TDD focus
The project is structured to support test-driven development:

- dataset loading is testable with fixture CSV files
- selection and namespace rewriting are pure functions
- seeded selection is testable for reproducibility
- dynamic exam generation is testable against fixture blueprints and question banks
- question bank merging and duplicate-id validation are testable with fixture CSV files
- grading can be tested with fake runners instead of calling real `kubectl`
- rendering can be tested as plain string output
- cleanup planning and safety rules are tested without touching a real cluster
- CLI help and validation behavior are covered with smoke tests

The unit tests currently use Python's built-in `unittest` framework.

### Grading model
Each drill is graded by executing the `verify` command from the CSV. The results are summarized into:

- per-drill pass/fail
- overall score
- percentage score
- per-domain scorecard
- failed drill tracking
- optional end-of-session solution review

### Notes and limitations
- The grader is only as good as the `verify` commands in the CSV files.
- Since verification is command-based, your local cluster state matters.
- Exam blueprints depend on the base question bank ids staying stable.
- Cleanup commands are intentionally conservative, but destructive cleanup still deserves care.
- Colored output is intended for interactive terminals and may not appear the same in every environment.
- Docker is possible for CI or reproducible development, but for local practice a native environment is simpler because `kubectl` and kubeconfig access are required.
