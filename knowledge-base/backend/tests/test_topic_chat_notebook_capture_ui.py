from __future__ import annotations

from pathlib import Path


def test_topic_chat_uses_lens_based_notebook_capture() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'chat' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Capture in notebook' in content
    assert 'Append to notebook' in content
    assert 'Notebook lens' in content
    assert 'Dialogue Focus' in content
    assert 'Source scope' in content
    assert 'Use notebook memory' in content
    assert 'Linked to current focus:' in content
    assert 'Optional note details' in content


def test_topic_chat_frames_dialogue_as_companion_not_tooling() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'chat' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Companion Prompt' in content
    assert 'Begin with one clear prompt.' in content
    assert 'Stay with ' in content
    assert 'Switch focus' in content
