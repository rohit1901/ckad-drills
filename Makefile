PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

# kind cluster defaults; override on the command line, e.g.:
#   make kind-up KIND_CLUSTER_NAME=my-cluster KIND_CONFIG=./kind-config.yaml
KIND_CLUSTER_NAME ?= ckad-practice
KIND_CONFIG ?= kind-config.yaml

# Practice namespace used by run/exam/cleanup. Override on the command line:
#   make cleanup NAMESPACE=drill-02
#   make run NAMESPACE=drill-02
NAMESPACE ?= drill-01

.PHONY: install test kind-up kind-down kind-nuke run exam \
        cleanup cleanup-objects cleanup-namespace cleanup-all \
        kind-cleanup

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -e .

test: install
	$(BIN)/python -m unittest discover -s tests -t . -p 'test_*.py'

# Bring up a local kind cluster from kind-config.yaml. Safe to re-run.
kind-up:
	./scripts/kind-setup.sh $(KIND_CLUSTER_NAME) $(KIND_CONFIG)

# Tear down the local kind cluster created by `make kind-up`.
kind-down:
	./scripts/kind-cleanup.sh $(KIND_CLUSTER_NAME)

# Nuke EVERY kind cluster on this machine (useful if you have leftovers like
# the default-named 'kind' cluster from a previous manual 'kind create cluster').
kind-nuke:
	./scripts/kind-cleanup.sh --all

# Drill / exam targets depend on the cluster being up.
run: install kind-up
	$(BIN)/ckad-drills run --mode drills --count 5 --namespace $(NAMESPACE)

exam: install kind-up
	$(BIN)/ckad-drills run --mode exam --count 5 --namespace $(NAMESPACE)

# ---- Cleanup ---------------------------------------------------------------
# Levels of cleanup, from least to most destructive:
#
#   make cleanup-objects     delete drill resources inside $(NAMESPACE)
#   make cleanup-namespace   delete the entire $(NAMESPACE) namespace
#   make kind-cleanup        delete the local kind cluster (and its kubectl ctx)
#   make cleanup-all         do all of the above, in order
#
# `make cleanup` is kept as a friendly alias for `cleanup-all` so users get a
# complete teardown by default instead of a partial one.

cleanup-objects: install
	$(BIN)/ckad-drills cleanup-only --cleanup objects --namespace $(NAMESPACE)

cleanup-namespace: install
	$(BIN)/ckad-drills cleanup-only --cleanup namespace --namespace $(NAMESPACE)

cleanup-all: cleanup-namespace kind-down

cleanup: cleanup-all

# Back-compat alias.
kind-cleanup: kind-down
