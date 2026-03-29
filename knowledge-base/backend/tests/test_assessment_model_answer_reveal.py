from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.assessment_agent import AssessmentAgent
from app.db.models import (
    Assessment,
    AssessmentQuestion,
    AssessmentQuestionType,
    SkillNode,
    Topic,
    User,
)


class _LLMStub:
    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError('LLM calls are not expected in reveal test.')


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    Assessment.__table__.create(bind=engine)
    AssessmentQuestion.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _seed(db):
    user = User(email='model-answer@test.local', hashed_password='x', display_name='Model Answer User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Python debugging', description='Debugging basics', goal='Improve tracing')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name='Trace reading', description='Read traceback output', difficulty=1, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    assessment = Assessment(topic_id=topic.id, skill_node_id=skill.id, user_id=user.id, title='Model answer assessment', questions=[])
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    rows = [
        AssessmentQuestion(
            assessment_id=assessment.id,
            question_type=AssessmentQuestionType.multiple_choice,
            assessment_style='multiple_choice',
            prompt='Which option best identifies the root cause?',
            choices=['Network issue', 'Type mismatch in parse() call', 'Cache eviction', 'Unknown'],
            model_answer='The best answer is B because the traceback pinpoints parse() receiving a wrong type.',
            hints=['Focus on traceback line and argument type.'],
            expected_concepts=['traceback', 'root cause'],
            rubric={'answer_index': 1},
            difficulty=1,
            order_index=0,
        ),
        AssessmentQuestion(
            assessment_id=assessment.id,
            question_type=AssessmentQuestionType.scenario,
            assessment_style='coding',
            prompt='Write a function that returns only even numbers from input.',
            choices=None,
            model_answer='```python\ndef filter_even(values):\n    return [value for value in values if value % 2 == 0]\n```',
            hints=['Use a deterministic filter and return list output.'],
            expected_concepts=['list comprehension', 'modulo'],
            rubric={'criteria': []},
            difficulty=1,
            order_index=1,
        ),
        AssessmentQuestion(
            assessment_id=assessment.id,
            question_type=AssessmentQuestionType.short_answer,
            assessment_style='math_problem',
            prompt='Compute 15% of 240 and show steps.',
            choices=None,
            model_answer='Step 1: convert 15% to 0.15.\nStep 2: multiply 240 * 0.15 = 36.\nFinal answer: 36.',
            hints=['Show conversion from percent to decimal.'],
            expected_concepts=['percentage', 'multiplication'],
            rubric={'criteria': []},
            difficulty=1,
            order_index=2,
        ),
        AssessmentQuestion(
            assessment_id=assessment.id,
            question_type=AssessmentQuestionType.explain,
            assessment_style='open_text',
            prompt='Explain why reading stack traces quickly improves debugging speed.',
            choices=None,
            model_answer='Reading stack traces quickly surfaces failure location, execution path, and likely cause early, reducing trial-and-error debugging.',
            hints=['Mention location, path, and diagnosis speed.'],
            expected_concepts=['failure location', 'execution path', 'diagnosis'],
            rubric={'criteria': []},
            difficulty=1,
            order_index=3,
        ),
        AssessmentQuestion(
            assessment_id=assessment.id,
            question_type=AssessmentQuestionType.scenario,
            assessment_style='scenario',
            prompt='A fix works locally but fails in CI. What do you do first?',
            choices=None,
            model_answer='First reproduce CI conditions locally, then compare environment variables and dependency versions before changing logic.',
            hints=['Use reproducibility before editing implementation.'],
            expected_concepts=['environment parity', 'reproducibility'],
            rubric={'criteria': []},
            difficulty=2,
            order_index=4,
        ),
        AssessmentQuestion(
            assessment_id=assessment.id,
            question_type=AssessmentQuestionType.short_answer,
            assessment_style='flashcard',
            prompt='Define idempotency.',
            choices=None,
            model_answer='Idempotency means repeating an operation yields the same end state as running it once.',
            hints=['Think repeated execution stability.'],
            expected_concepts=['idempotency'],
            rubric={'criteria': []},
            difficulty=1,
            order_index=5,
        ),
        AssessmentQuestion(
            assessment_id=assessment.id,
            question_type=AssessmentQuestionType.short_answer,
            assessment_style='short_answer',
            prompt='Name one practical benefit of unit tests.',
            choices=None,
            model_answer='You should include at least one benefit.',
            hints=['Be specific.'],
            expected_concepts=['regression prevention'],
            rubric={'criteria': []},
            difficulty=1,
            order_index=6,
        ),
    ]
    for row in rows:
        db.add(row)
    db.commit()
    return user, assessment


def test_reveal_answers_returns_concrete_model_answers_for_multiple_styles() -> None:
    db = _session()
    user, assessment = _seed(db)
    agent = AssessmentAgent(llm_service=_LLMStub())  # type: ignore[arg-type]

    reveals = agent.reveal_answers(db, assessment=assessment, user_id=user.id)
    by_style = {item['assessment_style']: item for item in reveals}

    assert 'Correct option:' in by_style['multiple_choice']['answer']
    assert '```python' in by_style['coding']['answer']
    assert 'Step 1:' in by_style['math_problem']['answer']
    assert 'execution path' in by_style['open_text']['answer']
    assert 'reproduce CI conditions' in by_style['scenario']['answer']
    assert 'Idempotency means' in by_style['flashcard']['answer']

    # Generic guidance text is repaired to a concrete answer fallback.
    assert 'You should include at least one benefit.' not in by_style['short_answer']['answer']
    assert len(by_style['short_answer']['answer']) > 24
