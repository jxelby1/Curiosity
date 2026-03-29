from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.core.exceptions import ConfigurationError, ProviderError
from app.db.models import SkillNode, Topic
from app.services.course_memory import CourseMemorySnapshot
from app.services.search import ExternalSearchService, SearchResult


_RESEARCH_TRIGGER_KEYWORDS = (
    'local',
    'city',
    'region',
    'geography',
    'history',
    'culture',
    'current',
    'modern',
    'ecosystem',
    'policy',
    'software',
    'community',
    'venue',
    'event',
    'hidden gem',
)
_RESEARCH_STOPWORDS = {
    'the',
    'and',
    'for',
    'with',
    'from',
    'into',
    'this',
    'that',
    'about',
    'topic',
    'lesson',
    'learning',
    'skill',
}
_MIN_RESEARCH_SCORE = 0.25
_TRUSTED_SOURCE_DOMAINS = (
    'wikipedia.org',
    'wikimedia.org',
    'britannica.com',
    'nationalgeographic.com',
    'history.com',
    'bbc.com',
    'bbc.co.uk',
    'reuters.com',
    'apnews.com',
    'nytimes.com',
    'washingtonpost.com',
    'theguardian.com',
    'economist.com',
    'bloomberg.com',
    'ft.com',
    'wsj.com',
    'pbs.org',
    'khanacademy.org',
    'openstax.org',
    'metmuseum.org',
    'moma.org',
    'tate.org.uk',
    'si.edu',
    'loc.gov',
    'archives.gov',
    'nasa.gov',
    'noaa.gov',
    'usgs.gov',
    'worldbank.org',
    'oecd.org',
    'imf.org',
    'who.int',
    'un.org',
    'unesco.org',
)
_LOW_CONFIDENCE_SOURCE_DOMAINS = (
    'blogspot.com',
    'wordpress.com',
    'medium.com',
    'quora.com',
    'fandom.com',
)


@dataclass(frozen=True)
class ResearchInsight:
    title: str
    url: str
    source_domain: str
    summary: str
    kind: str
    score: float

    def as_prompt_line(self) -> str:
        return f'- {self.title} ({self.source_domain}): {self.summary[:220]} [{self.url}]'


class CourseResearchService:
    def __init__(self, search_service: ExternalSearchService) -> None:
        self.search_service = search_service

    def _tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", (text or '').lower())
            if token not in _RESEARCH_STOPWORDS
        }

    def _is_trusted_domain(self, domain: str) -> bool:
        domain_clean = (domain or '').lower().strip()
        if not domain_clean:
            return False
        if domain_clean.endswith('.gov') or domain_clean.endswith('.edu'):
            return True
        return any(
            domain_clean == trusted or domain_clean.endswith(f'.{trusted}')
            for trusted in _TRUSTED_SOURCE_DOMAINS
        )

    def _is_low_confidence_domain(self, domain: str) -> bool:
        domain_clean = (domain or '').lower().strip()
        if not domain_clean:
            return True
        return any(
            domain_clean == weak or domain_clean.endswith(f'.{weak}')
            for weak in _LOW_CONFIDENCE_SOURCE_DOMAINS
        )

    def should_research(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode | None,
        kind: str,
        retrieval_hits: int = 0,
        memory: CourseMemorySnapshot | None = None,
    ) -> bool:
        if kind not in {'skill_graph', 'lesson', 'examples', 'deep_lesson'}:
            return False
        topic_blob = ' '.join(
            [
                topic.name or '',
                topic.description or '',
                topic.goal or '',
                skill_node.name if skill_node else '',
                skill_node.description if skill_node else '',
            ]
        ).lower()
        keyword_triggered = any(marker in topic_blob for marker in _RESEARCH_TRIGGER_KEYWORDS)
        low_local_context = retrieval_hits < 2
        sparse_grounding_history = bool(memory is not None and len(memory.source_backed_examples) < 2)
        return keyword_triggered or low_local_context or sparse_grounding_history or kind == 'skill_graph'

    def _score_result(
        self,
        *,
        result: SearchResult,
        topic_tokens: set[str],
        skill_tokens: set[str],
        memory: CourseMemorySnapshot | None,
    ) -> float:
        haystack = f'{result.title} {result.summary} {result.url}'.lower()
        token_hits = sum(1 for token in topic_tokens if token in haystack)
        skill_hits = sum(1 for token in skill_tokens if token in haystack)
        score = float(result.relevance_score)
        score += min(0.28, token_hits * 0.05)
        score += min(0.28, skill_hits * 0.07)
        if any(marker in haystack for marker in ('map', 'case study', 'archive', 'museum', 'dataset', 'report')):
            score += 0.08
        if self._is_trusted_domain(result.source_domain):
            score += 0.1
        if self._is_low_confidence_domain(result.source_domain):
            score -= 0.08
        if memory:
            duplicate_example = any(example.lower() in haystack for example in memory.used_examples[:8])
            if duplicate_example:
                score -= 0.16
        return max(0.0, min(1.0, score))

    def _select_diverse_insights(
        self,
        *,
        candidates: list[ResearchInsight],
        limit: int,
    ) -> list[ResearchInsight]:
        if not candidates:
            return []

        sorted_candidates = sorted(candidates, key=lambda insight: insight.score, reverse=True)
        per_domain_cap = 1 if limit <= 4 else 2
        domain_counts: dict[str, int] = {}
        selected: list[ResearchInsight] = []
        for insight in sorted_candidates:
            domain = (insight.source_domain or '').lower().strip()
            if domain and domain_counts.get(domain, 0) >= per_domain_cap:
                continue
            selected.append(insight)
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
            if len(selected) >= limit:
                break

        if len(selected) < limit:
            selected_urls = {item.url for item in selected}
            for insight in sorted_candidates:
                if insight.url in selected_urls:
                    continue
                selected.append(insight)
                selected_urls.add(insight.url)
                if len(selected) >= limit:
                    break

        trusted_candidates = [
            item for item in sorted_candidates if self._is_trusted_domain(item.source_domain)
        ]
        if trusted_candidates and not any(self._is_trusted_domain(item.source_domain) for item in selected):
            trusted = trusted_candidates[0]
            if selected:
                selected[-1] = trusted
            else:
                selected.append(trusted)

        deduped: list[ResearchInsight] = []
        seen_urls: set[str] = set()
        for item in selected:
            if item.url in seen_urls:
                continue
            deduped.append(item)
            seen_urls.add(item.url)
            if len(deduped) >= limit:
                break
        return deduped

    async def gather_for_skill(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        kind: str,
        memory: CourseMemorySnapshot | None,
        retrieval_hits: int = 0,
        limit: int = 4,
        force: bool = False,
    ) -> list[ResearchInsight]:
        if not force and not self.should_research(
            topic=topic,
            skill_node=skill_node,
            kind=kind,
            retrieval_hits=retrieval_hits,
            memory=memory,
        ):
            return []

        query = (
            f'{topic.name} {skill_node.name} concrete examples authoritative references '
            'maps case studies educational sources'
        )
        try:
            results = await self.search_service.search(
                topic.name,
                skill_node.name,
                query=query,
                limit=max(8, limit * 3),
                source_policy='grounding',
            )
        except (ConfigurationError, ProviderError):
            return []

        topic_tokens = self._tokens(f'{topic.name} {topic.description} {topic.goal}')
        skill_tokens = self._tokens(f'{skill_node.name} {skill_node.description}')

        ranked: list[ResearchInsight] = []
        seen_urls: set[str] = set()
        for item in results:
            if item.url in seen_urls:
                continue
            score = self._score_result(
                result=item,
                topic_tokens=topic_tokens,
                skill_tokens=skill_tokens,
                memory=memory,
            )
            if score < _MIN_RESEARCH_SCORE:
                continue
            seen_urls.add(item.url)
            ranked.append(
                ResearchInsight(
                    title=item.title,
                    url=item.url,
                    source_domain=item.source_domain,
                    summary=item.summary,
                    kind=item.kind,
                    score=score,
                )
            )

        return self._select_diverse_insights(candidates=ranked, limit=limit)

    async def gather_for_topic(self, *, topic: Topic, limit: int = 5) -> list[ResearchInsight]:
        if not self.should_research(topic=topic, skill_node=None, kind='skill_graph'):
            return []

        query = (
            f'{topic.name} {topic.description} {topic.goal} curriculum outline key concepts '
            'trusted references'
        )
        try:
            results = await self.search_service.search(
                topic.name,
                topic.name,
                query=query,
                limit=max(8, limit * 3),
                source_policy='grounding',
            )
        except (ConfigurationError, ProviderError):
            return []

        topic_tokens = self._tokens(f'{topic.name} {topic.description} {topic.goal}')
        ranked: list[ResearchInsight] = []
        seen_urls: set[str] = set()
        for item in results:
            if item.url in seen_urls:
                continue
            score = self._score_result(
                result=item,
                topic_tokens=topic_tokens,
                skill_tokens=topic_tokens,
                memory=None,
            )
            if score < _MIN_RESEARCH_SCORE:
                continue
            seen_urls.add(item.url)
            ranked.append(
                ResearchInsight(
                    title=item.title,
                    url=item.url,
                    source_domain=item.source_domain,
                    summary=item.summary,
                    kind=item.kind,
                    score=score,
                )
            )

        return self._select_diverse_insights(candidates=ranked, limit=limit)

    def format_prompt_context(self, insights: list[ResearchInsight], *, max_items: int = 4) -> str:
        if not insights:
            return ''
        return '\n'.join(item.as_prompt_line() for item in insights[:max_items])

    def to_ledger_records(self, insights: list[ResearchInsight], *, limit: int = 8) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for item in insights[:limit]:
            records.append(
                {
                    'title': item.title,
                    'url': item.url,
                    'source_domain': item.source_domain,
                    'summary': item.summary,
                    'kind': item.kind,
                    'score': round(float(item.score), 3),
                }
            )
        return records
