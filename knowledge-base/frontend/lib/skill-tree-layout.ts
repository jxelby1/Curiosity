import { SkillNode } from '@/lib/types';

export type SkillTreePoint = {
  x: number;
  y: number;
  depth: number;
  isOptional: boolean;
  rank: number;
};

type BuildOptions = {
  width: number;
  height: number;
  paddingX?: number;
  paddingY?: number;
};

export type SkillTreeAnchorEdge = {
  parentId: number;
  childId: number;
  synthetic: boolean;
};

const NODE_VERTICAL_FOOTPRINT = 116;
const MIN_VERTICAL_GAP = 152;
const MIN_HORIZONTAL_GAP = 188;
const NODE_LABEL_WIDTH = 148;

const CORE_SIBLING_GAP = 132;
const CORE_PARENT_PULL = 0.6;
const CORE_LANE_PULL = 0.4;
const OPTIONAL_ROOT_OFFSET = 146;
const OPTIONAL_ROOT_SIBLING_GAP = 76;
const OPTIONAL_CHAIN_DRIFT = 34;
const OPTIONAL_CHAIN_SIBLING_GAP = 42;
const MAX_VISUAL_PARENT_ANCHORS = 2;
const LEAF_PARENT_PULL = 0.26;
const BEAUTY_SHIFT_RATIO = 0.32;

function uniquePrerequisites(node: SkillNode, knownNodeIds: Set<number>): number[] {
  const deduped: number[] = [];
  for (const parentId of node.prerequisites || []) {
    if (
      parentId === node.id ||
      !knownNodeIds.has(parentId) ||
      deduped.includes(parentId)
    ) {
      continue;
    }
    deduped.push(parentId);
    if (deduped.length >= MAX_VISUAL_PARENT_ANCHORS) break;
  }
  return deduped;
}

function buildParentMap(
  nodes: SkillNode[],
  depthByNode: Map<number, number>
): Map<number, number[]> {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const map = new Map<number, number[]>();

  for (const node of nodes) {
    const ranked = uniquePrerequisites(node, nodeIds).sort((a, b) => {
      const depthA = depthByNode.get(a) ?? -1;
      const depthB = depthByNode.get(b) ?? -1;
      if (depthA !== depthB) return depthB - depthA;
      return a - b;
    });
    map.set(node.id, ranked.slice(0, MAX_VISUAL_PARENT_ANCHORS));
  }

  return map;
}

function buildChildMap(parentMap: Map<number, number[]>): Map<number, number[]> {
  const childMap = new Map<number, number[]>();
  for (const [childId, parentIds] of parentMap.entries()) {
    for (const parentId of parentIds) {
      const bucket = childMap.get(parentId) || [];
      bucket.push(childId);
      childMap.set(parentId, bucket);
    }
  }
  return childMap;
}

function computeSubtreeWeights(childMap: Map<number, number[]>): Map<number, number> {
  const memo = new Map<number, number>();

  function visit(nodeId: number, stack: Set<number>): number {
    if (memo.has(nodeId)) return memo.get(nodeId)!;
    if (stack.has(nodeId)) return 1;
    stack.add(nodeId);
    const children = childMap.get(nodeId) || [];
    const aggregate = children.reduce((sum, childId) => sum + visit(childId, stack) * 0.72, 1);
    stack.delete(nodeId);
    const weight = Math.max(1, Math.min(7.2, aggregate));
    memo.set(nodeId, weight);
    return weight;
  }

  for (const nodeId of childMap.keys()) {
    visit(nodeId, new Set());
  }

  return memo;
}

function coreLaneCenters(
  coreNodes: SkillNode[],
  coreTierCenter: number,
  subtreeWeightByNode: Map<number, number>
): Map<number, number> {
  if (!coreNodes.length) return new Map();
  const widths = coreNodes.map((node) =>
    Math.max(104, Math.min(212, 88 + (subtreeWeightByNode.get(node.id) || 1) * 34))
  );
  const totalWidth = widths.reduce((sum, width) => sum + width, 0);
  let cursor = -totalWidth / 2;
  const result = new Map<number, number>();
  coreNodes.forEach((node, index) => {
    const laneCenter = coreTierCenter + cursor + widths[index] / 2;
    result.set(node.id, laneCenter);
    cursor += widths[index];
  });
  return result;
}

function computeDepths(nodes: SkillNode[]): Map<number, number> {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const depthByNode = new Map<number, number>();
  const pending = new Set(nodes.map((node) => node.id));

  for (let i = 0; i < nodes.length + 4 && pending.size > 0; i += 1) {
    for (const id of Array.from(pending)) {
      const node = nodeMap.get(id);
      if (!node) {
        pending.delete(id);
        continue;
      }

      const prereqs = uniquePrerequisites(node, new Set(nodeMap.keys()));
      if (prereqs.length === 0) {
        depthByNode.set(id, 0);
        pending.delete(id);
        continue;
      }

      const known = prereqs.filter((parentId) => depthByNode.has(parentId));
      if (known.length === prereqs.length) {
        const parentDepth = Math.max(...known.map((parentId) => depthByNode.get(parentId) || 0));
        depthByNode.set(id, parentDepth + 1);
        pending.delete(id);
      }
    }
  }

  for (const id of pending) {
    depthByNode.set(id, 1);
  }
  return depthByNode;
}

function resolveTierCollisions(
  positions: Array<{ id: number; x: number }>,
  bounds: {
    minGap: number;
    minX: number;
    maxX: number;
  }
): Array<{ id: number; x: number }> {
  const { minGap, minX, maxX } = bounds;
  if (positions.length <= 1) return positions;

  const sorted = [...positions].sort((a, b) => a.x - b.x);
  sorted[0].x = Math.max(minX, sorted[0].x);
  for (let idx = 1; idx < sorted.length; idx += 1) {
    const prev = sorted[idx - 1];
    sorted[idx].x = Math.max(sorted[idx].x, prev.x + minGap);
  }

  const rightOverflow = sorted[sorted.length - 1].x - maxX;
  if (rightOverflow > 0) {
    for (const item of sorted) {
      item.x -= rightOverflow;
    }
  }

  const leftOverflow = minX - sorted[0].x;
  if (leftOverflow > 0) {
    for (const item of sorted) {
      item.x += leftOverflow;
    }
  }

  for (let idx = sorted.length - 2; idx >= 0; idx -= 1) {
    const next = sorted[idx + 1];
    sorted[idx].x = Math.min(sorted[idx].x, next.x - minGap);
  }

  return sorted;
}

function rebalanceTierAroundCenter(
  positions: Array<{ id: number; x: number }>,
  bounds: {
    centerX: number;
    minGap: number;
    minX: number;
    maxX: number;
  }
): Array<{ id: number; x: number }> {
  const { centerX, minGap, minX, maxX } = bounds;
  if (positions.length <= 1) return positions;
  const centroid = positions.reduce((sum, item) => sum + item.x, 0) / positions.length;
  const shift = Math.round((centerX - centroid) * 0.68);
  if (Math.abs(shift) < 2) {
    return positions;
  }
  return resolveTierCollisions(
    positions.map((item) => ({ ...item, x: item.x + shift })),
    { minGap, minX, maxX }
  );
}

function orderTierNodes(
  depth: number,
  items: SkillNode[],
  context: {
    xByNodeId: Map<number, number>;
    parentMap: Map<number, number[]>;
  }
): SkillNode[] {
  const { xByNodeId, parentMap } = context;
  if (depth === 0) {
    return [...items].sort((a, b) => {
      if (a.node_kind !== b.node_kind) return a.node_kind === 'core' ? -1 : 1;
      if (a.difficulty !== b.difficulty) return a.difficulty - b.difficulty;
      return a.id - b.id;
    });
  }

  return [...items].sort((a, b) => {
    const parentsA = (parentMap.get(a.id) || []).slice(0, MAX_VISUAL_PARENT_ANCHORS);
    const parentsB = (parentMap.get(b.id) || []).slice(0, MAX_VISUAL_PARENT_ANCHORS);
    const barycenterA =
      parentsA.length > 0
        ? parentsA.reduce((sum, parentId) => sum + (xByNodeId.get(parentId) ?? 0), 0) / parentsA.length
        : Number.POSITIVE_INFINITY;
    const barycenterB =
      parentsB.length > 0
        ? parentsB.reduce((sum, parentId) => sum + (xByNodeId.get(parentId) ?? 0), 0) / parentsB.length
        : Number.POSITIVE_INFINITY;
    if (barycenterA !== barycenterB) return barycenterA - barycenterB;
    if (a.node_kind !== b.node_kind) return a.node_kind === 'core' ? -1 : 1;
    if (a.difficulty !== b.difficulty) return a.difficulty - b.difficulty;
    return a.id - b.id;
  });
}

function runLayoutBeautyPass(
  tiers: Map<number, SkillNode[]>,
  points: Map<number, SkillTreePoint>,
  parentMap: Map<number, number[]>,
  childMap: Map<number, number[]>,
  bounds: {
    centerX: number;
    minGap: number;
    minX: number;
    maxX: number;
  },
  maxDepth: number
) {
  for (let depth = 1; depth <= maxDepth; depth += 1) {
    const tierNodes = tiers.get(depth) || [];
    if (tierNodes.length <= 1) continue;

    const desired = tierNodes
      .map((node) => {
        const point = points.get(node.id);
        if (!point) return null;

        const parentIds = parentMap.get(node.id) || [];
        const childIds = childMap.get(node.id) || [];
        const parentXs = parentIds
          .map((parentId) => points.get(parentId)?.x)
          .filter((value): value is number => typeof value === 'number');
        const childXs = childIds
          .map((childId) => points.get(childId)?.x)
          .filter((value): value is number => typeof value === 'number');

        let targetX = point.x;
        if (parentXs.length > 0) {
          const parentCenter =
            parentXs.reduce((sum, value) => sum + value, 0) / parentXs.length;
          targetX = targetX * (1 - BEAUTY_SHIFT_RATIO) + parentCenter * BEAUTY_SHIFT_RATIO;
          if (childXs.length === 0) {
            targetX = targetX * (1 - LEAF_PARENT_PULL) + parentCenter * LEAF_PARENT_PULL;
          }
        }
        if (childXs.length > 0) {
          const childCenter =
            childXs.reduce((sum, value) => sum + value, 0) / childXs.length;
          targetX = targetX * 0.84 + childCenter * 0.16;
        }

        return { id: node.id, x: targetX };
      })
      .filter((item): item is { id: number; x: number } => !!item);

    const resolved = resolveTierCollisions(
      desired.map((item) => ({ id: item.id, x: Math.round(item.x) })),
      { minGap: bounds.minGap, minX: bounds.minX, maxX: bounds.maxX }
    );
    const centered = rebalanceTierAroundCenter(resolved, bounds);

    for (const item of centered) {
      const point = points.get(item.id);
      if (!point) continue;
      points.set(item.id, { ...point, x: item.x });
    }
  }
}

export function buildSkillTreeLayout(
  nodes: SkillNode[],
  options: BuildOptions
): {
  points: Map<number, SkillTreePoint>;
  width: number;
  height: number;
  maxDepth: number;
} {
  const requestedWidth = Math.max(760, Math.floor(options.width));
  const requestedHeight = Math.max(520, Math.floor(options.height));
  const paddingX = options.paddingX ?? 88;
  const paddingY = options.paddingY ?? 74;

  if (!nodes.length) {
    return { points: new Map(), width: requestedWidth, height: requestedHeight, maxDepth: 0 };
  }

  const depthByNode = computeDepths(nodes);
  const parentMap = buildParentMap(nodes, depthByNode);
  const childMap = buildChildMap(parentMap);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const subtreeWeightByNode = computeSubtreeWeights(childMap);
  const maxDepth = Math.max(...Array.from(depthByNode.values()));
  const tiers = new Map<number, SkillNode[]>();

  for (const node of nodes) {
    const depth = depthByNode.get(node.id) || 0;
    const arr = tiers.get(depth) || [];
    arr.push(node);
    tiers.set(depth, arr);
  }

  const maxCoreCount = Math.max(
    ...Array.from(tiers.values()).map((items) => items.filter((item) => item.node_kind === 'core').length),
    1
  );
  const maxOptionalCount = Math.max(
    ...Array.from(tiers.values()).map((items) => items.filter((item) => item.node_kind === 'optional_branch').length),
    1
  );
  const maxBranchDepth = Math.max(...nodes.map((node) => node.branch_depth || 0), 0);

  const coreHalfSpread = ((maxCoreCount - 1) * CORE_SIBLING_GAP) / 2;
  const optionalHalfSpread =
    OPTIONAL_ROOT_OFFSET +
    Math.max(0, maxBranchDepth - 1) * OPTIONAL_CHAIN_DRIFT +
    Math.max(0, maxOptionalCount - 1) * OPTIONAL_ROOT_SIBLING_GAP;

  const computedWidth = Math.ceil(
    paddingX * 2 + NODE_LABEL_WIDTH + Math.max(560, coreHalfSpread * 2 + optionalHalfSpread * 2 + 220)
  );
  const computedHeight = Math.max(
    560,
    requestedHeight,
    paddingY * 2 + NODE_VERTICAL_FOOTPRINT + maxDepth * MIN_VERTICAL_GAP + 120
  );

  const width = Math.max(requestedWidth, computedWidth);
  const height = computedHeight;
  const centerX = Math.round(width / 2);
  const minX = paddingX + NODE_LABEL_WIDTH / 2;
  const maxX = width - paddingX - NODE_LABEL_WIDTH / 2;
  const minY = paddingY + NODE_VERTICAL_FOOTPRINT / 2;
  const maxY = height - paddingY - NODE_VERTICAL_FOOTPRINT / 2;
  const depthGap = maxDepth === 0 ? 0 : Math.max(MIN_VERTICAL_GAP, (maxY - minY) / maxDepth);

  const points = new Map<number, SkillTreePoint>();
  const xByNodeId = new Map<number, number>();
  const optionalDirectionByNode = new Map<number, -1 | 1>();
  const rootBranchLanesByParent = new Map<number, { left: number; right: number }>();
  const chainLaneByParent = new Map<number, number>();
  const globalOptionalSideCount = { left: 0, right: 0 };

  for (let depth = 0; depth <= maxDepth; depth += 1) {
    const items = tiers.get(depth) || [];
    if (!items.length) continue;

    const ordered = orderTierNodes(depth, items, { xByNodeId, parentMap });
    tiers.set(depth, ordered);

    const coreNodes = ordered.filter((item) => item.node_kind === 'core');
    const optionalNodes = ordered.filter((item) => item.node_kind === 'optional_branch');
    const provisional: Array<{ id: number; x: number }> = [];

    const coreParentBarycenters = coreNodes.map((node) => {
      const parentIds = (parentMap.get(node.id) || []).slice(0, MAX_VISUAL_PARENT_ANCHORS);
      const parentXs = parentIds.map((parentId) => xByNodeId.get(parentId)).filter((value): value is number => typeof value === 'number');
      const hasParents = parentXs.length > 0;
      return hasParents
        ? parentXs.reduce((sum, value) => sum + value, 0) / parentXs.length
        : centerX;
    });
    const coreTierCenter =
      depth === 0 || coreParentBarycenters.length === 0
        ? centerX
        : coreParentBarycenters.reduce((sum, value) => sum + value, 0) / coreParentBarycenters.length;
    const coreLaneById = coreLaneCenters(coreNodes, coreTierCenter, subtreeWeightByNode);

    coreNodes.forEach((node, index) => {
      const parentBarycenter = coreParentBarycenters[index] ?? centerX;
      const hasParents = (parentMap.get(node.id) || []).length > 0;
      const symmetricLaneX =
        coreLaneById.get(node.id) ??
        coreTierCenter + (index - (coreNodes.length - 1) / 2) * CORE_SIBLING_GAP;
      const laneX =
        depth === 0 || !hasParents
          ? symmetricLaneX
          : parentBarycenter * CORE_PARENT_PULL + symmetricLaneX * CORE_LANE_PULL;
      const x = Math.round(laneX);
      provisional.push({ id: node.id, x });
    });

    for (const node of optionalNodes) {
      const parentIds = parentMap.get(node.id) || [];
      const optionalParentId = parentIds.find((parentId) => {
        const parentNode = nodeById.get(parentId);
        return parentNode?.node_kind === 'optional_branch' && xByNodeId.has(parentId);
      });

      if (optionalParentId) {
        const parentX = xByNodeId.get(optionalParentId) ?? centerX;
        const inheritedDirection = optionalDirectionByNode.get(optionalParentId) ?? (parentX >= centerX ? 1 : -1);
        optionalDirectionByNode.set(node.id, inheritedDirection);
        const chainLane = chainLaneByParent.get(optionalParentId) || 0;
        chainLaneByParent.set(optionalParentId, chainLane + 1);
        const lateralFan =
          chainLane === 0
            ? 0
            : (chainLane % 2 === 0 ? 1 : -1) * Math.ceil(chainLane / 2) * OPTIONAL_CHAIN_SIBLING_GAP;
        provisional.push({
          id: node.id,
          x: parentX + inheritedDirection * OPTIONAL_CHAIN_DRIFT + lateralFan,
        });
        continue;
      }

      const anchorParentId = node.branch_parent_skill_id || parentIds[0] || -1;
      const anchorX = anchorParentId > 0 ? xByNodeId.get(anchorParentId) ?? centerX : centerX;
      const laneState = rootBranchLanesByParent.get(anchorParentId) || { left: 0, right: 0 };

      let direction: -1 | 1 = anchorX >= centerX ? 1 : -1;
      if (Math.abs(anchorX - centerX) < 140) {
        direction = globalOptionalSideCount.left <= globalOptionalSideCount.right ? -1 : 1;
      } else {
        const localImbalance = Math.abs(laneState.left - laneState.right);
        if (localImbalance >= 2) {
          direction = laneState.left > laneState.right ? 1 : -1;
        }
      }

      if (direction === -1) {
        laneState.left += 1;
        globalOptionalSideCount.left += 1;
      } else {
        laneState.right += 1;
        globalOptionalSideCount.right += 1;
      }
      rootBranchLanesByParent.set(anchorParentId, laneState);
      optionalDirectionByNode.set(node.id, direction);

      const lane = direction === -1 ? laneState.left - 1 : laneState.right - 1;
      const branchDepth = Math.max(1, node.branch_depth || 1);
      const depthSpread = Math.max(0, branchDepth - 1) * OPTIONAL_CHAIN_DRIFT * 0.28;
      const offset = OPTIONAL_ROOT_OFFSET + lane * OPTIONAL_ROOT_SIBLING_GAP + depthSpread;
      provisional.push({ id: node.id, x: anchorX + direction * offset });
    }

    const resolved = resolveTierCollisions(provisional, {
      minGap: MIN_HORIZONTAL_GAP,
      minX,
      maxX,
    });
    const balanced = rebalanceTierAroundCenter(resolved, {
      centerX,
      minGap: MIN_HORIZONTAL_GAP,
      minX,
      maxX,
    });
    const resolvedById = new Map(balanced.map((item) => [item.id, item.x]));

    const y = Math.round(minY + depth * depthGap);
    for (let rank = 0; rank < ordered.length; rank += 1) {
      const node = ordered[rank];
      const x = Math.round(Math.max(minX, Math.min(maxX, resolvedById.get(node.id) ?? centerX)));
      const clampedY = Math.round(Math.max(minY, Math.min(maxY, y)));
      points.set(node.id, {
        x,
        y: clampedY,
        depth,
        isOptional: node.node_kind === 'optional_branch',
        rank,
      });
      xByNodeId.set(node.id, x);
    }
  }

  runLayoutBeautyPass(
    tiers,
    points,
    parentMap,
    childMap,
    { centerX, minGap: MIN_HORIZONTAL_GAP, minX, maxX },
    maxDepth
  );

  return {
    points,
    width,
    height,
    maxDepth,
  };
}

function fallbackAnchorParentId(
  child: SkillNode,
  nodes: SkillNode[],
  points: Map<number, SkillTreePoint>,
  options?: {
    requiredDepth?: number;
  }
): number | null {
  const childPoint = points.get(child.id);
  if (!childPoint) return null;
  const requiredDepth =
    typeof options?.requiredDepth === 'number' ? options.requiredDepth : null;

  const sameTierBias = child.node_kind === 'core' ? 'core' : 'optional_branch';

  let candidates = nodes.filter((node) => {
    if (node.id === child.id) return false;
    const point = points.get(node.id);
    if (!point) return false;
    if (requiredDepth != null) return point.depth === requiredDepth;
    return point.depth === childPoint.depth - 1;
  });

  if (!candidates.length) {
    candidates = nodes.filter((node) => {
      if (node.id === child.id) return false;
      const point = points.get(node.id);
      if (!point) return false;
      return point.depth < childPoint.depth;
    });
  }

  if (!candidates.length) return null;

  candidates.sort((a, b) => {
    const pointA = points.get(a.id)!;
    const pointB = points.get(b.id)!;
    const depthA = childPoint.depth - pointA.depth;
    const depthB = childPoint.depth - pointB.depth;
    if (depthA !== depthB) return depthA - depthB;

    const sameKindA = a.node_kind === sameTierBias ? 0 : 1;
    const sameKindB = b.node_kind === sameTierBias ? 0 : 1;
    if (sameKindA !== sameKindB) return sameKindA - sameKindB;

    const dxA = Math.abs(pointA.x - childPoint.x);
    const dxB = Math.abs(pointB.x - childPoint.x);
    if (dxA !== dxB) return dxA - dxB;
    return a.id - b.id;
  });

  return candidates[0]?.id ?? null;
}

function nearestVisualParentId(
  child: SkillNode,
  nodes: SkillNode[],
  points: Map<number, SkillTreePoint>
): number | null {
  const childPoint = points.get(child.id);
  if (!childPoint) return null;

  const candidates = nodes
    .filter((node) => {
      if (node.id === child.id) return false;
      const point = points.get(node.id);
      if (!point) return false;
      return point.y < childPoint.y;
    })
    .sort((a, b) => {
      const pointA = points.get(a.id)!;
      const pointB = points.get(b.id)!;
      const yGapA = Math.abs(childPoint.y - pointA.y);
      const yGapB = Math.abs(childPoint.y - pointB.y);
      const xGapA = Math.abs(childPoint.x - pointA.x);
      const xGapB = Math.abs(childPoint.x - pointB.x);

      const kindMismatchA = a.node_kind === child.node_kind ? 0 : 1;
      const kindMismatchB = b.node_kind === child.node_kind ? 0 : 1;
      if (kindMismatchA !== kindMismatchB) return kindMismatchA - kindMismatchB;
      if (yGapA !== yGapB) return yGapA - yGapB;
      if (xGapA !== xGapB) return xGapA - xGapB;
      return a.id - b.id;
    });

  return candidates[0]?.id ?? null;
}

function nearestTierParentByX(
  child: SkillNode,
  nodes: SkillNode[],
  points: Map<number, SkillTreePoint>,
  requiredDepth: number,
  preferredKind?: SkillNode['node_kind']
): number | null {
  const childPoint = points.get(child.id);
  if (!childPoint) return null;

  const tierCandidates = nodes.filter((node) => {
    if (node.id === child.id) return false;
    const point = points.get(node.id);
    if (!point) return false;
    return point.depth === requiredDepth;
  });
  if (!tierCandidates.length) return null;

  const filtered =
    preferredKind && tierCandidates.some((node) => node.node_kind === preferredKind)
      ? tierCandidates.filter((node) => node.node_kind === preferredKind)
      : tierCandidates;

  filtered.sort((a, b) => {
    const pointA = points.get(a.id)!;
    const pointB = points.get(b.id)!;
    const xGapA = Math.abs(childPoint.x - pointA.x);
    const xGapB = Math.abs(childPoint.x - pointB.x);
    if (xGapA !== xGapB) return xGapA - xGapB;
    return a.id - b.id;
  });

  return filtered[0]?.id ?? null;
}

export function buildAnchoredTreeEdges(
  nodes: SkillNode[],
  points: Map<number, SkillTreePoint>
): SkillTreeAnchorEdge[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const candidatesByChild = new Map<number, SkillTreeAnchorEdge[]>();

  function pushCandidate(edge: SkillTreeAnchorEdge) {
    const childNode = nodeById.get(edge.childId);
    if (!childNode) return;
    const bucket = candidatesByChild.get(edge.childId) || [];
    if (bucket.some((item) => item.parentId === edge.parentId)) return;
    bucket.push(edge);
    candidatesByChild.set(edge.childId, bucket);
  }

  function edgeScore(edge: SkillTreeAnchorEdge): number {
    const childPoint = points.get(edge.childId);
    const parentPoint = points.get(edge.parentId);
    if (!childPoint || !parentPoint) return Number.POSITIVE_INFINITY;
    const child = nodeById.get(edge.childId);
    const parent = nodeById.get(edge.parentId);
    const depthGap = Math.max(1, childPoint.depth - parentPoint.depth);
    let score = depthGap * 420 + Math.abs(parentPoint.x - childPoint.x);
    if (edge.synthetic) score += 70;
    if (child?.node_kind === 'core' && parent?.node_kind === 'core') score -= 120;
    if (child?.node_kind === 'core' && parent?.node_kind !== 'core') score += 40;
    return score;
  }

  for (const child of nodes) {
    const childPoint = points.get(child.id);
    if (!childPoint) continue;

    const normalizedParents = uniquePrerequisites(child, new Set(nodeById.keys()));
    for (const parentId of normalizedParents) {
      const parentPoint = points.get(parentId);
      if (!parentPoint) continue;
      if (parentPoint.depth >= childPoint.depth) continue;
      pushCandidate({ parentId, childId: child.id, synthetic: false });
    }
  }

  const byDepth = [...nodes].sort(
    (a, b) => (points.get(a.id)?.depth || 0) - (points.get(b.id)?.depth || 0)
  );

  for (const child of byDepth) {
    const childPoint = points.get(child.id);
    if (!childPoint || childPoint.depth === 0) continue;
    const current = candidatesByChild.get(child.id) || [];
    const immediateTier = childPoint.depth - 1;
    const hasImmediateTierAnchor = current.some((edge) => {
      const parentPoint = points.get(edge.parentId);
      return parentPoint?.depth === immediateTier;
    });

    const fallbackParent = hasImmediateTierAnchor
      ? null
      : fallbackAnchorParentId(child, nodes, points, { requiredDepth: immediateTier });
    if (fallbackParent) {
      pushCandidate({ parentId: fallbackParent, childId: child.id, synthetic: true });
      continue;
    }

    if (current.length > 0) continue;

    const deepFallbackParent = fallbackAnchorParentId(child, nodes, points);
    if (!deepFallbackParent) continue;
    pushCandidate({ parentId: deepFallbackParent, childId: child.id, synthetic: true });
  }

  const edgesByChild = new Map<number, SkillTreeAnchorEdge[]>();
  for (const child of nodes) {
    const childPoint = points.get(child.id);
    if (!childPoint) continue;
    const candidates = candidatesByChild.get(child.id) || [];
    if (!candidates.length) continue;

    const maxEdges = child.node_kind === 'core' ? 1 : MAX_VISUAL_PARENT_ANCHORS;
    const immediateTier = childPoint.depth - 1;
    const immediateCandidates = candidates.filter((edge) => {
      const parentPoint = points.get(edge.parentId);
      return parentPoint?.depth === immediateTier;
    });

    const sortedCandidates = [...candidates].sort((a, b) => edgeScore(a) - edgeScore(b));
    const selected = sortedCandidates.slice(0, maxEdges);

    if (
      childPoint.depth > 0 &&
      immediateCandidates.length > 0 &&
      !selected.some((edge) => {
        const parentPoint = points.get(edge.parentId);
        return parentPoint?.depth === immediateTier;
      })
    ) {
      const bestImmediate = [...immediateCandidates].sort((a, b) => edgeScore(a) - edgeScore(b))[0];
      if (selected.length === 0) {
        selected.push(bestImmediate);
      } else {
        selected[selected.length - 1] = bestImmediate;
      }
    }

    const deduped = selected.filter(
      (edge, index) =>
        selected.findIndex((item) => item.parentId === edge.parentId && item.childId === edge.childId) === index
    );
    edgesByChild.set(child.id, deduped.slice(0, maxEdges));
  }

  for (const child of byDepth) {
    const childPoint = points.get(child.id);
    if (!childPoint || childPoint.depth === 0) continue;
    const current = edgesByChild.get(child.id) || [];
    if (current.length > 0) continue;
    const immediateTierParent = fallbackAnchorParentId(child, nodes, points, {
      requiredDepth: childPoint.depth - 1,
    });
    if (immediateTierParent) {
      edgesByChild.set(child.id, [
        { parentId: immediateTierParent, childId: child.id, synthetic: true },
      ]);
      continue;
    }
    const fallbackParent = fallbackAnchorParentId(child, nodes, points);
    if (!fallbackParent) continue;
    edgesByChild.set(child.id, [
      { parentId: fallbackParent, childId: child.id, synthetic: true },
    ]);
  }

  const MAX_LOCAL_X_GAP = 320;
  const MAX_LOCAL_Y_GAP = 360;
  for (const child of byDepth) {
    const childPoint = points.get(child.id);
    if (!childPoint || childPoint.depth === 0) continue;
    const current = edgesByChild.get(child.id) || [];
    const maxEdges = child.node_kind === 'core' ? 1 : MAX_VISUAL_PARENT_ANCHORS;

    const primary = current[0];
    const primaryParentPoint = primary ? points.get(primary.parentId) : null;
    const needsVisualRepair =
      !primary ||
      !primaryParentPoint ||
      Math.abs(primaryParentPoint.x - childPoint.x) > MAX_LOCAL_X_GAP ||
      childPoint.y - primaryParentPoint.y > MAX_LOCAL_Y_GAP;

    if (!needsVisualRepair) continue;

    const visualParentId = nearestVisualParentId(child, nodes, points);
    if (!visualParentId) continue;
    const repaired = {
      parentId: visualParentId,
      childId: child.id,
      synthetic: true,
    };
    const merged = [repaired, ...current.filter((edge) => edge.parentId !== visualParentId)];
    edgesByChild.set(child.id, merged.slice(0, maxEdges));
  }

  for (const child of byDepth) {
    const childPoint = points.get(child.id);
    if (!childPoint || childPoint.depth === 0) continue;
    const maxEdges = child.node_kind === 'core' ? 1 : MAX_VISUAL_PARENT_ANCHORS;
    const current = edgesByChild.get(child.id) || [];
    const immediateDepth = childPoint.depth - 1;

    if (child.node_kind === 'core') {
      const strictCoreParent = nearestTierParentByX(
        child,
        nodes,
        points,
        immediateDepth,
        'core'
      );
      if (strictCoreParent) {
        const next = [
          { parentId: strictCoreParent, childId: child.id, synthetic: true },
          ...current.filter((edge) => edge.parentId !== strictCoreParent),
        ];
        edgesByChild.set(child.id, next.slice(0, maxEdges));
        continue;
      }
    }

    if (child.node_kind === 'optional_branch' && child.branch_parent_skill_id) {
      const branchParentPoint = points.get(child.branch_parent_skill_id);
      if (branchParentPoint && branchParentPoint.depth < childPoint.depth) {
        const next = [
          { parentId: child.branch_parent_skill_id, childId: child.id, synthetic: true },
          ...current.filter((edge) => edge.parentId !== child.branch_parent_skill_id),
        ];
        edgesByChild.set(child.id, next.slice(0, maxEdges));
      }
    }
  }

  return Array.from(edgesByChild.values()).flat();
}
