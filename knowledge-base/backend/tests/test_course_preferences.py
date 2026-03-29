from __future__ import annotations

from app.core.course_preferences import (
    build_assessment_style_sequence,
    depth_node_bounds,
    normalize_assessment_styles,
    normalize_course_depth,
    normalize_starting_skill_level,
)


def test_depth_and_level_normalization_defaults() -> None:
    assert normalize_course_depth('unknown') == 'standard'
    assert normalize_course_depth('deep_dive') == 'deep_dive'
    assert normalize_starting_skill_level('unknown') == 'beginner'
    assert normalize_starting_skill_level('advanced') == 'advanced'
    assert depth_node_bounds('light') == (6, 8)
    assert depth_node_bounds('standard') == (8, 12)
    assert depth_node_bounds('deep_dive') == (12, 16)


def test_assessment_style_normalization_deduplicates() -> None:
    normalized = normalize_assessment_styles(
        ['multiple_choice', 'coding', 'coding', 'short_answer', 'math_problem']
    )
    assert normalized == ['multiple_choice', 'coding', 'short_answer', 'math_problem']


def test_style_sequence_prioritizes_code_for_code_topics() -> None:
    sequence = build_assessment_style_sequence(
        allowed_styles=['multiple_choice', 'short_answer', 'coding', 'debugging', 'math_problem'],
        question_count=6,
        topic_text='Python debugging and code quality',
        skill_text='Trace stack errors and fix faulty functions',
        learner_level='intermediate',
    )
    assert len(sequence) == 6
    assert any(style in {'coding', 'debugging'} for style in sequence)
    assert all(style in {'multiple_choice', 'short_answer', 'coding', 'debugging', 'math_problem'} for style in sequence)


def test_style_sequence_prioritizes_math_for_math_topics() -> None:
    sequence = build_assessment_style_sequence(
        allowed_styles=['math_problem', 'short_answer', 'scenario', 'multiple_choice'],
        question_count=6,
        topic_text='Probability and statistics',
        skill_text='Solve Bayes theorem questions with numeric values',
        learner_level='beginner',
    )
    assert len(sequence) == 6
    assert sequence[0] == 'math_problem'
    assert 'math_problem' in sequence
