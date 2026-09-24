from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path
from typing import Any

from .research_workspace import build_conversations


def _load_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]
    if suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Conversation JSONL line {line_number} must be an object.")
            rows.append(payload)
        return rows
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("records", "posts", "items"):
                values = payload.get(key)
                if isinstance(values, list):
                    return [dict(item) for item in values if isinstance(item, dict)]
            return [payload]
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd
        frame = pd.read_excel(path)
        return frame.where(frame.notna(), "").to_dict(orient="records")
    raise ValueError("Conversation input must be CSV, XLSX/XLS, JSON, or JSONL.")


def save_conversation_view(
    source_file: str | Path,
    output_file: str | Path,
    *,
    title: str = "SUGAR Conversation View",
) -> str:
    source = Path(source_file).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    conversations = build_conversations(_load_records(source))
    target = Path(output_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    blocks: list[str] = []
    for index, conversation in enumerate(conversations, 1):
        if not conversation:
            continue
        rows = []
        for message in conversation:
            meta = " · ".join(
                value for value in (
                    escape(message.platform),
                    escape(message.published_at),
                ) if value
            )
            source_link = (
                f'<a href="{escape(message.url, quote=True)}" target="_blank" rel="noopener noreferrer">source</a>'
                if message.url.startswith(("http://", "https://"))
                else ""
            )
            rows.append(
                '<div class="message">'
                f'<div class="speaker">{escape(message.author)}</div>'
                f'<div class="meta">{meta}{(" · " + source_link) if source_link else ""}</div>'
                f'<div class="text">{escape(message.text).replace(chr(10), "<br>")}</div>'
                '</div>'
            )
        blocks.append(
            f'<section class="conversation"><h2>Conversation {index}</h2>{"".join(rows)}</section>'
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f5f7fb;color:#172033;margin:0;padding:28px;}}
main{{max-width:980px;margin:auto;}}
h1{{margin:0 0 6px;}} .subtitle{{color:#637087;margin-bottom:24px;}}
.conversation{{background:white;border:1px solid #dfe5ef;border-radius:10px;padding:18px;margin:0 0 20px;}}
.conversation h2{{font-size:15px;margin:0 0 12px;color:#33415a;}}
.message{{border-left:4px solid #2d6cc0;padding:10px 12px;margin:10px 0;background:#f8fbff;border-radius:0 7px 7px 0;}}
.speaker{{font-weight:700;color:#17345d;}} .meta{{font-size:12px;color:#6e7b91;margin:2px 0 6px;}}
.text{{white-space:normal;line-height:1.45;}}
a{{color:#235fa8;}}
</style>
</head>
<body><main>
<h1>{escape(title)}</h1>
<div class="subtitle">{len(conversations)} reconstructed conversation group(s). Speaker identities remain separate; ordering uses explicit reply/thread relationships and timestamps where available.</div>
{"".join(blocks) if blocks else "<p>No conversation records could be reconstructed.</p>"}
</main></body></html>"""
    target.write_text(html, encoding="utf-8")
    metadata = {
        "schema_version": "1.0",
        "source_file": str(source),
        "conversation_count": len(conversations),
        "message_count": sum(len(item) for item in conversations),
        "method": "explicit thread/reply fields where present; no inferred private identity",
    }
    target.with_suffix(target.suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(target)
