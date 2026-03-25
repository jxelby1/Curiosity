from __future__ import annotations

import json
import logging
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import LearningResource, ResourceType, SkillNode, Topic
from app.schemas.llm import (
    ExamplesPlan,
    ExercisesPlan,
    ExternalResourceReasoningPlan,
    LessonPlan,
)
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService
from app.services.search import ExternalSearchService


logger = logging.getLogger(__name__)
ResourceSource = Literal['stored', 'generated', 'regenerated']


class ResourceAgent:
    def __init__(
        self,
        llm_service: LLMService,
        search_service: ExternalSearchService,
        retrieval_service: RetrievalService,
    ) -> None:
        self.llm_service = llm_service
        self.search_service = search_service
        self.retrieval_service = retrieval_service

    def _resource_type_for_kind(self, kind: str) -> ResourceType:
        mapping = {
            'lesson': ResourceType.generated_lesson,
            'examples': ResourceType.generated_examples,
            'exercises': ResourceType.generated_exercises,
        }
        if kind not in mapping:
            raise ValueError('Unsupported resource kind.')
        return mapping[kind]

    def _get_active_generated_resource(
        self,
        db: Session,
        *,
        user_id: int,
        skill_node_id: int,
        resource_type: ResourceType,
    ) -> LearningResource | None:
        return db.scalar(
            select(LearningResource)
            .where(
                LearningResource.skill_node_id == skill_node_id,
                LearningResource.resource_type == resource_type,
                LearningResource.is_active.is_(True),
                (LearningResource.user_id == user_id) | (LearningResource.user_id.is_(None)),
            )
            .order_by(LearningResource.version.desc(), LearningResource.created_at.desc())
        )

    def _extract_structured_content(self, resource: LearningResource) -> dict[str, Any] | None:
        if resource.content_json:
            return resource.content_json

        content = (resource.content or '').strip()
        if not content:
            return None
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    async def generate_material(
        self,
        db: Session,
        *,
        user_id: int,
        topic: Topic,
        skill_node: SkillNode,
        kind: str,
        regenerate: bool = False,
    ) -> tuple[LearningResource, dict[str, Any] | None, ResourceSource]:
        resource_type = self._resource_type_for_kind(kind)
        existing = self._get_active_generated_resource(
            db,
            user_id=user_id,
            skill_node_id=skill_node.id,
            resource_type=resource_type,
        )

        if existing and not regenerate:
            structured = self._extract_structured_content(existing)
            logger.info(
                'resource.loaded_from_store topic_id=%s skill_id=%s kind=%s version=%s',
                topic.id,
                skill_node.id,
                kind,
                existing.version,
            )
            return existing, structured, 'stored'

        prompts = {
            'lesson': (
                LessonPlan,
                'Create a practical lesson for this single skill node. Keep it concise and clear for self-study.',
            ),
            'examples': (
                ExamplesPlan,
                'Create concrete examples that build from simple to challenging and explain the reasoning.',
            ),
            'exercises': (
                ExercisesPlan,
                'Create exercises that can be completed in short practice sessions with clear expected outcomes.',
            ),
        }
        schema_model, instruction = prompts[kind]

        retrieved = await self.retrieval_service.retrieve_chunks(
            db,
            topic_id=topic.id,
            query=f'{topic.name} {skill_node.name}',
            top_k=3,
        )
        notes_context = '\n\n'.join(f'- {item.text[:320]}' for item in retrieved)

        system_prompt = (
            'You are ResourceAgent. Produce high-quality learning material that is technically correct and '
            'tailored to learner context.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n'
            f'Skill: {skill_node.name}\n'
            f'Skill description: {skill_node.description}\n\n'
            f'Retrieved learner notes:\n{notes_context or "No notes available"}\n\n'
            f'Instruction: {instruction}'
        )

        structured_model = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=schema_model,
            temperature=0.3,
            max_tokens=1700,
        )

        structured_content = structured_model.model_dump()
        content = json.dumps(structured_content, indent=2)
        summary = structured_content.get('summary') or structured_content.get('intro') or content[:240]

        next_version = 1
        if existing:
            next_version = existing.version + 1
            db.execute(
                update(LearningResource)
                .where(
                    LearningResource.skill_node_id == skill_node.id,
                    LearningResource.resource_type == resource_type,
                    LearningResource.is_active.is_(True),
                    (LearningResource.user_id == user_id) | (LearningResource.user_id.is_(None)),
                )
                .values(is_active=False)
            )

        resource = LearningResource(
            user_id=user_id,
            topic_id=topic.id,
            skill_node_id=skill_node.id,
            resource_type=resource_type,
            version=next_version,
            is_active=True,
            title=structured_content.get('title') or f'{skill_node.name} {kind.title()}',
            summary=summary,
            content_json=structured_content,
            content=content,
            url='',
            relevance_reason='Generated to match learner progression, selected skill, and uploaded note context.',
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)

        source: ResourceSource = 'regenerated' if existing else 'generated'
        logger.info(
            'resource.generated topic_id=%s skill_id=%s kind=%s version=%s source=%s',
            topic.id,
            skill_node.id,
            kind,
            resource.version,
            source,
        )
        return resource, structured_content, source

    async def fetch_external_resources(
        self,
        db: Session,
        *,
        topic: Topic,
        skill_node: SkillNode,
        limit: int = 3,
    ) -> list[LearningResource]:
        search_results = await self.search_service.search(topic.name, skill_node.name, limit=max(6, limit * 2))
        if not search_results:
            return []

        result_payload = [
            {
                'title': item.title,
                'url': item.url,
                'kind': item.kind,
                'summary': item.summary,
            }
            for item in search_results
        ]

        system_prompt = (
            'You are ResourceAgent. Select the most relevant external resources for a learner and provide concise '
            'relevance reasons tied to the selected skill.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Skill: {skill_node.name}\n'
            f'Skill description: {skill_node.description}\n'
            f'Select up to {limit} resources from these candidates:\n{json.dumps(result_payload, indent=2)}'
        )

        reasoning = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=ExternalResourceReasoningPlan,
            temperature=0.2,
            max_tokens=1200,
        )

        candidate_map = {item.url: item for item in search_results}
        selected_urls: list[str] = []
        reasons_by_url: dict[str, str] = {}

        for item in reasoning.resources:
            if item.url not in candidate_map:
                continue
            if item.url in reasons_by_url:
                continue
            reasons_by_url[item.url] = item.relevance_reason
            selected_urls.append(item.url)
            if len(selected_urls) >= limit:
                break

        if not selected_urls:
            selected_urls = [item.url for item in search_results[:limit]]
            for url in selected_urls:
                reasons_by_url[url] = 'Relevant to the selected skill path and current learning objective.'

        created: list[LearningResource] = []
        for url in selected_urls:
            source = candidate_map[url]
            existing = db.scalar(
                select(LearningResource).where(
                    LearningResource.topic_id == topic.id,
                    LearningResource.skill_node_id == skill_node.id,
                    LearningResource.url == source.url,
                )
            )
            if existing:
                created.append(existing)
                continue

            resource = LearningResource(
                user_id=None,
                topic_id=topic.id,
                skill_node_id=skill_node.id,
                resource_type=ResourceType(source.kind),
                title=source.title,
                url=source.url,
                summary=source.summary,
                content_json=None,
                content='',
                relevance_reason=reasons_by_url.get(source.url, 'Relevant to current skill progression.'),
            )
            db.add(resource)
            db.flush()
            created.append(resource)

        db.commit()
        for item in created:
            db.refresh(item)

        logger.info('resource.external topic_id=%s skill_id=%s count=%s', topic.id, skill_node.id, len(created))
        return created
