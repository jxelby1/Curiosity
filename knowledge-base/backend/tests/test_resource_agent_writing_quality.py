from __future__ import annotations

from app.agents.resource_agent import ResourceAgent


def _agent() -> ResourceAgent:
    return ResourceAgent(  # type: ignore[arg-type]
        llm_service=object(),
        search_service=object(),
        retrieval_service=object(),
    )


def test_writing_slop_flags_generic_waffle_language() -> None:
    agent = _agent()
    content = {
        'summary': (
            'This section leverages a strategy framework for optimization and stakeholder alignment. '
            'It is important to note this methodology can leverage synergies overall.'
        ),
        'sections': [
            {
                'heading': 'Overview',
                'content': (
                    'In this section we delve into a roadmap methodology for optimization strategy. '
                    'This highlights the importance of stakeholder synergy.'
                ),
            }
        ],
    }

    issues = agent._writing_slop_issues(content, kind='lesson')  # type: ignore[attr-defined]

    assert 'formulaic_phrasing' in issues
    assert 'generic_abstract_language' in issues


def test_writing_slop_accepts_specific_example_rich_text() -> None:
    agent = _agent()
    content = {
        'summary': (
            'The Cotswolds spans six counties, and village planning differs because limestone uplands '
            'shape road patterns and land use.'
        ),
        'sections': [
            {
                'heading': 'Terrain and settlement',
                'content': (
                    'For example, Bourton-on-the-Water and Stow-on-the-Wold developed different market roles '
                    'because elevation and routes constrained movement. A common mistake is assuming all villages '
                    'follow the same growth pattern.'
                ),
            }
        ],
    }

    issues = agent._writing_slop_issues(content, kind='lesson')  # type: ignore[attr-defined]

    assert 'formulaic_phrasing' not in issues
    assert 'generic_abstract_language' not in issues


def test_writing_slop_flags_assumed_familiarity_language() -> None:
    agent = _agent()
    content = {
        'summary': 'A short lesson on the topic.',
        'sections': [
            {
                'heading': 'Jump ahead',
                'content': (
                    'If you are already familiar with the novel, the symbolism is obvious and we can move straight to interpretation '
                    'without restating the relevant scenes or details here.'
                ),
            }
        ],
    }

    issues = agent._writing_slop_issues(content, kind='lesson')  # type: ignore[attr-defined]

    assert 'assumes_outside_familiarity' in issues
