from __future__ import annotations

import argparse
import os
import time

import httpx


def expect_ok(response: httpx.Response, step: str) -> dict:
    if response.status_code >= 400:
        raise RuntimeError(f'{step} failed: {response.status_code} {response.text}')
    if response.status_code == 204:
        return {}
    return response.json()


def auth_headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def main() -> None:
    parser = argparse.ArgumentParser(description='Run authenticated live smoke test flow.')
    parser.add_argument('--api-base', default=os.getenv('API_BASE_URL', 'http://localhost:8000/api'))
    parser.add_argument('--email', default=f'smoke-{int(time.time())}@knowledge-base.local')
    parser.add_argument('--password', default='password123')
    parser.add_argument('--display-name', default='Smoke User')
    parser.add_argument('--skip-external', action='store_true', help='Skip external resource fetch step.')
    args = parser.parse_args()

    topic_name = f'Python Debugging Smoke {int(time.time())}'

    with httpx.Client(timeout=120) as client:
        print('1) register')
        register_payload = {
            'email': args.email,
            'password': args.password,
            'display_name': args.display_name,
        }
        token_data = expect_ok(client.post(f'{args.api_base}/auth/register', json=register_payload), 'register')
        token = token_data['access_token']
        headers = auth_headers(token)

        print('2) auth/me')
        me = expect_ok(client.get(f'{args.api_base}/auth/me', headers=headers), 'auth/me')
        if not me.get('id'):
            raise RuntimeError('auth/me did not return user id')

        print('3) create topic')
        topic = expect_ok(
            client.post(
                f'{args.api_base}/topics',
                json={
                    'name': topic_name,
                    'description': 'Smoke test topic',
                    'goal': 'Validate auth + assessment flow',
                },
                headers=headers,
            ),
            'create topic',
        )
        topic_id = topic['id']

        print('4) get skill tree')
        tree = expect_ok(client.get(f'{args.api_base}/topics/{topic_id}/skill-tree', headers=headers), 'get skill tree')
        if not tree['nodes']:
            raise RuntimeError('Skill tree has no nodes.')

        selected_node = next((node for node in tree['nodes'] if node['status'] != 'locked'), tree['nodes'][0])
        skill_id = selected_node['id']

        print('5) upload source note')
        note = (
            'Use tracebacks bottom-up. Reproduce issues with a minimal script. '
            'Inspect state with breakpoints. Validate assumptions with assertions.'
        )
        expect_ok(
            client.post(
                f'{args.api_base}/topics/{topic_id}/notes/upload',
                data={'raw_text': note},
                headers=headers,
            ),
            'upload note',
        )

        print('6) chat')
        chat = expect_ok(
            client.post(
                f'{args.api_base}/topics/{topic_id}/chat',
                json={
                    'skill_node_id': skill_id,
                    'message': 'How do I isolate inconsistent function outputs?'
                },
                headers=headers,
            ),
            'chat',
        )
        if not chat.get('answer'):
            raise RuntimeError('Chat returned empty answer.')

        print('7) retention loop')
        retention = expect_ok(
            client.get(f'{args.api_base}/topics/{topic_id}/retention-loop', headers=headers),
            'retention loop',
        )
        if not retention.get('next_actions'):
            raise RuntimeError('No retention next actions returned.')

        print('8) generate lesson')
        lesson = expect_ok(
            client.post(
                f'{args.api_base}/skills/{skill_id}/resources/generate',
                json={'kind': 'lesson'},
                headers=headers,
            ),
            'generate lesson',
        )
        if lesson.get('source') not in {'stored', 'generated', 'regenerated'}:
            raise RuntimeError('Unexpected lesson source value')

        print('9) generate mixed assessment')
        assessment = expect_ok(
            client.post(
                f'{args.api_base}/assessments/generate',
                json={
                    'topic_id': topic_id,
                    'skill_node_id': skill_id,
                    'question_count': 6,
                    'regenerate': False,
                },
                headers=headers,
            ),
            'generate assessment',
        )
        if len(assessment.get('questions', [])) < 4:
            raise RuntimeError('Assessment has too few questions')

        question_types = {item['question_type'] for item in assessment['questions']}
        if len(question_types) < 2:
            raise RuntimeError('Assessment is not mixed type')

        print('10) submit assessment')
        responses = []
        for question in assessment['questions']:
            question_type = question['question_type']
            if question_type == 'multiple_choice':
                responses.append(
                    {
                        'question_id': question['id'],
                        'selected_option_index': 0,
                    }
                )
            else:
                responses.append(
                    {
                        'question_id': question['id'],
                        'answer_text': 'I would break the problem down, verify assumptions, and test one change at a time.',
                    }
                )

        result = expect_ok(
            client.post(
                f"{args.api_base}/assessments/{assessment['id']}/submit",
                json={'responses': responses},
                headers=headers,
            ),
            'submit assessment',
        )
        if 'updated_mastery' not in result:
            raise RuntimeError('Assessment submission did not return mastery update.')

        print('11) attempt fetch')
        attempt = expect_ok(
            client.get(f"{args.api_base}/assessment-attempts/{result['attempt_id']}", headers=headers),
            'get attempt',
        )
        if attempt.get('assessment_id') != assessment['id']:
            raise RuntimeError('Attempt assessment_id mismatch')

        print('12) topic progress + user summary')
        progress = expect_ok(client.get(f'{args.api_base}/topics/{topic_id}/progress', headers=headers), 'topic progress')
        if progress.get('total_nodes', 0) <= 0:
            raise RuntimeError('Topic progress returned no nodes')
        summary = expect_ok(client.get(f'{args.api_base}/users/me/progress-summary', headers=headers), 'user summary')
        if summary.get('topics_total', 0) <= 0:
            raise RuntimeError('User summary returned no topics')

        print('13) external resources')
        if args.skip_external:
            print('   skipped (--skip-external)')
        else:
            external = expect_ok(
                client.get(f'{args.api_base}/skills/{skill_id}/resources/external', headers=headers),
                'external resources',
            )
            if not external.get('resources'):
                raise RuntimeError('No external resources returned.')

    print('Authenticated smoke flow passed.')


if __name__ == '__main__':
    main()
