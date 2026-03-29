export type TopicGrowthMetrics = {
  totalNodes: number;
  verifiedNodes: number;
  unlockedNodes: number;
  masteryAverage: number;
};

export const TREE_STAGE_LABELS = [
  'Seed',
  'Sprout',
  'Young sapling',
  'Growing tree',
  'Mature tree',
  'Flourishing tree'
] as const;

export function computeTreeStage(metrics: TopicGrowthMetrics): number {
  if (metrics.totalNodes <= 0) return 1;

  const verifiedRatio = metrics.verifiedNodes / metrics.totalNodes;
  const unlockedRatio = metrics.unlockedNodes / metrics.totalNodes;
  const masteryRatio = Math.max(0, Math.min(1, metrics.masteryAverage));

  const growthScore = 0.45 * masteryRatio + 0.35 * verifiedRatio + 0.2 * unlockedRatio;
  const stage = Math.floor(growthScore * 5) + 1;
  return Math.max(1, Math.min(6, stage));
}

export function treeStageLabel(stage: number): string {
  return TREE_STAGE_LABELS[Math.max(1, Math.min(6, stage)) - 1];
}

export function treeStageAsset(stage: number): string {
  return `/assets/tree-growth/tree-stage-${Math.max(1, Math.min(6, stage))}.svg`;
}
