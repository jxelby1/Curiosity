from __future__ import annotations

from app.services.search import ExternalSearchService


def test_simplify_query_removes_problematic_boolean_syntax_and_caps_length() -> None:
    service = ExternalSearchService()
    raw = (
        "klimt's art klimt's artistic styles and techniques how does klimt use symbolism "
        "to convey complex themes in his paintings? what are the defining characteristics "
        "of art nouveau present in klimt's work? (map OR diagram OR archival image OR educational video) "
        "(site:wikipedia.org OR site:wikimedia.org OR site:britannica.com OR site:.edu)"
    )
    simplified = service._simplify_query(raw, topic="Klimt's Art", skill="Klimt's Artistic Styles and Techniques")

    assert len(simplified) <= 220
    assert 'site:.edu' not in simplified
    assert '(' not in simplified
    assert ')' not in simplified
    assert ' OR ' not in simplified
    assert '?' not in simplified


def test_simplify_query_provides_safe_default_for_empty_query() -> None:
    service = ExternalSearchService()
    simplified = service._simplify_query('', topic='Iran Geography', skill='Mountain Ranges and Deserts')
    assert 'Iran Geography' in simplified
    assert 'Mountain Ranges and Deserts' in simplified
