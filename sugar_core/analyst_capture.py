from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .models import PostRecord
from .storage import save_records
from .workspace import SugarWorkspace

_SECRET_KEY = re.compile(r"(?:token|secret|session|cookie|authorization|password|credential|api[_-]?key)", re.I)
_SECRET_TEXT = re.compile(
    r"(?i)(\b(?:access[_-]?token|auth[_-]?token|session[_-]?id|api[_-]?key|client[_-]?secret)\s*[:=]\s*)[^\s&;,<>\"]+"
    r"|\bBearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}"
    r"|\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    r"|\bsk-[A-Za-z0-9_-]{16,}\b"
)


def _sanitize_url(value: str, base_url: str = "") -> str:
    absolute = urljoin(base_url, str(value or "").strip())
    try:
        parsed = urlsplit(absolute)
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = hostname + (f":{parsed.port}" if parsed.port else "")
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"} or not netloc:
        return ""
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if not _SECRET_KEY.search(key)]
    return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), ""))


def _clean_text(value: str) -> str:
    return _SECRET_TEXT.sub(lambda match: f"{match.group(1) or ''}[REDACTED]", value)


def capture_saved_page(
    html_file: str | Path,
    *,
    source_url: str,
    workspace_path: str | Path,
) -> dict[str, Any]:
    """Import a user-saved public/authorized page snapshot without retaining executable HTML."""
    source = Path(html_file).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.casefold() not in {".html", ".htm"}:
        raise ValueError("Capture requires a saved .html or .htm page. MHTML and browser profile exports are not accepted.")
    safe_url = _sanitize_url(source_url)
    if not safe_url:
        raise ValueError("Provide the original public or authorized HTTP(S) page URL.")
    soup = BeautifulSoup(source.read_text(encoding="utf-8-sig", errors="replace"), "html.parser")
    for tag in soup.select("script, style, noscript, form, input, textarea, select, option, button, iframe, object, embed"):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        attrs = dict(tag.attrs)
        if "hidden" in attrs or str(attrs.get("aria-hidden") or "").casefold() == "true":
            tag.decompose()
            continue
        if _SECRET_KEY.search(" ".join([str(tag.get("id") or ""), str(tag.get("name") or "",), " ".join(tag.get("class") or [])])):
            tag.decompose()
            continue
        for key in attrs:
            if key.casefold().startswith("on") or _SECRET_KEY.search(key):
                tag.attrs.pop(key, None)
    title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    metadata: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        key = str(tag.get("property") or tag.get("name") or "").strip().casefold()
        if key in {"description", "article:published_time", "og:title", "og:description", "og:site_name"}:
            value = _clean_text(str(tag.get("content") or "").strip())
            if value:
                metadata[key] = value[:2000]
    media_refs = []
    for tag in soup.select("img[src], video[src], video[poster], audio[src], source[src]"):
        for attr in ("src", "poster"):
            value = tag.get(attr)
            if not value:
                continue
            safe_media_url = _sanitize_url(str(value or ""), safe_url)
            if safe_media_url:
                media_refs.append({"tag": tag.name, "url": safe_media_url})
    text = _clean_text(soup.get_text(" ", strip=True))
    text = " ".join(text.split())
    if not text:
        raise ValueError("No visible page text remained after removing scripts, controls, and hidden content.")
    workspace = SugarWorkspace.open(workspace_path)
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "schema_version": "1.0",
        "capture_method": "analyst_saved_html_import",
        "source_url": safe_url,
        "captured_at": captured_at,
        "title": title,
        "metadata": metadata,
        "visible_text": text,
        "media_references": sorted({(item["tag"], item["url"]) for item in media_refs}),
        "guardrails": [
            "This imports a page file saved by the analyst; it does not automate login or bypass access controls.",
            "Scripts, forms, hidden elements, frames, executable content, and credential-like URL parameters are removed.",
            "The saved HTML is not retained. The preserved artifact is sanitized visible text and public media references.",
        ],
    }
    payload["media_references"] = [{"tag": tag, "url": url} for tag, url in payload["media_references"]]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    capture_id = f"capture_{digest[:24]}"
    raw_dir = workspace.path_for("raw")
    capture_path = raw_dir / f"{capture_id}.json"
    capture_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    record = PostRecord(
        platform="analyst_capture",
        native_id=capture_id,
        canonical_url=safe_url,
        query="manual analyst capture",
        content_type="web_page_capture",
        source_mode="analyst_saved_page",
        source_host=urlsplit(safe_url).hostname or "",
        source_url=safe_url,
        collected_at=captured_at,
        published_at=metadata.get("article:published_time", ""),
        original_text=text,
        raw_stats={"title": title, "metadata": metadata, "media_references": payload["media_references"], "capture_sha256": digest},
    )
    records_path = raw_dir / f"{capture_id}.csv"
    save_records([record], records_path, metadata={"capture_method": payload["capture_method"]})
    workspace.register_artifact("evidence", records_path, metadata={"capture_id": capture_id, "sha256": digest})
    workspace.register_artifact("analyst_capture", capture_path, metadata={"capture_id": capture_id, "sha256": digest})
    payload["capture_id"] = capture_id
    payload["sha256"] = digest
    payload["record_file"] = str(records_path)
    payload["snapshot_file"] = str(capture_path)
    return payload
