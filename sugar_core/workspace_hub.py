from __future__ import annotations

import json
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

import pandas as pd

from .conversations import save_conversation_view
from .listening_posts import (
    capture_monitor_material,
    complete_monitor_run,
    due_monitors,
    list_monitors,
    list_monitor_material,
    review_monitor_material,
    save_monitor,
    set_monitor_status,
)
from .mapping import MapOptions, ReferenceLayer, create_map, load_map_frame
from .official_baselines import sync_official_baselines
from .project_bundle import export_project_bundle, import_project_bundle
from .reference_registry import (
    add_relationship,
    compare_entities,
    entity_profile,
    export_registry,
    import_reference_dataset,
    list_entities,
    list_lifecycle,
    list_relationships,
    preview_reference_import,
    registry_paths,
    upsert_entity,
)
from .service import run_search
from .workspace import SugarWorkspace
from .workspace_memory import (
    create_subproject,
    dashboard,
    list_project_history,
    list_projects,
    link_subproject,
    log_project_event,
    record_project_run,
)


ProgressCallback = Callable[[str, dict[str, Any]], None]


def _emit(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


def _workspace(config: dict[str, Any], *, required: bool = True) -> SugarWorkspace | None:
    path = str(config.get("workspace") or "").strip()
    if path:
        return SugarWorkspace.open(path)
    if required:
        raise ValueError("Choose a SUGAR project workspace first.")
    return None


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return str(path)


def _project_file_path(workspace: SugarWorkspace | None, value: Any) -> Path:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.casefold() in {"sugar-workspace", "sugar-file"}:
        if workspace is None or parsed.hostname != workspace.manifest.project_id:
            raise ValueError("The selected file does not belong to this project.")
        relative = unquote(parsed.path).lstrip("/")
        target = (workspace.root / relative).resolve()
        try:
            target.relative_to(workspace.root)
        except ValueError as exc:
            raise ValueError("Project file references cannot leave the selected workspace.") from exc
        return target
    if not raw:
        raise ValueError("Choose a project data file first.")
    return Path(raw).expanduser().resolve()


def _load_dataset_rows(source_file: str) -> tuple[list[dict[str, Any]], list[str]]:
    source = Path(source_file).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.casefold() in {".jsonl", ".ndjson"}:
        rows: list[dict[str, Any]] = []
        with source.open("r", encoding="utf-8-sig") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"Dataset row {line_number} must be a JSON object.")
                rows.append(value)
        return rows, sorted({str(key) for row in rows for key in row})
    from .reference_registry import load_reference_table
    return load_reference_table(source)


def _dataset_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _geography_assignments_path(workspace: SugarWorkspace) -> Path:
    return workspace.internal_path / "geography-assignments.json"


def _read_geography_assignments(workspace: SugarWorkspace) -> dict[str, Any]:
    path = _geography_assignments_path(workspace)
    if not path.is_file():
        return {"datasets": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Geography annotations are unreadable; restore or remove .sugar/geography-assignments.json.") from exc
    if not isinstance(value, dict) or not isinstance(value.get("datasets", {}), dict):
        raise ValueError("Geography annotations have an invalid format.")
    return value


def _apply_geography_assignments(
    workspace: SugarWorkspace, source: Path, rows: list[dict[str, Any]], *, include_row_number: bool = False,
) -> list[dict[str, Any]]:
    dataset_id = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()
    dataset = _read_geography_assignments(workspace).get("datasets", {}).get(dataset_id, {})
    if dataset.get("sha256") != _dataset_fingerprint(source):
        return rows
    assignments = dataset.get("rows", {})
    result = []
    for index, original in enumerate(rows):
        row = dict(original)
        row_number = int(row.get("_sugar_row_number", index))
        annotation = assignments.get(str(row_number)) if isinstance(assignments, dict) else None
        if isinstance(annotation, dict):
            for field in ("country", "region", "city"):
                value = str(annotation.get(field) or "").strip()
                if value:
                    row[f"analyst_{field}"] = value
            row["location_provenance"] = "analyst_manual"
            row["location_note"] = str(annotation.get("note") or "")
        if include_row_number:
            row["_sugar_row_number"] = row_number
        result.append(row)
    return result


def _assign_dataset_geography(workspace: SugarWorkspace, source: Path, row_number: int, values: dict[str, Any]) -> dict[str, Any]:
    rows, _columns = _load_dataset_rows(str(source))
    if row_number < 0 or row_number >= len(rows):
        raise ValueError(f"Dataset row number must be between 0 and {max(0, len(rows) - 1)}.")
    location = {field: str(values.get(field) or "").strip() for field in ("country", "region", "city")}
    if not any(location.values()):
        raise ValueError("Enter at least one analyst-assigned country, region, or city.")
    note = str(values.get("note") or "").strip()
    if len(note) > 2000:
        raise ValueError("Geography assignment notes must be 2,000 characters or fewer.")
    dataset_id = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()
    document = _read_geography_assignments(workspace)
    datasets = document.setdefault("datasets", {})
    current_hash = _dataset_fingerprint(source)
    dataset = datasets.get(dataset_id, {})
    if dataset.get("sha256") != current_hash:
        dataset = {"source_name": source.name, "sha256": current_hash, "rows": {}}
    assignments = dataset.setdefault("rows", {})
    annotation = {
        **location, "note": note,
        "assigned_by": str(values.get("actor") or "Analyst")[:120],
        "assigned_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "provenance": "analyst_manual",
    }
    assignments[str(row_number)] = annotation
    datasets[dataset_id] = dataset
    path = Path(_write_json(_geography_assignments_path(workspace), document))
    workspace.register_artifact("geography_assignments", path, label="Analyst-assigned dataset geography", metadata={"dataset": source.name, "row_number": row_number})
    log_project_event(workspace, "dataset_geography_assigned", {"dataset": source.name, "row_number": row_number, "provenance": "analyst_manual"})
    return {"row_number": row_number, **annotation, "source_file": str(source)}


def _compare_region_groups(left: list[dict[str, Any]], right: list[dict[str, Any]], level: str) -> dict[str, Any]:
    left_summary = _geography_summary(left, level)
    right_summary = _geography_summary(right, level)
    left_groups = {str(item["label"]).casefold(): item for item in left_summary["groups"]}
    right_groups = {str(item["label"]).casefold(): item for item in right_summary["groups"]}
    groups = []
    for key in sorted(set(left_groups) | set(right_groups)):
        left_item, right_item = left_groups.get(key, {}), right_groups.get(key, {})
        left_share = float(left_item.get("share", 0.0))
        right_share = float(right_item.get("share", 0.0))
        groups.append({
            "label": left_item.get("label") or right_item.get("label"),
            "left_records": int(left_item.get("records", 0)), "right_records": int(right_item.get("records", 0)),
            "left_share": left_share, "right_share": right_share,
            "share_difference": round(right_share - left_share, 4),
        })
    return {
        "group_by": left_summary["group_by"],
        "left_total": left_summary["total_rows"], "right_total": right_summary["total_rows"],
        "left_located": left_summary["located_rows"], "right_located": right_summary["located_rows"],
        "groups": groups,
        "guardrail": "This is a descriptive comparison of supplied or analyst-assigned location labels. Different sample sizes, source coverage, and collection methods can explain differences; the comparison does not establish change, influence, or causation.",
    }


def _filter_dataset_rows(rows: list[dict[str, Any]], column: str = "", value: str = "") -> list[dict[str, Any]]:
    if not column or not value:
        return rows
    query = value.casefold()
    return [row for row in rows if query in str(row.get(column, "")).casefold()]


def _geography_value(row: dict[str, Any], level: str) -> str:
    row = {str(key).casefold(): value for key, value in row.items()}
    aliases = {
        "country": ("analyst_country", "country", "country_name", "country_code"),
        "region": ("analyst_region", "region", "admin1", "admin_region", "state", "province"),
        "city": ("analyst_city", "city", "town", "locality"),
    }
    if level == "coordinate_grid":
        try:
            latitude = float(str(row.get("latitude") or row.get("lat") or "").strip())
            longitude = float(str(row.get("longitude") or row.get("lon") or row.get("lng") or "").strip())
        except (TypeError, ValueError):
            return "Unlocated"
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return "Unlocated"
        return f"{latitude:.2f}, {longitude:.2f}"
    if level == "hierarchy":
        parts = []
        for key in ("analyst_country", "country", "country_name", "analyst_region", "region", "admin1", "admin_region", "state", "province", "analyst_city", "city", "town", "locality"):
            value = str(row.get(key) or "").strip()
            if value and value.casefold() not in {part.casefold() for part in parts}:
                parts.append(value)
        if parts:
            return " / ".join(parts)
        return _geography_value(row, "coordinate_grid")
    for key in aliases.get(level, ()):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return "Unspecified"


def _geography_summary(rows: list[dict[str, Any]], level: str) -> dict[str, Any]:
    supported = {"country", "region", "city", "coordinate_grid"}
    selected = level.strip().casefold() or "auto"
    if selected == "auto":
        selected = "hierarchy"
    if selected not in supported | {"hierarchy"}:
        raise ValueError("Geographic grouping supports auto, country, region, city, or coordinate_grid.")
    counts: dict[str, int] = {}
    located = 0
    for row in rows:
        value = _geography_value(row, selected)
        if value != "Unlocated" and value != "Unspecified":
            located += 1
        counts[value] = counts.get(value, 0) + 1
    total = len(rows)
    groups = [
        {"label": label, "records": count, "share": round(count / total, 4) if total else 0.0}
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]
    return {
        "group_by": selected,
        "total_rows": total,
        "located_rows": located,
        "unlocated_rows": total - located,
        "groups": groups,
        "guardrail": "Geographic groups summarize supplied location fields or coordinate grid cells; they do not establish influence, coordination, or causation.",
    }


def _event_result(progress: ProgressCallback | None, action: str, payload: Any) -> list[str]:
    _emit(progress, "workspace_hub_data", action=action, data=payload)
    return []


def _project_research_state(workspace: SugarWorkspace) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for key, filename in (
        ("research_requirement", "research-requirement.json"),
        ("search_plan", "search-plan.json"),
        ("research_strategy", "research-strategy.json"),
    ):
        path = workspace.path_for("state") / filename
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            state[key] = payload
    return state


def _project_profile_path(workspace: SugarWorkspace) -> Path:
    return workspace.internal_path / "project-profile.json"


def _project_comments_path(workspace: SugarWorkspace) -> Path:
    return workspace.internal_path / "project-comments.jsonl"


def _load_project_comments(workspace: SugarWorkspace) -> list[dict[str, Any]]:
    path = _project_comments_path(workspace)
    if not path.is_file():
        return []
    comments = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                comments.append(item)
    return comments[-100:]


def _add_project_comment(workspace: SugarWorkspace, config: dict[str, Any]) -> dict[str, Any]:
    body = str(config.get("body") or "").strip()
    if not body or len(body) > 10_000:
        raise ValueError("A project comment must contain 1 to 10,000 characters.")
    actor = str(config.get("actor") or "Analyst").strip()[:120] or "Analyst"
    comment = {
        "comment_id": uuid.uuid4().hex,
        "actor": actor,
        "body": body,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    path = _project_comments_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(comment, ensure_ascii=False) + "\n")
    workspace.register_artifact("project_comments", path, label="Project discussion", metadata={"comment_count": len(_load_project_comments(workspace))})
    log_project_event(workspace, "project_comment_added", {"comment_id": comment["comment_id"], "actor": actor})
    return comment


def _load_project_profile(workspace: SugarWorkspace) -> dict[str, Any]:
    path = _project_profile_path(workspace)
    if not path.is_file():
        return {"notes": "", "members": [], "access_control": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Project profile is unreadable; restore or remove .sugar/project-profile.json.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Project profile must contain a JSON object.")
    notes = str(payload.get("notes") or "")
    members = payload.get("members") or []
    if not isinstance(members, list):
        raise ValueError("Project members must be a list.")
    return {"notes": notes, "members": members, "access_control": False}


def _validate_project_profile(config: dict[str, Any]) -> dict[str, Any]:
    notes = str(config.get("notes") or "").strip()
    if len(notes) > 100_000:
        raise ValueError("Project notes must be 100,000 characters or fewer.")
    members_raw = config.get("members") or []
    if not isinstance(members_raw, list) or len(members_raw) > 100:
        raise ValueError("Project members must be a list of at most 100 people.")
    members: list[dict[str, str]] = []
    seen_emails: set[str] = set()
    for index, raw in enumerate(members_raw, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Project member {index} must be an object.")
        name = str(raw.get("name") or "").strip()
        email = str(raw.get("email") or "").strip()
        role = str(raw.get("role") or "analyst").strip()
        if not name or len(name) > 120:
            raise ValueError(f"Project member {index} requires a name of 1 to 120 characters.")
        if len(email) > 254 or (email and ("@" not in email or any(ch.isspace() for ch in email))):
            raise ValueError(f"Project member {index} has an invalid email address.")
        if not role or len(role) > 60:
            raise ValueError(f"Project member {index} requires a role label of 1 to 60 characters.")
        email_key = email.casefold()
        if email_key and email_key in seen_emails:
            raise ValueError(f"Project member email addresses must be unique: {email}")
        if email_key:
            seen_emails.add(email_key)
        members.append({"name": name, "email": email, "role": role})
    return {"notes": notes, "members": members, "access_control": False}


def _registry_map_frame(workspace: SugarWorkspace) -> pd.DataFrame:
    entities = list_entities(workspace)
    entity_names = {entity["entity_id"]: entity.get("name", "") for entity in entities}
    relationship_rows = list_relationships(workspace)
    lifecycle_rows = list_lifecycle(workspace)
    rows = []
    for entity in entities:
        if entity.get("latitude") in (None, "") or entity.get("longitude") in (None, ""):
            continue
        status_resolution = entity.get("resolved_fields", {}).get("status", {})
        status_claims = status_resolution.get("claims", [])
        status_refs = [ref for claim in status_claims for ref in claim.get("evidence_refs", [])]
        status_source = next((ref.get("source_url") for ref in status_refs if ref.get("source_url")), "")
        related = []
        for relationship in relationship_rows:
            if entity["entity_id"] not in {relationship.get("source_entity_id"), relationship.get("target_entity_id")}:
                continue
            other_id = relationship.get("target_entity_id") if relationship.get("source_entity_id") == entity["entity_id"] else relationship.get("source_entity_id")
            related.append(f"{relationship.get('relationship_type', 'related_to')}: {entity_names.get(other_id, other_id)}")
        lifecycle = [f"{item.get('event_type')}: {item.get('effective_date') or item.get('observed_at')}" for item in lifecycle_rows if item.get("entity_id") == entity["entity_id"]]
        evidence_urls = []
        for claim in entity.get("claims", []):
            for ref in claim.get("evidence_refs", []):
                url = ref.get("source_url") if isinstance(ref, dict) else ""
                if url and url not in evidence_urls:
                    evidence_urls.append(url)
        description_parts = [entity.get("description", "")]
        if related:
            description_parts.append("Relationships: " + "; ".join(related))
        if lifecycle:
            description_parts.append("Lifecycle history: " + "; ".join(lifecycle))
        rows.append({
            "platform": entity.get("network") or "reference", "native_id": entity["entity_id"],
            "record_key": entity["entity_id"], "content_type": entity.get("entity_type", "institution"),
            "status": entity.get("status", "unknown"), "published_at": "",
            "status_date": entity.get("status_date", ""), "status_source_url": status_source,
            "opened_date": entity.get("opened_date", ""), "closed_date": entity.get("closed_date", ""),
            "location_precision": entity.get("location_precision", "unknown"),
            "author_name": entity.get("name", ""), "original_text": "\n".join(part for part in description_parts if part),
            "registry_id": entity.get("entity_id", ""), "evidence_urls": evidence_urls,
            "canonical_url": (entity.get("public_links") or [""])[0],
            "source_url": (entity.get("source_evidence") or [{}])[0].get("source_url", ""),
            "latitude": entity["latitude"], "longitude": entity["longitude"],
            "country": entity.get("country", ""), "city": entity.get("city", ""),
            "aliases": entity.get("aliases", []),
            "program_domains": entity.get("normalized_program_domains") or entity.get("program_domains", []),
            "audiences": entity.get("normalized_audiences") or entity.get("audiences", []),
            "delivery_modes": entity.get("normalized_delivery_modes") or entity.get("delivery_modes", []),
            "program_descriptions": entity.get("program_descriptions", []),
            "normalized_program_domains": entity.get("normalized_program_domains", []),
            "audience_descriptions": entity.get("audience_descriptions", []),
            "normalized_audiences": entity.get("normalized_audiences", []),
            "delivery_mode_descriptions": entity.get("delivery_mode_descriptions", []),
            "normalized_delivery_modes": entity.get("normalized_delivery_modes", []),
            "coverage_scope": entity.get("coverage_scope", []), "accounts": entity.get("accounts", []),
            "relationship_summary": related,
            "verification_state": "human_verified" if entity.get("resolved_fields", {}).get("name", {}).get("state", "") == "human_verified" else "unreviewed",
        })
    return pd.DataFrame(rows)


def _run_monitor(
    workspace: SugarWorkspace,
    monitor: dict[str, Any],
    secrets: dict[str, str],
    progress: ProgressCallback | None,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    terms = list(monitor.get("terms") or []) or list(monitor.get("target_entities") or [])
    output_dir = workspace.path_for("raw") / "listening_posts" / str(monitor["monitor_id"])
    config = {
        "workspace": str(workspace.root), "sources": list(monitor.get("sources") or []),
        "terms": terms, "since": monitor.get("since") or "", "until": monitor.get("until") or "",
        "post_languages": list(monitor.get("post_languages") or []),
        "max_posts_per_query": int(monitor.get("max_posts_per_query", 20)),
        "max_pages_per_query": int(monitor.get("max_pages_per_query", 1)),
        "translate_posts": False, "infer_locations": False, "translate_term_languages": [],
        "continue_on_source_error": True, "output_directory": str(output_dir),
    }
    if monitor.get("last_run_at"):
        previous = datetime.fromisoformat(str(monitor["last_run_at"]).replace("Z", "+00:00"))
        config["since"] = (previous - timedelta(hours=24)).date().isoformat()
        config["until"] = datetime.now(timezone.utc).date().isoformat()
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    _emit(progress, "listening_post_run_start", monitor_id=monitor["monitor_id"], run_id=run_id,
          sources=config["sources"], terms=terms)
    try:
        outputs = run_search(config, secrets, progress=progress)
        coverage_file = next((Path(item) for item in outputs if str(item).endswith(".coverage.json")), None)
        coverage = json.loads(coverage_file.read_text(encoding="utf-8")) if coverage_file and coverage_file.is_file() else {}
        source_rows = coverage.get("sources", {})
        statuses = [str(row.get("status") or "") for row in source_rows.values() if isinstance(row, dict)] if isinstance(source_rows, dict) else []
        status = "partial" if any(item in {"failed", "unavailable", "partial", "blocked"} for item in statuses) else "succeeded"
        csv_file = next((Path(item) for item in outputs if Path(item).suffix.casefold() == ".csv"), None)
        if csv_file and csv_file.is_file():
            with csv_file.open("r", encoding="utf-8-sig") as stream:
                count = max(0, sum(1 for _ in stream) - 1)
        else:
            count = None
        if count == 0 and status == "succeeded":
            status = "zero_result"
        material = capture_monitor_material(workspace, monitor, csv_file, run_id=run_id) if csv_file else {
            "new": 0, "updated": 0, "unchanged": 0, "new_material_file": "", "material_count": 0,
        }
        if material.get("new_material_file"):
            outputs = [*outputs, material["new_material_file"]]
        record_project_run(workspace, command="listening_post", config={"monitor_id": monitor["monitor_id"], **config},
                           outputs=outputs, status=status, run_id=run_id, started_at=started_at)
        saved = complete_monitor_run(workspace, monitor["monitor_id"], run_id=run_id, status=status, outputs=outputs)
        return {"monitor": saved, "run_id": run_id, "status": status, "record_count": count,
                "new_material": material, "coverage": coverage, "outputs": outputs}
    except Exception as exc:
        safe_error = str(exc)
        for value in secrets.values():
            secret = str(value or "")
            if len(secret) >= 8:
                safe_error = safe_error.replace(secret, "[REDACTED]")
        record_project_run(workspace, command="listening_post", config={"monitor_id": monitor["monitor_id"], **config},
                           status="failed", error=safe_error, run_id=run_id, started_at=started_at)
        complete_monitor_run(workspace, monitor["monitor_id"], run_id=run_id, status="failed", outputs=[], error=safe_error)
        raise


def run_workspace_hub(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    secrets = secrets or {}
    action = str(config.get("action") or "dashboard").strip().casefold().replace("_", "-")
    workspace = None if action in {"project-list", "project-import"} else _workspace(config)

    if action == "project-list":
        root = str(config.get("projects_root") or config.get("workspace") or "").strip()
        if not root:
            raise ValueError("Choose a folder containing SUGAR projects.")
        return _event_result(progress, action, list_projects(root))

    if action == "dashboard":
        data = dashboard(workspace)
        data.update(_project_research_state(workspace))
        data["project_profile"] = _load_project_profile(workspace)
        return _event_result(progress, action, data)

    if action == "project-profile":
        return _event_result(progress, action, _load_project_profile(workspace))

    if action == "project-profile-update":
        profile = _validate_project_profile(config)
        _write_json(_project_profile_path(workspace), profile)
        workspace.register_artifact(
            "project_profile",
            _project_profile_path(workspace),
            label="Project notes and member roster",
            metadata={"member_count": len(profile["members"]), "access_control": False},
        )
        log_project_event(
            workspace,
            "project_profile_updated",
            {"member_count": len(profile["members"]), "notes_characters": len(profile["notes"])},
        )
        return _event_result(progress, action, profile)

    if action == "project-comment-list":
        return _event_result(progress, action, {"comments": _load_project_comments(workspace)})

    if action == "project-comment-add":
        return _event_result(progress, action, _add_project_comment(workspace, config))

    if action == "research-template-list":
        from .research_templates import list_research_templates
        return _event_result(progress, action, {"templates": list_research_templates(workspace)})

    if action == "research-template-save":
        from .research_templates import save_research_template
        fields = config.get("fields") or {}
        if not isinstance(fields, dict):
            raise ValueError("Research template fields must be an object.")
        template = save_research_template(workspace, str(config.get("name") or ""), fields)
        return _event_result(progress, action, template)

    if action == "project-create-subproject":
        child = create_subproject(workspace, str(config.get("name") or ""), description=str(config.get("description") or ""))
        return _event_result(progress, action, {"project_id": child.manifest.project_id,
                                                 "name": child.manifest.name, "root": str(child.root),
                                                 "parent_project_id": workspace.manifest.project_id})

    if action == "project-history":
        return _event_result(progress, action, list_project_history(workspace, limit=int(config.get("limit", 300))))

    if action == "project-export":
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", workspace.manifest.name.casefold()).strip("-") or "sugar-project"
        target = Path(str(config.get("output_file") or (workspace.path_for("exports") / f"{slug}.sugar.zip"))).expanduser().resolve()
        report = export_project_bundle(workspace, target)
        log_project_event(workspace, "project_bundle_exported", report)
        return _event_result(progress, action, report) + [str(target)]

    if action == "project-import":
        target = Path(str(config.get("destination") or "")).expanduser().resolve()
        if not str(config.get("destination") or "").strip():
            raise ValueError("Choose a new project import destination.")
        parent_path = str(config.get("parent_workspace") or "").strip()
        parent_workspace = SugarWorkspace.open(parent_path) if parent_path else None
        if parent_workspace is not None:
            try:
                target.relative_to(parent_workspace.root)
            except ValueError as exc:
                raise ValueError("To link an imported project as a subproject, choose its destination inside the parent project folder.") from exc
            if target == parent_workspace.root:
                raise ValueError("An imported project cannot replace its parent project folder.")
        report = import_project_bundle(str(config.get("bundle") or ""), target)
        opened = SugarWorkspace.open(target)
        if parent_workspace is not None:
            link_subproject(parent_workspace, opened)
        log_project_event(opened, "project_bundle_imported", {"source_bundle": Path(str(config["bundle"])).name})
        return _event_result(progress, action, report) + [str(target / "sugar-project.json")]

    if action == "registry-list":
        rows = list_entities(workspace, filters=config.get("filters") if isinstance(config.get("filters"), dict) else config)
        return _event_result(progress, action, {"entities": rows, "count": len(rows),
                                                 "relationships": sum(1 for _ in registry_paths(workspace)["relationships"].open(encoding="utf-8") if _.strip()) if registry_paths(workspace)["relationships"].exists() else 0})

    if action == "registry-template":
        from .reference_templates import REFERENCE_TEMPLATES, write_reference_template
        key = str(config.get("template") or "custom").strip()
        output = write_reference_template(workspace, key)
        template = REFERENCE_TEMPLATES[key.replace("-", "_").replace(" ", "_").casefold()]
        return _event_result(progress, action, {"template": key, "label": template["label"],
                                                  "network": template["network"], "path": output}) + [output]

    if action == "registry-preview":
        preview = preview_reference_import(str(config.get("source_file") or ""), sample_size=int(config.get("sample_size", 12)))
        if isinstance(config.get("mapping"), dict):
            preview["suggested_mapping"].update({str(k): str(v) for k, v in config["mapping"].items()})
        return _event_result(progress, action, preview)

    if action == "dataset-browse":
        source_file = str(_project_file_path(workspace, config.get("source_file")))
        rows, columns = _load_dataset_rows(source_file)
        rows = [{**row, "_sugar_row_number": index} for index, row in enumerate(rows)]
        rows = _apply_geography_assignments(workspace, Path(source_file), rows, include_row_number=True)
        filtered = _filter_dataset_rows(rows, str(config.get("filter_column") or ""), str(config.get("filter_value") or ""))
        maximum = max(1, min(5000, int(config.get("max_rows", 500))))
        return _event_result(progress, action, {"source_file": str(Path(source_file).expanduser().resolve()),
            "columns": columns, "row_count": len(rows), "matching_rows": len(filtered),
            "rows_shown": min(maximum, len(filtered)), "filter_column": str(config.get("filter_column") or ""),
            "filter_value": str(config.get("filter_value") or ""), "rows": filtered[:maximum]})

    if action == "dataset-geography-summary":
        source_file = str(_project_file_path(workspace, config.get("source_file")))
        rows, _columns = _load_dataset_rows(source_file)
        rows = _apply_geography_assignments(workspace, Path(source_file), rows)
        filtered = _filter_dataset_rows(rows, str(config.get("filter_column") or ""), str(config.get("filter_value") or ""))
        return _event_result(progress, action, _geography_summary(filtered, str(config.get("group_by") or "auto")))

    if action == "dataset-geography-assign":
        source_file = _project_file_path(workspace, config.get("source_file"))
        try:
            row_number = int(str(config.get("row_number", "")).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Dataset row number must be a non-negative integer.") from exc
        if row_number < 0:
            raise ValueError("Dataset row number must be a non-negative integer.")
        assigned = _assign_dataset_geography(workspace, source_file, row_number, config)
        return _event_result(progress, action, assigned)

    if action == "dataset-region-compare":
        left_path = _project_file_path(workspace, config.get("source_file"))
        right_path = _project_file_path(workspace, config.get("comparison_file"))
        left, _left_columns = _load_dataset_rows(str(left_path))
        right, _right_columns = _load_dataset_rows(str(right_path))
        left = _apply_geography_assignments(workspace, left_path, left)
        right = _apply_geography_assignments(workspace, right_path, right)
        level = str(config.get("group_by") or "auto")
        return _event_result(progress, action, _compare_region_groups(left, right, level))

    if action == "dataset-export":
        source_file = str(_project_file_path(workspace, config.get("source_file")))
        rows, _columns = _load_dataset_rows(source_file)
        rows = _apply_geography_assignments(workspace, Path(source_file), rows)
        filtered = _filter_dataset_rows(rows, str(config.get("filter_column") or ""), str(config.get("filter_value") or ""))
        export_format = str(config.get("format") or "").strip().casefold().lstrip(".")
        extension_for_format = {"csv": ".csv", "jsonl": ".jsonl", "ndjson": ".jsonl", "xlsx": ".xlsx", "json": ".json", "geojson": ".geojson"}
        if not export_format:
            export_format = Path(str(config.get("output_file") or "")).suffix.casefold().lstrip(".") or "csv"
        suffix = extension_for_format.get(export_format)
        if suffix is None:
            raise ValueError("Dataset export supports CSV, XLSX, JSONL, JSON, and GeoJSON.")
        if str(config.get("output_file") or "").strip():
            target = _project_file_path(workspace, config["output_file"])
        else:
            file_name = Path(str(config.get("file_name") or f"research-records{suffix}")).name
            target = workspace.path_for("exports") / file_name
        if target.suffix.casefold() != suffix:
            target = target.with_suffix(suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        if suffix == ".csv":
            pd.DataFrame(filtered).to_csv(target, index=False, encoding="utf-8-sig")
        elif suffix in {".jsonl", ".ndjson"}:
            target.write_text("".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in filtered), encoding="utf-8")
        elif suffix == ".xlsx":
            pd.DataFrame(filtered).to_excel(target, index=False)
        elif suffix == ".json":
            target.write_text(json.dumps(filtered, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        elif suffix == ".geojson":
            features = []
            for row in filtered:
                props = dict(row)
                try:
                    latitude = float(str(props.pop("latitude", "")).strip())
                    longitude = float(str(props.pop("longitude", "")).strip())
                    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                        geometry = {"type": "Point", "coordinates": [longitude, latitude]}
                    else:
                        geometry = None
                except (TypeError, ValueError):
                    geometry = None
                features.append({"type": "Feature", "geometry": geometry, "properties": props})
            target.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        else:
            raise ValueError("Dataset export supports CSV, XLSX, JSONL, JSON, and GeoJSON.")
        workspace.register_artifact("dataset_view_export", target, label="Filtered dataset export",
                                     metadata={"source_file": Path(source_file).name,
                                               "filter_column": str(config.get("filter_column") or ""),
                                               "filter_value": str(config.get("filter_value") or ""),
                                               "matching_rows": len(filtered)})
        return _event_result(progress, action, {"output_file": str(target), "matching_rows": len(filtered),
                                                 "source_file": source_file}) + [str(target)]

    if action == "registry-import":
        mapping = config.get("mapping")
        if isinstance(mapping, str):
            mapping = json.loads(mapping)
        if not isinstance(mapping, dict):
            raise ValueError("Confirm a canonical-field to source-column mapping before import.")
        result = import_reference_dataset(
            workspace, str(config.get("source_file") or ""), mapping={str(k): str(v) for k, v in mapping.items()},
            dataset_name=str(config.get("dataset_name") or ""), network=str(config.get("network") or ""),
            geographic_scope=str(config.get("geographic_scope") or ""),
            known_coverage_limits=str(config.get("known_coverage_limits") or ""),
            license_notes=str(config.get("license_notes") or ""), actor=str(config.get("actor") or "analyst"),
            review_state=str(config.get("review_state") or "unreviewed"),
            accept_partial=bool(config.get("accept_partial", False)),
        )
        return _event_result(progress, action, result)

    if action == "registry-sync-official-baselines":
        requested = config.get("sources") or ["american_spaces", "language_centers"]
        if isinstance(requested, str):
            requested = [item.strip() for item in requested.split(",") if item.strip()]
        result = sync_official_baselines(
            workspace,
            sources=requested,
            timeout=float(config.get("timeout") or 30.0),
            actor=str(config.get("actor") or "official-baseline-sync"),
        )
        return _event_result(progress, action, result)

    if action == "registry-upsert":
        values = config.get("entity") or {}
        evidence = config.get("evidence_refs") or []
        entity = upsert_entity(workspace, values, evidence_refs=evidence, actor=str(config.get("actor") or "analyst"),
                               reason=str(config.get("reason") or ""), review_state=str(config.get("review_state") or "unreviewed"))
        return _event_result(progress, action, entity)

    if action == "registry-profile":
        return _event_result(progress, action, entity_profile(workspace, str(config.get("entity_id") or "")))

    if action == "registry-relationship":
        relationship = add_relationship(
            workspace, source_entity_id=str(config.get("source_entity_id") or ""),
            target_entity_id=str(config.get("target_entity_id") or ""),
            relationship_type=str(config.get("relationship_type") or "other"),
            evidence_refs=config.get("evidence_refs") or [], actor=str(config.get("actor") or "analyst"),
            review_state=str(config.get("review_state") or "unreviewed"),
            valid_from=str(config.get("valid_from") or ""), valid_to=str(config.get("valid_to") or ""),
            note=str(config.get("note") or ""),
        )
        return _event_result(progress, action, relationship)

    if action == "registry-export":
        output = str(config.get("output_file") or (workspace.path_for("exports") / "entity_registry.csv"))
        return [export_registry(workspace, output, format=str(config.get("format") or "") or None)]

    if action == "registry-compare":
        left = entity_profile(workspace, str(config.get("left_entity_id") or ""))
        right = entity_profile(workspace, str(config.get("right_entity_id") or ""))
        return _event_result(progress, action, compare_entities(left, right, coverage_documented=bool(config.get("coverage_documented", False))))

    if action == "registry-map":
        if config.get("source_file"):
            frame = load_map_frame(str(config["source_file"]))
        else:
            frame = _registry_map_frame(workspace)
        raw_layers = config.get("reference_files") or []
        if isinstance(raw_layers, str):
            raw_layers = [item.strip() for item in raw_layers.split(";") if item.strip()]
        layers: list[ReferenceLayer] = []
        for spec in raw_layers:
            if isinstance(spec, dict):
                path = str(spec.get("path") or spec.get("file") or "")
                name = str(spec.get("name") or Path(path).stem)
                color = str(spec.get("color") or "")
                show = bool(spec.get("show", True))
            else:
                path = str(spec)
                name, color, show = Path(path).stem.replace("_", " ").title(), "", True
            from .reference_registry import load_reference_table
            rows, _columns = load_reference_table(path)
            layers.append(ReferenceLayer(name=name, frame=pd.DataFrame(rows), color=color, show=show))
        target = Path(str(config.get("output_file") or (workspace.path_for("maps") / "research_workspace_map.html"))).expanduser().resolve()
        as_of = str(config.get("as_of_date") or "").strip()
        options = MapOptions(title=str(config.get("title") or "SUGAR Research Workspace"),
                             subtitle="Institutions, programs, and public-diplomacy context",
                             as_of_date=as_of)
        output = create_map(frame, target, options=options, reference_layers=layers)
        workspace.register_artifact("map", output, label="Research workspace map", metadata={"reference_layers": [layer.name for layer in layers], "as_of_date": as_of})
        return [output]

    if action == "monitor-list":
        return _event_result(progress, action, list_monitors(workspace))

    if action == "monitor-feed":
        rows = list_monitor_material(workspace, monitor_id=str(config.get("monitor_id") or ""),
                                     review_state=str(config.get("review_state") or ""))
        unreviewed = len(list_monitor_material(workspace, review_state="unreviewed"))
        return _event_result(progress, action, {"material": rows, "count": len(rows), "unreviewed_count": unreviewed})

    if action == "monitor-review":
        row = review_monitor_material(workspace, str(config.get("material_id") or ""),
                                      str(config.get("review_state") or "needs_followup"),
                                      actor=str(config.get("actor") or "analyst"), note=str(config.get("note") or ""))
        return _event_result(progress, action, row)

    if action == "monitor-save":
        monitor = save_monitor(
            workspace, name=str(config.get("name") or ""), terms=config.get("terms") or [],
            sources=config.get("sources") or [], cadence_minutes=int(config.get("cadence_minutes", 1440)),
            target_entities=config.get("target_entities") or [], geographies=config.get("geographies") or [],
            since=str(config.get("since") or ""), until=str(config.get("until") or ""),
            post_languages=config.get("post_languages") or [], max_posts_per_query=int(config.get("max_posts_per_query", 20)),
            max_pages_per_query=int(config.get("max_pages_per_query", 1)), status=str(config.get("status") or "active"),
            monitor_id=str(config.get("monitor_id") or ""), actor=str(config.get("actor") or "analyst"),
            reason=str(config.get("reason") or ""),
        )
        return _event_result(progress, action, monitor)

    if action == "monitor-status":
        monitor = set_monitor_status(workspace, str(config.get("monitor_id") or ""),
                                     str(config.get("status") or "paused"),
                                     actor=str(config.get("actor") or "analyst"), reason=str(config.get("reason") or ""))
        return _event_result(progress, action, monitor)

    if action in {"monitor-run", "monitor-run-due"}:
        monitors = due_monitors(workspace) if action == "monitor-run-due" else list_monitors(workspace)
        if action == "monitor-run":
            selected_id = str(config.get("monitor_id") or "")
            monitors = [item for item in monitors if item.get("monitor_id") == selected_id and item.get("status") == "active"]
            if not monitors:
                raise KeyError(f"No active listening post with ID {selected_id!r}; resume it before running.")
        maximum = max(1, min(25, int(config.get("max_monitors", 10))))
        results = []
        for monitor in monitors[:maximum]:
            if monitor.get("status") != "active":
                continue
            try:
                results.append(_run_monitor(workspace, monitor, secrets, progress))
            except Exception as exc:
                results.append({"monitor_id": monitor["monitor_id"], "status": "failed", "error": str(exc)})
        return _event_result(progress, action, {"due_count": len(monitors), "run_count": len(results), "runs": results})

    if action == "conversation-view":
        source = str(config.get("source_file") or "")
        if not source:
            artifact = workspace.latest_artifact("raw_collection") or workspace.latest_artifact("evidence")
            if artifact is None:
                raise ValueError("Choose a source-record file or collect/import records into this project first.")
            source = str(workspace.artifact_absolute_path(artifact))
        output = Path(str(config.get("output_file") or (workspace.path_for("intelligence") / "conversation_view.json")))
        saved = save_conversation_view(source, output, conversation_id=str(config.get("conversation_id") or ""))
        payload = json.loads(Path(saved).read_text(encoding="utf-8"))
        workspace.register_artifact("conversation_view", saved, label="Account and conversation structure", metadata={"source": Path(source).name})
        _emit(progress, "workspace_hub_data", action=action, data=payload)
        return [saved]

    raise ValueError(f"Unsupported workspace hub action: {action}")
