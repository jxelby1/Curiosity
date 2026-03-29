from __future__ import annotations

from pathlib import Path


def test_topic_creation_defaults_focus_on_three_core_assessment_styles() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    frontend_options = (repo_root / 'frontend' / 'lib' / 'course-options.ts').read_text(encoding='utf-8')
    backend_options = (repo_root / 'backend' / 'app' / 'core' / 'course_preferences.py').read_text(encoding='utf-8')

    assert "export const DEFAULT_ASSESSMENT_STYLES: AssessmentStyle[] = [" in frontend_options
    assert "'short_answer'" in frontend_options
    assert "'multiple_choice'" in frontend_options
    assert "'flashcard'" in frontend_options

    assert 'DEFAULT_ASSESSMENT_STYLES: list[AssessmentStyle] = [' in backend_options
    assert "'short_answer'" in backend_options
    assert "'multiple_choice'" in backend_options
    assert "'flashcard'" in backend_options
