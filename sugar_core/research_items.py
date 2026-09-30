"""Collected-item model: provenance, evidence-chain lineage, deduplication, language detection.

Every collected item carries the minimum provenance of section 26 (platform, original URL,
retrieval time, discovering query, language, transformations, project, run, status). Derived
content (extracted paragraphs, translations, later coded findings) is linked back to the
original through an explicit lineage chain (section 27):

    search_result -> fetched_document -> extracted_paragraph -> translated_paragraph -> coded_finding
"""
from __future__ import annotations

import hashlib
import re
import threading
import unicodedata
from dataclasses import dataclass, field, fields
from typing import Any

from . import gazetteer as gz
from .research_plan import utc_now

ITEM_STATUSES = ("collected", "processed", "rejected", "duplicate", "excluded")
LINEAGE_TYPES = ("search_result", "fetched_document", "extracted_paragraph", "translated_paragraph", "coded_finding")


def _sha(text: str, length: int = 12) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def item_id_for(platform: str, native_id: str, url: str) -> str:
    identity = (native_id or url or "").strip()
    return f"it_{_sha(f'{platform}|{identity}')}"


# ---------------------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------------------
_URL = re.compile(r"https?://\S+")
_MENTION = re.compile(r"(?<!\w)@\w+")
_CJK = re.compile(r"[㐀-鿿぀-ヿ가-힯]")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    text = _URL.sub(" ", text)
    text = _MENTION.sub(" ", text)
    text = re.sub(r"^(?:rt)\s+:?", "", text.strip())
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _shingles(normalized: str) -> set[str]:
    if _CJK.search(normalized):
        chars = normalized.replace(" ", "")
        return {chars[i:i + 2] for i in range(max(1, len(chars) - 1))}
    tokens = normalized.split()
    if len(tokens) < 3:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i + 3]) for i in range(len(tokens) - 2)}


def _simhash(shingles: set[str]) -> int:
    weights = [0] * 64
    for shingle in shingles:
        value = int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")
        for bit in range(64):
            weights[bit] += 1 if (value >> bit) & 1 else -1
    return sum(1 << bit for bit in range(64) if weights[bit] > 0)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a and b else 0.0


class DedupIndex:
    """Exact + near-duplicate detection (SimHash banding, verified by Jaccard similarity)."""

    BANDS = 8       # 8 bands x 8 bits: any near-identical text shares at least one band

    def __init__(self, threshold: float = 0.9, enabled: bool = True) -> None:
        self.threshold = threshold
        self.enabled = enabled
        self._exact: dict[str, str] = {}
        self._bands: list[dict[int, list[str]]] = [dict() for _ in range(self.BANDS)]
        self._shingles: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def add(self, item_id: str, text: str) -> None:
        normalized = normalize_text(text)
        if not normalized:
            return
        shingles = _shingles(normalized)
        with self._lock:
            self._exact.setdefault(_sha(normalized, 20), item_id)
            self._shingles[item_id] = shingles
            digest = _simhash(shingles)
            for band in range(self.BANDS):
                self._bands[band].setdefault((digest >> (band * 8)) & 0xFF, []).append(item_id)

    def check(self, item_id: str, text: str) -> tuple[str, float] | None:
        """Return (duplicate_of, similarity) if ``text`` duplicates an earlier item, else None (and indexes it)."""
        if not self.enabled:
            return None
        normalized = normalize_text(text)
        if not normalized:
            return None
        key = _sha(normalized, 20)
        shingles = _shingles(normalized)
        with self._lock:
            existing = self._exact.get(key)
            if existing and existing != item_id:
                return existing, 1.0
            if len(normalized) >= 25 and self.threshold < 1.0:
                digest = _simhash(shingles)
                candidates: set[str] = set()
                for band in range(self.BANDS):
                    candidates.update(self._bands[band].get((digest >> (band * 8)) & 0xFF, ()))
                best: tuple[str, float] | None = None
                for other in candidates:
                    if other == item_id:
                        continue
                    similarity = jaccard(shingles, self._shingles.get(other, set()))
                    if similarity >= self.threshold and (best is None or similarity > best[1]):
                        best = (other, similarity)
                if best:
                    return best
            self._exact[key] = item_id
            self._shingles[item_id] = shingles
            digest = _simhash(shingles)
            for band in range(self.BANDS):
                self._bands[band].setdefault((digest >> (band * 8)) & 0xFF, []).append(item_id)
        return None


# ---------------------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------------------
_ENGLISH_HINT = re.compile(r"\b(the|and|of|to|in|is|that|for|with|are|this|not|have|was|on)\b", re.I)


def detect_language(text: str, platform_language: str = "") -> tuple[str, str, float]:
    """Return (iso_code or 'und', method, confidence). Platform-supplied language wins when present."""
    platform_language = (platform_language or "").strip().casefold().split("-")[0]
    sample = _URL.sub(" ", _MENTION.sub(" ", str(text or ""))).strip()
    if platform_language and platform_language not in {"und", "unknown", "auto"}:
        return platform_language, "platform", 0.95
    if len(sample) < 3:
        return "und", "none", 0.0
    counts = {"ar": 0, "he": 0, "cyr": 0, "cjk": 0, "kana": 0, "hangul": 0, "deva": 0, "thai": 0, "greek": 0, "latin": 0}
    for ch in sample:
        code = ord(ch)
        if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F or 0xFB50 <= code <= 0xFDFF or 0xFE70 <= code <= 0xFEFF:
            counts["ar"] += 1
        elif 0x0590 <= code <= 0x05FF:
            counts["he"] += 1
        elif 0x0400 <= code <= 0x04FF:
            counts["cyr"] += 1
        elif 0x3040 <= code <= 0x30FF:
            counts["kana"] += 1
        elif 0x3400 <= code <= 0x9FFF:
            counts["cjk"] += 1
        elif 0xAC00 <= code <= 0xD7AF:
            counts["hangul"] += 1
        elif 0x0900 <= code <= 0x097F:
            counts["deva"] += 1
        elif 0x0E00 <= code <= 0x0E7F:
            counts["thai"] += 1
        elif 0x0370 <= code <= 0x03FF:
            counts["greek"] += 1
        elif ch.isalpha() and code < 0x0250:
            counts["latin"] += 1
    total = sum(counts.values())
    if total == 0:
        return "und", "none", 0.0
    script, share = max(counts.items(), key=lambda kv: kv[1])
    if share / total < 0.5:
        script = "latin"
    if script == "ar":
        return ("fa" if re.search(r"[پچژگ]", sample) else "ar"), "script", 0.8
    if script == "he":
        return "he", "script", 0.85
    if script == "cyr":
        return ("uk" if re.search(r"[іїєґ]", sample) else "ru"), "script", 0.7
    if script == "kana" or (script == "cjk" and counts["kana"]):
        return "ja", "script", 0.85
    if script == "cjk":
        return "zh", "script", 0.8
    if script == "hangul":
        return "ko", "script", 0.9
    if script == "deva":
        return "hi", "script", 0.7
    if script == "thai":
        return "th", "script", 0.9
    if script == "greek":
        return "el", "script", 0.85
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0
        best = detect_langs(sample)[0]
        return best.lang.split("-")[0], "langdetect", round(float(best.prob), 2)
    except Exception:
        pass
    hits = len(_ENGLISH_HINT.findall(sample))
    if hits >= 2 or (hits and len(sample.split()) <= 4):
        return "en", "heuristic", 0.6
    return "und", "heuristic", 0.2


def is_language(code: str, target: str) -> bool:
    target_code = gz.language_code(target) or target.casefold()[:2]
    return (code or "").split("-")[0] == target_code


# ---------------------------------------------------------------------------------------
# Paragraphs, lineage, and the item record
# ---------------------------------------------------------------------------------------
def split_paragraphs(text: str, *, max_chars: int = 600) -> list[tuple[int, int, str]]:
    """Split into (start, end, text) paragraphs; long blocks are packed sentence by sentence."""
    text = str(text or "")
    out: list[tuple[int, int, str]] = []

    def flush(base: int, block: str, begin: int, end: int) -> None:
        piece = block[begin:end]
        if piece.strip():
            out.append((base + begin, base + end, piece.strip()))

    for match in re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", text):
        block, base = match.group(0), match.start()
        if len(block) <= max_chars:
            flush(base, block, 0, len(block))
            continue
        begin = end = -1
        for sentence in re.finditer(r"[^.!?؟。！？]+[.!?؟。！？]*\s*", block):
            if begin < 0:
                begin, end = sentence.start(), sentence.end()
            elif sentence.end() - begin <= max_chars:
                end = sentence.end()
            else:
                flush(base, block, begin, end)
                begin, end = sentence.start(), sentence.end()
        if begin >= 0:
            flush(base, block, begin, end)
    if not out and text.strip():
        out.append((0, len(text), text.strip()))
    return out


@dataclass
class LineageNode:
    id: str
    type: str
    parent: str = ""
    created_at: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchItem:
    item_id: str
    run_id: str
    project_id: str
    platform: str
    native_id: str = ""
    url: str = ""
    author: str = ""
    published_at: str = ""
    retrieved_at: str = ""
    query_id: str = ""
    query: str = ""
    query_dispatched: str = ""
    queries: list[str] = field(default_factory=list)
    language: str = ""
    language_method: str = ""
    original_text: str = ""
    translation: dict[str, Any] = field(default_factory=dict)      # {text, provider, model, target_language, at, status}
    paragraphs: list[dict[str, Any]] = field(default_factory=list)
    transformations: list[dict[str, Any]] = field(default_factory=list)
    status: str = "collected"
    rejection_reason: str = ""
    duplicate_of: str = ""
    similarity: float = 0.0
    geography: list[dict[str, Any]] = field(default_factory=list)
    coordinates: dict[str, float] = field(default_factory=dict)
    engagement: dict[str, Any] = field(default_factory=dict)
    content_type: str = "post"
    source_mode: str = ""
    known_from_run: str = ""          # set on refresh when this item existed in an earlier run
    changed_since_known: bool = False  # refresh found different content for an item seen before
    derived_from: dict[str, str] = field(default_factory=dict)   # {run_id, item_id} for reprocessed items
    evidence_chain: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "ResearchItem":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in row.items() if k in names})

    def add_transformation(self, step: str, **detail: Any) -> None:
        self.transformations.append({"step": step, "at": utc_now(), **detail})

    def add_node(self, node_type: str, *, parent: str = "", data: dict[str, Any] | None = None, key: str = "") -> LineageNode:
        node = LineageNode(id=f"{node_type[:2]}_{_sha(f'{self.item_id}|{node_type}|{parent}|{key}')}", type=node_type,
                           parent=parent, created_at=utc_now(), data=dict(data or {}))
        if not any(n["id"] == node.id for n in self.evidence_chain):
            self.evidence_chain.append(node.__dict__.copy())
        return node

    def trace_back(self, node_id: str) -> list[dict[str, Any]]:
        """Chain from ``node_id`` back to the originating search result (nearest first)."""
        by_id = {n["id"]: n for n in self.evidence_chain}
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        current = by_id.get(node_id)
        while current and current["id"] not in seen:
            chain.append(current)
            seen.add(current["id"])
            current = by_id.get(current.get("parent", ""))
        return chain


def start_chain(item: ResearchItem, *, query_id: str, query_text: str, dispatched: str) -> str:
    """search_result -> fetched_document. Returns the fetched_document node id."""
    result = item.add_node("search_result", data={"query_id": query_id, "query": query_text, "dispatched": dispatched,
                                                   "platform": item.platform, "discovered_at": item.retrieved_at})
    document = item.add_node("fetched_document", parent=result.id, data={
        "url": item.url, "native_id": item.native_id, "retrieved_at": item.retrieved_at,
        "source_mode": item.source_mode, "content_hash": item.content_hash, "chars": len(item.original_text)})
    return document.id


def extract_paragraphs(item: ResearchItem, *, split: bool = True) -> int:
    document = next((n for n in item.evidence_chain if n["type"] == "fetched_document"), None)
    parent = document["id"] if document else ""
    parts = split_paragraphs(item.original_text) if split else [(0, len(item.original_text), item.original_text.strip())]
    item.paragraphs = []
    for index, (start, end, text) in enumerate(parts):
        node = item.add_node("extracted_paragraph", parent=parent, key=str(index),
                             data={"index": index, "char_start": start, "char_end": end, "text_hash": _sha(text)})
        item.paragraphs.append({"index": index, "node_id": node.id, "text": text, "char_start": start, "char_end": end})
    item.add_transformation("extract_paragraphs", count=len(item.paragraphs))
    return len(item.paragraphs)


def matches_exclusion(text: str, exclusions: list[str]) -> str:
    """Return the first exclusion term found in ``text`` ('' if none). Whole-word for Latin, substring for others."""
    lowered = unicodedata.normalize("NFKC", text or "").casefold()
    for term in exclusions:
        needle = unicodedata.normalize("NFKC", term).casefold().strip()
        if not needle:
            continue
        if _CJK.search(needle) or not re.fullmatch(r"[\w\s'’-]+", needle):
            if needle in lowered:
                return term
        elif re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", lowered):
            return term
    return ""


def tag_geography(item: ResearchItem, plan_geography: list[str], *, query_geography: str = "", author_location: str = "") -> None:
    """Attach geographic tags: places named in the text/author location, and the query's place."""
    tags: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(name: str, method: str, confidence: float) -> None:
        if name and name not in seen:
            seen.add(name)
            tags.append({"name": name, "method": method, "confidence": confidence})

    haystack = f"{item.original_text}\n{author_location}".casefold()
    candidates = list(gz.all_countries()) + list(gz.REGIONS)
    for name in candidates:
        if re.search(rf"(?<![\w]){re.escape(name.casefold())}(?![\w])", haystack):
            add(name, "text_match", 0.7)
    if item.coordinates:
        add("coordinates", "platform_coordinates", 0.9)
    if query_geography:
        add(query_geography, "discovering_query", 0.4)
    elif not tags:
        for place in plan_geography[:1]:
            add(place, "plan_scope", 0.2)
    item.geography = tags


def record_to_item(record: Any, *, run_id: str, project_id: str, query_id: str, query_text: str,
                   dispatched: str) -> tuple[ResearchItem, str]:
    """Convert a collector ``PostRecord`` into an item; also returns the platform-supplied language code."""
    platform = str(getattr(record, "platform", "") or "")
    native = str(getattr(record, "native_id", "") or "")
    url = str(getattr(record, "canonical_url", "") or getattr(record, "source_url", "") or "")
    text = str(getattr(record, "original_text", "") or "")
    item = ResearchItem(
        item_id=item_id_for(platform, native, url), run_id=run_id, project_id=project_id, platform=platform,
        native_id=native, url=url, author=str(getattr(record, "author_name", "") or getattr(record, "author_handle", "") or ""),
        published_at=str(getattr(record, "published_at", "") or ""),
        retrieved_at=str(getattr(record, "collected_at", "") or utc_now()),
        query_id=query_id, query=query_text, query_dispatched=dispatched,
        queries=[query_text], original_text=text, content_type=str(getattr(record, "content_type", "post") or "post"),
        source_mode=str(getattr(record, "source_mode", "") or ""), engagement=dict(getattr(record, "engagement", {}) or {}),
        content_hash=_sha(text, 16),
    )
    lat, lon = getattr(record, "latitude", None), getattr(record, "longitude", None)
    if lat is not None and lon is not None:
        item.coordinates = {"lat": float(lat), "lon": float(lon)}
    platform_language = str(getattr(record, "platform_language", "") or getattr(record, "detected_language", "") or "")
    item.transformations.append({"step": "retrieved", "at": item.retrieved_at, "platform": platform, "source_mode": item.source_mode})
    return item, platform_language
