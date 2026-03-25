from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, ChatSession, SkillNode, Topic, UserSkillState
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService


logger = logging.getLogger(__name__)


class TutorAgent:
    def __init__(self, llm_service: LLMService, retrieval_service: RetrievalService) -> None:
        self.llm_service = llm_service
        self.retrieval_service = retrieval_service

    async def respond(
        self,
        db: Session,
        *,
        topic: Topic,
        user_id: int,
        message: str,
        session_id: int | None,
        skill_node_id: int | None,
    ) -> tuple[int, str, list[str]]:
        session: ChatSession | None = None
        if session_id is not None:
            session = db.scalar(select(ChatSession).where(ChatSession.id == session_id, ChatSession.topic_id == topic.id))

        if session is None:
            session = ChatSession(topic_id=topic.id, user_id=user_id, title=f'{topic.name} chat')
            db.add(session)
            db.flush()

        db.add(
            ChatMessage(
                session_id=session.id,
                topic_id=topic.id,
                skill_node_id=skill_node_id,
                role='user',
                content=message,
            )
        )

        node: SkillNode | None = None
        mastery_context = 'beginner'
        if skill_node_id is not None:
            node = db.scalar(select(SkillNode).where(SkillNode.id == skill_node_id, SkillNode.topic_id == topic.id))

        if node is not None:
            state = db.scalar(
                select(UserSkillState).where(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_node_id == node.id,
                )
            )
            if state:
                if state.mastery >= 0.75:
                    mastery_context = 'advanced'
                elif state.mastery >= 0.35:
                    mastery_context = 'intermediate'

        retrieved = await self.retrieval_service.retrieve_chunks(
            db,
            topic_id=topic.id,
            query=f'{message}\n{node.name if node else topic.name}',
            top_k=4,
        )
        chunk_texts = [item.text for item in retrieved]

        history_items = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(8)
        ).all()
        history_items.reverse()
        history_text = '\n'.join(f'{item.role}: {item.content[:400]}' for item in history_items)

        notes_context = '\n\n'.join(f'- {item.text[:350]}' for item in retrieved)
        skill_context = (
            f'Selected skill: {node.name}\nSkill description: {node.description}' if node else 'No specific skill selected.'
        )

        system_prompt = (
            'You are TutorAgent in a multi-agent learning system. '
            'Give accurate, concise teaching. Use provided notes when relevant, and explicitly mention practical '
            'next steps. If notes conflict with best practice, explain the conflict and provide corrected guidance.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n'
            f'User level estimate: {mastery_context}\n'
            f'{skill_context}\n\n'
            f'Recent chat history:\n{history_text or "No history"}\n\n'
            f'Retrieved note chunks:\n{notes_context or "No note chunks found"}\n\n'
            f'User question:\n{message}'
        )

        answer = await self.llm_service.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1000,
        )

        db.add(
            ChatMessage(
                session_id=session.id,
                topic_id=topic.id,
                skill_node_id=skill_node_id,
                role='assistant',
                content=answer,
            )
        )
        db.commit()

        logger.info('tutor.response topic_id=%s session_id=%s retrieval_hits=%s', topic.id, session.id, len(retrieved))
        return session.id, answer, chunk_texts
