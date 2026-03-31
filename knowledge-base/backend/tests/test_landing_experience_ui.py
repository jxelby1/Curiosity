from __future__ import annotations

from pathlib import Path


def test_public_landing_page_has_premium_product_story_and_auth_ctas() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    landing_path = repo_root / 'frontend' / 'app' / 'page.tsx'
    content = landing_path.read_text(encoding='utf-8')

    assert 'Grow your taste through living study paths.' in content
    assert 'Sign in' in content
    assert 'Enter {PRODUCT_NAME}' in content
    assert 'One trunk. Selective branches. Lasting reflection.' in content
    assert 'Notebook Memory' in content
    assert 'Start from a work' in content
    assert 'Living Study Tree' in content


def test_post_login_dashboard_has_motivating_home_composition() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx'
    content = dashboard_path.read_text(encoding='utf-8')

    assert '{PRODUCT_NAME} Studio' in content
    assert 'Welcome back' in content
    assert 'At a glance' in content
    assert 'Continue your studies' in content
    assert 'Begin a new study' in content
