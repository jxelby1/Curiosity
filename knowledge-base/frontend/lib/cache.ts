import { SkillTree } from '@/lib/types';

type CacheEntry<T> = {
  value: T;
  createdAt: number;
};

const skillTreeCache = new Map<string, CacheEntry<SkillTree>>();

const SKILL_TREE_TTL_MS = 60_000;

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

export function invalidateTopicCache(topicId: string | number): void {
  const key = String(topicId);
  skillTreeCache.delete(key);
}
