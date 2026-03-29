from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, urlparse

from app.core.config import Settings
from app.db.models import SkillNode, Topic
from app.services.search import ExternalSearchService, SearchResult


logger = logging.getLogger(__name__)

_BLOCKED_DOMAINS = (
    'facebook.com',
    'fb.watch',
    'instagram.com',
    'tiktok.com',
    'x.com',
    'twitter.com',
    'threads.net',
    'snapchat.com',
    'pinterest.com',
    'reddit.com',
    'gettyimages.com',
    'istockphoto.com',
    'shutterstock.com',
    'stock.adobe.com',
    'adobestock.com',
    'dreamstime.com',
    'alamy.com',
    'depositphotos.com',
    '123rf.com',
)
_TRUSTED_VISUAL_DOMAINS = (
    'metmuseum.org',
    'moma.org',
    'tate.org.uk',
    'si.edu',
    'loc.gov',
    'archives.gov',
    'khanacademy.org',
    'nationalgallery.org.uk',
    'nga.gov',
    'rmg.co.uk',
    'vam.ac.uk',
    'artic.edu',
    'britishmuseum.org',
    'youtube.com',
    'youtu.be',
    'bbc.com',
    'bbc.co.uk',
    'pbs.org',
    'nationalgeographic.com',
    'unesco.org',
    'un.org',
    'worldhistory.org',
    'britannica.com',
)
_DEEMPHASIZED_VISUAL_DOMAINS = (
    'wikipedia.org',
    'wikimedia.org',
)
_VISUAL_NEED_HINTS = (
    'art',
    'painting',
    'photography',
    'photo',
    'image',
    'architecture',
    'building',
    'design',
    'poster',
    'layout',
    'typography',
    'film',
    'cinema',
    'scene',
    'fashion',
    'craft',
    'artifact',
    'object',
    'manuscript',
    'map',
    'city',
    'place',
    'visual',
    'composition',
    'exemplar',
    'compare',
)
_DIRECT_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif')
_TOKEN_STOPWORDS = {
    'also',
    'about',
    'along',
    'among',
    'around',
    'after',
    'again',
    'because',
    'being',
    'before',
    'between',
    'chapter',
    'could',
    'context',
    'detail',
    'during',
    'each',
    'example',
    'first',
    'from',
    'have',
    'into',
    'guide',
    'image',
    'images',
    'just',
    'lesson',
    'material',
    'more',
    'most',
    'much',
    'many',
    'over',
    'overview',
    'part',
    'practice',
    'reference',
    'references',
    'same',
    'section',
    'should',
    'study',
    'support',
    'than',
    'that',
    'them',
    'then',
    'there',
    'these',
    'this',
    'those',
    'through',
    'topic',
    'very',
    'visual',
    'with',
    'without',
}
_GENERIC_FILE_PREFIXES = (
    'chapter',
    'image',
    'img',
    'photo',
    'picture',
    'figure',
    'scan',
    'document',
    'page',
    'cover',
    'untitled',
)
_VISUAL_MODE_KEYWORDS: dict[
    Literal['photography', 'architecture', 'film', 'design', 'art', 'place', 'literature', 'music', 'general'],
    tuple[str, ...],
] = {
    'photography': (
        'photography',
        'photograph',
        'camera',
        'exposure',
        'aperture',
        'shutter',
        'composition',
        'editing',
        'light',
        'lighting',
        'portrait',
        'street',
    ),
    'architecture': (
        'architecture',
        'building',
        'facade',
        'urban',
        'city',
        'plan',
        'section',
        'elevation',
        'material',
        'space',
    ),
    'film': (
        'film',
        'cinema',
        'scene',
        'frame',
        'cinematography',
        'shot',
        'director',
        'editing',
        'mise',
        'screen',
    ),
    'design': (
        'design',
        'typography',
        'layout',
        'poster',
        'product',
        'interface',
        'graphic',
        'visual',
        'brand',
        'object',
    ),
    'art': (
        'art',
        'painting',
        'sculpture',
        'drawing',
        'artist',
        'museum',
        'gallery',
        'canvas',
        'movement',
        'style',
    ),
    'place': (
        'city',
        'place',
        'map',
        'landmark',
        'neighborhood',
        'street',
        'cultural',
        'history',
        'region',
        'site',
    ),
    'literature': (
        'literature',
        'poetry',
        'novel',
        'manuscript',
        'author',
        'archive',
        'text',
        'essay',
        'book',
        'reading',
    ),
    'music': (
        'music',
        'album',
        'record',
        'composer',
        'performer',
        'instrument',
        'jazz',
        'classical',
        'electronic',
        'poster',
    ),
    'general': (
        'visual',
        'artifact',
        'archive',
        'collection',
        'example',
        'reference',
    ),
}
_VISUAL_MODE_QUERY_TERMS: dict[str, str] = {
    'photography': 'photography composition lighting exposure editing camera',
    'architecture': 'architecture building facade plan detail visual study',
    'film': 'film scene still cinematography frame composition',
    'design': 'design typography layout poster object visual reference',
    'art': 'artwork painting sculpture museum collection image',
    'place': 'city landmark streetscape map cultural site image',
    'literature': 'manuscript portrait archive artifact place image',
    'music': 'album cover concert poster musician photograph',
    'general': 'diagram map timeline portrait manuscript artifact archive educational image',
}
_VISUAL_MODE_REQUIRED_TOKENS: dict[str, tuple[str, ...]] = {
    'photography': ('photo', 'photography', 'photograph', 'camera', 'exposure', 'aperture', 'shutter', 'composition'),
    'architecture': ('architecture', 'building', 'facade', 'plan', 'elevation', 'urban'),
    'film': ('film', 'cinema', 'scene', 'frame', 'cinematography', 'shot'),
    'design': ('design', 'typography', 'layout', 'poster', 'graphic', 'interface'),
    'art': ('art', 'painting', 'sculpture', 'drawing', 'gallery', 'museum'),
    'place': ('city', 'map', 'landmark', 'region', 'street', 'place'),
    'literature': ('manuscript', 'archive', 'author', 'book', 'literature', 'poetry'),
    'music': ('music', 'album', 'composer', 'performer', 'instrument', 'record'),
}


@dataclass
class LessonImageSelection:
    media_items: list[dict[str, str]]
    diagnostics: dict[str, Any]


class LessonImageAgent:
    def __init__(self, *, search_service: ExternalSearchService, settings: Settings) -> None:
        self.search_service = search_service
        self.settings = settings

    def _domain_for_url(self, url: str) -> str:
        host = urlparse(url).netloc.lower().strip()
        if host.startswith('www.'):
            host = host[4:]
        return host

    def _is_direct_image_url(self, url: str) -> bool:
        lowered = (url or '').lower().split('?', 1)[0].split('#', 1)[0]
        if '/wiki/file:' in lowered:
            return False
        return lowered.endswith(_DIRECT_IMAGE_EXTENSIONS)

    def _preview_url_for_candidate(self, url: str) -> str | None:
        if self._is_direct_image_url(url):
            return url
        return None

    def canonical_media_url(self, url: str) -> str:
        raw = (url or '').strip()
        if not raw:
            return ''
        parsed = urlparse(raw)
        host = (parsed.netloc or '').lower().strip()
        if host.startswith('www.'):
            host = host[4:]
        path = parsed.path or ''

        if host in {'youtube.com', 'm.youtube.com'}:
            query = parse_qs(parsed.query or '')
            video_id = (query.get('v') or [''])[0].strip().lower()
            if video_id:
                return f'youtube:{video_id}'
        if host == 'youtu.be':
            video_id = path.strip('/').lower()
            if video_id:
                return f'youtube:{video_id}'

        if host.endswith('wikimedia.org'):
            lowered_path = path.lower()
            marker = '/wiki/file:'
            if marker in lowered_path:
                filename = unquote(path.split('/wiki/File:', 1)[1] if '/wiki/File:' in path else path.split(marker, 1)[1]).lower()
                return f'wikifile:{filename}'

        normalized_path = path.rstrip('/').lower()
        if not normalized_path:
            normalized_path = '/'
        return f'{host}{normalized_path}'

    def _tokenize(self, text: str) -> list[str]:
        raw = re.findall(r'[a-z0-9]{3,}', (text or '').lower())
        tokens: list[str] = []
        seen: set[str] = set()
        for token in raw:
            if token in _TOKEN_STOPWORDS:
                continue
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
        return tokens

    def _anchor_tokens(self, *, topic: Topic, skill_node: SkillNode) -> list[str]:
        source = ' '.join(
            [
                str(topic.name or ''),
                str(topic.description or ''),
                str(topic.goal or ''),
                str(skill_node.name or ''),
                str(skill_node.description or ''),
            ]
        )
        return self._tokenize(source)[:24]

    def _keyword_tokens(self, *, keywords: list[str]) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            for token in self._tokenize(keyword):
                if token in seen:
                    continue
                seen.add(token)
                tokens.append(token)
        return tokens[:64]

    def _looks_generic_filename(self, title: str) -> bool:
        lowered_raw = (title or '').strip().lower()
        lowered_raw = lowered_raw.replace('file:', '').strip()
        if not lowered_raw:
            return True
        lowered = lowered_raw.replace('_', ' ')
        for prefix in _GENERIC_FILE_PREFIXES:
            if re.match(rf'^{re.escape(prefix)}[\s\-_]*\d*(?:\.[a-z0-9]+)?$', lowered):
                return True
        if re.match(r'^[a-z]{1,4}[\s\-_]*\d{1,4}(?:\.[a-z0-9]+)?$', lowered):
            return True
        tokenized = re.findall(r'[a-z0-9]+', lowered)
        if len(tokenized) <= 2 and any(token in _GENERIC_FILE_PREFIXES for token in tokenized):
            return True
        return False

    def _candidate_token_set(self, *, title: str, summary: str, url: str) -> set[str]:
        tokens = self._tokenize(f'{title} {summary} {url}')
        return set(tokens)

    def _detect_visual_mode(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        lesson_content: dict[str, Any],
    ) -> Literal['photography', 'architecture', 'film', 'design', 'art', 'place', 'literature', 'music', 'general']:
        haystack = ' '.join(
            [
                str(topic.name or ''),
                str(topic.description or ''),
                str(topic.goal or ''),
                str(skill_node.name or ''),
                str(skill_node.description or ''),
                str(lesson_content.get('title') or ''),
                str(lesson_content.get('summary') or ''),
                ' '.join(str(item) for item in lesson_content.get('exemplar_focus', []) if str(item).strip()),
                ' '.join(str(item) for item in lesson_content.get('comparison_prompts', []) if str(item).strip()),
                ' '.join(str(item.get('heading')) for item in lesson_content.get('sections', []) if isinstance(item, dict)),
            ]
        ).lower()
        best_mode: Literal['photography', 'architecture', 'film', 'design', 'art', 'place', 'literature', 'music', 'general'] = 'general'
        best_score = 0
        for mode, hints in _VISUAL_MODE_KEYWORDS.items():
            if mode == 'general':
                continue
            score = sum(1 for hint in hints if hint in haystack)
            if score > best_score:
                best_mode = mode
                best_score = score
        if best_score < 2:
            return 'general'
        return best_mode

    def _is_blocked_domain(self, domain: str) -> bool:
        if not domain:
            return True
        return any(domain == blocked or domain.endswith(f'.{blocked}') for blocked in _BLOCKED_DOMAINS)

    def _is_trusted_domain(self, domain: str) -> bool:
        if not domain:
            return False
        if domain.endswith('.edu') or domain.endswith('.gov'):
            return True
        return any(domain == trusted or domain.endswith(f'.{trusted}') for trusted in _TRUSTED_VISUAL_DOMAINS)

    def _is_deemphasized_domain(self, domain: str) -> bool:
        if not domain:
            return False
        return any(domain == blocked or domain.endswith(f'.{blocked}') for blocked in _DEEMPHASIZED_VISUAL_DOMAINS)

    def assess_visual_support(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        lesson_content: dict[str, Any],
        kind: str,
        study_mode: str,
    ) -> dict[str, Any]:
        haystack = ' '.join(
            [
                str(topic.name or ''),
                str(topic.description or ''),
                str(topic.goal or ''),
                str(skill_node.name or ''),
                str(skill_node.description or ''),
                str(lesson_content.get('title') or ''),
                str(lesson_content.get('summary') or ''),
                ' '.join(str(item) for item in lesson_content.get('exemplar_focus', []) if str(item).strip()),
                ' '.join(str(item) for item in lesson_content.get('comparison_prompts', []) if str(item).strip()),
                ' '.join(str(item.get('heading')) for item in lesson_content.get('sections', []) if isinstance(item, dict)),
            ]
        ).lower()
        matched_hints = sorted({hint for hint in _VISUAL_NEED_HINTS if hint in haystack})
        score = len(matched_hints)
        visual_mode = self._detect_visual_mode(topic=topic, skill_node=skill_node, lesson_content=lesson_content)
        if visual_mode != 'general':
            score += 1
        if study_mode in {'exemplar', 'compare'}:
            score += 2
        if kind == 'deep_lesson':
            score += 1

        # All lessons should attempt contextual visual support; highly visual domains get higher priority.
        visual_support_needed = kind in {'lesson', 'examples', 'deep_lesson'} or score >= 3
        visual_priority: Literal['low', 'medium', 'high']
        if score >= 8:
            visual_priority = 'high'
        elif score >= 4:
            visual_priority = 'medium'
        else:
            visual_priority = 'low'
        if score >= 4:
            reason = 'Visual support is likely valuable due to topic and lesson cues.'
        elif visual_support_needed:
            reason = 'Contextual visual support is enabled to ground understanding in concrete references.'
        else:
            reason = 'Visual support is optional; topic appears less visually anchored.'
        return {
            'visual_support_needed': visual_support_needed,
            'visual_priority': visual_priority,
            'visual_mode': visual_mode,
            'matched_hints': matched_hints[:12],
            'reason': reason,
        }

    def _extract_keywords(self, *, topic: Topic, skill_node: SkillNode, lesson_content: dict[str, Any]) -> list[str]:
        seeds = [
            str(topic.name or ''),
            str(skill_node.name or ''),
            str(lesson_content.get('title') or ''),
            str(lesson_content.get('summary') or ''),
            *(str(item) for item in lesson_content.get('exemplar_focus', []) if str(item).strip()),
            *(str(item.get('heading')) for item in lesson_content.get('sections', []) if isinstance(item, dict)),
        ]
        keywords: list[str] = []
        seen: set[str] = set()
        for seed in seeds:
            cleaned = ' '.join(seed.split()).strip()
            if len(cleaned) < 3:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            keywords.append(cleaned)
            if len(keywords) >= 8:
                break
        return keywords

    def _build_image_queries(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        lesson_content: dict[str, Any],
        visual_priority: str,
        visual_mode: str,
    ) -> list[str]:
        keywords = self._extract_keywords(topic=topic, skill_node=skill_node, lesson_content=lesson_content)
        anchor = keywords[0] if keywords else skill_node.name
        secondary = keywords[1] if len(keywords) > 1 else topic.name
        tertiary = keywords[2] if len(keywords) > 2 else lesson_content.get('title') or skill_node.name
        title_focus = str(lesson_content.get('title') or skill_node.name).strip() or skill_node.name
        mode_terms = _VISUAL_MODE_QUERY_TERMS.get(visual_mode, _VISUAL_MODE_QUERY_TERMS['general'])
        anchor_short = ' '.join(str(anchor).split()[:8]).strip()
        secondary_short = ' '.join(str(secondary).split()[:8]).strip()
        tertiary_short = ' '.join(str(tertiary).split()[:8]).strip()
        title_focus_short = ' '.join(title_focus.split()[:10]).strip()
        queries = [
            f'{title_focus_short} {mode_terms} exemplar visual reference',
            f'{anchor_short} {secondary_short} {mode_terms} educational image example',
            f'{anchor_short} {tertiary_short} {mode_terms} museum archive gallery image',
        ]
        if visual_priority == 'high':
            queries.append(f'{topic.name} {mode_terms} authoritative visual reference image')

        normalized: list[str] = []
        seen: set[str] = set()
        for query in queries:
            compact = ' '.join(str(query).split()).strip()
            lowered = compact.lower()
            if not compact or lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(compact[:220])
        return normalized[:4]

    def _candidate_relevance_score(
        self,
        *,
        title: str,
        summary: str,
        url: str,
        keywords: list[str],
        visual_mode: str,
    ) -> float:
        haystack = f'{title} {summary} {url}'.lower()
        if not haystack.strip():
            return 0.0

        candidate_tokens = self._candidate_token_set(title=title, summary=summary, url=url)
        keyword_tokens: list[str] = []
        for keyword in keywords:
            keyword_tokens.extend(self._tokenize(keyword))
        deduped_tokens = list(dict.fromkeys(keyword_tokens))
        token_matches = sum(1 for token in deduped_tokens if token in candidate_tokens)
        phrase_matches = sum(1 for keyword in keywords if keyword.lower() in haystack)
        score = phrase_matches / max(1, len(keywords))
        score += min(0.45, token_matches * 0.06)
        if any(token in haystack for token in ('museum', 'archive', 'collection', 'exhibit', 'gallery')):
            score += 0.14
        if any(token in haystack for token in ('map', 'diagram', 'painting', 'photo', 'photograph', 'scene', 'facade', 'poster')):
            score += 0.1
        mode_tokens = set(_VISUAL_MODE_REQUIRED_TOKENS.get(visual_mode, ()))
        if mode_tokens and candidate_tokens.intersection(mode_tokens):
            score += 0.2
        return min(score, 1.0)

    def _context_match_reason(
        self,
        *,
        title: str,
        summary: str,
        url: str,
        anchor_tokens: list[str],
        keyword_tokens: list[str],
        visual_mode: str,
    ) -> tuple[bool, Literal['ok', 'generic_filename', 'insufficient_context_match', 'mode_mismatch']]:
        if self._looks_generic_filename(title):
            return False, 'generic_filename'
        candidate_tokens = self._candidate_token_set(title=title, summary=summary, url=url)
        anchor_match_count = len(candidate_tokens.intersection(anchor_tokens))
        keyword_match_count = len(candidate_tokens.intersection(keyword_tokens))
        mode_tokens = set(_VISUAL_MODE_REQUIRED_TOKENS.get(visual_mode, ()))
        mode_match_count = len(candidate_tokens.intersection(mode_tokens))
        title_token_count = len(self._tokenize(title))

        if anchor_match_count == 0 and keyword_match_count == 0:
            if not (mode_match_count >= 1 and title_token_count >= 2):
                return False, 'insufficient_context_match'
        elif anchor_match_count == 0 and keyword_match_count == 1 and mode_match_count == 0:
            return False, 'insufficient_context_match'

        if mode_tokens and mode_match_count == 0:
            if anchor_match_count < 2 and keyword_match_count < 2:
                return False, 'mode_mismatch'
        return True, 'ok'

    def filter_existing_media_items(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        lesson_content: dict[str, Any],
        media_items: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], dict[str, int]]:
        keywords = self._extract_keywords(topic=topic, skill_node=skill_node, lesson_content=lesson_content)
        keyword_tokens = self._keyword_tokens(keywords=keywords)
        anchor_tokens = self._anchor_tokens(topic=topic, skill_node=skill_node)
        visual_mode = self._detect_visual_mode(topic=topic, skill_node=skill_node, lesson_content=lesson_content)
        diagnostics = {
            'kept': 0,
            'dropped_generic_filename': 0,
            'dropped_insufficient_context_match': 0,
            'dropped_mode_mismatch': 0,
        }
        kept: list[dict[str, str]] = []
        for item in media_items:
            if str(item.get('media_type') or '') != 'image':
                kept.append(item)
                diagnostics['kept'] += 1
                continue
            title = str(item.get('title') or '').strip()
            summary = str(item.get('relevance_reason') or '').strip()
            url = str(item.get('url') or '').strip()
            passed, reason = self._context_match_reason(
                title=title,
                summary=summary,
                url=url,
                anchor_tokens=anchor_tokens,
                keyword_tokens=keyword_tokens,
                visual_mode=visual_mode,
            )
            if not passed:
                if reason == 'generic_filename':
                    diagnostics['dropped_generic_filename'] += 1
                elif reason == 'mode_mismatch':
                    diagnostics['dropped_mode_mismatch'] += 1
                else:
                    diagnostics['dropped_insufficient_context_match'] += 1
                continue
            kept.append(item)
            diagnostics['kept'] += 1
        return kept, diagnostics

    async def select_supporting_images(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        lesson_content: dict[str, Any],
        kind: str,
        study_mode: str,
        limit: int,
        exclude_media_keys: set[str] | None = None,
    ) -> LessonImageSelection:
        visual_decision = self.assess_visual_support(
            topic=topic,
            skill_node=skill_node,
            lesson_content=lesson_content,
            kind=kind,
            study_mode=study_mode,
        )
        diagnostics: dict[str, Any] = {
            'topic_id': topic.id,
            'skill_id': skill_node.id,
            'kind': kind,
            'study_mode': study_mode,
            'visual_support_needed': visual_decision['visual_support_needed'],
            'visual_priority': visual_decision['visual_priority'],
            'visual_mode': visual_decision.get('visual_mode', 'general'),
            'decision_reason': visual_decision['reason'],
            'queries': [],
            'candidate_count': 0,
            'candidate_domains': [],
            'renderable_urls_found': 0,
            'selected_count': 0,
            'rejections': {
                'blocked_domain': 0,
                'deemphasized_domain': 0,
                'untrusted_domain': 0,
                'non_renderable': 0,
                'generic_filename': 0,
                'insufficient_context_match': 0,
                'mode_mismatch': 0,
                'low_relevance': 0,
                'duplicate': 0,
                'used_by_other_node': 0,
            },
        }
        if not visual_decision['visual_support_needed']:
            logger.info(
                'resource.lesson_image_selection topic_id=%s skill_id=%s kind=%s visual_support_needed=%s priority=%s selected=0 reason=%s',
                topic.id,
                skill_node.id,
                kind,
                False,
                visual_decision['visual_priority'],
                visual_decision['reason'],
            )
            return LessonImageSelection(media_items=[], diagnostics=diagnostics)

        queries = self._build_image_queries(
            topic=topic,
            skill_node=skill_node,
            lesson_content=lesson_content,
            visual_priority=visual_decision['visual_priority'],
            visual_mode=str(visual_decision.get('visual_mode') or 'general'),
        )
        diagnostics['queries'] = queries
        keywords = self._extract_keywords(topic=topic, skill_node=skill_node, lesson_content=lesson_content)
        keyword_tokens = self._keyword_tokens(keywords=keywords)
        anchor_tokens = self._anchor_tokens(topic=topic, skill_node=skill_node)
        visual_mode = str(visual_decision.get('visual_mode') or 'general')

        raw_candidates: list[dict[str, str]] = []
        for query in queries:
            try:
                if hasattr(self.search_service, 'search_images'):
                    web_results = await self.search_service.search_images(
                        topic.name,
                        skill_node.name,
                        query=query,
                        limit=max(8, limit * 4),
                        source_policy='strict_media',
                    )
                else:
                    web_results = await self.search_service.search(
                        topic.name,
                        skill_node.name,
                        query=query,
                        limit=max(8, limit * 4),
                        source_policy='strict_media',
                    )
            except TypeError:
                web_results = await self.search_service.search(
                    topic.name,
                    skill_node.name,
                    query=query,
                    limit=max(8, limit * 4),
                    source_policy='strict_media',
                )
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    'resource.lesson_image_web_search_error topic_id=%s skill_id=%s query=%s error=%s',
                    topic.id,
                    skill_node.id,
                    query,
                    exc,
                )
                web_results = []

            for item in web_results:
                raw_candidates.append(
                    {
                        'title': item.title,
                        'url': item.url,
                        'summary': item.summary,
                        'source_domain': item.source_domain or self._domain_for_url(item.url),
                        'origin': 'web',
                        'kind': item.kind,
                    }
                )

        diagnostics['candidate_count'] = len(raw_candidates)
        diagnostics['candidate_domains'] = sorted({self._domain_for_url(item.get('url', '')) for item in raw_candidates if item.get('url')})[:16]

        selected: list[tuple[float, dict[str, str]]] = []
        seen_urls: set[str] = set()
        blocked_keys = {item for item in (exclude_media_keys or set()) if item}
        threshold = 0.16 if visual_decision['visual_priority'] == 'high' else 0.2
        for candidate in raw_candidates:
            url = str(candidate.get('url') or '').strip()
            if not url:
                continue
            candidate_key = self.canonical_media_url(url)
            if candidate_key and candidate_key in blocked_keys:
                diagnostics['rejections']['used_by_other_node'] += 1
                continue
            if url in seen_urls:
                diagnostics['rejections']['duplicate'] += 1
                continue
            seen_urls.add(url)

            source_domain = str(candidate.get('source_domain') or self._domain_for_url(url))
            if self._is_blocked_domain(source_domain):
                diagnostics['rejections']['blocked_domain'] += 1
                continue
            if self._is_deemphasized_domain(source_domain):
                diagnostics['rejections']['deemphasized_domain'] += 1
                continue
            trusted_domain = self._is_trusted_domain(source_domain)

            preview_url = str(candidate.get('preview_url') or '').strip() or self._preview_url_for_candidate(url) or ''
            if not preview_url:
                diagnostics['rejections']['non_renderable'] += 1
                continue
            diagnostics['renderable_urls_found'] += 1

            title = str(candidate.get('title') or '').strip() or 'Supporting image'
            summary = str(candidate.get('summary') or '').strip()
            context_ok, context_reason = self._context_match_reason(
                title=title,
                summary=summary,
                url=url,
                anchor_tokens=anchor_tokens,
                keyword_tokens=keyword_tokens,
                visual_mode=visual_mode,
            )
            if not context_ok:
                diagnostics['rejections'][context_reason] += 1
                continue

            relevance_score = self._candidate_relevance_score(
                title=title,
                summary=summary,
                url=url,
                keywords=keywords,
                visual_mode=visual_mode,
            )
            if trusted_domain:
                relevance_score = min(1.0, relevance_score + 0.06)
            elif relevance_score < (threshold + 0.08):
                diagnostics['rejections']['untrusted_domain'] += 1
                continue
            if relevance_score < threshold:
                diagnostics['rejections']['low_relevance'] += 1
                continue

            selected.append(
                (
                    relevance_score,
                    {
                        'title': title,
                        'url': url,
                        'preview_url': preview_url,
                        'media_type': 'image',
                        'source_domain': source_domain,
                        'relevance_reason': 'Selected because this image directly supports observation and interpretation in this lesson.',
                    },
                )
            )

        selected.sort(key=lambda item: item[0], reverse=True)
        media_items = [item for _, item in selected[:limit]]
        diagnostics['selected_count'] = len(media_items)

        logger.info(
            'resource.lesson_image_selection topic_id=%s skill_id=%s kind=%s visual_support_needed=%s priority=%s queries=%s candidates=%s renderable=%s selected=%s domains=%s rejections=%s',
            topic.id,
            skill_node.id,
            kind,
            diagnostics['visual_support_needed'],
            diagnostics['visual_priority'],
            diagnostics['queries'],
            diagnostics['candidate_count'],
            diagnostics['renderable_urls_found'],
            diagnostics['selected_count'],
            diagnostics['candidate_domains'],
            diagnostics['rejections'],
        )
        return LessonImageSelection(media_items=media_items, diagnostics=diagnostics)
