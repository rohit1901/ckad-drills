# ⎈ CKAD Drills

> A local, offline CKAD practice rig. Spins up a kind cluster, hands you a
> randomized exam, grades it against real `kubectl` output, and tears
> everything down when you're done.

## Why this exists

I sat the CKAD with the usual mix of resources — killer.sh, YouTube
walkthroughs, the official curriculum PDF — and kept running into the
same friction:

- killer.sh sessions are time-boxed and you only get two; you can't
  iterate on a topic until it sticks.
- "practice" repos on GitHub are mostly question lists. You still have
  to set up the cluster, eyeball whether your answer is correct, and
  reset state by hand between attempts.
- Cloud playgrounds cost money and pull you online when the actual
  exam environment is just a terminal and `kubectl`.

What I actually wanted was something I could run from my laptop, that
would behave like the real exam: a kind cluster on localhost, a fixed
time limit, randomized but domain-balanced questions, a verifier that
actually runs commands against the cluster instead of trusting me to
self-grade, and a one-keypress teardown so I could re-run the whole
thing fifty times in a weekend without leaving stale namespaces behind.

So I built it. This tool is the daily-driver I used to pass the exam,
hardened into something other people can pick up.

## What it does

- **Spins up a local cluster** (`make kind-up`) — 1 control plane + 2
  workers via `kind`, no cloud account needed.
- **Generates a balanced exam** — 22 questions / 2h by default, drawn
  from a YAML question bank using a blueprint that mirrors the
  published CKAD domain weights (20 / 20 / 15 / 25 / 20).
- **Grades against the live cluster** — each question carries
  declarative `verify` checks (`equals` / `contains` / `regex` /
  `exit_code`) that run as real `kubectl` commands.
- **Times you like the real thing** — countdown banner, periodic
  remaining-time reminders, auto-grade when the clock runs out.
- **Cleans up after itself** — opt-in tiered cleanup, from "delete the
  objects I created" all the way to "wipe the kind cluster".

```
$ ckad-drills run --mode exam
========================================================================
EXAM TIMER STARTED
========================================================================
⏱  Timer is running. Total: 2h.
   Reminders will print at 1h / 30m / 10m / 5m remaining.
...
SCORE: 17 / 22
PERCENTAGE: 77%
RESULT: 🎉 PASSING SCORE!
```

## Prerequisites

You need four things on your `PATH` before the tool can do anything
useful. All are free; none require an account.

| Tool      | Why                                            | Install                                                                                  |
| --------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Python    | runs the CLI itself (3.10 or newer)            | [python.org](https://www.python.org/downloads/) or your OS package manager               |
| Docker    | hosts the local Kubernetes cluster             | [Docker Desktop](https://docs.docker.com/get-docker/) (macOS/Windows) or Docker Engine   |
| `kind`    | spins up a kind cluster in Docker              | [kind quick-start](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)         |
| `kubectl` | talks to that cluster; also runs verify checks | [kubectl install guide](https://kubernetes.io/docs/tasks/tools/)                         |

You do **not** need a remote/cloud cluster. The repo ships its own
[`kind-config.yaml`](./kind-config.yaml) and the setup script uses it
to build the cluster locally:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
- role: worker
- role: worker
```

That gives you a 1 control-plane + 2 worker topology, which is enough
for every drill in the bank (Services / Networking drills want at
least two workers so a Service has somewhere to schedule replicas).
If you want a different shape — a single-node cluster, an extra
worker, port mappings, an image-registry sidecar — edit
`kind-config.yaml` before `make kind-up`, or point at a different
file:

```bash
make kind-up KIND_CONFIG=./my-kind-config.yaml
```

Quick sanity check before continuing:

```bash
docker info >/dev/null && kind version && kubectl version --client && python3 --version
```

If any of those error out, fix that one first — every later step
assumes them.

## First-time setup

From the repo root, run these three commands in order. They're
idempotent, so re-running any of them is safe.

```bash
# 1. Install the Python package into a local .venv (editable install).
#    Creates .venv/ on the first run; later runs just refresh deps.
make install

# 2. Bring up the local kind cluster (named 'ckad-practice' by default).
#    Runs scripts/kind-setup.sh which preflights docker/kind/kubectl,
#    creates the cluster from the bundled kind-config.yaml (1 control
#    plane + 2 workers), switches your kubectl context to
#    'kind-ckad-practice', and waits for nodes to be Ready.
#    Skips creation if the cluster already exists.
make kind-up

# 3. (Optional) Confirm the cluster is healthy.
kubectl get nodes
```

At this point you have a working cluster and the `ckad-drills` CLI is
on `PATH` inside `.venv` (or run it directly as
`.venv/bin/ckad-drills`).

## Your first exam

```bash
make exam
```

That starts a full CKAD-shaped session: **22 questions / 2-hour
timer**, drawn from the YAML banks via the balanced blueprint. You'll
see each drill's scenario and tasks; the verify commands and grading
stay hidden until you press <kbd>Enter</kbd> (or the timer expires).

Prefer a shorter warm-up?

```bash
# 5 randomized questions, no timer, against namespace drill-01
.venv/bin/ckad-drills run --mode drills --count 5 --namespace drill-01
```

On macOS, double-clicking `start_ckad_exam.command` does the
`install + kind-up + exam` chain in one shot from Finder.

## Cleaning up

When you're done practicing:

```bash
make cleanup        # delete practice namespace + kind cluster
```

If you want finer control — e.g. keep the cluster but wipe the
resources you created — see the [Cleanup tiers](#cleanup-tiers)
section below.

## CLI reference

| Flag                                          | What it does                                                            |
| --------------------------------------------- | ----------------------------------------------------------------------- |
| `--mode {exam,drills}`                        | `exam` uses the balanced blueprint; `drills` samples from the full pool |
| `--count N`                                   | override the question count (default: 22 exam, 5 drills)                |
| `--namespace drill-01`                        | rewrite known namespaces in every question to this one                  |
| `--time-limit 2h` / `--no-timer`              | override or disable the countdown                                       |
| `--seed 42`                                   | reproducible selection                                                  |
| `--hide-solutions`                            | skip the end-of-session solution review                                 |
| `--cleanup {none,objects,namespace,kind-cluster}` | tiered post-session cleanup                                          |
| `cleanup-only`                                | run cleanup without starting a session                                  |

Exit codes:

| Code | Meaning                                                          |
| ---- | ---------------------------------------------------------------- |
| `0`  | session completed and the exam was passed (≥ 66%)                |
| `1`  | infrastructure failure — bad args, dataset error, cleanup failed |
| `2`  | exam ran to completion but the final score was below 66%         |

This lets CI / shell pipelines distinguish "the runner broke" from "the
practice attempt didn't pass".

## Cleanup tiers

Pick the one that matches what you want gone (all honour
`NAMESPACE=...` and `KIND_CLUSTER_NAME=...`):

| Target                   | Deletes                                                       |
| ------------------------ | ------------------------------------------------------------- |
| `make cleanup-objects`   | drill resources inside the practice namespace                 |
| `make cleanup-namespace` | the entire practice namespace                                 |
| `make kind-down`         | the local kind cluster + its kubectl context                  |
| `make kind-nuke`         | **every** kind cluster on the machine (useful for leftovers)  |
| `make cleanup`           | full teardown: namespace + kind cluster                       |

Protected namespaces (`default`, `kube-system`, …) are blocked from
destructive cleanup. `kind-cluster` cleanup requires an explicit
`--kind-cluster-name`.

## Question banks

The canonical question pool lives under
[`question_banks/`](./question_banks). Each YAML file is a list of
drills with `scenario`, `tasks`, declarative `verify` checks, and
optional `setup` / `teardown` phases.

`question_banks/balanced_exam.yaml` is the **blueprint** — it lists
`(domain, topic)` slots, not real questions, and the runtime samples a
matching question from the full pool for each slot. This means exam
mode varies between runs while staying domain-balanced.

To extend the pool, drop another `*.yaml` (or legacy `*.csv`) into
`question_banks/`; see
[`question_banks/README.md`](./question_banks/README.md) for the full
schema and the maintenance workflow.

## Coming soon

Things on the roadmap, roughly in priority order:

- 🧠 **Per-question hint streaming.** Right now hints surface only in
  the end-of-session review. The plan is to expose them on-demand
  during a drill (`h` to reveal one hint at a time) without affecting
  the score.
- 🧪 **Custom playlists.** Save a named subset of question ids ("things
  I keep failing") and replay them as a focused mini-exam.
- 📊 **Per-domain analytics across runs.** A small JSON log under
  `~/.ckad-drills/history.json` so you can see whether your Networking
  score actually improved over a week of practice.
- 🔁 **Spaced-repetition mode.** Questions you failed recently get
  weighted higher in `--mode drills` until you pass them N times in a
  row.
- 🧰 **Operator-style per-drill namespaces.** One ephemeral namespace
  per drill, deleted on teardown, so concurrent drills can't stomp on
  each other's state.
- 🪟 **Cross-platform launcher.** A `start_ckad_exam.ps1` /
  `start_ckad_exam.sh` sibling to the existing macOS `.command`
  double-click launcher.
- 🌐 **Question-bank sharing.** A documented convention for publishing
  community YAML banks (e.g. `ckad-drills install
  github:user/repo@v1`).

If any of these are interesting to you, open an issue or a PR — the
codebase is structured to make most of them additive rather than
invasive (see `REFACTORING_TODO.md` for the recent cleanup that paved
the way).

## Project layout

```
src/ckad_drills/
├── cli.py              # argparse + SessionRunner orchestration
├── session.py          # load → prepare → grade → cleanup
├── generator.py        # drill selection, exam blueprint sampling, ns rewriting
├── yaml_datasets.py    # YamlBankParser
├── datasets.py         # legacy CSV loader
├── check_evaluator.py  # equals / contains / regex / exit_code dispatch
├── grading.py          # score summarization
├── environment.py      # setup / teardown phase execution
├── cleanup.py          # tiered post-session cleanup
├── renderer.py         # ANSI Style + section helpers
├── timer.py            # SessionTimer with reminders + SIGINT-on-expiry
├── kubectl_runner.py   # subprocess wrappers
├── models.py           # frozen dataclasses + runner type aliases
└── config.py           # CKAD_* constants + question-bank discovery
question_banks/         # YAML banks + balanced_exam.yaml blueprint
tests/                  # one test_*.py per source module
scripts/                # kind-setup / kind-cleanup / a YAML-pipeline demo
```

## Running the test suite

```bash
make test       # 77 tests, all offline — no cluster required
```

The grader, cleanup planner, YAML parser, renderer, and timer are all
pure-function-friendly and tested with fake runners; no test touches a
real `kubectl`.

## Limitations / honest caveats

- The grader is only as good as the `verify` commands in the YAML
  banks. A bad check passes a wrong answer; a brittle check fails a
  correct one.
- `kubectl` and a working kubeconfig are required at runtime —
  containerizing the runner itself is possible but adds friction for
  no obvious gain on a local laptop.
- The real CKAD also tests speed in a remote browser-based terminal.
  This tool can simulate the time limit but not the input lag.
