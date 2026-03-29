from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from urllib.parse import urlparse

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import (
    Assessment,
    AssessmentAttempt,
    BranchSuggestion,
    LearningResource,
    ResourceType,
    SkillEdge,
    SkillNode,
    SkillStatus,
    Topic,
    UserSkillState,
)
from app.services.skill_tree_graph import build_normalized_skill_graph


def _dedupe_keep_order(items: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        cleaned = ' '.join(str(item or '').split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        kept.append(cleaned)
        if len(kept) >= limit:
            break
    return kept


def _domain_for_url(url: str) -> str:
    parsed = urlparse(url)
    domain = (parsed.netloc or '').lower().strip()
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def _extract_terms(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", (text or '').lower())


@dataclass
class CourseMemorySnapshot:
    taught_node_lines: list[str] = field(default_factory=list)
    taught_concepts: list[str] = field(default_factory=list)
    used_examples: list[str] = field(default_factory=list)
    assessed_strengths: list[str] = field(default_factory=list)
    assessed_weaknesses: list[str] = field(default_factory=list)
    future_core_lines: list[str] = field(default_factory=list)
    existing_branch_lines: list[str] = field(default_factory=list)
    source_backed_examples: list[str] = field(default_factory=list)
    completed_node_ids: list[int] = field(default_factory=list)
    stable_node_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            'taught_node_lines': list(self.taught_node_lines),
            'taught_concepts': list(self.taught_concepts),
            'used_examples': list(self.used_examples),
            'assessed_strengths': list(self.assessed_strengths),
            'assessed_weaknesses': list(self.assessed_weaknesses),
            'future_core_lines': list(self.future_core_lines),
            'existing_branch_lines': list(self.existing_branch_lines),
            'source_backed_examples': list(self.source_backed_examples),
            'completed_node_ids': list(self.completed_node_ids),
            'stable_node_ids': list(self.stable_node_ids),
        }

    def to_prompt_context(self) -> str:
        def _render(label: str, values: list[str], max_items: int = 6) -> str:
            if not values:
                return f'{label}: none'
            lines = '\n'.join(f'  - {item}' for item in values[:max_items])
            return f'{label}:\n{lines}'

        return '\n\n'.join(
            [
                _render('Already taught nodes', self.taught_node_lines),
                _render('Concepts already introduced', self.taught_concepts),
                _render('Examples already used', self.used_examples),
                _render('Assessment strengths', self.assessed_strengths),
                _render('Assessment weak spots', self.assessed_weaknesses),
                _render('Planned future core coverage', self.future_core_lines),
                _render('Existing optional branches', self.existing_branch_lines),
                _render('Previously used source-backed examples', self.source_backed_examples),
            ]
        )


class CourseMemoryService:
    def _extract_resource_memory(self, resource: LearningResource) -> tuple[list[str], list[str], list[str]]:
        concepts: list[str] = []
        examples: list[str] = []
        source_backed: list[str] = []

        if resource.resource_type in {
            ResourceType.external_article,
            ResourceType.external_video,
            ResourceType.external_documentation,
        }:
            source = _domain_for_url(resource.url)
            if source:
                source_backed.append(f'{resource.title} ({source})')
            return concepts, examples, source_backed

        payload = resource.content_json if isinstance(resource.content_json, dict) else {}
        if not payload:
            return concepts, examples, source_backed

        if resource.resource_type == ResourceType.generated_lesson:
            key_concepts = payload.get('key_concepts') or payload.get('key_terms')
            if isinstance(key_concepts, list):
                for item in key_concepts[:12]:
                    if not isinstance(item, dict):
                        continue
                    term = str(item.get('term') or '').strip()
                    description = str(item.get('description') or '').strip()
                    if term:
                        concepts.append(term)
                    if description:
                        concepts.append(description)
            sections = payload.get('sections')
            if isinstance(sections, list):
                for item in sections[:8]:
                    if not isinstance(item, dict):
                        continue
                    heading = str(item.get('heading') or '').strip()
                    if heading:
                        concepts.append(heading)

        if resource.resource_type == ResourceType.generated_examples:
            raw_examples = payload.get('examples')
            if isinstance(raw_examples, list):
                for item in raw_examples[:10]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get('name') or '').strip()
                    explanation = str(item.get('explanation') or '').strip()
                    if name:
                        examples.append(name)
                    if explanation:
                        concepts.append(explanation)

        return concepts, examples, source_backed

    def build_snapshot(
        self,
        db: Session,
        *,
        topic: Topic,
        user_id: int,
        focus_skill_id: int | None = None,
    ) -> CourseMemorySnapshot:
        nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
        node_by_id = {node.id: node for node in nodes}
        node_ids = list(node_by_id.keys())
        if not node_ids:
            return CourseMemorySnapshot()

        states = db.scalars(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id.in_(node_ids),
            )
        ).all()
        state_by_node = {state.skill_node_id: state for state in states}

        taught_node_ids: set[int] = set()
        completed_node_ids: list[int] = []
        stable_node_ids: list[int] = []
        taught_lines: list[str] = []

        for node in nodes:
            state = state_by_node.get(node.id)
            if not state:
                continue
            taught = (
                state.progress_state in {'learning', 'completed', 'verified'}
                or state.lesson_completed_at is not None
                or state.examples_generated_at is not None
            )
            if taught:
                taught_node_ids.add(node.id)
                taught_lines.append(f'{node.name} — {node.instructional_role}')
            if state.progress_state in {'completed', 'verified'}:
                completed_node_ids.append(node.id)
                stable_node_ids.append(node.id)

        resources = db.scalars(
            select(LearningResource).where(
                LearningResource.topic_id == topic.id,
                LearningResource.skill_node_id.in_(node_ids),
                LearningResource.is_active.is_(True),
                (LearningResource.user_id == user_id) | (LearningResource.user_id.is_(None)),
            )
        ).all()
        taught_concepts: list[str] = []
        used_examples: list[str] = []
        source_backed_examples: list[str] = []
        for resource in resources:
            if resource.skill_node_id not in taught_node_ids and resource.skill_node_id != focus_skill_id:
                continue
            concepts, examples, sources = self._extract_resource_memory(resource)
            taught_concepts.extend(concepts)
            used_examples.extend(examples)
            source_backed_examples.extend(sources)

        attempts = db.scalars(
            select(AssessmentAttempt)
            .join(Assessment, AssessmentAttempt.assessment_id == Assessment.id)
            .where(
                Assessment.topic_id == topic.id,
                AssessmentAttempt.user_id == user_id,
            )
            .order_by(desc(AssessmentAttempt.created_at))
            .limit(16)
        ).all()
        strengths: list[str] = []
        weaknesses: list[str] = []
        for attempt in attempts:
            strengths.extend(str(item).strip() for item in (attempt.strengths or []) if str(item).strip())
            weaknesses.extend(str(item).strip() for item in (attempt.weaknesses or []) if str(item).strip())

        prereq_edges = db.scalars(
            select(SkillEdge).where(
                SkillEdge.topic_id == topic.id,
                SkillEdge.edge_type == 'prerequisite',
            )
        ).all()
        normalized = build_normalized_skill_graph(
            nodes=nodes,
            edges=prereq_edges,
            include_edge_types={'prerequisite'},
            max_non_core_prereqs=2,
        )
        child_map = normalized.child_map
        core_node_ids = {node.id for node in nodes if node.node_kind == 'core'}
        if focus_skill_id and focus_skill_id in node_by_id:
            start_ids = {focus_skill_id}
        else:
            start_ids = {
                node.id
                for node in nodes
                if node.id in core_node_ids and (node.id in taught_node_ids or state_by_node.get(node.id, None) and state_by_node[node.id].status != SkillStatus.locked)
            }
            if not start_ids and normalized.core_root_id:
                start_ids = {normalized.core_root_id}

        future_core_lines: list[str] = []
        queue = list(start_ids)
        visited: set[int] = set()
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for child_id in child_map.get(current, []):
                if child_id in visited:
                    continue
                queue.append(child_id)
                if child_id not in core_node_ids:
                    continue
                if child_id in taught_node_ids:
                    continue
                child = node_by_id.get(child_id)
                if child:
                    future_core_lines.append(f'{child.name} — {child.instructional_role}')

        branch_nodes = [node for node in nodes if node.node_kind == 'optional_branch']
        existing_branch_lines = [f'{node.name} — {node.branch_purpose}' for node in branch_nodes]
        branch_suggestions = db.scalars(
            select(BranchSuggestion).where(
                BranchSuggestion.topic_id == topic.id,
                BranchSuggestion.user_id == user_id,
            )
        ).all()
        existing_branch_lines.extend(
            f'{item.title} — {item.purpose}'
            for item in branch_suggestions
            if item.status in {'pending', 'accepted'}
        )

        return CourseMemorySnapshot(
            taught_node_lines=_dedupe_keep_order(taught_lines, limit=16),
            taught_concepts=_dedupe_keep_order(taught_concepts, limit=20),
            used_examples=_dedupe_keep_order(used_examples, limit=12),
            assessed_strengths=_dedupe_keep_order(strengths, limit=10),
            assessed_weaknesses=_dedupe_keep_order(weaknesses, limit=10),
            future_core_lines=_dedupe_keep_order(future_core_lines, limit=14),
            existing_branch_lines=_dedupe_keep_order(existing_branch_lines, limit=14),
            source_backed_examples=_dedupe_keep_order(source_backed_examples, limit=14),
            completed_node_ids=sorted(set(completed_node_ids)),
            stable_node_ids=sorted(set(stable_node_ids)),
        )

    def build_editorial_spine(self, db: Session, *, topic: Topic) -> dict[str, object]:
        nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
        if not nodes:
            return {'core_arc': [], 'optional_arc': []}

        core_nodes = [node for node in nodes if node.node_kind == 'core']
        optional_nodes = [node for node in nodes if node.node_kind == 'optional_branch']
        core_nodes_sorted = sorted(core_nodes, key=lambda item: (item.difficulty, item.id))
        optional_nodes_sorted = sorted(optional_nodes, key=lambda item: (item.branch_depth, item.id))

        core_arc = [
            {
                'skill_id': node.id,
                'name': node.name,
                'instructional_role': node.instructional_role,
                'difficulty': node.difficulty,
                'description': node.description,
            }
            for node in core_nodes_sorted
        ]
        optional_arc = [
            {
                'skill_id': node.id,
                'name': node.name,
                'branch_parent_skill_id': node.branch_parent_skill_id,
                'branch_purpose': node.branch_purpose,
                'instructional_role': node.instructional_role,
            }
            for node in optional_nodes_sorted
        ]
        return {'core_arc': core_arc, 'optional_arc': optional_arc}

    def persist_snapshot(
        self,
        db: Session,
        *,
        topic: Topic,
        snapshot: CourseMemorySnapshot,
        reason: str,
    ) -> None:
        topic.curriculum_ledger = {
            'updated_at': datetime.utcnow().isoformat(),
            'reason': reason,
            'summary': snapshot.to_dict(),
        }
        db.flush()

    def persist_editorial_spine(
        self,
        db: Session,
        *,
        topic: Topic,
        spine: dict[str, object],
        reason: str,
    ) -> None:
        topic.curriculum_blueprint = {
            'updated_at': datetime.utcnow().isoformat(),
            'reason': reason,
            **spine,
        }
        db.flush()
