import unittest
from unittest.mock import patch

from ckad_drills import session as _session
from ckad_drills.datasets import load_question_bank
from ckad_drills.session import (
    cleanup_session,
    load_configured_question_bank,
    prepare_drills,
)
from tests._fixtures import (
    EXTRA_BANK_FIXTURE,
    FIXTURE_PATH,
    SAMPLE_EXAM_BLUEPRINT_YAML_FIXTURE,
)


class TestSession(unittest.TestCase):
    def test_load_configured_question_bank_includes_extensions(self):
        with (
            patch.object(
                _session,
                "resolve_question_bank_extension_paths",
                return_value=[FIXTURE_PATH, EXTRA_BANK_FIXTURE],
            ),
            patch.object(
                _session,
                "resolve_yaml_question_bank_paths",
                return_value=[],
            ),
        ):
            questions = load_configured_question_bank()

        self.assertEqual(
            [question.question_id for question in questions], ["Q01", "Q02", "Q03"]
        )

    def test_prepare_drills_is_reproducible_with_seed(self):
        with patch.object(
            _session,
            "load_configured_question_bank",
            return_value=load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE]),
        ):
            first = prepare_drills("drills", 2, "drill-01", seed=5)
            second = prepare_drills("drills", 2, "drill-01", seed=5)

        self.assertEqual(
            [drill.question_id for drill in first],
            [drill.question_id for drill in second],
        )

    def test_prepare_exam_drills_uses_blueprint_and_full_bank(self):
        with (
            patch.object(
                _session,
                "load_configured_question_bank",
                return_value=load_question_bank([FIXTURE_PATH, EXTRA_BANK_FIXTURE]),
            ),
            patch.object(
                _session,
                "resolve_exam_blueprint_path",
                return_value=SAMPLE_EXAM_BLUEPRINT_YAML_FIXTURE,
            ),
        ):
            drills = prepare_drills("exam", 2, "drill-01", seed=7)

        self.assertEqual(len(drills), 2)
        self.assertTrue(
            all(drill.question_id in {"Q01", "Q02", "Q03"} for drill in drills)
        )

    def test_cleanup_session_uses_cleanup_module(self):
        summary = cleanup_session("objects", "drill-01", runner=lambda command: True)

        self.assertTrue(summary.attempted)
        self.assertTrue(summary.succeeded)


if __name__ == "__main__":
    unittest.main()
