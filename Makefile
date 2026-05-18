PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: install test run exam cleanup

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -e .

test: install
	$(BIN)/python -m unittest discover -s tests -p 'test_*.py'

run: install
	$(BIN)/ckad-drills run --mode drills --count 5 --namespace drill-01

exam: install
	$(BIN)/ckad-drills run --mode exam --count 5 --namespace drill-01

cleanup: install
	$(BIN)/ckad-drills cleanup-only --cleanup objects --namespace drill-01
