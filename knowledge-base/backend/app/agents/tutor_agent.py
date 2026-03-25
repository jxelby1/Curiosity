from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, ChatSession, LearningResource, Note, SkillEdge, SkillNode, Topic, UserSkillState
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService
from app.services.search import ExternalSearchService, SearchResult


logger = logging.getLogger(__name__)


class TutorAgent:
    def __init__(
        self,
        llm_service: LLMService,
        retrieval_service: RetrievalService,
        search_service: ExternalSearchService | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.retrieval_service = retrieval_service
        self.search_service = search_service

    def _detect_response_mode(self, message: str) -> str:
        normalized = message.lower()
        if any(token in normalized for token in ['question', 'questions', 'what should i ask']):
            return 'questions'
        if any(token in normalized for token in ['example', 'examples', 'sample']):
            return 'examples'
        if any(token in normalized for token in ['compare', 'difference', 'vs ', ' versus ']):
            return 'compare'
        if any(token in normalized for token in ['step-by-step', 'step by step', 'walk me through', 'how do i']):
            return 'steps'
        if any(token in normalized for token in ['brainstorm', 'ideas']):
            return 'brainstorm'
        if any(token in normalized for token in ['list', 'top ', 'bullet']):
            return 'list'
        return 'explain'

    def _mode_instruction(self, mode: str) -> str:
        if mode == 'examples':
            return (
                'Primary output format: concise bullet list of concrete examples. '
                'Lead with examples immediately and add only brief context as needed.'
            )
        if mode == 'questions':
            return (
                'Primary output format: concise list of practical questions/prompts the user asked for. '
                'Do not replace with a generic overview.'
            )
        if mode == 'compare':
            return (
                'Primary output format: side-by-side comparison using short bullets. '
                'Highlight clear differences and when to use each option.'
            )
        if mode == 'steps':
            return (
                'Primary output format: numbered step-by-step guidance. '
                'Keep each step actionable and in sequence.'
            )
        if mode == 'brainstorm':
            return 'Primary output format: idea list with short practical descriptions.'
        if mode == 'list':
            return 'Primary output format: concise list as requested.'
        return (
            'Primary output format: focused direct answer with short paragraphs and bullets where helpful. '
            'Answer the user question first, then optional follow-up guidance.'
        )

    def _should_use_web(self, message: str, topic_name: str, skill_name: str | None) -> bool:
        text = f'{message}\n{topic_name}\n{skill_name or ""}'.lower()
        temporal_markers = (
            'latest',
            'most recent',
            'current',
            'today',
            'this week',
            'this month',
            'news',
            'recent',
            'up-to-date',
            'up to date',
            'as of',
            'release',
            'version',
            'updated',
            '2025',
            '2026',
        )
        return any(marker in text for marker in temporal_markers)

    def _format_web_context(self, results: list[SearchResult]) -> str:
        if not results:
            return 'No web resources.'
        lines: list[str] = []
        for idx, item in enumerate(results, start=1):
            lines.append(f'[{idx}] {item.title}')
            lines.append(f'URL: {item.url}')
            if item.summary:
                lines.append(f'Snippet: {item.summary[:240]}')
            lines.append('')
        return '\n'.join(lines).strip()

    async def respond(
        self,
        db: Session,
        *,
        topic: Topic,
        user_id: int,
        message: str,
        session_id: int | None,
        skill_node_id: int | None,
        include_personal_notes: bool,
        include_web_resources: bool,
    ) -> tuple[int, int, str, list[str], dict | None, dict[str, int], list[dict]]:
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
        else:
            state = None

        retrieved = await self.retrieval_service.retrieve_chunks(
            db,
            topic_id=topic.id,
            query=f'{message}\n{node.name if node else topic.name}',
            top_k=4,
        )
        chunk_texts = [item.text for item in retrieved]

        personal_notes: list[Note] = []
        if include_personal_notes:
            note_stmt = select(Note).where(Note.user_id == user_id, Note.topic_id == topic.id)
            if skill_node_id is not None:
                note_stmt = note_stmt.where(
                    or_(Note.skill_node_id == skill_node_id, Note.skill_node_id.is_(None))
                )
            personal_notes = db.scalars(note_stmt.order_by(Note.updated_at.desc()).limit(4)).all()

        prereq_names: list[str] = []
        child_names: list[str] = []
        if node is not None:
            prereq_ids = db.scalars(
                select(SkillEdge.parent_skill_id).where(
                    SkillEdge.topic_id == topic.id,
                    SkillEdge.child_skill_id == node.id,
                    SkillEdge.edge_type == 'prerequisite',
                )
            ).all()
            child_ids = db.scalars(
                select(SkillEdge.child_skill_id).where(
                    SkillEdge.topic_id == topic.id,
                    SkillEdge.parent_skill_id == node.id,
                    SkillEdge.edge_type == 'prerequisite',
                )
            ).all()
            if prereq_ids:
                prereq_nodes = db.scalars(select(SkillNode).where(SkillNode.id.in_(prereq_ids))).all()
                prereq_names = [item.name for item in prereq_nodes]
            if child_ids:
                child_nodes = db.scalars(select(SkillNode).where(SkillNode.id.in_(child_ids))).all()
                child_names = [item.name for item in child_nodes]

        resource_stmt = (
            select(LearningResource)
            .where(
                LearningResource.topic_id == topic.id,
                LearningResource.is_active.is_(True),
                LearningResource.content_json.is_not(None),
            )
            .order_by(LearningResource.created_at.desc())
            .limit(4)
        )
        if node is not None:
            resource_stmt = (
                select(LearningResource)
                .where(
                    LearningResource.topic_id == topic.id,
                    LearningResource.skill_node_id == node.id,
                    LearningResource.is_active.is_(True),
                    LearningResource.content_json.is_not(None),
                )
                .order_by(LearningResource.created_at.desc())
                .limit(4)
            )
        generated_resources = db.scalars(resource_stmt).all()
        generated_resource_context = '\n'.join(
            f'- {item.title}: {item.summary[:220]}'
            for item in generated_resources
        )

        history_items = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(8)
        ).all()
        history_items.reverse()
        history_text = '\n'.join(f'{item.role}: {item.content[:400]}' for item in history_items)

        document_context = '\n\n'.join(f'- {item.text[:320]}' for item in retrieved)
        personal_notes_context = '\n\n'.join(
            f"- {note.title}: {note.body[:260]}"
            for note in personal_notes
        )
        skill_context = (
            f'Selected skill: {node.name}\nSkill description: {node.description}' if node else 'No specific skill selected.'
        )
        profile_context = (
            f'Progress state: {state.progress_state}; mastery={state.mastery:.2f}; '
            f'best_quiz_score={state.best_quiz_score:.2f}'
            if state is not None
            else 'No explicit skill progress state available.'
        )
        graph_context = (
            f'Prerequisites: {", ".join(prereq_names) if prereq_names else "None"}\n'
            f'Dependent skills: {", ".join(child_names) if child_names else "None"}'
        )

        should_use_web = include_web_resources and self._should_use_web(
            message=message,
            topic_name=topic.name,
            skill_name=node.name if node else None,
        )
        web_results: list[SearchResult] = []
        if should_use_web and self.search_service is not None:
            try:
                web_results = await self.search_service.search(
                    topic=topic.name,
                    skill=node.name if node else topic.name,
                    query=message,
                    limit=4,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning('tutor.web_search_skipped topic_id=%s reason=%s', topic.id, exc)
                web_results = []
        web_context = self._format_web_context(web_results)

        response_mode = self._detect_response_mode(message)
        mode_instruction = self._mode_instruction(response_mode)

        system_prompt = (
            'You are TutorAgent in a multi-agent learning system.\n'
            'Always answer the exact user request directly before anything else.\n'
            'Do not force a fixed response template.\n'
            'When the user asks for examples, questions, or a list, output that format first.\n'
            'Avoid long generic preambles and avoid markdown tables.\n'
            'Use clear bullets or numbered steps when useful.\n'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n'
            f'User level estimate: {mastery_context}\n'
            f'{skill_context}\n\n'
            f'Skill graph context:\n{graph_context}\n'
            f'Skill/profile context:\n{profile_context}\n'
            f'Recent generated learning material:\n{generated_resource_context or "No generated material yet."}\n\n'
            f'Response mode: {response_mode}\n'
            f'Mode instruction: {mode_instruction}\n\n'
            f'Recent chat history:\n{history_text or "No history"}\n\n'
            f'Retrieved source-document chunks:\n{document_context or "No source chunks found"}\n\n'
            f'Personal notes (user opted-in={include_personal_notes}):\n'
            f'{personal_notes_context or "No personal notes included"}\n\n'
            f'External web context enabled={should_use_web}:\n{web_context}\n\n'
            f'User question:\n{message}\n\n'
            'Answer now. Keep it practical, specific, and aligned to the request.\n'
            'If you use web context, cite sources inline as [1], [2], etc. and end with a short "Sources" list.'
        )

        answer = await self.llm_service.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.25,
            max_tokens=1100,
        )

        assistant_message = ChatMessage(
            session_id=session.id,
            topic_id=topic.id,
            skill_node_id=skill_node_id,
            role='assistant',
            content=answer,
        )
        db.add(assistant_message)
        db.flush()

        db.commit()

        citations = [
            {
                'title': item.title,
                'url': item.url,
                'snippet': item.summary,
            }
            for item in web_results
        ]

        logger.info(
            'tutor.response topic_id=%s session_id=%s mode=%s retrieval_hits=%s personal_notes=%s web_results=%s include_personal_notes=%s include_web_resources=%s',
            topic.id,
            session.id,
            response_mode,
            len(retrieved),
            len(personal_notes),
            len(web_results),
            include_personal_notes,
            include_web_resources,
        )
        return (
            session.id,
            assistant_message.id,
            answer,
            chunk_texts,
            None,
            {
                'document_chunks': len(retrieved),
                'personal_notes': len(personal_notes),
                'external_resources': len(web_results),
            },
            citations,
        )
