import unittest

from ckad_drills.datasets import (
    load_question_bank,
    load_questions,
    validate_exam_blueprint_references,
)
from ckad_drills.exceptions import DatasetValidationError
from tests._fixtures import (
    EXTRA_BANK_FIXTURE,
    FIXTURE_PATH,
    INVALID_EXAM_BLUEPRINT_FIXTURE,
    INVALID_ROW_FIXTURE,
    INVALID_SCHEMA_FIXTURE,
)


class TestDatasets(unittest.TestCase):
    def test_load_questions_returns_typed_questions(self):
        questions = load_questions(FIXTURE_PATH)

        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0].question_id, "Q01")
        self.assertEqual(questions[1].verify, "kubectl get svc -n team-alpha")

    def test_load_question_bank_merges_base_and_extension_files(self):
        questions = load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE])

        self.assertEqual(len(questions), 3)
        self.assertEqual(
            [question.question_id for question in questions], ["Q01", "Q02", "Q03"]
        )

    def test_load_question_bank_rejects_duplicate_ids(self):
        with self.assertRaises(DatasetValidationError) as context:
            load_question_bank([FIXTURE_PATH, FIXTURE_PATH])

        self.assertIn("Duplicate question id 'Q01'", str(context.exception))

    def test_validate_exam_blueprint_references_rejects_unknown_ids(self):
        question_bank = load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE])
        blueprint_questions = load_questions(INVALID_EXAM_BLUEPRINT_FIXTURE)

        with self.assertRaises(DatasetValidationError) as context:
            validate_exam_blueprint_references(
                blueprint_questions,
                question_bank,
                blueprint_path=INVALID_EXAM_BLUEPRINT_FIXTURE,
            )

        self.assertIn("invalid_exam_blueprint_unknown_id.csv", str(context.exception))
        self.assertIn("Q99", str(context.exception))

    def test_load_questions_rejects_missing_required_columns(self):
        with self.assertRaises(DatasetValidationError) as context:
            load_questions(INVALID_SCHEMA_FIXTURE)

        self.assertIn("invalid_questions_missing_verify.csv", str(context.exception))
        self.assertIn("verify", str(context.exception))

    def test_load_questions_rejects_missing_required_row_values(self):
        with self.assertRaises(DatasetValidationError) as context:
            load_questions(INVALID_ROW_FIXTURE)

        self.assertIn("invalid_questions_empty_verify.csv", str(context.exception))
        self.assertIn("missing value(s) for verify", str(context.exception))


if __name__ == "__main__":
    unittest.main()
