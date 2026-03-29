from __future__ import annotations

from pathlib import Path


def test_public_landing_page_has_premium_product_story_and_auth_ctas() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    landing_path = repo_root / 'frontend' / 'app' / 'page.tsx'
    content = landing_path.read_text(encoding='utf-8')

    assert 'Build a living learning tree, not a static course.' in content
    assert 'Sign in' in content
    assert 'Create account' in content
    assert 'Branching mastery map' in content
    assert 'Project journal + artifacts' in content
    assert 'Simple first start' in content


def test_post_login_dashboard_has_motivating_home_composition() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx'
    content = dashboard_path.read_text(encoding='utf-8')

    assert 'Learning home' in content
    assert 'Welcome back' in content
    assert 'Progress snapshot' in content
    assert 'Active topics' in content
    assert 'Create a new topic' in content
