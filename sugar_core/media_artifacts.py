from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TIME_RE = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):([0-5]?\d)(?:[.,](\d{1,3}))?$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_source_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlsplit(text)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Media source URL must use HTTP or HTTPS.")
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname + (f":{parsed.port}" if parsed.port else "")
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
             if not re.search(r"token|secret|session|cookie|auth|password|api[_-]?key", key, re.I)]
    return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), ""))


def _probe_media(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        return {"status": "unavailable", "tool": "ffprobe"}
    try:
        result = subprocess.run(
            [executable, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
            check=True, capture_output=True, text=True, timeout=15,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"status": "failed", "tool": "ffprobe"}
    streams = payload.get("streams") or []
    image_stream = next((row for row in streams if row.get("width") and row.get("height")), {})
    duration = (payload.get("format") or {}).get("duration")
    return {
        "status": "available",
        "duration_seconds": float(duration) if duration else None,
        "width": image_stream.get("width"),
        "height": image_stream.get("height"),
        "stream_types": sorted({str(row.get("codec_type")) for row in streams if row.get("codec_type")}),
    }


def parse_timestamp(value: str) -> float:
    match = _TIME_RE.fullmatch(str(value).strip())
    if not match:
        raise ValueError(f"Invalid media timestamp: {value!r}; use HH:MM:SS.mmm or MM:SS.mmm.")
    hours, minutes, seconds, millis = match.groups()
    total = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
    return total + (int((millis or "0").ljust(3, "0")) / 1000)


def _transcript_cues(text: str) -> list[dict[str, Any]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        match = re.match(r"\s*(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})", lines[index])
        if not match:
            index += 1
            continue
        start, end = parse_timestamp(match.group(1)), parse_timestamp(match.group(2))
        index += 1
        cue_lines = []
        while index < len(lines) and lines[index].strip():
            cue_lines.append(lines[index].strip())
            index += 1
        if cue_lines and end >= start:
            cues.append({"start_seconds": start, "end_seconds": end, "text": " ".join(cue_lines)})
    return cues


def ingest_media(
    source: str | Path,
    output_directory: str | Path,
    *,
    source_url: str = "",
    parent_record_id: str = "",
    language: str = "",
    transcript_file: str | Path | None = None,
    ocr_file: str | Path | None = None,
) -> dict[str, Any]:
    media_path = Path(source).expanduser().resolve(strict=True)
    if not media_path.is_file():
        raise ValueError("Media source must be one local image, audio, or video file.")
    mime_type = mimetypes.guess_type(media_path.name)[0] or "application/octet-stream"
    if not mime_type.startswith(("image/", "audio/", "video/")):
        raise ValueError(f"Unsupported media type {mime_type!r}; expected an image, audio, or video file.")
    target_root = Path(output_directory).expanduser().resolve()
    media_root = target_root / "media" if (target_root / "sugar-project.json").is_file() else target_root
    media_root.mkdir(parents=True, exist_ok=True)
    digest = _sha256(media_path)
    artifact_id = f"media_{digest[:24]}"
    suffix = media_path.suffix.casefold()[:16]
    stored_media = media_root / f"{artifact_id}{suffix}"
    if not stored_media.is_file() or _sha256(stored_media) != digest:
        temporary_media = stored_media.with_suffix(stored_media.suffix + ".tmp")
        shutil.copy2(media_path, temporary_media)
        if _sha256(temporary_media) != digest:
            temporary_media.unlink(missing_ok=True)
            raise IOError("Media integrity check failed after copying the local artifact.")
        temporary_media.replace(stored_media)
    derivatives = []
    for kind, raw in (("transcript", transcript_file), ("ocr", ocr_file)):
        if raw is None:
            continue
        derivative_path = Path(raw).expanduser().resolve(strict=True)
        if not derivative_path.is_file():
            raise ValueError(f"{kind} source must be a file.")
        text = derivative_path.read_text(encoding="utf-8-sig")
        out = media_root / f"{artifact_id}.{kind}.txt"
        out.write_text(text, encoding="utf-8")
        derivatives.append({
            "artifact_id": f"{artifact_id}_{kind}",
            "kind": kind,
            "path": out.name,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "language": str(language).strip().casefold(),
            "provenance": "analyst-supplied derivative; extraction tool and method were not inferred",
            "human_review_state": "unreviewed",
            "timestamped_cues": _transcript_cues(text) if kind == "transcript" else [],
        })
    manifest = {
        "schema_version": "1.0",
        "artifact_id": artifact_id,
        "parent_record_id": str(parent_record_id).strip(),
        "source_url": _safe_source_url(source_url),
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "media_type": mime_type.split("/", 1)[0],
        "mime_type": mime_type,
        "filename": media_path.name,
        "stored_path": stored_media.name,
        "sha256": digest,
        "bytes": stored_media.stat().st_size,
        "metadata_probe": _probe_media(stored_media),
        "derivatives": derivatives,
        "human_review_state": "unreviewed",
        "guardrails": [
            "Media is preserved from an analyst-supplied local file; this command does not bypass access controls or fetch platform content.",
            "Transcription and OCR are not run automatically. Supplied derivatives remain unreviewed and identify their provenance.",
            "Use artifact IDs and timestamp locators when citing a media segment; do not cite a whole post as if it proves every frame.",
        ],
    }
    manifest_path = media_root / f"{artifact_id}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if (target_root / "sugar-project.json").is_file():
        from .workspace import SugarWorkspace

        workspace = SugarWorkspace.open(target_root)
        workspace.register_artifact("media_artifact", stored_media, metadata={"artifact_id": artifact_id, "sha256": digest})
        workspace.register_artifact("media_manifest", manifest_path, metadata={"artifact_id": artifact_id})
        for derivative in derivatives:
            workspace.register_artifact("media_derivative", media_root / derivative["path"], metadata=derivative)
    return manifest


def build_media_citation(
    manifest_file: str | Path,
    *,
    start: str,
    end: str,
    quote: str = "",
) -> dict[str, Any]:
    path = Path(manifest_file).expanduser().resolve(strict=True)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not str(manifest.get("artifact_id") or "").startswith("media_"):
        raise ValueError("Input is not a SUGAR media manifest.")
    start_seconds, end_seconds = parse_timestamp(start), parse_timestamp(end)
    if end_seconds < start_seconds:
        raise ValueError("Media citation end must be at or after its start.")
    duration = (manifest.get("metadata_probe") or {}).get("duration_seconds")
    if duration is not None and end_seconds > float(duration):
        raise ValueError("Media citation end exceeds the measured artifact duration.")
    return {
        "media_artifact_id": manifest["artifact_id"],
        "media_sha256": manifest.get("sha256", ""),
        "source_url": manifest.get("source_url", ""),
        "locator": {"start": start, "end": end, "start_seconds": start_seconds, "end_seconds": end_seconds},
        "quote_or_description": str(quote).strip(),
        "review_state": "unreviewed",
    }


def attach_media_citation(
    observations_file: str | Path,
    output_file: str | Path,
    *,
    observation_id: str,
    citation: dict[str, Any],
    quote: str = "",
) -> str:
    from .observation_storage import load_observations, save_observations
    from .observations import EvidenceReference

    observations = load_observations(observations_file)
    target = next((item for item in observations if item.observation_id == str(observation_id).strip()), None)
    if target is None:
        raise ValueError(f"Observation ID not found: {observation_id}")
    locator = citation["locator"]
    locator_value = f"t={locator['start']}-{locator['end']}"
    media_id = str(citation["media_artifact_id"])
    if any(item.media_artifact_id == media_id and item.media_locator == locator_value for item in target.evidence):
        raise ValueError("This media artifact citation is already attached to the observation.")
    target.evidence.append(EvidenceReference(
        url=str(citation.get("source_url") or ""),
        title=f"Media evidence {media_id}",
        platform="media",
        native_id=media_id,
        source_type="analyst_preserved_media",
        note=str(quote).strip(),
        media_artifact_id=media_id,
        media_locator=locator_value,
    ))
    save_observations(observations, output_file)
    return str(Path(output_file).expanduser().resolve())
