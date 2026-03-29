from __future__ import annotations

import os
import time
from typing import Any

import httpx
import pytest


API_BASE = os.getenv('LIVE_API_BASE_URL')
if not API_BASE:
    pytest.skip('Set LIVE_API_BASE_URL to run live integration tests.', allow_module_level=True)


def expect_ok(response: httpx.Response, step: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise AssertionError(f'{step} failed: {response.status_code} {response.text}')
    if response.status_code == 204:
        return {}
    return response.json()


def auth_headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def register_user(client: httpx.Client, email: str, password: str, display_name: str) -> str:
    data = expect_ok(
        client.post(
            f'{API_BASE}/auth/register',
            json={'email': email, 'password': password, 'display_name': display_name},
        ),
        f'register {email}',
    )
    return data['access_token']


def build_assessment_responses(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for question in assessment['questions']:
        question_type = question['question_type']
        if question_type == 'multiple_choice':
            answer_index = question.get('rubric', {}).get('answer_index', 0)
            responses.append(
                {
                    'question_id': question['id'],
                    'selected_option_index': answer_index,
                }
            )
        else:
            responses.append(
                {
                    'question_id': question['id'],
                    'answer_text': (
                        'I would identify the core concept, apply it to the exact scenario, '
                        'and justify each step with the expected principles.'
                    ),
                }
            )
    return responses


@pytest.mark.integration
def test_registration_login_and_protected_route() -> None:
    stamp = int(time.time())
    email = f'live-auth-{stamp}@knowledge-base.local'
    password = 'password123'

    with httpx.Client(timeout=120) as client:
        token = register_user(client, email, password, 'Live Auth User')
        headers = auth_headers(token)

        me = expect_ok(client.get(f'{API_BASE}/auth/me', headers=headers), 'auth/me')
        assert me['email'] == email

        expect_ok(
            client.post(f'{API_BASE}/auth/login', json={'email': email, 'password': password}),
            'login',
        )

        no_auth = client.get(f'{API_BASE}/topics')
        assert no_auth.status_code == 401


@pytest.mark.integration
def test_user_scoped_isolation() -> None:
    stamp = int(time.time())
    password = 'password123'
    email_a = f'live-iso-a-{stamp}@knowledge-base.local'
    email_b = f'live-iso-b-{stamp}@knowledge-base.local'

    with httpx.Client(timeout=120) as client:
        token_a = register_user(client, email_a, password, 'Isolation A')
        token_b = register_user(client, email_b, password, 'Isolation B')
        headers_a = auth_headers(token_a)
        headers_b = auth_headers(token_b)

        topic = expect_ok(
            client.post(
                f'{API_BASE}/topics',
                json={'name': 'Isolation Topic', 'description': 'isolation test', 'goal': 'verify ownership'},
                headers=headers_a,
            ),
            'create topic',
        )

        topics_a = expect_ok(client.get(f'{API_BASE}/topics', headers=headers_a), 'topics A')
        topics_b = expect_ok(client.get(f'{API_BASE}/topics', headers=headers_b), 'topics B')
        assert any(item['id'] == topic['id'] for item in topics_a['topics'])
        assert all(item['id'] != topic['id'] for item in topics_b['topics'])

        denied = client.get(f"{API_BASE}/topics/{topic['id']}/skill-tree", headers=headers_b)
        assert denied.status_code == 404


@pytest.mark.integration
def test_assessment_generation_submission_and_mastery_update() -> None:
    stamp = int(time.time())
    email = f'live-assessment-{stamp}@knowledge-base.local'
    password = 'password123'

    with httpx.Client(timeout=180) as client:
        token = register_user(client, email, password, 'Assessment User')
        headers = auth_headers(token)

        topic = expect_ok(
            client.post(
                f'{API_BASE}/topics',
                json={'name': 'Python Debugging', 'description': 'assessment flow test', 'goal': 'improve skill'},
                headers=headers,
            ),
            'create topic',
        )
        tree = expect_ok(client.get(f"{API_BASE}/topics/{topic['id']}/skill-tree", headers=headers), 'skill tree')
        node = next((item for item in tree['nodes'] if item['status'] != 'locked'), tree['nodes'][0])

        assessment = expect_ok(
            client.post(
                f'{API_BASE}/assessments/generate',
                json={
                    'topic_id': topic['id'],
                    'skill_node_id': node['id'],
                    'question_count': 6,
                    'regenerate': False,
                },
                headers=headers,
            ),
            'generate assessment',
        )
        assert len(assessment['questions']) >= 4
        assert len({item['question_type'] for item in assessment['questions']}) >= 2

        submission = expect_ok(
            client.post(
                f"{API_BASE}/assessments/{assessment['id']}/submit",
                json={'responses': build_assessment_responses(assessment)},
                headers=headers,
            ),
            'submit assessment',
        )
        assert 'updated_mastery' in submission
        assert isinstance(submission['feedback'], list) and len(submission['feedback']) > 0

        attempt = expect_ok(
            client.get(f"{API_BASE}/assessment-attempts/{submission['attempt_id']}", headers=headers),
            'get attempt',
        )
        assert attempt['assessment_id'] == assessment['id']
