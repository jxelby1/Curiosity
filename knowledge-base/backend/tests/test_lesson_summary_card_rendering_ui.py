from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEARNING_CONTENT = ROOT / 'frontend' / 'components' / 'learning-content.tsx'


def test_learning_content_parser_normalizes_clipped_snippets() -> None:
    content = LEARNING_CONTENT.read_text(encoding='utf-8')

    assert 'function normalizeCardSnippet' in content
    assert 'function truncateToCompleteSentence' in content
    assert 'function ensureSentenceClosure' in content
    assert 'withoutEllipsis.length >= maxLen - 1' in content
    assert 'endsWithEllipsis' in content
    assert 'return truncateToCompleteSentence(withoutEllipsis, maxLen);' in content
    assert 'ensureSentenceClosure(withoutEllipsis, maxLen)' in content


def test_lesson_and_related_cards_use_normalized_snippet_parser() -> None:
    content = LEARNING_CONTENT.read_text(encoding='utf-8')

    assert 'summary: normalizeCardSnippet(input.summary, LESSON_SUMMARY_MAX)' in content
    assert 'description: normalizeCardSnippet(item.description, LESSON_KEY_CONCEPT_DESC_MAX)' in content
    assert 'intro: normalizeCardSnippet(input.intro, EXAMPLES_INTRO_MAX)' in content
    assert 'expected_outcome: normalizeCardSnippet(item.expected_outcome, EXERCISE_OUTCOME_MAX)' in content
