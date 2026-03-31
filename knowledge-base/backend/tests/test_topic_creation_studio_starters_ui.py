from __future__ import annotations

from pathlib import Path


def test_topic_creation_includes_cultural_and_creative_studio_starters() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx'
    content = dashboard_path.read_text(encoding='utf-8')

    assert 'STUDIO_TOPIC_STARTERS' in content
    assert "area: 'Art'" in content
    assert "area: 'Literature'" in content
    assert "area: 'Philosophy'" in content
    assert "area: 'Film'" in content
    assert "area: 'Music'" in content
    assert "area: 'Architecture'" in content
    assert "area: 'Photography'" in content
    assert "area: 'Writing'" in content
    assert "area: 'Design'" in content
    assert "area: 'Cultural History'" in content
    assert "area: 'City and Place'" in content
    assert 'Studio starters' in content
    assert 'Photograph with Intention' in content
    assert 'Listening Like a Curator' in content
    assert 'Creative Neighborhood Exploration Studio' in content
    assert 'Practice-forward starting points' in content
    assert 'Selecting a starter fills the study title and intent.' in content
