from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from app.services.llm import LLMService, _extract_json_object, _sanitize_payload_for_model, _truncate_text_cleanly


class _MiniStructured(BaseModel):
    value: str = Field(min_length=1, max_length=30)


class _TruncationStructured(BaseModel):
    summary: str = Field(min_length=1, max_length=60)
    source_url: str = Field(min_length=8, max_length=60)


def test_extract_json_object_handles_code_fence_and_trailing_comma() -> None:
    raw = """
```json
{
  "value": "ok",
}
```
"""
    parsed = _extract_json_object(raw)
    assert parsed['value'] == 'ok'


def test_extract_json_object_handles_wrapped_text() -> None:
    raw = 'assistant output: {"value":"wrapped"} -- end'
    parsed = _extract_json_object(raw)
    assert parsed['value'] == 'wrapped'


def test_generate_structured_repairs_invalid_json_via_repair_call() -> None:
    service = object.__new__(LLMService)
    service.model = 'test-model'

    calls: list[tuple[str, str, bool]] = []
    responses = [
        '{"value":"broken"',  # invalid JSON from primary generation
        '{"value":"repaired"}',  # valid JSON from repair pass
    ]

    async def _fake_generate(system_prompt: str, user_prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((system_prompt, user_prompt, bool(kwargs.get('json_mode'))))
        return responses.pop(0)

    service.generate = _fake_generate  # type: ignore[assignment]

    result = asyncio.run(
        service.generate_structured(
            system_prompt='system',
            user_prompt='user',
            schema_model=_MiniStructured,
            retries=0,
            max_tokens=200,
        )
    )

    assert result.value == 'repaired'
    assert len(calls) == 2
    assert 'repair malformed json' in calls[1][0].lower()


def test_truncate_text_cleanly_preserves_word_boundary() -> None:
    raw = (
        'This summary explains foundational analysis techniques for identifying patterns across long-form '
        'historical source material without losing context.'
    )
    truncated = _truncate_text_cleanly(raw, 70)

    assert len(truncated) <= 70
    assert truncated.endswith('…')
    prefix = truncated[:-1]
    assert raw.startswith(prefix)
    assert raw[len(prefix)] in {' ', '\n', '\t', '.', ',', ';', ':', '!', '?', ')'}


def test_payload_sanitizer_uses_clean_truncation_for_text_and_hard_cut_for_url() -> None:
    payload = {
        'summary': (
            'A long summary that should be shortened safely without cutting words midway through a rendered card.'
        ),
        'source_url': 'https://example.com/' + ('very-long-path-' * 8),
    }

    sanitized = _sanitize_payload_for_model(payload, _TruncationStructured)

    assert len(sanitized['summary']) <= 60
    assert sanitized['summary'].endswith('…')
    assert len(sanitized['source_url']) <= 60
    assert not sanitized['source_url'].endswith('…')
