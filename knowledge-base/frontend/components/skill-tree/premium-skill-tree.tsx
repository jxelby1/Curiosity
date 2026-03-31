'use client';

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent,
} from 'react';

import {
  buildAnchoredTreeEdges,
  buildSkillTreeLayout,
  type SkillTreePoint,
} from '@/lib/skill-tree-layout';
import { SkillNode } from '@/lib/types';

type NodeState = 'locked' | 'available' | 'in_progress' | 'verified';
type ViewTransform = { x: number; y: number; scale: number };
type AnchorPoint = { x: number; y: number };

type NodeAnchorSet = {
  center: AnchorPoint;
  top: AnchorPoint;
  bottom: AnchorPoint;
};

type EdgeRender = {
  key: string;
  parentId: number;
  childId: number;
  from: SkillTreePoint;
  to: SkillTreePoint;
  start: AnchorPoint;
  end: AnchorPoint;
  path: string;
  routeMode: 'preferred' | 'fallback' | 'emergency';
  source: string;
  isLocked: boolean;
  isVerified: boolean;
  isCore: boolean;
  isOptional: boolean;
  isSuggested: boolean;
  isPrimary: boolean;
  isSynthetic: boolean;
};

type CoreBackboneEdge = {
  key: string;
  parentId: number;
  childId: number;
  start: AnchorPoint;
  end: AnchorPoint;
  path: string;
};

const MIN_ZOOM = 0.62;
const MAX_ZOOM = 1.72;
const PAN_PADDING = 180;
const MIN_VISIBLE_CONNECTOR_DY = 6;
const MIN_VISIBLE_CONNECTOR_DISTANCE = 6;
const CORE_CONNECTOR_STROKE = 'stroke-[4.1]';
const CORE_CONNECTOR_DEBUG_STROKE = 'stroke-[4.4]';
const CORE_CONNECTOR_COLOR = 'rgba(100,116,139,0.5)';
const CORE_CONNECTOR_GLOW_COLOR = 'rgba(71,85,105,0.22)';

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function nodeState(node: SkillNode): NodeState {
  if (node.status === 'locked') return 'locked';
  if (node.progress_state === 'verified' || node.status === 'mastered') return 'verified';
  if (node.progress_state === 'learning' || node.status === 'in_progress') return 'in_progress';
  return 'available';
}

function truncateTitle(title: string): string {
  if (title.length <= 34) return title;
  return `${title.slice(0, 33)}...`;
}

type StateTone = {
  shell: string;
  core: string;
  text: string;
  label: string;
  ring: string;
  status: string;
};

const tones: Record<NodeState, StateTone> = {
  locked: {
    shell: 'border-zinc-300 bg-zinc-100',
    core: 'border-zinc-300 bg-zinc-200',
    text: 'text-zinc-600',
    label: 'border-zinc-300 bg-zinc-100 text-zinc-600',
    ring: 'border-zinc-300',
    status: 'Locked',
  },
  available: {
    shell: 'border-sky-300 bg-sky-50',
    core: 'border-sky-300 bg-sky-100',
    text: 'text-sky-700',
    label: 'border-sky-200 bg-white text-sky-700',
    ring: 'border-sky-300',
    status: 'Available',
  },
  in_progress: {
    shell: 'border-amber-300 bg-amber-50',
    core: 'border-amber-300 bg-amber-100',
    text: 'text-amber-700',
    label: 'border-amber-200 bg-white text-amber-700',
    ring: 'border-amber-300',
    status: 'In progress',
  },
  verified: {
    shell: 'border-emerald-300 bg-emerald-50',
    core: 'border-emerald-300 bg-emerald-100',
    text: 'text-emerald-700',
    label: 'border-emerald-200 bg-white text-emerald-700',
    ring: 'border-emerald-300',
    status: 'Verified',
  },
};

function clampPan({
  x,
  y,
  scale,
  viewportWidth,
  viewportHeight,
  sceneWidth,
  sceneHeight,
}: {
  x: number;
  y: number;
  scale: number;
  viewportWidth: number;
  viewportHeight: number;
  sceneWidth: number;
  sceneHeight: number;
}) {
  const scaledWidth = sceneWidth * scale;
  const scaledHeight = sceneHeight * scale;
  const minX = viewportWidth - scaledWidth - PAN_PADDING;
  const maxX = PAN_PADDING;
  const minY = viewportHeight - scaledHeight - PAN_PADDING;
  const maxY = PAN_PADDING;
  return {
    x: clamp(x, Math.min(minX, maxX), Math.max(minX, maxX)),
    y: clamp(y, Math.min(minY, maxY), Math.max(minY, maxY)),
  };
}

function nodeMarkerSize(node: SkillNode): number {
  return node.progress_state === 'verified' || node.status === 'mastered' ? 56 : 48;
}

function nodeAnchorSet(node: SkillNode, point: SkillTreePoint): NodeAnchorSet {
  const markerRadius = nodeMarkerSize(node) / 2;
  return {
    center: { x: point.x, y: point.y },
    top: { x: point.x, y: point.y - markerRadius + 1 },
    bottom: { x: point.x, y: point.y + markerRadius - 1 },
  };
}

function connectorAnchors(
  parentNode: SkillNode,
  childNode: SkillNode,
  from: SkillTreePoint,
  to: SkillTreePoint
): { start: AnchorPoint; end: AnchorPoint } {
  const parentAnchors = nodeAnchorSet(parentNode, from);
  const childAnchors = nodeAnchorSet(childNode, to);
  const descending = to.y >= from.y;
  return {
    start: descending ? parentAnchors.bottom : parentAnchors.top,
    end: descending ? childAnchors.top : childAnchors.bottom,
  };
}

function hasFiniteAnchor(point: AnchorPoint): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y);
}

function straightConnectorPath(start: AnchorPoint, end: AnchorPoint): string {
  return `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
}

function elbowConnectorPath(start: AnchorPoint, end: AnchorPoint): string {
  const midY = start.y + (end.y - start.y) * 0.54;
  return `M ${start.x} ${start.y} L ${start.x} ${midY} L ${end.x} ${midY} L ${end.x} ${end.y}`;
}

function preferredCoreConnectorPath(start: AnchorPoint, end: AnchorPoint): string {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  if (Math.abs(dx) <= 14 || Math.abs(dy) <= 16) {
    return straightConnectorPath(start, end);
  }
  const bend = Math.max(26, Math.min(80, Math.abs(dy) * 0.34));
  const cp1x = start.x + dx * 0.2;
  const cp2x = end.x - dx * 0.2;
  return `M ${start.x} ${start.y} C ${cp1x} ${start.y + bend}, ${cp2x} ${end.y - bend}, ${end.x} ${end.y}`;
}

function preferredBranchConnectorPath(start: AnchorPoint, end: AnchorPoint): string {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  if (Math.abs(dx) <= 12 || Math.abs(dy) <= 16) {
    return straightConnectorPath(start, end);
  }
  const bend = Math.max(20, Math.min(68, Math.abs(dy) * 0.28));
  const cp1x = start.x + dx * 0.32;
  const cp2x = end.x - dx * 0.32;
  return `M ${start.x} ${start.y} C ${cp1x} ${start.y + bend}, ${cp2x} ${end.y - bend}, ${end.x} ${end.y}`;
}

function safeConnectorPath(
  edge: Pick<EdgeRender, 'start' | 'end' | 'isCore'>
): { path: string; routeMode: 'preferred' | 'fallback' | 'emergency' } {
  if (!hasFiniteAnchor(edge.start) || !hasFiniteAnchor(edge.end)) {
    return { path: '', routeMode: 'emergency' };
  }
  const dy = Math.abs(edge.end.y - edge.start.y);
  const dx = Math.abs(edge.end.x - edge.start.x);

  if (dy < 2 && dx < 2) {
    return { path: '', routeMode: 'emergency' };
  }

  const preferred = edge.isCore
    ? preferredCoreConnectorPath(edge.start, edge.end)
    : preferredBranchConnectorPath(edge.start, edge.end);
  if (preferred.length > 0) {
    return { path: preferred, routeMode: 'preferred' };
  }

  const fallback = elbowConnectorPath(edge.start, edge.end);
  if (fallback.length > 0) {
    return { path: fallback, routeMode: 'fallback' };
  }

  return {
    path: straightConnectorPath(edge.start, edge.end),
    routeMode: 'emergency',
  };
}

function hasVisibleConnectorGeometry(
  edge: Pick<EdgeRender, 'start' | 'end' | 'path'>
): boolean {
  if (!edge.path || edge.path.length === 0) return false;
  if (!hasFiniteAnchor(edge.start) || !hasFiniteAnchor(edge.end)) return false;
  const dx = edge.end.x - edge.start.x;
  const dy = edge.end.y - edge.start.y;
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return false;
  if (dy < MIN_VISIBLE_CONNECTOR_DY) return false;
  const distance = Math.hypot(dx, dy);
  if (!Number.isFinite(distance)) return false;
  return distance >= MIN_VISIBLE_CONNECTOR_DISTANCE;
}

function buildGuaranteedCoreBackboneEdges(
  nodes: SkillNode[],
  points: Map<number, SkillTreePoint>
): CoreBackboneEdge[] {
  const coreEntries = nodes
    .map((node) => ({ node, point: points.get(node.id) }))
    .filter(
      (entry): entry is { node: SkillNode; point: SkillTreePoint } =>
        !!entry.point && entry.node.node_kind === 'core'
    )
    .sort((a, b) => {
      if (a.point.depth !== b.point.depth) return a.point.depth - b.point.depth;
      if (a.point.y !== b.point.y) return a.point.y - b.point.y;
      return a.point.x - b.point.x;
    });

  if (coreEntries.length <= 1) return [];
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const minDepth = coreEntries[0].point.depth;
  const rootIds = new Set(
    coreEntries
      .filter((entry) => entry.point.depth === minDepth)
      .map((entry) => entry.node.id)
  );

  const links: CoreBackboneEdge[] = [];

  for (const entry of coreEntries) {
    const child = entry.node;
    const childPoint = entry.point;
    if (rootIds.has(child.id)) continue;

    const explicitCoreParentCandidates = (child.prerequisites || [])
      .map((parentId) => nodeMap.get(parentId))
      .filter((parent): parent is SkillNode => !!parent && parent.node_kind === 'core')
      .map((parent) => ({ node: parent, point: points.get(parent.id) }))
      .filter(
        (candidate): candidate is { node: SkillNode; point: SkillTreePoint } =>
          !!candidate.point && candidate.point.depth < childPoint.depth
      )
      .sort((a, b) => {
        if (a.point.depth !== b.point.depth) return b.point.depth - a.point.depth;
        return Math.abs(a.point.x - childPoint.x) - Math.abs(b.point.x - childPoint.x);
      });

    const immediateDepthCandidates = coreEntries
      .filter((candidate) => candidate.node.id !== child.id)
      .filter((candidate) => candidate.point.depth === childPoint.depth - 1)
      .sort((a, b) => {
        const dxA = Math.abs(a.point.x - childPoint.x);
        const dxB = Math.abs(b.point.x - childPoint.x);
        if (dxA !== dxB) return dxA - dxB;
        return Math.abs(a.point.y - childPoint.y) - Math.abs(b.point.y - childPoint.y);
      });

    const nearestCoreAbove = coreEntries
      .filter((candidate) => candidate.node.id !== child.id && candidate.point.y < childPoint.y)
      .sort((a, b) => {
        const dyA = childPoint.y - a.point.y;
        const dyB = childPoint.y - b.point.y;
        if (dyA !== dyB) return dyA - dyB;
        return Math.abs(a.point.x - childPoint.x) - Math.abs(b.point.x - childPoint.x);
      });

    const parent =
      explicitCoreParentCandidates[0] || immediateDepthCandidates[0] || nearestCoreAbove[0];
    if (!parent) continue;
    if (parent.point.y >= childPoint.y) continue;

    const { start, end } = connectorAnchors(parent.node, child, parent.point, childPoint);
    links.push({
      key: `${parent.node.id}-${child.id}`,
      parentId: parent.node.id,
      childId: child.id,
      start,
      end,
      path: straightConnectorPath(start, end),
    });
  }

  return links.filter((edge) => hasVisibleConnectorGeometry(edge));
}

export function PremiumSkillTree({
  nodes,
  selectedNodeId,
  onSelectNode,
}: {
  nodes: SkillNode[];
  selectedNodeId: number | null;
  onSelectNode: (nodeId: number) => void;
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [viewportSize, setViewportSize] = useState({ width: 1040, height: 620 });
  const [sceneSize, setSceneSize] = useState({ width: 1400, height: 860 });
  const [transform, setTransform] = useState<ViewTransform>({ x: 130, y: 64, scale: 0.94 });
  const [treeDebugMode, setTreeDebugMode] = useState(false);
  const [coreOnlyMode, setCoreOnlyMode] = useState(false);
  const [initializedForNodeCount, setInitializedForNodeCount] = useState<number | null>(null);
  const [revealedNodeIds, setRevealedNodeIds] = useState<Record<number, true>>({});
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);
  const previousNodesRef = useRef<Map<number, SkillNode> | null>(null);
  const revealTimersRef = useRef<Map<number, number>>(new Map());

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const width = Math.floor(entry.contentRect.width);
      const height = Math.floor(entry.contentRect.height);
      setViewportSize({
        width: Math.max(720, width),
        height: Math.max(500, height),
      });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const debug = params.get('treeDebug') === '1';
    const coreOnly = params.get('treeCoreOnly') === '1';
    setTreeDebugMode(debug);
    setCoreOnlyMode(coreOnly);
  }, []);

  const layout = useMemo(
    () =>
      buildSkillTreeLayout(nodes, {
        width: Math.max(1360, viewportSize.width + 560),
        height: Math.max(800, viewportSize.height + 220),
      }),
    [nodes, viewportSize.width, viewportSize.height]
  );

  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const guaranteedCoreBackboneEdges = useMemo<CoreBackboneEdge[]>(
    () => buildGuaranteedCoreBackboneEdges(nodes, layout.points),
    [nodes, layout.points]
  );

  useEffect(() => {
    const previous = previousNodesRef.current;
    if (!previous) {
      previousNodesRef.current = new Map(nodes.map((node) => [node.id, node]));
      return;
    }

    const newlyRevealed: number[] = [];
    for (const node of nodes) {
      const before = previous.get(node.id);
      const isNewBranch = !before && node.node_kind === 'optional_branch';
      const unlockedNow = !!before && before.status === 'locked' && node.status !== 'locked';
      if (isNewBranch || unlockedNow) {
        newlyRevealed.push(node.id);
      }
    }

    if (newlyRevealed.length > 0) {
      setRevealedNodeIds((prev) => {
        const next = { ...prev };
        newlyRevealed.forEach((nodeId) => {
          next[nodeId] = true;
          const activeTimer = revealTimersRef.current.get(nodeId);
          if (activeTimer) window.clearTimeout(activeTimer);
          const timer = window.setTimeout(() => {
            setRevealedNodeIds((current) => {
              const updated = { ...current };
              delete updated[nodeId];
              return updated;
            });
            revealTimersRef.current.delete(nodeId);
          }, 2200);
          revealTimersRef.current.set(nodeId, timer);
        });
        return next;
      });
    }

    previousNodesRef.current = new Map(nodes.map((node) => [node.id, node]));
  }, [nodes]);

  useEffect(() => {
    const timers = revealTimersRef.current;
    return () => {
      for (const timer of timers.values()) {
        window.clearTimeout(timer);
      }
      timers.clear();
    };
  }, []);

  const edges = useMemo<EdgeRender[]>(() => {
    type AnchorCandidate = {
      parentId: number;
      childId: number;
      synthetic: boolean;
      forcedCore?: boolean;
      forcedBranchParent?: boolean;
      reason:
        | 'anchored'
        | 'declared_core'
        | 'branch_parent'
        | 'fallback_nearest'
        | 'fallback_core';
    };

    const candidatesByChild = new Map<number, AnchorCandidate[]>();
    const anchoredEdges = buildAnchoredTreeEdges(nodes, layout.points);

    function nearestAboveNode(
      child: SkillNode,
      childPoint: SkillTreePoint,
      preferCore: boolean
    ): SkillNode | null {
      const ranked = nodes
        .filter((candidate) => {
          if (candidate.id === child.id) return false;
          const candidatePoint = layout.points.get(candidate.id);
          if (!candidatePoint) return false;
          if (candidatePoint.y >= childPoint.y) return false;
          if (preferCore && candidate.node_kind !== 'core') return false;
          return true;
        })
        .sort((a, b) => {
          const aPoint = layout.points.get(a.id)!;
          const bPoint = layout.points.get(b.id)!;
          const dyA = Math.abs(childPoint.y - aPoint.y);
          const dyB = Math.abs(childPoint.y - bPoint.y);
          if (dyA !== dyB) return dyA - dyB;
          return Math.abs(childPoint.x - aPoint.x) - Math.abs(childPoint.x - bPoint.x);
        });
      return ranked[0] || null;
    }

    function pushCandidate(candidate: AnchorCandidate) {
      const child = nodeMap.get(candidate.childId);
      const parent = nodeMap.get(candidate.parentId);
      const childPoint = layout.points.get(candidate.childId);
      const parentPoint = layout.points.get(candidate.parentId);
      if (!child || !parent || !childPoint || !parentPoint) return;
      if (parentPoint.depth >= childPoint.depth) return;

      const bucket = candidatesByChild.get(candidate.childId) || [];
      const existingIndex = bucket.findIndex((item) => item.parentId === candidate.parentId);
      if (existingIndex >= 0) {
        const existing = bucket[existingIndex];
        bucket[existingIndex] = {
          ...existing,
          synthetic: existing.synthetic && candidate.synthetic,
          forcedCore: existing.forcedCore || candidate.forcedCore,
          forcedBranchParent: existing.forcedBranchParent || candidate.forcedBranchParent,
          reason: existing.reason,
        };
      } else {
        bucket.push(candidate);
      }
      candidatesByChild.set(candidate.childId, bucket);
    }

    function visibleGeometry(edge: Pick<EdgeRender, 'start' | 'end' | 'path'>): boolean {
      return hasVisibleConnectorGeometry(edge);
    }

    function declaredCoreParentId(child: SkillNode, childPoint: SkillTreePoint): number | null {
      const parentIds = (child.prerequisites || [])
        .map((parentId) => nodeMap.get(parentId))
        .filter((parent): parent is SkillNode => !!parent && parent.node_kind === 'core')
        .map((parent) => ({
          node: parent,
          point: layout.points.get(parent.id),
        }))
        .filter((entry): entry is { node: SkillNode; point: SkillTreePoint } => !!entry.point && entry.point.depth < childPoint.depth)
        .sort((a, b) => {
          if (a.point.depth !== b.point.depth) return b.point.depth - a.point.depth;
          return Math.abs(a.point.x - childPoint.x) - Math.abs(b.point.x - childPoint.x);
        });

      if (parentIds.length > 0) return parentIds[0].node.id;

      // Prefer visual continuity on the core trunk if explicit prerequisites are absent.
      // This avoids detached-looking vertical core chains when depth assignments are imperfect.
      const higherCore = nearestAboveNode(child, childPoint, true);
      if (higherCore) return higherCore.id;

      const immediateCoreParents = nodes
        .filter((candidate) => {
          if (candidate.id === child.id || candidate.node_kind !== 'core') return false;
          const point = layout.points.get(candidate.id);
          if (!point) return false;
          return point.depth === childPoint.depth - 1;
        })
        .sort((a, b) => {
          const aPoint = layout.points.get(a.id)!;
          const bPoint = layout.points.get(b.id)!;
          return Math.abs(aPoint.x - childPoint.x) - Math.abs(bPoint.x - childPoint.x);
        });
      if (immediateCoreParents.length > 0) return immediateCoreParents[0].id;

      // Final deterministic fallback: any core node from a shallower depth lane.
      // This guarantees a parent selection for non-root core nodes even when y-ordering
      // is unusual due to balancing/beauty passes.
      const depthFallback = nodes
        .filter((candidate) => {
          if (candidate.id === child.id || candidate.node_kind !== 'core') return false;
          const point = layout.points.get(candidate.id);
          if (!point) return false;
          return point.depth < childPoint.depth;
        })
        .sort((a, b) => {
          const aPoint = layout.points.get(a.id)!;
          const bPoint = layout.points.get(b.id)!;
          if (aPoint.depth !== bPoint.depth) return bPoint.depth - aPoint.depth;
          return Math.abs(aPoint.x - childPoint.x) - Math.abs(bPoint.x - childPoint.x);
        });
      if (depthFallback.length > 0) return depthFallback[0].id;
      return null;
    }

    for (const edge of anchoredEdges) {
      pushCandidate({
        parentId: edge.parentId,
        childId: edge.childId,
        synthetic: edge.synthetic,
        reason: 'anchored',
      });
    }

    for (const node of nodes) {
      const point = layout.points.get(node.id);
      if (!point || point.depth === 0) continue;

      if (node.node_kind === 'core') {
        const preferredCoreParent = declaredCoreParentId(node, point);
        if (preferredCoreParent) {
          pushCandidate({
            parentId: preferredCoreParent,
            childId: node.id,
            synthetic: true,
            forcedCore: true,
            reason: 'declared_core',
          });
        }
      } else if (node.branch_parent_skill_id) {
        pushCandidate({
          parentId: node.branch_parent_skill_id,
          childId: node.id,
          synthetic: true,
          forcedBranchParent: true,
          reason: 'branch_parent',
        });
      }

      if ((candidatesByChild.get(node.id) || []).length === 0) {
        const nearestAbove =
          nearestAboveNode(node, point, node.node_kind === 'core') ||
          nearestAboveNode(node, point, false);
        if (nearestAbove) {
          pushCandidate({
            parentId: nearestAbove.id,
            childId: node.id,
            synthetic: true,
            reason: node.node_kind === 'core' ? 'fallback_core' : 'fallback_nearest',
          });
        }
      }
    }

    const resolved: EdgeRender[] = [];

    for (const node of nodes) {
      const childPoint = layout.points.get(node.id);
      if (!childPoint) continue;
      const candidates = candidatesByChild.get(node.id) || [];
      if (childPoint.depth > 0 && candidates.length === 0) {
        continue;
      }
      if (candidates.length === 0) continue;

      const maxEdges = node.node_kind === 'core' ? 1 : 2;
      const scored = [...candidates].sort((a, b) => {
        const parentA = nodeMap.get(a.parentId);
        const parentB = nodeMap.get(b.parentId);
        const pointA = layout.points.get(a.parentId);
        const pointB = layout.points.get(b.parentId);
        if (!parentA || !parentB || !pointA || !pointB) return 0;
        const depthGapA = childPoint.depth - pointA.depth;
        const depthGapB = childPoint.depth - pointB.depth;
        const dxA = Math.abs(pointA.x - childPoint.x);
        const dxB = Math.abs(pointB.x - childPoint.x);
        let scoreA = depthGapA * 220 + dxA + (a.synthetic ? 40 : 0);
        let scoreB = depthGapB * 220 + dxB + (b.synthetic ? 40 : 0);
        if (a.forcedCore) scoreA -= 12000;
        if (b.forcedCore) scoreB -= 12000;
        if (a.forcedBranchParent) scoreA -= 8000;
        if (b.forcedBranchParent) scoreB -= 8000;
        if (node.node_kind === 'core' && parentA.node_kind === 'core' && depthGapA === 1) scoreA -= 1500;
        if (node.node_kind === 'core' && parentB.node_kind === 'core' && depthGapB === 1) scoreB -= 1500;
        return scoreA - scoreB;
      });

      const selected = scored.slice(0, maxEdges);
      selected.forEach((candidate, index) => {
        const child = nodeMap.get(candidate.childId);
        const parent = nodeMap.get(candidate.parentId);
        const from = layout.points.get(candidate.parentId);
        const to = layout.points.get(candidate.childId);
        if (!child || !parent || !from || !to) return;
        const { start, end } = connectorAnchors(parent, child, from, to);
        const childState = nodeState(child);
        const parentState = nodeState(parent);
        const isCore = parent.node_kind === 'core' && child.node_kind === 'core';
        const routed = safeConnectorPath({ start, end, isCore });
        const source =
          candidate.reason === 'declared_core'
            ? 'declared_core'
            : candidate.forcedBranchParent
              ? 'forced_branch_parent'
              : candidate.reason === 'fallback_core'
                ? 'fallback_core'
                : candidate.reason === 'fallback_nearest'
                  ? 'fallback_nearest'
                  : candidate.synthetic
                    ? 'synthetic'
                    : 'declared';
        resolved.push({
          key: `${candidate.parentId}-${candidate.childId}-${source}-${index}`,
          parentId: candidate.parentId,
          childId: candidate.childId,
          from,
          to,
          start,
          end,
          path: routed.path,
          routeMode: routed.routeMode,
          source,
          isLocked: childState === 'locked',
          isVerified: childState === 'verified' && parentState === 'verified',
          isCore,
          isOptional: !isCore,
          isSuggested:
            child.branch_origin === 'system_suggested' || parent.branch_origin === 'system_suggested',
          isPrimary: index === 0,
          isSynthetic: candidate.synthetic,
        });
      });
    }

    const hasRenderedEdge = (childId: number): boolean =>
      resolved.some((edge) => edge.childId === childId && visibleGeometry(edge));
    const hasRenderedCoreEdge = (childId: number): boolean =>
      resolved.some((edge) => edge.childId === childId && edge.isCore && visibleGeometry(edge));
    const edgeExists = (parentId: number, childId: number): boolean =>
      resolved.some((edge) => edge.parentId === parentId && edge.childId === childId);
    const visibleEdgeExists = (parentId: number, childId: number): boolean =>
      resolved.some(
        (edge) =>
          edge.parentId === parentId &&
          edge.childId === childId &&
          visibleGeometry(edge)
      );

    for (const node of nodes) {
      const point = layout.points.get(node.id);
      if (!point || point.depth === 0) continue;
      if (hasRenderedEdge(node.id)) continue;

      const emergencyParent =
        nearestAboveNode(node, point, node.node_kind === 'core') ||
        nearestAboveNode(node, point, false);
      if (!emergencyParent) continue;
      if (visibleEdgeExists(emergencyParent.id, node.id)) continue;
      const replacingBrokenEdge = edgeExists(emergencyParent.id, node.id);
      const parentPoint = layout.points.get(emergencyParent.id);
      if (!parentPoint) continue;
      const { start, end } = connectorAnchors(emergencyParent, node, parentPoint, point);
      const isCore = emergencyParent.node_kind === 'core' && node.node_kind === 'core';
      resolved.push({
        key: `${emergencyParent.id}-${node.id}-emergency-incoming-${replacingBrokenEdge ? 'repair' : 'missing'}`,
        parentId: emergencyParent.id,
        childId: node.id,
        from: parentPoint,
        to: point,
        start,
        end,
        path: straightConnectorPath(start, end),
        routeMode: 'emergency',
        source: replacingBrokenEdge ? 'emergency_repair_incoming' : 'emergency_missing_incoming',
        isLocked: nodeState(node) === 'locked',
        isVerified: nodeState(node) === 'verified' && nodeState(emergencyParent) === 'verified',
        isCore,
        isOptional: !isCore,
        isSuggested:
          node.branch_origin === 'system_suggested' ||
          emergencyParent.branch_origin === 'system_suggested',
        isPrimary: true,
        isSynthetic: true,
      });
    }

    for (const node of nodes) {
      const point = layout.points.get(node.id);
      if (!point || point.depth === 0 || node.node_kind !== 'core') continue;
      if (hasRenderedCoreEdge(node.id)) continue;

      const preferredCoreParentId = declaredCoreParentId(node, point);
      const emergencyCoreParent =
        (preferredCoreParentId ? nodeMap.get(preferredCoreParentId) || null : null) ||
        nearestAboveNode(node, point, true);
      if (!emergencyCoreParent) continue;
      if (visibleEdgeExists(emergencyCoreParent.id, node.id)) continue;
      const replacingBrokenEdge = edgeExists(emergencyCoreParent.id, node.id);
      const parentPoint = layout.points.get(emergencyCoreParent.id);
      if (!parentPoint) continue;
      const { start, end } = connectorAnchors(emergencyCoreParent, node, parentPoint, point);
      resolved.push({
        key: `${emergencyCoreParent.id}-${node.id}-emergency-core-${replacingBrokenEdge ? 'repair' : 'missing'}`,
        parentId: emergencyCoreParent.id,
        childId: node.id,
        from: parentPoint,
        to: point,
        start,
        end,
        path: straightConnectorPath(start, end),
        routeMode: 'emergency',
        source: replacingBrokenEdge ? 'emergency_repair_core' : 'emergency_core_continuity',
        isLocked: nodeState(node) === 'locked',
        isVerified:
          nodeState(node) === 'verified' &&
          nodeState(emergencyCoreParent) === 'verified',
        isCore: true,
        isOptional: false,
        isSuggested:
          node.branch_origin === 'system_suggested' ||
          emergencyCoreParent.branch_origin === 'system_suggested',
        isPrimary: true,
        isSynthetic: true,
      });
    }

    // Final guaranteed core backbone pass: ensure every non-root visible core node
    // receives a concrete visible core connector, independent of decorative routing.
    const coreEntries = nodes
      .map((node) => ({ node, point: layout.points.get(node.id) }))
      .filter(
        (entry): entry is { node: SkillNode; point: SkillTreePoint } =>
          !!entry.point && entry.node.node_kind === 'core'
      )
      .sort((a, b) => {
        if (a.point.y !== b.point.y) return a.point.y - b.point.y;
        return a.point.x - b.point.x;
      });

    if (coreEntries.length > 1) {
      const minCoreY = coreEntries[0].point.y;
      const rootCoreIds = new Set(
        coreEntries
          .filter((entry) => Math.abs(entry.point.y - minCoreY) <= 4)
          .map((entry) => entry.node.id)
      );

      const nearestCoreAbove = (childId: number): SkillNode | null => {
        const childPoint = layout.points.get(childId);
        if (!childPoint) return null;
        const candidates = coreEntries
          .filter((entry) => entry.node.id !== childId && entry.point.y < childPoint.y)
          .sort((a, b) => {
            const dyA = childPoint.y - a.point.y;
            const dyB = childPoint.y - b.point.y;
            if (dyA !== dyB) return dyA - dyB;
            return Math.abs(childPoint.x - a.point.x) - Math.abs(childPoint.x - b.point.x);
          });
        return candidates[0]?.node || null;
      };

      for (const entry of coreEntries) {
        const child = entry.node;
        const childPoint = entry.point;
        if (rootCoreIds.has(child.id)) continue;
        if (hasRenderedCoreEdge(child.id)) continue;

        const declaredParentId = declaredCoreParentId(child, childPoint);
        const declaredParent =
          (declaredParentId ? nodeMap.get(declaredParentId) || null : null) ||
          nearestCoreAbove(child.id);
        if (!declaredParent) continue;
        const parentPoint = layout.points.get(declaredParent.id);
        if (!parentPoint) continue;
        if (parentPoint.y >= childPoint.y) continue;

        const repairing = edgeExists(declaredParent.id, child.id);
        if (visibleEdgeExists(declaredParent.id, child.id)) continue;

        const { start, end } = connectorAnchors(declaredParent, child, parentPoint, childPoint);
        resolved.push({
          key: `${declaredParent.id}-${child.id}-core-backbone-${repairing ? 'repair' : 'missing'}`,
          parentId: declaredParent.id,
          childId: child.id,
          from: parentPoint,
          to: childPoint,
          start,
          end,
          path: straightConnectorPath(start, end),
          routeMode: 'emergency',
          source: repairing ? 'core_backbone_repair' : 'core_backbone_guarantee',
          isLocked: nodeState(child) === 'locked',
          isVerified:
            nodeState(child) === 'verified' &&
            nodeState(declaredParent) === 'verified',
          isCore: true,
          isOptional: false,
          isSuggested:
            child.branch_origin === 'system_suggested' ||
            declaredParent.branch_origin === 'system_suggested',
          isPrimary: true,
          isSynthetic: true,
        });
      }
    }

    // Enforce core-chain continuity against the declared/immediate core parent.
    // If the preferred core link is not visibly rendered, force a direct emergency connector.
    for (const node of nodes) {
      const point = layout.points.get(node.id);
      if (!point || point.depth === 0 || node.node_kind !== 'core') continue;

      const preferredCoreParentId = declaredCoreParentId(node, point);
      if (!preferredCoreParentId) continue;
      if (visibleEdgeExists(preferredCoreParentId, node.id)) continue;

      const preferredCoreParent = nodeMap.get(preferredCoreParentId);
      const parentPoint = layout.points.get(preferredCoreParentId);
      if (!preferredCoreParent || !parentPoint) continue;
      if (parentPoint.depth >= point.depth) continue;

      const replacingBrokenEdge = edgeExists(preferredCoreParentId, node.id);
      const { start, end } = connectorAnchors(preferredCoreParent, node, parentPoint, point);
      resolved.push({
        key: `${preferredCoreParentId}-${node.id}-emergency-core-declared-${replacingBrokenEdge ? 'repair' : 'missing'}`,
        parentId: preferredCoreParentId,
        childId: node.id,
        from: parentPoint,
        to: point,
        start,
        end,
        path: straightConnectorPath(start, end),
        routeMode: 'emergency',
        source: replacingBrokenEdge ? 'emergency_repair_declared_core' : 'emergency_declared_core',
        isLocked: nodeState(node) === 'locked',
        isVerified:
          nodeState(node) === 'verified' &&
          nodeState(preferredCoreParent) === 'verified',
        isCore: true,
        isOptional: false,
        isSuggested:
          node.branch_origin === 'system_suggested' ||
          preferredCoreParent.branch_origin === 'system_suggested',
        isPrimary: true,
        isSynthetic: true,
      });
    }

    // Deterministic one-parent vertical repair: if a node has exactly one visible declared
    // parent in the graph and the chain is near-vertical, force a direct connector.
    // This prevents intermittent detached nodes in straightforward core continuations.
    for (const node of nodes) {
      const childPoint = layout.points.get(node.id);
      if (!childPoint || childPoint.depth === 0) continue;

      const declaredVisibleParents = (node.prerequisites || [])
        .map((parentId) => nodeMap.get(parentId))
        .filter((parent): parent is SkillNode => !!parent)
        .map((parent) => ({ parent, point: layout.points.get(parent.id) }))
        .filter(
          (entry): entry is { parent: SkillNode; point: SkillTreePoint } =>
            !!entry.point && entry.point.depth < childPoint.depth && entry.point.y < childPoint.y
        );

      if (declaredVisibleParents.length !== 1) continue;

      const target = declaredVisibleParents[0];
      const xGap = Math.abs(target.point.x - childPoint.x);
      const yGap = childPoint.y - target.point.y;
      const nearVertical = xGap <= 150 && yGap >= MIN_VISIBLE_CONNECTOR_DY;
      if (!nearVertical) continue;
      if (visibleEdgeExists(target.parent.id, node.id)) continue;

      const replacingBrokenEdge = edgeExists(target.parent.id, node.id);
      const { start, end } = connectorAnchors(target.parent, node, target.point, childPoint);
      resolved.push({
        key: `${target.parent.id}-${node.id}-emergency-single-parent-vertical-${replacingBrokenEdge ? 'repair' : 'missing'}`,
        parentId: target.parent.id,
        childId: node.id,
        from: target.point,
        to: childPoint,
        start,
        end,
        path: straightConnectorPath(start, end),
        routeMode: 'emergency',
        source: replacingBrokenEdge
          ? 'emergency_repair_single_parent_vertical'
          : 'emergency_single_parent_vertical',
        isLocked: nodeState(node) === 'locked',
        isVerified:
          nodeState(node) === 'verified' &&
          nodeState(target.parent) === 'verified',
        isCore: target.parent.node_kind === 'core' && node.node_kind === 'core',
        isOptional: !(target.parent.node_kind === 'core' && node.node_kind === 'core'),
        isSuggested:
          node.branch_origin === 'system_suggested' ||
          target.parent.branch_origin === 'system_suggested',
        isPrimary: true,
        isSynthetic: true,
      });
    }

    const unresolved = nodes
      .map((node) => ({ node, point: layout.points.get(node.id) }))
      .filter((entry): entry is { node: SkillNode; point: SkillTreePoint } => !!entry.point && entry.point.depth > 0)
      .filter((entry) => !hasRenderedEdge(entry.node.id));
    const unresolvedCore = nodes
      .map((node) => ({ node, point: layout.points.get(node.id) }))
      .filter((entry): entry is { node: SkillNode; point: SkillTreePoint } => !!entry.point && entry.point.depth > 0)
      .filter((entry) => entry.node.node_kind === 'core' && !hasRenderedCoreEdge(entry.node.id));

    if (unresolved.length > 0 || unresolvedCore.length > 0) {
      const diagnostics = unresolved.map((entry) => {
        const renderedIncoming = resolved
          .filter((edge) => edge.childId === entry.node.id)
          .map((edge) => ({
            parentId: edge.parentId,
            routeMode: edge.routeMode,
            source: edge.source,
            isCore: edge.isCore,
            pathLen: edge.path.length,
            start: edge.start,
            end: edge.end,
          }));
        return {
          nodeId: entry.node.id,
          nodeName: entry.node.name,
          depth: entry.point.depth,
          prereqs: entry.node.prerequisites || [],
          renderedIncoming,
        };
      });
      console.error('skill_tree.connector.invariant_violation', {
        unresolvedNodeCount: unresolved.length,
        unresolvedCoreNodeCount: unresolvedCore.length,
        unresolvedNodes: diagnostics,
        unresolvedCoreNodeIds: unresolvedCore.map((entry) => entry.node.id),
      });
      if (process.env.NODE_ENV !== 'production') {
        throw new Error(
          `Skill tree connector invariant failed for node IDs: ${[
            ...unresolved.map((entry) => entry.node.id),
            ...unresolvedCore.map((entry) => entry.node.id),
          ]
            .join(', ')}`
        );
      }
    }

    return resolved;
  }, [nodes, layout.points, nodeMap]);

  const rootSpineSegments = useMemo(() => {
    const roots = nodes
      .map((node) => ({ node, point: layout.points.get(node.id) }))
      .filter((entry): entry is { node: SkillNode; point: SkillTreePoint } => !!entry.point && entry.point.depth === 0)
      .sort((a, b) => a.point.x - b.point.x);

    if (roots.length <= 1) return [];
    const segments: Array<{ key: string; start: AnchorPoint; end: AnchorPoint }> = [];
    for (let index = 1; index < roots.length; index += 1) {
      segments.push({
        key: `${roots[index - 1].node.id}-${roots[index].node.id}`,
        start: nodeAnchorSet(roots[index - 1].node, roots[index - 1].point).center,
        end: nodeAnchorSet(roots[index].node, roots[index].point).center,
      });
    }
    return segments;
  }, [nodes, layout.points]);

  const revealedNodeSet = useMemo(
    () => new Set(Object.keys(revealedNodeIds).map((value) => Number(value))),
    [revealedNodeIds]
  );

  const edgePaths = useMemo(
    () =>
      edges
        .filter((edge) => edge.path.length > 0 && hasVisibleConnectorGeometry(edge))
        .map((edge) => ({ edge, d: edge.path })),
    [edges]
  );
  const coreEdgePaths = useMemo(
    () => edgePaths.filter((item) => item.edge.isCore),
    [edgePaths]
  );
  const guaranteedCoreBackboneFallbackEdges = useMemo(() => {
    const renderedCoreChildren = new Set(coreEdgePaths.map((item) => item.edge.childId));
    return guaranteedCoreBackboneEdges.filter((edge) => !renderedCoreChildren.has(edge.childId));
  }, [coreEdgePaths, guaranteedCoreBackboneEdges]);
  const decorativeEdgePaths = useMemo(
    () => edgePaths.filter((item) => !item.edge.isCore),
    [edgePaths]
  );
  const branchGhostEdges = useMemo(
    () => decorativeEdgePaths.filter((item) => item.edge.isOptional && item.edge.isPrimary).slice(0, 18),
    [decorativeEdgePaths]
  );

  useEffect(() => {
    const isVisible = (edge: EdgeRender) => {
      return hasVisibleConnectorGeometry(edge);
    };

    const visibleBackboneByChild = new Map<number, number[]>();
    for (const link of guaranteedCoreBackboneFallbackEdges) {
      if (!hasVisibleConnectorGeometry(link)) continue;
      const bucket = visibleBackboneByChild.get(link.childId) || [];
      bucket.push(link.parentId);
      visibleBackboneByChild.set(link.childId, bucket);
    }

    const incomingByChild = new Map<number, number>();
    const incomingCoreByChild = new Map<number, number>();
    for (const item of edgePaths) {
      const edge = item.edge;
      if (!isVisible(edge)) continue;
      const current = incomingByChild.get(edge.childId) || 0;
      incomingByChild.set(edge.childId, current + 1);
      if (edge.isCore) {
        incomingCoreByChild.set(edge.childId, (incomingCoreByChild.get(edge.childId) || 0) + 1);
      }
    }
    for (const [childId, parents] of visibleBackboneByChild.entries()) {
      incomingByChild.set(childId, (incomingByChild.get(childId) || 0) + parents.length);
      incomingCoreByChild.set(childId, (incomingCoreByChild.get(childId) || 0) + parents.length);
    }

    const orphans = nodes
      .map((node) => ({ node, point: layout.points.get(node.id) }))
      .filter((entry) => !!entry.point && entry.point.depth > 0)
      .filter((entry) => !incomingByChild.has(entry.node.id))
      .map((entry) => entry.node.id);
    const detachedCore = nodes
      .map((node) => ({ node, point: layout.points.get(node.id) }))
      .filter((entry) => !!entry.point && entry.point.depth > 0 && entry.node.node_kind === 'core')
      .filter((entry) => !incomingCoreByChild.has(entry.node.id))
      .map((entry) => entry.node.id);
    const droppedPathEdges = edges.filter((edge) => edge.path.length === 0).map((edge) => edge.key);
    const fallbackUsage = edges.filter((edge) => edge.routeMode === 'fallback').map((edge) => edge.key);
    const emergencyUsage = edges.filter((edge) => edge.routeMode === 'emergency').map((edge) => edge.key);
    const weakGeometryUsage = edges.filter((edge) => edge.path.length > 0 && !isVisible(edge)).map((edge) => edge.key);
    const repairedUsage = edges
      .filter(
        (edge) =>
          edge.source === 'emergency_repair_incoming' ||
          edge.source === 'emergency_repair_core' ||
          edge.source === 'emergency_repair_declared_core' ||
          edge.source === 'emergency_repair_single_parent_vertical'
      )
      .map((edge) => edge.key);
    const declaredCoreFallbackUsage = edges
      .filter((edge) => edge.source === 'emergency_declared_core')
      .map((edge) => edge.key);
    const singleParentVerticalFallbackUsage = edges
      .filter((edge) => edge.source === 'emergency_single_parent_vertical')
      .map((edge) => edge.key);
    const backboneUsage = edges
      .filter((edge) => edge.source === 'core_backbone_guarantee' || edge.source === 'core_backbone_repair')
      .map((edge) => edge.key);

    if (
      orphans.length > 0 ||
      detachedCore.length > 0 ||
      droppedPathEdges.length > 0 ||
      fallbackUsage.length > 0 ||
      emergencyUsage.length > 0 ||
      weakGeometryUsage.length > 0 ||
      repairedUsage.length > 0 ||
      declaredCoreFallbackUsage.length > 0 ||
      singleParentVerticalFallbackUsage.length > 0 ||
      backboneUsage.length > 0
    ) {
      const nodeDebugRows =
        process.env.NODE_ENV !== 'production'
          ? nodes.map((node) => {
              const point = layout.points.get(node.id);
              const incoming = edges
                .filter((edge) => edge.childId === node.id)
                .map((edge) => ({
                  parentId: edge.parentId,
                  source: edge.source,
                  routeMode: edge.routeMode,
                  isCore: edge.isCore,
                  visible: isVisible(edge),
                }));
              const incomingBackbone = (visibleBackboneByChild.get(node.id) || []).map((parentId) => ({
                parentId,
                source: 'core_backbone_guarantee',
                routeMode: 'emergency',
                isCore: true,
                visible: true,
              }));
              const incomingAll = [...incoming, ...incomingBackbone];
              const incomingVisible = incomingAll
                .filter((item) => item.visible)
                .map((item) => item.parentId);
              const incomingVisibleCore = incomingAll
                .filter((item) => item.visible && item.isCore)
                .map((item) => item.parentId);
              return {
                nodeId: node.id,
                nodeTitle: node.name,
                isCorePath: node.node_kind === 'core',
                parentIds: node.prerequisites || [],
                coordinates: point ? { x: point.x, y: point.y, depth: point.depth } : null,
                incomingVisibleParentIds: incomingVisible,
                incomingVisibleCoreParentIds: incomingVisibleCore,
                fallbackUsed: incomingAll.some((item) => item.routeMode === 'fallback'),
                emergencyUsed: incomingAll.some((item) => item.routeMode === 'emergency'),
              };
            })
          : undefined;
      console.warn('skill_tree.connector.validation_failed', {
        orphanNodeIds: orphans,
        detachedCoreNodeIds: detachedCore,
        droppedPathEdgeKeys: droppedPathEdges,
        fallbackConnectorEdgeKeys: fallbackUsage,
        emergencyConnectorEdgeKeys: emergencyUsage,
        weakGeometryEdgeKeys: weakGeometryUsage,
        repairedConnectorEdgeKeys: repairedUsage,
        declaredCoreFallbackEdgeKeys: declaredCoreFallbackUsage,
        singleParentVerticalFallbackEdgeKeys: singleParentVerticalFallbackUsage,
        coreBackboneEdgeKeys: backboneUsage,
        nodeDiagnostics: nodeDebugRows,
      });
    }
  }, [edges, edgePaths, nodes, layout.points, guaranteedCoreBackboneFallbackEdges]);

  useEffect(() => {
    if (process.env.NODE_ENV === 'production') return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    const svg = viewport.querySelector('svg');
    if (!svg) return;

    const missing: Array<{ key: string; parentId: number; childId: number }> = [];
    const hidden: Array<{ key: string; stroke: string; strokeWidth: string; opacity: string }> = [];
    const degenerate: Array<{ key: string; length: number }> = [];
    const outOfBounds: Array<{ key: string; bbox: DOMRect }> = [];

    const svgBounds = svg.getBoundingClientRect();

    for (const link of guaranteedCoreBackboneFallbackEdges) {
      const element = svg.querySelector<SVGPathElement>(`[data-core-backbone-key="${link.key}"]`);
      if (!element) {
        missing.push({ key: link.key, parentId: link.parentId, childId: link.childId });
        continue;
      }

      const style = window.getComputedStyle(element);
      const opacity = Number.parseFloat(style.opacity || '1');
      const strokeWidth = Number.parseFloat(style.strokeWidth || '0');
      if (!style.stroke || style.stroke === 'none' || strokeWidth < 0.6 || opacity < 0.05) {
        hidden.push({
          key: link.key,
          stroke: style.stroke || '',
          strokeWidth: style.strokeWidth || '',
          opacity: style.opacity || '',
        });
      }

      let length = 0;
      try {
        length = element.getTotalLength();
      } catch {
        length = Math.hypot(link.end.x - link.start.x, link.end.y - link.start.y);
      }
      if (!Number.isFinite(length) || length < MIN_VISIBLE_CONNECTOR_DISTANCE) {
        degenerate.push({ key: link.key, length });
      }

      try {
        const bbox = element.getBoundingClientRect();
        const outside =
          bbox.right < svgBounds.left ||
          bbox.left > svgBounds.right ||
          bbox.bottom < svgBounds.top ||
          bbox.top > svgBounds.bottom;
        if (outside) {
          outOfBounds.push({ key: link.key, bbox });
        }
      } catch {
        // no-op: keep diagnostics best-effort
      }
    }

    if (missing.length || hidden.length || degenerate.length || outOfBounds.length) {
      console.error('skill_tree.core_backbone.dom_validation_failed', {
        missingCoreConnectorElements: missing,
        hiddenCoreConnectorElements: hidden,
        degenerateCoreConnectorElements: degenerate,
        outOfBoundsCoreConnectorElements: outOfBounds,
        debugMode: treeDebugMode,
        coreOnlyMode,
      });
    }
  }, [guaranteedCoreBackboneFallbackEdges, treeDebugMode, coreOnlyMode, transform.x, transform.y, transform.scale]);

  useEffect(() => {
    setSceneSize({ width: layout.width, height: layout.height });
  }, [layout.width, layout.height]);

  useEffect(() => {
    if (!nodes.length) return;
    if (initializedForNodeCount === nodes.length) return;

    const preferred =
      (selectedNodeId && nodes.find((node) => node.id === selectedNodeId)) ||
      nodes.find((node) => node.status !== 'locked') ||
      nodes[0];
    const point = preferred ? layout.points.get(preferred.id) : null;
    const baseScale = 0.94;
    const targetX = point ? viewportSize.width * 0.44 - point.x * baseScale : 130;
    const targetY = point ? viewportSize.height * 0.4 - point.y * baseScale : 70;
    const clamped = clampPan({
      x: targetX,
      y: targetY,
      scale: baseScale,
      viewportWidth: viewportSize.width,
      viewportHeight: viewportSize.height,
      sceneWidth: layout.width,
      sceneHeight: layout.height,
    });
    setTransform({ x: clamped.x, y: clamped.y, scale: baseScale });
    setInitializedForNodeCount(nodes.length);
  }, [nodes, layout.points, layout.width, layout.height, selectedNodeId, viewportSize, initializedForNodeCount]);

  useEffect(() => {
    if (!selectedNodeId) return;
    const point = layout.points.get(selectedNodeId);
    if (!point) return;

    setTransform((prev) => {
      const currentX = point.x * prev.scale + prev.x;
      const currentY = point.y * prev.scale + prev.y;
      const marginX = 160;
      const marginY = 120;
      let nextX = prev.x;
      let nextY = prev.y;

      if (currentX < marginX) {
        nextX += marginX - currentX;
      } else if (currentX > viewportSize.width - marginX) {
        nextX -= currentX - (viewportSize.width - marginX);
      }

      if (currentY < marginY) {
        nextY += marginY - currentY;
      } else if (currentY > viewportSize.height - marginY) {
        nextY -= currentY - (viewportSize.height - marginY);
      }

      if (nextX === prev.x && nextY === prev.y) return prev;
      const clampedPan = clampPan({
        x: nextX,
        y: nextY,
        scale: prev.scale,
        viewportWidth: viewportSize.width,
        viewportHeight: viewportSize.height,
        sceneWidth: sceneSize.width,
        sceneHeight: sceneSize.height,
      });
      return { ...prev, x: clampedPan.x, y: clampedPan.y };
    });
  }, [selectedNodeId, layout.points, viewportSize.width, viewportSize.height, sceneSize.width, sceneSize.height]);

  function adjustZoom(nextScale: number, anchorX: number, anchorY: number) {
    setTransform((prev) => {
      const clampedScale = clamp(nextScale, MIN_ZOOM, MAX_ZOOM);
      const factor = clampedScale / prev.scale;
      const nextX = anchorX - (anchorX - prev.x) * factor;
      const nextY = anchorY - (anchorY - prev.y) * factor;
      const clampedPan = clampPan({
        x: nextX,
        y: nextY,
        scale: clampedScale,
        viewportWidth: viewportSize.width,
        viewportHeight: viewportSize.height,
        sceneWidth: sceneSize.width,
        sceneHeight: sceneSize.height,
      });
      return { x: clampedPan.x, y: clampedPan.y, scale: clampedScale };
    });
  }

  function onWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const rect = viewportRef.current?.getBoundingClientRect();
    if (!rect) return;
    const anchorX = event.clientX - rect.left;
    const anchorY = event.clientY - rect.top;
    const zoomFactor = event.deltaY < 0 ? 1.08 : 0.92;
    adjustZoom(transform.scale * zoomFactor, anchorX, anchorY);
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement;
    if (target.closest('[data-skill-node="true"]')) return;

    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: transform.x,
      originY: transform.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) return;
    const dx = event.clientX - dragRef.current.startX;
    const dy = event.clientY - dragRef.current.startY;
    const nextX = dragRef.current.originX + dx;
    const nextY = dragRef.current.originY + dy;
    const clampedPan = clampPan({
      x: nextX,
      y: nextY,
      scale: transform.scale,
      viewportWidth: viewportSize.width,
      viewportHeight: viewportSize.height,
      sceneWidth: sceneSize.width,
      sceneHeight: sceneSize.height,
    });
    setTransform((prev) => ({ ...prev, x: clampedPan.x, y: clampedPan.y }));
  }

  function onPointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragRef.current && dragRef.current.pointerId === event.pointerId) {
      dragRef.current = null;
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function resetView() {
    setInitializedForNodeCount(null);
  }

  const zoomPct = Math.round(transform.scale * 100);

  return (
    <div className="relative overflow-hidden rounded-3xl border border-black/10 bg-[radial-gradient(circle_at_16%_10%,rgba(125,211,252,0.2),transparent_40%),radial-gradient(circle_at_82%_20%,rgba(110,231,183,0.14),transparent_38%),linear-gradient(165deg,rgba(255,255,255,0.94),rgba(245,252,243,0.9))]">
      <div className="absolute right-3 top-3 z-20 flex items-center gap-1.5 rounded-full border border-black/10 bg-white/90 px-2 py-1 shadow-sm backdrop-blur">
        <button
          type="button"
          className="rounded-md border border-black/10 bg-white px-2 py-1 text-xs hover:bg-black/[0.03]"
          onClick={() => adjustZoom(transform.scale * 1.12, viewportSize.width * 0.5, viewportSize.height * 0.5)}
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          className="rounded-md border border-black/10 bg-white px-2 py-1 text-xs hover:bg-black/[0.03]"
          onClick={() => adjustZoom(transform.scale * 0.88, viewportSize.width * 0.5, viewportSize.height * 0.5)}
          aria-label="Zoom out"
        >
          -
        </button>
        <span className="text-[11px] font-medium text-black/65">{zoomPct}%</span>
        <button
          type="button"
          className="rounded-md border border-black/10 bg-white px-2 py-1 text-xs hover:bg-black/[0.03]"
          onClick={resetView}
        >
          Reset
        </button>
        {process.env.NODE_ENV !== 'production' && treeDebugMode && (
          <span className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[10px] font-semibold text-rose-700">
            DEBUG
          </span>
        )}
        {process.env.NODE_ENV !== 'production' && coreOnlyMode && (
          <span className="rounded-md border border-sky-200 bg-sky-50 px-2 py-1 text-[10px] font-semibold text-sky-700">
            CORE-ONLY
          </span>
        )}
      </div>

      <div
        ref={viewportRef}
        className="relative h-[600px] w-full touch-none overflow-hidden md:h-[640px] xl:h-[680px]"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <div
          className="absolute left-0 top-0"
          style={{
            width: `${sceneSize.width}px`,
            height: `${sceneSize.height}px`,
            transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
            transformOrigin: '0 0',
            willChange: 'transform',
          }}
        >
          <svg width={layout.width} height={layout.height} className="absolute left-0 top-0">
            <defs>
              <linearGradient id="skillTreeTrunk" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="rgba(15,23,42,0.2)" />
                <stop offset="100%" stopColor="rgba(15,23,42,0.38)" />
              </linearGradient>
              <linearGradient id="skillTreeBranchGhost" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="rgba(59,130,246,0.08)" />
                <stop offset="100%" stopColor="rgba(168,85,247,0.08)" />
              </linearGradient>
              <linearGradient id="skillPathReady" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(56,189,248,0.24)" />
                <stop offset="100%" stopColor="rgba(14,116,144,0.62)" />
              </linearGradient>
              <linearGradient id="skillPathVerified" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(16,185,129,0.34)" />
                <stop offset="100%" stopColor="rgba(5,150,105,0.78)" />
              </linearGradient>
              <linearGradient id="skillPathOptional" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(168,85,247,0.26)" />
                <stop offset="100%" stopColor="rgba(124,58,237,0.62)" />
              </linearGradient>
              <linearGradient id="skillPathSynthetic" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(45,212,191,0.18)" />
                <stop offset="100%" stopColor="rgba(13,148,136,0.5)" />
              </linearGradient>
            </defs>

            {!coreOnlyMode &&
              rootSpineSegments.map((segment) => {
                const d = preferredCoreConnectorPath(segment.start, segment.end);
                return (
                  <path
                    key={`root-spine-${segment.key}`}
                    d={d}
                    className="fill-none stroke-[6] opacity-55"
                    style={{ stroke: CORE_CONNECTOR_COLOR }}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                );
              })}

            {guaranteedCoreBackboneFallbackEdges.map((edge) => (
              <g key={`core-backbone-${edge.key}`}>
                <path
                  data-core-backbone-key={edge.key}
                  d={edge.path}
                  className={`fill-none ${treeDebugMode ? `stroke-rose-700 ${CORE_CONNECTOR_DEBUG_STROKE}` : CORE_CONNECTOR_STROKE}`}
                  style={treeDebugMode ? undefined : { stroke: CORE_CONNECTOR_COLOR }}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {!treeDebugMode && (
                  <path
                    d={edge.path}
                    className="skill-tree-link-glow fill-none stroke-[1.15]"
                    style={{ stroke: CORE_CONNECTOR_GLOW_COLOR }}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}
              </g>
            ))}

            {coreEdgePaths.map(({ edge, d }) => {
              const edgeRevealed = edge.isPrimary && revealedNodeSet.has(edge.childId);
              return (
                <g key={`core-${edge.key}`}>
                  <path
                    data-core-edge-key={edge.key}
                    d={d}
                    pathLength={edgeRevealed ? 1 : undefined}
                    className={`fill-none ${treeDebugMode ? `stroke-rose-700 ${CORE_CONNECTOR_DEBUG_STROKE}` : CORE_CONNECTOR_STROKE} ${
                      edgeRevealed ? 'skill-tree-edge-reveal' : ''
                    }`}
                    style={treeDebugMode ? undefined : { stroke: CORE_CONNECTOR_COLOR }}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  {!treeDebugMode && (
                    <path
                      d={d}
                      className="skill-tree-link-glow fill-none stroke-[1.15]"
                      style={{ stroke: CORE_CONNECTOR_GLOW_COLOR }}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  )}
                </g>
              );
            })}

            {!coreOnlyMode &&
              branchGhostEdges.map(({ edge, d }) => {
                return (
                  <path
                    key={`ghost-${edge.key}`}
                    d={d}
                    className="fill-none stroke-[1.15]"
                    style={{ stroke: 'url(#skillTreeBranchGhost)' }}
                  />
                );
              })}

            {!coreOnlyMode &&
              decorativeEdgePaths.map(({ edge, d }) => {
              const edgeRevealed = edge.isPrimary && revealedNodeSet.has(edge.childId);
              return (
                <g key={edge.key}>
                  <path
                    d={d}
                    pathLength={edgeRevealed ? 1 : undefined}
                    className={`fill-none ${
                      edge.isLocked
                        ? 'stroke-black/16 stroke-[1.3] [stroke-dasharray:5_6]'
                        : edge.isCore
                          ? edge.isPrimary
                            ? 'stroke-[2.75]'
                            : 'stroke-[1.4] opacity-45'
                          : edge.isPrimary
                            ? 'stroke-[2.15]'
                            : 'stroke-[1.2] opacity-42'
                    } ${edgeRevealed ? 'skill-tree-edge-reveal' : ''}`}
                    style={
                      edge.isLocked
                        ? undefined
                        : {
                            stroke: edge.isSynthetic
                              ? 'url(#skillPathSynthetic)'
                              : edge.isVerified
                              ? 'url(#skillPathVerified)'
                              : edge.isOptional
                                ? 'url(#skillPathOptional)'
                                : 'url(#skillPathReady)',
                          }
                    }
                  />

                  {!edge.isLocked && edge.isPrimary && (
                    <path
                      d={d}
                      className={`skill-tree-link-glow fill-none ${
                        edge.isVerified
                          ? 'stroke-emerald-500/30 stroke-[1.2]'
                          : edge.isOptional
                            ? edge.isSuggested
                              ? 'stroke-fuchsia-500/24 stroke-[1.05]'
                              : 'stroke-violet-500/22 stroke-[1.02]'
                            : 'stroke-sky-500/22 stroke-[1.05]'
                      }`}
                    />
                  )}
                </g>
              );
            })}

            {treeDebugMode &&
              [...guaranteedCoreBackboneFallbackEdges, ...coreEdgePaths.map((item) => ({
                key: item.edge.key,
                parentId: item.edge.parentId,
                childId: item.edge.childId,
                start: item.edge.start,
                end: item.edge.end,
                path: item.edge.path,
              }))].map((edge) => (
                <g key={`core-debug-${edge.key}`}>
                  <circle cx={edge.start.x} cy={edge.start.y} r={4} className="fill-rose-600" />
                  <circle cx={edge.end.x} cy={edge.end.y} r={4} className="fill-sky-600" />
                  <text
                    x={(edge.start.x + edge.end.x) / 2 + 8}
                    y={(edge.start.y + edge.end.y) / 2 - 6}
                    className="fill-black text-[10px] font-semibold"
                  >
                    {edge.parentId}→{edge.childId}
                  </text>
                </g>
              ))}
          </svg>

          {nodes.map((node) => {
            const point = layout.points.get(node.id);
            if (!point) return null;

            const state = nodeState(node);
            const tone = tones[state];
            const selected = selectedNodeId === node.id;
            const milestone = node.progress_state === 'verified' || node.status === 'mastered';
            const isOptional = node.node_kind === 'optional_branch';
            const isSuggested = isOptional && node.branch_origin === 'system_suggested';
            const size = milestone ? 56 : 48;
            const branchTag = isOptional ? (isSuggested ? 'Suggested' : 'Optional') : 'Core';
            const revealNode = revealedNodeSet.has(node.id);

            return (
              <button
                key={node.id}
                type="button"
                data-skill-node="true"
                onClick={() => onSelectNode(node.id)}
                className="group absolute text-left focus:outline-none"
                style={{
                  left: `${point.x}px`,
                  top: `${point.y}px`,
                  width: '156px',
                  transform: `translate(-50%, -${Math.round(size / 2)}px)`,
                }}
                aria-label={`${node.name}, ${tone.status}, difficulty ${node.difficulty}`}
              >
                <div className="mx-auto flex flex-col items-center">
                  <span
                    className={`relative inline-flex items-center justify-center rounded-full border ${tone.shell} transition duration-200 ${
                      selected ? 'scale-[1.1] shadow-[0_0_0_3px_rgba(56,189,248,0.2)]' : 'group-hover:scale-105'
                    } ${revealNode ? 'skill-tree-node-reveal' : ''}`}
                    style={{
                      width: `${size}px`,
                      height: `${size}px`,
                    }}
                  >
                    <span className={`absolute inset-[4px] rounded-full border ${tone.core}`} />
                    <span className={`relative z-[1] text-sm font-semibold ${tone.text}`}>{milestone ? 'M' : node.difficulty}</span>
                    {selected && <span className={`skill-tree-node-pulse absolute inset-[-8px] rounded-full ${tone.ring}`} />}
                  </span>

                  <span
                    className={`mt-2 max-w-[156px] rounded-md border px-2.5 py-1 text-center text-[11px] font-medium leading-tight ${
                      selected
                        ? 'border-sky-300 bg-sky-50 text-sky-800'
                        : isSuggested
                          ? 'border-fuchsia-200 bg-fuchsia-50 text-fuchsia-700'
                          : isOptional
                            ? 'border-violet-200 bg-violet-50 text-violet-700'
                            : tone.label
                    }`}
                    title={node.name}
                  >
                    {truncateTitle(node.name)}
                  </span>

                  <span className="mt-1 text-[10px] uppercase tracking-[0.14em] text-black/45">
                    {tone.status} · {branchTag}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
