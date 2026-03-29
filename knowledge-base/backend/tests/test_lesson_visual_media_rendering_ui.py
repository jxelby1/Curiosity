from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEARNING_CONTENT = ROOT / 'frontend' / 'components' / 'learning-content.tsx'
SKILL_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'


def test_learning_content_prefers_preview_urls_for_supporting_images() -> None:
    content = LEARNING_CONTENT.read_text(encoding='utf-8')

    assert 'preview_url?: string;' in content
    assert "if (mediaType === 'image' && !isDirectImageUrl(url) && !isDirectImageUrl(previewUrl)) return null;" in content
    assert 'item.preview_url && isDirectImageUrl(item.preview_url)' in content
    assert 'data-testid="supporting-media-image"' in content
    assert 'function toVimeoEmbedUrl(url: string): string | null' in content
    assert "kind: 'iframe' | 'native'" in content
    assert '<video' in content
    assert 'const lessonImages = content.supporting_media.filter((item) => item.media_type === \'image\');' in content
    assert 'const lessonVideos = content.supporting_media.filter((item) => item.media_type === \'video\');' in content
    assert 'title="Visual Reference"' in content
    assert 'title="Supporting Video"' in content


def test_deep_lesson_fallback_media_section_uses_preview_urls_for_images() -> None:
    content = SKILL_PAGE.read_text(encoding='utf-8')

    assert 'renderableImageUrl(item.url, item.preview_url)' in content
    assert 'src={imageUrl || item.url}' in content
    assert 'function toVideoEmbedSource(url: string): { kind: \'iframe\' | \'native\'; src: string } | null' in content
    assert 'embedSource?.kind === \'iframe\'' in content
    assert 'embedSource?.kind === \'native\'' in content
