from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.resource_agent import ResourceAgent
from app.db.models import (
    Assessment,
    AssessmentAttempt,
    BranchSuggestion,
    LearningResource,
    SkillEdge,
    SkillNode,
    Topic,
    User,
    UserSkillState,
)


class _DumpOnlyModel:
    def __init__(self, payload):  # type: ignore[no-untyped-def]
        self._payload = payload

    def model_dump(self):  # type: ignore[no-untyped-def]
        return self._payload


class _WeakThenStrongLessonLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        schema_model = kwargs.get('schema_model')
        self.calls += 1
        if schema_model.__name__ != 'LessonPlan':
            raise AssertionError('unexpected schema model')
        if self.calls == 1:
            return _DumpOnlyModel(
                {
                    'title': 'Causes of the French Revolution',
                    'summary': 'A lesson on the French Revolution.',
                    'learning_objectives': ['Describe the causes.', 'Apply the idea to revolution.'],
                    'key_concepts': [
                        {'term': 'Revolution', 'description': 'Major political change.'},
                        {'term': 'Taxation', 'description': 'Government revenue system.'},
                    ],
                    'sections': [
                        {'heading': 'Overview', 'content': 'The revolution mattered for many reasons and changed history in important ways.'},
                        {'heading': 'Reflect', 'content': 'Notice what matters and respond with your view.'},
                        {'heading': 'Try it', 'content': 'Apply the lesson to your own case right away.'},
                    ],
                    'exemplar_focus': ['Use France as the example.'],
                    'observation_prompts': ['Notice what stands out.'],
                    'response_prompts': ['Write a quick response.'],
                    'practice_hooks': ['Apply it immediately.'],
                    'takeaways': ['The revolution mattered.', 'History changed.'],
                    'next_steps': ['Try a follow-up task.'],
                }
            )
        return _DumpOnlyModel(
            {
                'title': 'Causes of the French Revolution',
                'summary': 'Learn the main causes of the French Revolution through one concrete fiscal case, one political contrast, and a worked transfer into another unrest scenario.',
                'learning_objectives': [
                    'Explain how fiscal pressure, political privilege, and food insecurity combined before 1789.',
                    'Use one concrete case to explain why discontent became revolutionary.',
                ],
                'key_concepts': [
                    {'term': 'Fiscal crisis', 'description': 'The crown’s worsening inability to finance war debt and ordinary government spending.'},
                    {'term': 'Privilege', 'description': 'The unequal distribution of tax burdens and political protection across estates.'},
                    {'term': 'Political legitimacy', 'description': 'Whether people still regard a ruling order as justified and workable.'},
                ],
                'sections': [
                    {
                        'role': 'example',
                        'heading': 'Start from one fiscal case',
                        'content': 'Consider the royal debt crisis after costly wars in the late eighteenth century. For example, the monarchy needed new revenue but still relied on a system that protected many privileged groups from the heaviest burdens, which gave ordinary taxpayers evidence that sacrifice was being distributed unevenly.',
                    },
                    {
                        'role': 'analysis',
                        'heading': 'Explain why the case became explosive',
                        'content': 'This matters because a fiscal crisis was not only an accounting problem. Because reform threatened privilege while bread prices were already straining households, financial weakness exposed a larger legitimacy crisis, which means economic pressure and political resentment reinforced one another.',
                    },
                    {
                        'role': 'comparison',
                        'heading': 'Contrast reform pressure with elite resistance',
                        'content': 'By contrast, a stable tax reform would have required broader elite cooperation. Compare that unrealized path with the actual resistance to reform and the difference becomes clear: the system could still name solutions, but it could not make powerful groups accept them.',
                    },
                    {
                        'role': 'transfer',
                        'heading': 'Transfer the pattern',
                        'content': 'Apply the same reasoning to another case of unrest by asking three questions: what financial pressure is visible, which groups are protected, and why does that pattern change how ordinary people judge the regime. The point is not to flatten all revolutions into one model, but to show how a worked case creates a basis for transfer.',
                    },
                    ],
                'exemplar_focus': ['Keep the late-eighteenth-century royal debt crisis as the anchor case.'],
                'comparison_prompts': ['Compare the failed reform path with the actual resistance to reform and explain the difference.'],
                'observation_prompts': ['Identify one concrete detail in the fiscal case and connect it to the broader legitimacy problem.'],
                'response_prompts': ['Explain why debt alone did not cause revolution without using vague summary language.'],
                'practice_hooks': ['Use the same three-question frame on one other case of unrest.'],
                'takeaways': [
                    'Concrete fiscal evidence makes the pre-1789 crisis easier to understand than broad claims about unrest alone.',
                    'Comparison shows why pressure became revolutionary rather than merely difficult.',
                ],
                'next_steps': ['Move to examples and compare one additional revolutionary trigger pattern.'],
            }
        )


class _AlwaysWeakLessonLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return _DumpOnlyModel(
            {
                'title': 'Thermodynamics basics',
                'summary': 'A lesson about heat.',
                'learning_objectives': ['Understand heat.', 'Apply heat.'],
                'key_concepts': [
                    {'term': 'Heat', 'description': 'Energy.'},
                    {'term': 'Temperature', 'description': 'How hot something is.'},
                ],
                'sections': [
                    {'heading': 'Overview', 'content': 'Heat is important in many situations and should be kept in mind generally.'},
                    {'heading': 'Respond', 'content': 'Reflect and respond right away.'},
                    {'heading': 'Practice', 'content': 'Apply the concept immediately without a worked case.'},
                ],
                'response_prompts': ['Write a response.'],
                'practice_hooks': ['Try it immediately.'],
                'takeaways': ['Heat matters.', 'Temperature matters.'],
                'next_steps': ['Do more practice.'],
            }
        )


class _RetrievalStub:
    async def retrieve_chunks(self, db, *, topic_id, query, top_k):  # type: ignore[no-untyped-def]
        _ = db, topic_id, query, top_k
        return []


class _SearchStub:
    async def search(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return []


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    SkillEdge.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    LearningResource.__table__.create(bind=engine)
    Assessment.__table__.create(bind=engine)
    AssessmentAttempt.__table__.create(bind=engine)
    BranchSuggestion.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _seed_topic_and_skill(db, *, topic_name: str, topic_description: str, goal: str, skill_name: str, skill_description: str):
    user = User(email=f'{skill_name.lower().replace(" ", "-")}@test.local', hashed_password='x', display_name='Quality Gate User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name=topic_name, description=topic_description, goal=goal)
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name=skill_name, description=skill_description, difficulty=2, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return user, topic, skill


def test_quality_gate_triggers_rewrite_for_structurally_weak_lesson() -> None:
    db = _session()
    user, topic, skill = _seed_topic_and_skill(
        db,
        topic_name='Modern European History',
        topic_description='Revolutions and political change',
        goal='Understand why revolutions happen',
        skill_name='Causes of the French Revolution',
        skill_description='Fiscal, political, and social causes before 1789',
    )
    llm = _WeakThenStrongLessonLLM()
    agent = ResourceAgent(
        llm_service=llm,  # type: ignore[arg-type]
        search_service=_SearchStub(),  # type: ignore[arg-type]
        retrieval_service=_RetrievalStub(),  # type: ignore[arg-type]
    )

    resource, content, source = asyncio.run(
        agent.generate_material(
            db,
            user_id=user.id,
            topic=topic,
            skill_node=skill,
            kind='lesson',
            regenerate=False,
        )
    )

    assert source == 'generated'
    assert resource.content_json is not None
    assert content is not None
    assert llm.calls == 2
    assert content['sections'][0]['role'] == 'example'
    assert any(section['role'] == 'transfer' for section in content['sections'])
    assert content['title'] == 'Causes of the French Revolution'


def test_quality_gate_falls_back_after_repeated_weak_lesson_outputs() -> None:
    db = _session()
    user, topic, skill = _seed_topic_and_skill(
        db,
        topic_name='Physics',
        topic_description='Introductory thermodynamics',
        goal='Understand thermal systems',
        skill_name='Heat transfer basics',
        skill_description='Foundational heat transfer concepts',
    )
    llm = _AlwaysWeakLessonLLM()
    agent = ResourceAgent(
        llm_service=llm,  # type: ignore[arg-type]
        search_service=_SearchStub(),  # type: ignore[arg-type]
        retrieval_service=_RetrievalStub(),  # type: ignore[arg-type]
    )

    resource, content, source = asyncio.run(
        agent.generate_material(
            db,
            user_id=user.id,
            topic=topic,
            skill_node=skill,
            kind='lesson',
            regenerate=False,
        )
    )

    assert source == 'generated'
    assert resource.content_json is not None
    assert content is not None
    assert llm.calls == 3
    assert content['title'].endswith('Starter lesson')
    assert content['sections'][0]['role'] == 'example'
