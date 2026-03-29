from __future__ import annotations

import argparse
import os
import time

import httpx


def expect_status(response: httpx.Response, expected: int, step: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f'{step} expected {expected} got {response.status_code}: {response.text}')


def expect_ok(response: httpx.Response, step: str) -> dict:
    if response.status_code >= 400:
        raise RuntimeError(f'{step} failed: {response.status_code} {response.text}')
    if response.status_code == 204:
        return {}
    return response.json()


def register_user(client: httpx.Client, api_base: str, email: str, password: str, display_name: str) -> str:
    payload = {'email': email, 'password': password, 'display_name': display_name}
    data = expect_ok(client.post(f'{api_base}/auth/register', json=payload), f'register {email}')
    return data['access_token']


def auth_headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def main() -> None:
    parser = argparse.ArgumentParser(description='Validate auth protection and user data isolation.')
    parser.add_argument('--api-base', default=os.getenv('API_BASE_URL', 'http://localhost:8000/api'))
    parser.add_argument('--password', default='password123')
    args = parser.parse_args()

    stamp = int(time.time())
    user_a = f'iso-a-{stamp}@knowledge-base.local'
    user_b = f'iso-b-{stamp}@knowledge-base.local'

    with httpx.Client(timeout=120) as client:
        print('1) protected route rejects unauthenticated access')
        expect_status(client.get(f'{args.api_base}/topics'), 401, 'unauthenticated topics')

        print('2) register user A and user B')
        token_a = register_user(client, args.api_base, user_a, args.password, 'Isolation User A')
        token_b = register_user(client, args.api_base, user_b, args.password, 'Isolation User B')
        headers_a = auth_headers(token_a)
        headers_b = auth_headers(token_b)

        print('3) user A creates topic')
        topic = expect_ok(
            client.post(
                f'{args.api_base}/topics',
                json={'name': 'Isolation Topic', 'description': 'auth test', 'goal': 'verify ownership'},
                headers=headers_a,
            ),
            'create topic user A',
        )
        topic_id = topic['id']

        print('4) user A can see topic, user B cannot')
        topics_a = expect_ok(client.get(f'{args.api_base}/topics', headers=headers_a), 'list topics A')
        topics_b = expect_ok(client.get(f'{args.api_base}/topics', headers=headers_b), 'list topics B')
        if not any(item['id'] == topic_id for item in topics_a.get('topics', [])):
            raise RuntimeError('User A cannot see own topic')
        if any(item['id'] == topic_id for item in topics_b.get('topics', [])):
            raise RuntimeError('User B can see user A topic')

        print('5) user B cannot access user A topic resources')
        expect_status(
            client.get(f'{args.api_base}/topics/{topic_id}/skill-tree', headers=headers_b),
            404,
            'user B get user A tree',
        )

    print('Auth/isolation smoke passed.')


if __name__ == '__main__':
    main()
