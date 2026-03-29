from __future__ import annotations

from dataclasses import dataclass

from app.db.models import SkillEdge, SkillNode


@dataclass(frozen=True)
class CoreParentRepair:
    node_id: int
    node_title: str
    is_core_path: bool
    declared_parent_ids: list[int]
    repaired_parent_id: int | None
    repair_succeeded: bool
    reason: str


@dataclass(frozen=True)
class NormalizedSkillGraph:
    prereq_map: dict[int, list[int]]
    child_map: dict[int, list[int]]
    core_root_id: int | None
    core_nodes_without_parent: list[int]
    repairs: list[CoreParentRepair]


def _ordered_unique(items: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for value in items:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def build_normalized_skill_graph(
    *,
    nodes: list[SkillNode],
    edges: list[SkillEdge],
    include_edge_types: set[str] | None = None,
    max_non_core_prereqs: int = 2,
) -> NormalizedSkillGraph:
    effective_edge_types = include_edge_types or {'prerequisite'}
    node_map = {node.id: node for node in nodes}

    declared_prereq_map: dict[int, list[int]] = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.edge_type not in effective_edge_types:
            continue
        if edge.child_skill_id not in node_map or edge.parent_skill_id not in node_map:
            continue
        if edge.parent_skill_id == edge.child_skill_id:
            continue
        declared_prereq_map[edge.child_skill_id].append(edge.parent_skill_id)

    declared_prereq_map = {
        node_id: _ordered_unique(parent_ids)
        for node_id, parent_ids in declared_prereq_map.items()
    }

    core_nodes = [node for node in nodes if node.node_kind == 'core']
    core_nodes_sorted = sorted(core_nodes, key=lambda item: (item.difficulty, item.id))
    core_index = {node.id: index for index, node in enumerate(core_nodes_sorted)}
    core_ids = set(core_index.keys())

    explicit_core_parent_map: dict[int, list[int]] = {}
    for node in core_nodes_sorted:
        explicit_core_parent_map[node.id] = [
            parent_id
            for parent_id in declared_prereq_map.get(node.id, [])
            if parent_id in core_ids and core_index[parent_id] < core_index[node.id]
        ]

    explicit_roots = [
        node
        for node in core_nodes_sorted
        if len(explicit_core_parent_map.get(node.id, [])) == 0
    ]
    root_core = explicit_roots[0] if explicit_roots else (core_nodes_sorted[0] if core_nodes_sorted else None)

    prereq_map: dict[int, list[int]] = {}
    repairs: list[CoreParentRepair] = []
    for node in nodes:
        declared_parents = declared_prereq_map.get(node.id, [])
        if node.node_kind != 'core':
            prereq_map[node.id] = declared_parents[:max_non_core_prereqs]
            continue

        if root_core and node.id == root_core.id:
            prereq_map[node.id] = []
            continue

        valid_declared_core_parents = explicit_core_parent_map.get(node.id, [])
        if valid_declared_core_parents:
            chosen_parent = max(valid_declared_core_parents, key=lambda parent_id: core_index[parent_id])
            prereq_map[node.id] = [chosen_parent]
            continue

        chosen_parent: int | None = None
        reason: str = 'missing'
        idx = core_index.get(node.id)
        if idx is not None and idx > 0:
            chosen_parent = core_nodes_sorted[idx - 1].id
            reason = 'sequential_core_repair'
        elif root_core and root_core.id != node.id:
            chosen_parent = root_core.id
            reason = 'root_core_repair'

        if chosen_parent is None:
            prereq_map[node.id] = []
            repairs.append(
                CoreParentRepair(
                    node_id=node.id,
                    node_title=node.name,
                    is_core_path=True,
                    declared_parent_ids=declared_parents,
                    repaired_parent_id=None,
                    repair_succeeded=False,
                    reason=reason,
                )
            )
            continue

        prereq_map[node.id] = [chosen_parent]
        repairs.append(
            CoreParentRepair(
                node_id=node.id,
                node_title=node.name,
                is_core_path=True,
                declared_parent_ids=declared_parents,
                repaired_parent_id=chosen_parent,
                repair_succeeded=True,
                reason=reason,
            )
        )

    child_map: dict[int, list[int]] = {}
    for child_id, parent_ids in prereq_map.items():
        for parent_id in parent_ids:
            child_map.setdefault(parent_id, []).append(child_id)
    child_map = {
        parent_id: _ordered_unique(child_ids)
        for parent_id, child_ids in child_map.items()
    }

    core_nodes_without_parent = [
        node.id
        for node in core_nodes_sorted
        if not prereq_map.get(node.id)
    ]

    return NormalizedSkillGraph(
        prereq_map=prereq_map,
        child_map=child_map,
        core_root_id=root_core.id if root_core else None,
        core_nodes_without_parent=core_nodes_without_parent,
        repairs=repairs,
    )
