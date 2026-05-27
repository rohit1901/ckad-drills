import unittest
from random import Random

from ckad_drills.datasets import load_question_bank, load_questions
from ckad_drills.generator import (
    build_drills,
    rewrite_namespace,
    select_exam_questions,
    select_questions,
)
from ckad_drills.models import Drill
from tests._fixtures import (
    EXTRA_BANK_FIXTURE,
    FIXTURE_PATH,
    SAMPLE_EXAM_BLUEPRINT_FIXTURE,
)


class TestGenerator(unittest.TestCase):
    def test_select_questions_uses_bounded_sample(self):
        questions = load_questions(FIXTURE_PATH)

        selected = select_questions(questions, 5, rng=Random(7))

        self.assertEqual(len(selected), 2)

    def test_select_questions_rejects_negative_count(self):
        questions = load_questions(FIXTURE_PATH)

        with self.assertRaises(ValueError):
            select_questions(questions, -1)

    def test_select_questions_is_reproducible_with_same_seed(self):
        questions = load_questions(FIXTURE_PATH)

        first = select_questions(questions, 2, rng=Random(11))
        second = select_questions(questions, 2, rng=Random(11))

        self.assertEqual(
            [question.question_id for question in first],
            [question.question_id for question in second],
        )

    def test_select_exam_questions_uses_full_bank_for_dynamic_variation(self):
        question_bank = load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE])
        blueprint_slot = [load_questions(SAMPLE_EXAM_BLUEPRINT_FIXTURE)[0]]

        picked_ids = {
            select_exam_questions(question_bank, blueprint_slot, 1, rng=Random(seed))[
                0
            ].question_id
            for seed in range(10)
        }

        self.assertIn("Q01", picked_ids)
        self.assertIn("Q03", picked_ids)

    def test_rewrite_namespace_updates_kubectl_and_dns_references(self):
        text = "kubectl get pod -n default && nslookup db-service.default.svc.cluster.local"

        rewritten = rewrite_namespace(text, "drill-01")

        self.assertEqual(
            rewritten,
            "kubectl get pod -n drill-01 && nslookup db-service.drill-01.svc.cluster.local",
        )

    def test_rewrite_namespace_preserves_filesystem_paths(self):
        for text in (
            "command -v helm >/dev/null",
            "kubectl auth can-i delete pods 2>/dev/null; true",
            "/etc/staging/foo",
            "/var/log/prod/app.log",
            "developer",
        ):
            with self.subTest(text=text):
                self.assertEqual(rewrite_namespace(text, "drill-01"), text)

    def test_build_drills_returns_drill_models(self):
        questions = load_questions(FIXTURE_PATH)

        drills = build_drills(questions, "drill-01")

        self.assertEqual(len(drills), 2)
        self.assertIsInstance(drills[0], Drill)
        self.assertIn("drill-01", drills[0].tasks)
        self.assertIn("drill-01", drills[1].verify)


if __name__ == "__main__":
    unittest.main()
