from __future__ import annotations

from datetime import datetime
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.config import get_settings
from app.db.database import Base


EMBEDDING_DIMENSIONS = get_settings().embedding_dimensions


class SkillStatus(str, Enum):
    locked = 'locked'
    available = 'available'
    in_progress = 'in_progress'
    mastered = 'mastered'


class ResourceType(str, Enum):
    generated_lesson = 'generated_lesson'
    generated_examples = 'generated_examples'
    generated_exercises = 'generated_exercises'
    external_article = 'external_article'
    external_video = 'external_video'
    external_documentation = 'external_documentation'


class NoteType(str, Enum):
    personal = 'personal'
    lesson = 'lesson'
    summary = 'summary'
    reflection = 'reflection'
    reminder = 'reminder'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default='Demo User')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    topics: Mapped[list['Topic']] = relationship(back_populates='user', cascade='all,delete')


class Topic(Base):
    __tablename__ = 'topics'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default='')
    goal: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped['User'] = relationship(back_populates='topics')
    skills: Mapped[list['SkillNode']] = relationship(back_populates='topic', cascade='all,delete')
    edges: Mapped[list['SkillEdge']] = relationship(back_populates='topic', cascade='all,delete')


class SkillNode(Base):
    __tablename__ = 'skill_nodes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    node_kind: Mapped[str] = mapped_column(String(40), default='core')
    branch_parent_skill_id: Mapped[int | None] = mapped_column(ForeignKey('skill_nodes.id'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    mastery_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[SkillStatus] = mapped_column(SAEnum(SkillStatus), default=SkillStatus.locked)
    suggested_resources: Mapped[list[dict]] = mapped_column(JSON, default=list)
    generated_lessons: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    topic: Mapped['Topic'] = relationship(back_populates='skills')
    user_states: Mapped[list['UserSkillState']] = relationship(back_populates='skill_node', cascade='all,delete')


class SkillEdge(Base):
    __tablename__ = 'skill_edges'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    parent_skill_id: Mapped[int] = mapped_column(ForeignKey('skill_nodes.id'), index=True)
    child_skill_id: Mapped[int] = mapped_column(ForeignKey('skill_nodes.id'), index=True)
    edge_type: Mapped[str] = mapped_column(String(40), default='prerequisite')

    topic: Mapped['Topic'] = relationship(back_populates='edges')

    __table_args__ = (UniqueConstraint('topic_id', 'parent_skill_id', 'child_skill_id', name='uq_skill_edge'),)


class UserSkillState(Base):
    __tablename__ = 'user_skill_states'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    skill_node_id: Mapped[int] = mapped_column(ForeignKey('skill_nodes.id'), index=True)
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[SkillStatus] = mapped_column(SAEnum(SkillStatus), default=SkillStatus.locked)
    progress_state: Mapped[str] = mapped_column(String(40), default='not_started')
    lesson_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    examples_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exercises_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quiz_taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    best_quiz_score: Mapped[float] = mapped_column(Float, default=0.0)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    skill_node: Mapped['SkillNode'] = relationship(back_populates='user_states')

    __table_args__ = (UniqueConstraint('user_id', 'skill_node_id', name='uq_user_skill_state'),)


class Document(Base):
    __tablename__ = 'documents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    note_id: Mapped[int | None] = mapped_column(ForeignKey('notes.id'), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default='text/plain')
    raw_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chunks: Mapped[list['DocumentChunk']] = relationship(back_populates='document', cascade='all,delete')


class Note(Base):
    __tablename__ = 'notes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    skill_node_id: Mapped[int | None] = mapped_column(ForeignKey('skill_nodes.id'), nullable=True, index=True)
    note_type: Mapped[NoteType] = mapped_column(SAEnum(NoteType), default=NoteType.personal)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(60), default='user_authored')
    source_chat_session_id: Mapped[int | None] = mapped_column(ForeignKey('chat_sessions.id'), nullable=True, index=True)
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey('chat_messages.id'), nullable=True, index=True)
    created_from_skill_node_id: Mapped[int | None] = mapped_column(ForeignKey('skill_nodes.id'), nullable=True, index=True)
    created_from_topic_id: Mapped[int | None] = mapped_column(ForeignKey('topics.id'), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentChunk(Base):
    __tablename__ = 'document_chunks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('documents.id'), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    document: Mapped['Document'] = relationship(back_populates='chunks')


class ChatSession(Base):
    __tablename__ = 'chat_sessions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(255), default='Learning Chat')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    messages: Mapped[list['ChatMessage']] = relationship(back_populates='session', cascade='all,delete')


class ChatMessage(Base):
    __tablename__ = 'chat_messages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('chat_sessions.id'), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    skill_node_id: Mapped[int | None] = mapped_column(ForeignKey('skill_nodes.id'), nullable=True)
    role: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped['ChatSession'] = relationship(back_populates='messages')


class Recommendation(Base):
    __tablename__ = 'recommendations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    skill_node_id: Mapped[int] = mapped_column(ForeignKey('skill_nodes.id'), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(String(80), default='study_generated')
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LearningResource(Base):
    __tablename__ = 'learning_resources'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), index=True, nullable=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    skill_node_id: Mapped[int] = mapped_column(ForeignKey('skill_nodes.id'), index=True)
    resource_type: Mapped[ResourceType] = mapped_column(SAEnum(ResourceType))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(default=True)
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024), default='')
    summary: Mapped[str] = mapped_column(Text, default='')
    content_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content: Mapped[str] = mapped_column(Text, default='')
    relevance_reason: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Assessment(Base):
    __tablename__ = 'assessments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'), index=True)
    skill_node_id: Mapped[int] = mapped_column(ForeignKey('skill_nodes.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(default=True)
    title: Mapped[str] = mapped_column(String(255), default='Skill Check')
    questions: Mapped[list[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssessmentAttempt(Base):
    __tablename__ = 'assessment_attempts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey('assessments.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    answers: Mapped[list[int]] = mapped_column(JSON)
    score: Mapped[float] = mapped_column(Float)
    feedback: Mapped[list[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
