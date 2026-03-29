from __future__ import annotations

from app.schemas.api import AssessmentSubmitRequest


def test_assessment_submit_request_accepts_answers_without_confidence() -> None:
    payload = AssessmentSubmitRequest.model_validate(
        {
            'responses': [
                {'question_id': 1, 'selected_option_index': 2},
                {'question_id': 2, 'answer_text': 'I would isolate variables and test incrementally.'},
            ]
        }
    )

    assert len(payload.responses) == 2
    assert payload.responses[0].confidence_score is None
    assert payload.responses[1].confidence_score is None
