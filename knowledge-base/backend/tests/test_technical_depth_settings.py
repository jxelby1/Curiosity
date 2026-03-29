from __future__ import annotations

from app.core.course_preferences import (
    DEFAULT_TECHNICAL_DEPTH,
    normalize_technical_depth,
    technical_depth_lesson_targets,
    technical_depth_prompt_guidance,
)


def test_technical_depth_normalization_and_defaults() -> None:
    assert normalize_technical_depth('phd') == 'phd'
    assert normalize_technical_depth('masters') == 'masters'
    assert normalize_technical_depth('unknown') == DEFAULT_TECHNICAL_DEPTH
    assert normalize_technical_depth(None) == DEFAULT_TECHNICAL_DEPTH


def test_technical_depth_guidance_and_targets_scale_up() -> None:
    beginner = technical_depth_lesson_targets('beginner')
    phd = technical_depth_lesson_targets('phd')

    assert phd['section_min_chars'] > beginner['section_min_chars']
    assert phd['max_tokens'] > beginner['max_tokens']
    assert 'research-grade' in technical_depth_prompt_guidance('phd')
    assert 'beginner depth' in technical_depth_prompt_guidance('beginner')
