from __future__ import annotations

from app.agents.skill_graph_agent import SkillGraphAgent


def test_non_business_topic_flags_generic_jargon_titles() -> None:
    issues = SkillGraphAgent._title_quality_issues(
        topic_name='finding hidden gems in Chalk Farm',
        topic_description='local exploration and neighbourhood discovery',
        topic_goal='discover specific places to visit',
        title='Optimization techniques to find hidden gems',
    )
    assert 'generic_jargon' in issues


def test_concrete_local_title_passes_quality_rules() -> None:
    issues = SkillGraphAgent._title_quality_issues(
        topic_name='finding hidden gems in Chalk Farm',
        topic_description='local exploration and neighbourhood discovery',
        topic_goal='discover specific places to visit',
        title='Cafes, bars, and local favourites in Chalk Farm',
    )
    assert issues == []


def test_business_topic_can_use_strategy_language_when_specific() -> None:
    issues = SkillGraphAgent._title_quality_issues(
        topic_name='B2B SaaS growth strategy',
        topic_description='improve activation and retention',
        topic_goal='build a measurable go-to-market plan',
        title='Pricing strategy for retention',
    )
    assert issues == []
