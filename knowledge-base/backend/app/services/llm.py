from __future__ import annotations

import json
import logging
import re
import time
from types import UnionType
from typing import Any, Callable, TypeVar, Union, get_args, get_origin

from annotated_types import MaxLen

from openai import APIError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.exceptions import ProviderError


logger = logging.getLogger(__name__)
T = TypeVar('T', bound=BaseModel)


def _extract_json_object(text: str) -> dict:
    cleaned = _strip_wrapping_fences(text).strip()
    if not cleaned:
        raise ProviderError('LLM returned empty response while JSON output was required.')

    parse_errors: list[str] = []
    for candidate in _json_candidate_strings(cleaned):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            parse_errors.append(str(exc))
            repaired = _repair_common_json_issues(candidate)
            if repaired != candidate:
                try:
                    parsed = json.loads(repaired)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError as repaired_exc:
                    parse_errors.append(str(repaired_exc))

    detail = parse_errors[-1] if parse_errors else 'No parseable JSON object found.'
    raise ProviderError(f'Could not parse structured LLM JSON response: {detail}')


def _strip_wrapping_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
    return cleaned


def _json_candidate_strings(cleaned: str) -> list[str]:
    candidates: list[str] = []
    if cleaned:
        candidates.append(cleaned)

    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start >= 0 and end > start:
        candidates.append(cleaned[start:end + 1])

    # Balanced-object scan for cases where wrapper text or extra braces are present.
    depth = 0
    object_start: int | None = None
    for idx, char in enumerate(cleaned):
        if char == '{':
            if depth == 0:
                object_start = idx
            depth += 1
        elif char == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and object_start is not None:
                    candidates.append(cleaned[object_start: idx + 1])
                    object_start = None

    deduped: list[str] = []
    seen: set[str] = set()
    for item in sorted(candidates, key=len, reverse=True):
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def _repair_common_json_issues(raw: str) -> str:
    repaired = raw
    repaired = repaired.replace('\u201c', '"').replace('\u201d', '"')
    repaired = repaired.replace('\u2018', "'").replace('\u2019', "'")
    repaired = repaired.replace('\xa0', ' ')
    # Remove trailing commas before object/array close.
    repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)
    return repaired


def _unwrap_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]  # noqa: E721
        if len(args) == 1:
            return args[0]
    return annotation


def _max_len_from_metadata(metadata: list[Any]) -> int | None:
    for item in metadata:
        if isinstance(item, MaxLen):
            return int(item.max_length)
        max_length = getattr(item, 'max_length', None)
        if isinstance(max_length, int):
            return max_length
    return None


def _hard_cut_field(field_name: str) -> bool:
    lowered = field_name.lower()
    if lowered in {
        'id',
        'key',
        'url',
        'slug',
        'email',
        'token',
        'code',
        'filename',
        'content_type',
        'kind',
        'status',
    }:
        return True
    if lowered.endswith('_id') or lowered.endswith('_url') or lowered.endswith('_key'):
        return True
    return False


def _truncate_text_cleanly(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    if max_len <= 1:
        return value[:max_len]
    if max_len <= 4:
        return value[:max_len]

    budget = max_len - 1  # reserve for ellipsis
    window = value[:budget]

    sentence_matches = list(re.finditer(r'[.!?](?=(?:["\')\]]|\s|$))', window))
    cut_idx: int | None = None
    if sentence_matches:
        candidate = sentence_matches[-1].end()
        if candidate >= int(budget * 0.55):
            cut_idx = candidate

    if cut_idx is None:
        candidate = max(window.rfind(' '), window.rfind('\n'), window.rfind('\t'))
        if candidate >= int(budget * 0.65):
            cut_idx = candidate

    if cut_idx is None:
        cut_idx = budget

    trimmed = window[:cut_idx].rstrip(' ,;:-')
    if not trimmed:
        trimmed = window.rstrip()
    if len(trimmed) >= max_len:
        trimmed = trimmed[: max_len - 1].rstrip()
    return f'{trimmed}…'


def _sanitize_payload_for_model(payload: dict[str, Any], model: type[BaseModel]) -> dict[str, Any]:
    sanitized = dict(payload)

    for field_name, field in model.model_fields.items():
        if field_name not in sanitized:
            continue

        value = sanitized[field_name]
        annotation = _unwrap_optional(field.annotation)

        if isinstance(value, str):
            max_len = _max_len_from_metadata(list(field.metadata))
            if max_len is not None and len(value) > max_len:
                if _hard_cut_field(field_name):
                    sanitized[field_name] = value[:max_len].rstrip()
                else:
                    sanitized[field_name] = _truncate_text_cleanly(value.rstrip(), max_len)
            continue

        if value is None:
            continue

        origin = get_origin(annotation)
        if origin in (list, tuple) and isinstance(value, list):
            args = get_args(annotation)
            item_annotation = _unwrap_optional(args[0]) if args else Any
            if isinstance(item_annotation, type) and issubclass(item_annotation, BaseModel):
                sanitized[field_name] = [
                    _sanitize_payload_for_model(item, item_annotation) if isinstance(item, dict) else item
                    for item in value
                ]
            continue

        if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(value, dict):
            sanitized[field_name] = _sanitize_payload_for_model(value, annotation)

    return sanitized


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.openai_api_key:
            raise ProviderError('OPENAI_API_KEY is required for LLM usage.')

        self.client = AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.openai_timeout_seconds,
        )
        self.model = self.settings.openai_model

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 900,
        json_mode: bool = False,
    ) -> str:
        started = time.perf_counter()
        logger.info('openai.chat.start model=%s json_mode=%s', self.model, json_mode)

        request_kwargs: dict = {}
        if json_mode:
            request_kwargs['response_format'] = {'type': 'json_object'}

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                **request_kwargs,
            )
        except (APITimeoutError, APIError) as exc:
            logger.exception('openai.chat.error model=%s', self.model)
            raise ProviderError(f'OpenAI chat completion failed: {exc}') from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        usage = response.usage
        logger.info(
            'openai.chat.complete model=%s latency_ms=%s prompt_tokens=%s completion_tokens=%s',
            self.model,
            elapsed_ms,
            getattr(usage, 'prompt_tokens', None),
            getattr(usage, 'completion_tokens', None),
        )

        content = response.choices[0].message.content or ''
        if not content.strip():
            raise ProviderError('OpenAI returned an empty completion.')
        return content

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_model: type[T],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1800,
        retries: int = 2,
        repair_payload: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> T:
        schema_json = json.dumps(schema_model.model_json_schema(), indent=2)
        structured_prompt = (
            f'{user_prompt}\n\n'
            'Return a single JSON object that strictly follows the schema below.\n'
            'Do not include markdown, commentary, or code fences.\n'
            f'JSON Schema:\n{schema_json}'
        )

        async def _repair_broken_json(raw_text: str) -> dict[str, Any]:
            repair_system_prompt = (
                'You repair malformed JSON. Return one valid JSON object only with no commentary. '
                'Preserve user intent and satisfy the required schema.'
            )
            repair_user_prompt = (
                f'Target schema:\n{schema_json}\n\n'
                'Malformed output to repair:\n'
                f'{raw_text}\n\n'
                'Return strictly valid JSON.'
            )
            repaired_raw = await self.generate(
                repair_system_prompt,
                repair_user_prompt,
                temperature=0.0,
                max_tokens=max_tokens,
                json_mode=True,
            )
            return _extract_json_object(repaired_raw)

        attempt = 0
        while attempt <= retries:
            raw = await self.generate(
                system_prompt,
                structured_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
            try:
                payload = _extract_json_object(raw)
            except ProviderError as exc:
                logger.warning('openai.structured.parse_failed attempt=%s error=%s', attempt + 1, exc)
                try:
                    payload = await _repair_broken_json(raw)
                    logger.info(
                        'openai.structured.json_repaired schema=%s attempt=%s',
                        schema_model.__name__,
                        attempt + 1,
                    )
                except Exception as repair_exc:  # noqa: BLE001
                    logger.warning(
                        'openai.structured.retry attempt=%s error=%s repair_error=%s',
                        attempt + 1,
                        exc,
                        repair_exc,
                    )
                    if attempt == retries:
                        raise ProviderError(
                            f'Unable to parse structured output for schema {schema_model.__name__}: {exc}'
                        ) from exc
                    attempt += 1
                    continue

            if repair_payload is not None:
                try:
                    repaired_custom = repair_payload(payload)
                    if isinstance(repaired_custom, dict):
                        if repaired_custom != payload:
                            logger.info(
                                'openai.structured.custom_repair schema=%s attempt=%s',
                                schema_model.__name__,
                                attempt + 1,
                            )
                        payload = repaired_custom
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        'openai.structured.custom_repair_failed schema=%s attempt=%s error=%s',
                        schema_model.__name__,
                        attempt + 1,
                        exc,
                    )

            try:
                return schema_model.model_validate(payload)
            except ValidationError as exc:
                repaired_payload = _sanitize_payload_for_model(payload, schema_model)
                if repaired_payload != payload:
                    try:
                        repaired_model = schema_model.model_validate(repaired_payload)
                        logger.info(
                            'openai.structured.repaired schema=%s attempt=%s',
                            schema_model.__name__,
                            attempt + 1,
                        )
                        return repaired_model
                    except ValidationError:
                        pass

                validation_errors = exc.errors()
                compact_errors = [
                    {
                        'loc': '.'.join(str(part) for part in item.get('loc', [])),
                        'type': item.get('type'),
                        'msg': item.get('msg'),
                    }
                    for item in validation_errors[:6]
                ]
                logger.warning(
                    'openai.structured.retry attempt=%s schema=%s validation_errors=%s',
                    attempt + 1,
                    schema_model.__name__,
                    compact_errors,
                )
                if attempt == retries:
                    raise ProviderError(
                        f'Unable to parse structured output for schema {schema_model.__name__}: {exc}'
                    ) from exc
                attempt += 1

        raise ProviderError(f'Unable to produce structured output for schema {schema_model.__name__}.')
