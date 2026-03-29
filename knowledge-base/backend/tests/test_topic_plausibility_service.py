from __future__ import annotations

import asyncio

from app.services.topic_plausibility import TopicPlausibilityService


def _evaluate(
    *,
    name: str,
    description: str = '',
    goal: str = '',
    topic_mode: str = 'factual',
    technical_depth: str = 'intermediate',
):
    service = TopicPlausibilityService(llm_service=None)
    return asyncio.run(
        service.evaluate(
            name=name,
            description=description,
            goal=goal,
            topic_mode=topic_mode,
            technical_depth=technical_depth,
        )
    )


def test_plausible_factual_topics_pass_normally() -> None:
    assert _evaluate(name="Haruki Murakami's literary themes").status == 'pass'
    assert _evaluate(name="Shakespeare's tragedies").status == 'pass'
    assert _evaluate(name="Donald Trump's political communication style").status == 'pass'


def test_likely_fabricated_factual_topics_trigger_clarification() -> None:
    assert _evaluate(name="Haruki Murakami's professional football career").status == 'clarify'
    assert _evaluate(name="William Shakespeare's Six Nations appearances").status == 'clarify'
    assert _evaluate(name="Donald Trump's music compositions").status == 'clarify'
    assert _evaluate(name='Donald Trumps Snooker Career').status == 'clarify'


def test_explicit_fictional_or_hypothetical_topics_are_allowed() -> None:
    assert _evaluate(name='A fictional football career for Haruki Murakami').status == 'pass'
    assert _evaluate(name='Alternate history: Shakespeare in modern rugby').status == 'pass'
    assert _evaluate(name='Imagining Trump as a composer in a satirical universe').status == 'pass'


def test_niche_but_plausible_topics_are_not_overblocked() -> None:
    assert _evaluate(name='Advanced symbolic methods in quantum field theory').status == 'pass'
    assert _evaluate(name='The history of obscure Balkan rail systems').status == 'pass'
    assert _evaluate(name='Murakami and jazz influence in fiction').status == 'pass'


def test_topic_mode_override_allows_creative_frame_for_clarified_topics() -> None:
    result = _evaluate(
        name="Haruki Murakami's professional football career",
        topic_mode='hypothetical',
    )
    assert result.status == 'pass'


def test_private_or_unknown_person_topics_require_more_context() -> None:
    result = _evaluate(name='My friend John Smith career background')
    assert result.status == 'needs_context'
    assert result.requires_source_material is True


def test_bare_person_name_topic_requires_context() -> None:
    result = _evaluate(name='Mustafa Yasir')
    assert result.status == 'needs_context'
    assert result.requires_source_material is True


def test_generic_person_request_still_requires_context_even_with_short_description() -> None:
    result = _evaluate(
        name='Mustafa Yasir',
        description='Learn about him',
    )
    assert result.status == 'needs_context'
    assert result.requires_source_material is True


def test_high_technical_depth_requires_stronger_grounding() -> None:
    result = _evaluate(
        name='History of a niche local policy figure',
        description='',
        goal='',
        technical_depth='phd',
    )
    assert result.status == 'needs_context'
