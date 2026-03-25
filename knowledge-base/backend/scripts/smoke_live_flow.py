from __future__ import annotations

import argparse
import os
import time

import httpx


def expect_ok(response: httpx.Response, step: str) -> dict:
    if response.status_code >= 400:
        raise RuntimeError(f'{step} failed: {response.status_code} {response.text}')
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description='Run live smoke test flow against running backend API.')
    parser.add_argument('--api-base', default=os.getenv('API_BASE_URL', 'http://localhost:8000/api'))
    parser.add_argument('--user-id', type=int, default=1)
    parser.add_argument('--skip-external', action='store_true', help='Skip external resource fetch step.')
    args = parser.parse_args()

    topic_name = f'Python Debugging Smoke {int(time.time())}'

    with httpx.Client(timeout=60) as client:
        print('1) create topic')
        topic = expect_ok(
            client.post(
                f'{args.api_base}/topics',
                json={
                    'user_id': args.user_id,
                    'name': topic_name,
                    'description': 'Smoke test topic',
                    'goal': 'Validate live end-to-end flow',
                },
            ),
            'create topic',
        )
        topic_id = topic['id']

        print('2) generate/get skill tree')
        tree = expect_ok(
            client.get(f'{args.api_base}/topics/{topic_id}/skill-tree', params={'user_id': args.user_id}),
            'get skill tree',
        )
        if not tree['nodes']:
            raise RuntimeError('Skill tree has no nodes.')

        selected_node = next((node for node in tree['nodes'] if node['status'] != 'locked'), tree['nodes'][0])
        skill_id = selected_node['id']

        print('3) upload notes')
        note = (
            'Use tracebacks bottom-up. Reproduce the issue with a minimal script. '
            'Inspect variable state with debugger breakpoints and assertions.'
        )
        expect_ok(
            client.post(
                f'{args.api_base}/topics/{topic_id}/notes/upload',
                data={'user_id': str(args.user_id), 'raw_text': note},
            ),
            'upload notes',
        )

        print('4) chat with retrieval')
        chat = expect_ok(
            client.post(
                f'{args.api_base}/topics/{topic_id}/chat',
                json={
                    'user_id': args.user_id,
                    'skill_node_id': skill_id,
                    'message': 'How should I debug inconsistent function outputs?'
                },
            ),
            'chat',
        )
        if not chat.get('answer'):
            raise RuntimeError('Chat returned empty answer.')

        print('5) get recommendations')
        recs = expect_ok(
            client.get(f'{args.api_base}/topics/{topic_id}/recommendations', params={'user_id': args.user_id}),
            'recommendations',
        )
        if not recs.get('recommendations'):
            raise RuntimeError('No recommendations returned.')

        print('6) generate lesson (and persist)')
        lesson_first = expect_ok(
            client.post(
                f'{args.api_base}/skills/{skill_id}/resources/generate',
                json={'user_id': args.user_id, 'kind': 'lesson'},
            ),
            'generate lesson',
        )
        if not lesson_first.get('content'):
            raise RuntimeError('Lesson generation returned empty content.')
        if lesson_first.get('source') not in {'generated', 'stored'}:
            raise RuntimeError('Unexpected lesson source on first request.')

        lesson_cached = expect_ok(
            client.post(
                f'{args.api_base}/skills/{skill_id}/resources/generate',
                json={'user_id': args.user_id, 'kind': 'lesson'},
            ),
            'load stored lesson',
        )
        if lesson_cached.get('source') != 'stored':
            raise RuntimeError('Lesson was not loaded from store on second request.')
        if lesson_cached.get('version') != lesson_first.get('version'):
            raise RuntimeError('Stored lesson version mismatch.')

        lesson_regen = expect_ok(
            client.post(
                f'{args.api_base}/skills/{skill_id}/resources/generate?regenerate=true',
                json={'user_id': args.user_id, 'kind': 'lesson'},
            ),
            'regenerate lesson',
        )
        if lesson_regen.get('source') != 'regenerated':
            raise RuntimeError('Lesson regenerate did not report regenerated source.')
        if int(lesson_regen.get('version', 0)) <= int(lesson_cached.get('version', 0)):
            raise RuntimeError('Lesson version did not increment after regenerate.')

        print('7) external resources')
        if args.skip_external:
            print('   skipped (--skip-external)')
        else:
            external = expect_ok(
                client.get(
                    f'{args.api_base}/skills/{skill_id}/resources/external',
                    params={'user_id': args.user_id, 'limit': 3},
                ),
                'external resources',
            )
            if not external.get('resources'):
                raise RuntimeError('No external resources returned.')

        print('8) generate quiz (and persist)')
        quiz = expect_ok(
            client.post(
                f'{args.api_base}/skills/{skill_id}/quiz/generate',
                json={'user_id': args.user_id, 'num_questions': 3},
            ),
            'generate quiz',
        )
        if quiz.get('source') not in {'generated', 'stored'}:
            raise RuntimeError('Unexpected quiz source on first request.')

        quiz_cached = expect_ok(
            client.post(
                f'{args.api_base}/skills/{skill_id}/quiz/generate',
                json={'user_id': args.user_id, 'num_questions': 3},
            ),
            'load stored quiz',
        )
        if quiz_cached.get('source') != 'stored':
            raise RuntimeError('Quiz was not loaded from store on second request.')
        if quiz_cached.get('version') != quiz.get('version'):
            raise RuntimeError('Stored quiz version mismatch.')

        print('9) submit quiz answers')
        answers = [0 for _ in quiz['questions']]
        result = expect_ok(
            client.post(
                f"{args.api_base}/assessments/{quiz['assessment_id']}/submit",
                json={'user_id': args.user_id, 'answers': answers},
            ),
            'submit quiz',
        )
        if 'updated_mastery' not in result:
            raise RuntimeError('Quiz submission did not return mastery update.')

        print('10) update progression (idempotent lesson completion)')
        progress_first = expect_ok(
            client.post(
                f'{args.api_base}/skills/{skill_id}/progress/update',
                json={'user_id': args.user_id, 'action': 'complete_lesson'},
            ),
            'progress update first lesson completion',
        )
        progress_second = expect_ok(
            client.post(
                f'{args.api_base}/skills/{skill_id}/progress/update',
                json={'user_id': args.user_id, 'action': 'complete_lesson'},
            ),
            'progress update duplicate lesson completion',
        )
        if progress_first['mastery'] != progress_second['mastery']:
            raise RuntimeError('Duplicate lesson completion changed mastery unexpectedly.')
        if progress_first['progress_state'] != progress_second['progress_state']:
            raise RuntimeError('Duplicate lesson completion changed progress state unexpectedly.')

        expect_ok(
            client.post(
                f'{args.api_base}/skills/{skill_id}/progress/update',
                json={'user_id': args.user_id, 'action': 'complete_exercises'},
            ),
            'progress update exercises completion',
        )

        print('11) verify updated skill tree')
        updated = expect_ok(
            client.get(f'{args.api_base}/topics/{topic_id}/skill-tree', params={'user_id': args.user_id}),
            'get updated skill tree',
        )
        if not updated.get('nodes'):
            raise RuntimeError('Updated skill tree is empty.')

        updated_node = next((node for node in updated['nodes'] if node['id'] == skill_id), None)
        if not updated_node:
            raise RuntimeError('Updated node missing from skill tree.')
        if not updated_node.get('lesson_completed'):
            raise RuntimeError('Lesson completion state was not persisted.')
        if not updated_node.get('exercises_completed'):
            raise RuntimeError('Exercises completion state was not persisted.')

    print('Smoke test passed.')


if __name__ == '__main__':
    main()
