"""Shared fixture-path constants for the test suite."""

from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_ROOT / "fixtures"

FIXTURE_PATH = FIXTURES_DIR / "sample_questions.csv"
EXTRA_BANK_FIXTURE = FIXTURES_DIR / "sample_questions_extra.csv"
SAMPLE_EXAM_BLUEPRINT_FIXTURE = FIXTURES_DIR / "sample_exam_blueprint.csv"
SAMPLE_EXAM_BLUEPRINT_YAML_FIXTURE = FIXTURES_DIR / "sample_exam_blueprint.yaml"
INVALID_EXAM_BLUEPRINT_FIXTURE = FIXTURES_DIR / "invalid_exam_blueprint_unknown_id.csv"
INVALID_SCHEMA_FIXTURE = FIXTURES_DIR / "invalid_questions_missing_verify.csv"
INVALID_ROW_FIXTURE = FIXTURES_DIR / "invalid_questions_empty_verify.csv"
YAML_BANK_FIXTURE = FIXTURES_DIR / "sample_yaml_bank.yaml"
