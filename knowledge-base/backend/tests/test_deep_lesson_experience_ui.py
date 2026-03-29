from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTES_FILE = ROOT / 'backend' / 'app' / 'api' / 'routes.py'
RESOURCE_AGENT = ROOT / 'backend' / 'app' / 'agents' / 'resource_agent.py'
SKILL_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
LEARNING_CONTENT = ROOT / 'frontend' / 'components' / 'learning-content.tsx'
API_CLIENT = ROOT / 'frontend' / 'lib' / 'api.ts'


def test_backend_exposes_deep_lesson_endpoint_and_strict_media_pipeline() -> None:
    routes_content = ROUTES_FILE.read_text(encoding='utf-8')
    agent_content = RESOURCE_AGENT.read_text(encoding='utf-8')
    assert "@router.get('/skills/{skill_id}/deep-lesson'" in routes_content
    assert 'generate_deep_lesson_material(' in routes_content
    assert 'fetch_strict_supporting_media(' in routes_content
    assert 'async def generate_deep_lesson_material(' in agent_content
    assert 'async def fetch_strict_supporting_media(' in agent_content
    assert '_STRICT_MEDIA_SCORE_THRESHOLD = 0.34' in agent_content
    assert '_RELAXED_MEDIA_SCORE_THRESHOLD = 0.2' in agent_content
    assert '_BROAD_MEDIA_SCORE_THRESHOLD = 0.12' in agent_content
    assert 'fallback_query = (' in agent_content
    assert 'broad_query = ' in agent_content


def test_skill_workspace_includes_deep_dive_tab_and_renderer() -> None:
    page_content = SKILL_PAGE.read_text(encoding='utf-8')
    learning_content = LEARNING_CONTENT.read_text(encoding='utf-8')
    api_content = API_CLIENT.read_text(encoding='utf-8')
    assert "{ id: 'deep_dive', label: 'Deep Dive' }" in page_content
    assert "if (activeTab === 'deep_dive')" in page_content
    assert 'ensureDeepLesson' in page_content
    assert '<DeepLessonRenderer content={deepLessonContent} />' in page_content
    assert "export async function getDeepLesson(skillId: number): Promise<DeepLesson>" in api_content
    assert 'export function DeepLessonRenderer' in learning_content
    assert 'export function parseDeepLessonContent' in learning_content
