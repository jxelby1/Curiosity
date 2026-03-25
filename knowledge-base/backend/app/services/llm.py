from __future__ import annotations

import json
import logging
import time
from types import UnionType
from typing import Any, TypeVar, Union, get_args, get_origin

from annotated_types import MaxLen

from openai import APIError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.exceptions import ProviderError


logger = logging.getLogger(__name__)
T = TypeVar('T', bound=BaseModel)


def _extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    if not cleaned:
        raise ProviderError('LLM returned empty response while JSON output was required.')

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise ProviderError(f'Could not parse structured LLM JSON response: {exc}') from exc

    raise ProviderError('Could not locate a valid JSON object in LLM response.')


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
                sanitized[field_name] = value[:max_len].rstrip()
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
    ) -> T:
        schema_json = json.dumps(schema_model.model_json_schema(), indent=2)
        structured_prompt = (
            f'{user_prompt}\n\n'
            'Return a single JSON object that strictly follows the schema below.\n'
            'Do not include markdown, commentary, or code fences.\n'
            f'JSON Schema:\n{schema_json}'
        )

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
                logger.warning('openai.structured.retry attempt=%s error=%s', attempt + 1, exc)
                if attempt == retries:
                    raise ProviderError(
                        f'Unable to parse structured output for schema {schema_model.__name__}: {exc}'
                    ) from exc
                attempt += 1
                continue

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

                logger.warning('openai.structured.retry attempt=%s error=%s', attempt + 1, exc)
                if attempt == retries:
                    raise ProviderError(
                        f'Unable to parse structured output for schema {schema_model.__name__}: {exc}'
                    ) from exc
                attempt += 1

        raise ProviderError(f'Unable to produce structured output for schema {schema_model.__name__}.')
