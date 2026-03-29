import { RecommendationItem, SkillTree } from '@/lib/types';

type CacheEntry<T> = {
  value: T;
  createdAt: number;
};

const skillTreeCache = new Map<string, CacheEntry<SkillTree>>();
const recommendationCache = new Map<string, CacheEntry<RecommendationItem[]>>();

const SKILL_TREE_TTL_MS = 60_000;
const RECOMMENDATION_TTL_MS = 90_000;

function readCached<T>(map: Map<string, CacheEntry<T>>, key: string, ttlMs: number): T | null {
  const entry = map.get(key);
  if (!entry) return null;
  if (Date.now() - entry.createdAt > ttlMs) return null;
  return entry.value;
}

function writeCached<T>(map: Map<string, CacheEntry<T>>, key: string, value: T): void {
  map.set(key, { value, createdAt: Date.now() });
}

export function readSkillTreeCache(topicId: string | number): SkillTree | null {
  return readCached(skillTreeCache, String(topicId), SKILL_TREE_TTL_MS);
}

export function writeSkillTreeCache(topicId: string | number, tree: SkillTree): void {
  writeCached(skillTreeCache, String(topicId), tree);
}

export function readRecommendationCache(topicId: string | number): RecommendationItem[] | null {
  return readCached(recommendationCache, String(topicId), RECOMMENDATION_TTL_MS);
}

export function writeRecommendationCache(topicId: string | number, items: RecommendationItem[]): void {
  writeCached(recommendationCache, String(topicId), items);
}

export function invalidateTopicCache(topicId: string | number): void {
  const key = String(topicId);
  skillTreeCache.delete(key);
  recommendationCache.delete(key);
}
