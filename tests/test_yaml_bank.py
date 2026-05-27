import unittest

from ckad_drills.yaml_datasets import load_yaml_questions
from tests._fixtures import YAML_BANK_FIXTURE


class TestYAMLBank(unittest.TestCase):
    def test_load_yaml_questions_parses_structured_checks(self):
        questions = load_yaml_questions(YAML_BANK_FIXTURE)

        self.assertEqual(len(questions), 2)
        first = questions[0]
        self.assertEqual(first.question_id, "YQ-FIX-01")
        self.assertEqual(len(first.checks), 4)
        self.assertEqual(first.checks[0].kind, "equals")
        self.assertEqual(first.checks[0].value, "hello")
        self.assertEqual(first.checks[1].kind, "contains")
        self.assertEqual(first.checks[2].kind, "regex")
        # No expect block -> default exit_code 0.
        self.assertEqual(first.checks[3].kind, "exit_code")
        self.assertEqual(first.checks[3].value, "0")
        self.assertEqual(len(first.setup_steps), 1)
        self.assertEqual(len(first.teardown_steps), 1)

    def test_load_yaml_questions_supports_string_verify_fallback(self):
        questions = load_yaml_questions(YAML_BANK_FIXTURE)
        second = questions[1]

        self.assertEqual(second.question_id, "YQ-FIX-02")
        self.assertEqual(second.checks, ())
        self.assertEqual(second.verify, "true")


if __name__ == "__main__":
    unittest.main()
