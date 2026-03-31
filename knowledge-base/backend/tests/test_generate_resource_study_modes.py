from __future__ import annotations

from pathlib import Path


def test_generate_resource_schema_supports_study_modes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    schema_path = repo_root / 'backend' / 'app' / 'schemas' / 'api.py'
    content = schema_path.read_text(encoding='utf-8')

    assert "study_mode: Literal['standard', 'exemplar', 'compare'] = 'standard'" in content
    assert "exemplar_title: str = Field(default='', max_length=200)" in content
    assert "comparison_left: str = Field(default='', max_length=200)" in content
    assert "comparison_right: str = Field(default='', max_length=200)" in content
    assert 'exemplar_title is required when study_mode is exemplar.' in content
    assert 'comparison_left and comparison_right are required when study_mode is compare.' in content


def test_generate_resource_route_threads_study_modes_and_logs_notebook_entries() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    routes_path = repo_root / 'backend' / 'app' / 'api' / 'routes.py'
    content = routes_path.read_text(encoding='utf-8')

    assert 'study_mode=payload.study_mode' in content
    assert 'exemplar_title=payload.exemplar_title.strip() or None' in content
    assert 'comparison_left=payload.comparison_left.strip() or None' in content
    assert "if payload.kind == 'examples' and payload.study_mode in {'exemplar', 'compare'}:" in content
    assert "source_type='tutor_generated'" in content
    assert 'note_type=NoteType.summary' in content


def test_resource_generation_models_and_agent_support_exemplar_compare_response_fields() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    llm_schema_path = repo_root / 'backend' / 'app' / 'schemas' / 'llm.py'
    resource_agent_path = repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py'
    llm_content = llm_schema_path.read_text(encoding='utf-8')
    agent_content = resource_agent_path.read_text(encoding='utf-8')

    assert 'exemplar_focus: list[str] = Field(default_factory=list' in llm_content
    assert 'comparison_prompts: list[str] = Field(default_factory=list' in llm_content
    assert 'observation_prompts: list[str] = Field(default_factory=list' in llm_content
    assert 'response_prompts: list[str] = Field(default_factory=list' in llm_content
    assert 'practice_hooks: list[str] = Field(default_factory=list' in llm_content
    assert '_practice_balance_rules(' in agent_content
    assert '_ensure_studio_balance_fields(' in agent_content
    assert '_clear_legacy_supporting_media_fields(' in agent_content
