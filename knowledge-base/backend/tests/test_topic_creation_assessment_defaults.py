from __future__ import annotations

from pathlib import Path


def test_topic_creation_defaults_focus_on_multiple_choice_only() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    frontend_options = (repo_root / 'frontend' / 'lib' / 'course-options.ts').read_text(encoding='utf-8')
    backend_options = (repo_root / 'backend' / 'app' / 'core' / 'course_preferences.py').read_text(encoding='utf-8')

    assert "export const DEFAULT_ASSESSMENT_STYLES: AssessmentStyle[] = [" in frontend_options
    assert "'multiple_choice'" in frontend_options
    assert "'short_answer'" not in frontend_options.split('export const DEFAULT_ASSESSMENT_STYLES: AssessmentStyle[] = [', 1)[1].split('];', 1)[0]
    assert "'flashcard'" not in frontend_options.split('export const DEFAULT_ASSESSMENT_STYLES: AssessmentStyle[] = [', 1)[1].split('];', 1)[0]

    assert 'DEFAULT_ASSESSMENT_STYLES: list[AssessmentStyle] = [' in backend_options
    assert "'multiple_choice'" in backend_options
    backend_default_block = backend_options.split('DEFAULT_ASSESSMENT_STYLES: list[AssessmentStyle] = [', 1)[1].split(']', 1)[0]
    assert "'short_answer'" not in backend_default_block
    assert "'flashcard'" not in backend_default_block
