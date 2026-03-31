from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import _topic_journal_response
from app.db.models import (
    Assessment,
    AssessmentAttempt,
    BranchSuggestion,
    ExerciseCompletion,
    LearningResource,
    MilestoneEvent,
    Note,
    NoteType,
    ResourceType,
    SkillNode,
    Topic,
    User,
    UserSkillState,
)


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    LearningResource.__table__.create(bind=engine)
    Note.__table__.create(bind=engine)
    ExerciseCompletion.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    Assessment.__table__.create(bind=engine)
    AssessmentAttempt.__table__.create(bind=engine)
    MilestoneEvent.__table__.create(bind=engine)
    BranchSuggestion.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_topic_journal_merges_notes_exercises_assessments_and_milestones() -> None:
    db = _session()
    user = User(email='journal@test.local', hashed_password='x', display_name='Journal User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Cooking', description='desc', goal='goal')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name='Knife skills', description='desc', difficulty=1, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    now = datetime.utcnow()
    db.add(
        Note(
            user_id=user.id,
            topic_id=topic.id,
            skill_node_id=skill.id,
            note_type=NoteType.personal,
            title='My takeaway',
            body='- **Style and Technique:** Keep fingers curled and move slowly.',
            tags=['reflection', 'comparison', 'exemplar', 'interpretation', 'view_shift', 'next_thread'],
            created_at=now - timedelta(minutes=40),
            updated_at=now - timedelta(minutes=35),
        )
    )
    db.add(
        ExerciseCompletion(
            user_id=user.id,
            topic_id=topic.id,
            skill_node_id=skill.id,
            resource_id=None,
            exercise_index=0,
            exercise_title='Knife grip drill',
            completed_at=now - timedelta(minutes=30),
        )
    )
    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=skill.id,
            progress_state='learning',
            lesson_completed_at=now - timedelta(minutes=50),
            exercises_completed_at=now - timedelta(minutes=30),
        )
    )
    assessment = Assessment(
        topic_id=topic.id,
        skill_node_id=skill.id,
        user_id=user.id,
        title='Knife skill check',
        questions=[],
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    db.add(
        AssessmentAttempt(
            assessment_id=assessment.id,
            user_id=user.id,
            answers=[],
            score=0.82,
            confidence_avg=0.0,
            mastery_delta=0.1,
            strengths=['steady technique'],
            weaknesses=['speed consistency'],
            review_next='Repeat controlled slicing.',
            recommended_follow_up='Continue to next node.',
            feedback=[],
            created_at=now - timedelta(minutes=20),
        )
    )
    db.add(
        MilestoneEvent(
            user_id=user.id,
            topic_id=topic.id,
            skill_node_id=skill.id,
            milestone_key='topic:first_skill',
            milestone_type='first_skill_mastered',
            title='First skill mastered',
            message='Great momentum.',
            created_at=now - timedelta(minutes=10),
        )
    )
    db.add(
        BranchSuggestion(
            topic_id=topic.id,
            user_id=user.id,
            parent_skill_id=skill.id,
            title='Knife speed progression',
            focus='Increase slicing speed while preserving form',
            rationale='You are ready for a focused speed branch.',
            purpose='specialization',
            origin='system_suggested',
            trigger_event='completion',
            status='accepted',
            updated_at=now - timedelta(minutes=8),
        )
    )
    db.commit()

    journal = _topic_journal_response(db, topic=topic, user_id=user.id)
    entry_types = {entry.entry_type for entry in journal.entries}
    assert {'note', 'exercise', 'module', 'assessment', 'milestone', 'branch'}.issubset(entry_types)
    assert journal.topic_id == topic.id
    assert journal.topic_name == topic.name
    assert journal.summary.total_entries >= len(journal.entries)
    assert journal.summary.evidence_entries >= 1
    assert journal.summary.notes_count == 1
    assert journal.summary.exercises_completed == 1
    assert journal.summary.assessments_taken == 1
    assert journal.summary.milestones_reached == 1
    assert journal.summary.branches_accepted == 1
    assert journal.summary.reflections_logged == 1
    assert journal.summary.comparisons_logged == 1
    assert journal.summary.exemplars_saved == 1
    assert journal.summary.interpretations_logged == 1
    assert journal.summary.view_shifts_logged == 1
    assert journal.summary.next_threads_logged == 1
    assert journal.summary.total_nodes == 1
    assert journal.summary.verified_nodes in {0, 1}
    assert journal.summary.growth_signal
    assert journal.summary.reflection_prompt
    assert journal.summary.recommended_lens
    assert journal.summary.recommended_lens_label
    assert journal.summary.recommended_lens_reason
    assert journal.summary.latest_note_title == 'My takeaway'
    assert journal.summary.latest_note_at is not None
    assert journal.summary.latest_note_skill_name == 'Knife skills'
    assert len(journal.chapters) >= 1
    note_created_entries = [
        entry
        for entry in journal.entries
        if entry.entry_type == 'note' and entry.metadata.get('note_event') == 'created'
    ]
    assert len(note_created_entries) == 1
    assert note_created_entries[0].title.startswith('Added a new note:')
    assert '**' not in note_created_entries[0].description
    assert 'Style and Technique:' in note_created_entries[0].description
    note_updated_entries = [
        entry
        for entry in journal.entries
        if entry.entry_type == 'note' and entry.metadata.get('note_event') == 'updated'
    ]
    assert len(note_updated_entries) == 1
    branch_entries = [
        entry
        for entry in journal.entries
        if entry.entry_type == 'branch' and entry.metadata.get('branch_status') == 'accepted'
    ]
    assert len(branch_entries) == 1
