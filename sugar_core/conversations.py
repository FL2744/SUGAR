from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .triage_io import load_post_records


def build_conversation_view(records: list[Any], *, conversation_id: str = "") -> dict[str, Any]:
    by_key = {record.record_key: record for record in records if record.record_key}
    grouped: dict[str, list[Any]] = {}
    for record in records:
        if conversation_id and str(record.conversation_id) != conversation_id:
            continue
        root = str(record.conversation_id or record.thread_root_key or record.parent_record_key or record.record_key or "unthreaded")
        if ":" not in root and record.platform:
            root = f"{record.platform}:{root}"
        grouped.setdefault(root, []).append(record)

    conversations: list[dict[str, Any]] = []
    for root, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: (str(item.published_at or item.collected_at or ""), item.record_key))
        rows: list[dict[str, Any]] = []
        for record in ordered:
            parent = str(record.parent_record_key or "")
            quoted = str(record.quoted_record_key or "")
            if parent and parent in by_key:
                link_state = "parent_collected"
            elif parent:
                link_state = "parent_not_collected"
            else:
                link_state = "root_or_no_parent"
            rows.append({
                "record_key": record.record_key, "platform": record.platform,
                "actor_handle": record.author_handle, "actor_name": record.author_name,
                "published_at": record.published_at, "collected_at": record.collected_at,
                "text": record.original_text, "translation": record.translated_text,
                "language": record.platform_language or record.detected_language,
                "canonical_url": record.canonical_url, "source_url": record.source_url,
                "content_type": record.content_type, "is_repost": bool(record.is_repost),
                "parent_record_key": parent, "thread_root_key": record.thread_root_key,
                "conversation_id": record.conversation_id, "reply_to_actor": record.reply_to_actor,
                "quoted_record_key": quoted, "mentioned_actors": record.mentioned_actors,
                "link_state": link_state, "source_mode": record.source_mode,
            })
        conversations.append({
            "conversation_id": root, "platforms": sorted({str(item.platform) for item in ordered if item.platform}),
            "record_count": len(rows), "actors": sorted({str(item.author_handle) for item in ordered if item.author_handle}),
            "items": rows,
        })
    return {
        "schema_version": "1.0", "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "conversation_count": len(conversations), "record_count": sum(row["record_count"] for row in conversations),
        "conversations": conversations,
        "method_note": "Conversation links are only those present in source records. Parent, quote, mention, and actor links are not inferred when absent.",
    }


def save_conversation_view(
    source_file: str | Path,
    output_file: str | Path,
    *,
    conversation_id: str = "",
) -> str:
    records = load_post_records(source_file)
    payload = build_conversation_view(records, conversation_id=conversation_id)
    payload["source_file"] = Path(source_file).name
    target = Path(output_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return str(target)
