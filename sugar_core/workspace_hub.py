from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

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


def _filter_dataset_rows(rows: list[dict[str, Any]], column: str = "", value: str = "") -> list[dict[str, Any]]:
    if not column or not value:
        return rows
    query = value.casefold()
    return [row for row in rows if query in str(row.get(column, "")).casefold()]


def _event_result(progress: ProgressCallback | None, action: str, payload: Any) -> list[str]:
    _emit(progress, "workspace_hub_data", action=action, data=payload)
    return []


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
        return _event_result(progress, action, dashboard(workspace))

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
        source_file = str(config.get("source_file") or "")
        rows, columns = _load_dataset_rows(source_file)
        filtered = _filter_dataset_rows(rows, str(config.get("filter_column") or ""), str(config.get("filter_value") or ""))
        maximum = max(1, min(5000, int(config.get("max_rows", 500))))
        return _event_result(progress, action, {"source_file": str(Path(source_file).expanduser().resolve()),
            "columns": columns, "row_count": len(rows), "matching_rows": len(filtered),
            "rows_shown": min(maximum, len(filtered)), "filter_column": str(config.get("filter_column") or ""),
            "filter_value": str(config.get("filter_value") or ""), "rows": filtered[:maximum]})

    if action == "dataset-export":
        source_file = str(config.get("source_file") or "")
        rows, _columns = _load_dataset_rows(source_file)
        filtered = _filter_dataset_rows(rows, str(config.get("filter_column") or ""), str(config.get("filter_value") or ""))
        target = Path(str(config.get("output_file") or "")).expanduser().resolve()
        if not str(config.get("output_file") or "").strip():
            raise ValueError("Choose an output path for the filtered dataset export.")
        target.parent.mkdir(parents=True, exist_ok=True)
        suffix = target.suffix.casefold()
        if suffix == ".csv":
            pd.DataFrame(filtered).to_csv(target, index=False, encoding="utf-8-sig")
        elif suffix in {".jsonl", ".ndjson"}:
            target.write_text("".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in filtered), encoding="utf-8")
        elif suffix == ".xlsx":
            pd.DataFrame(filtered).to_excel(target, index=False)
        elif suffix in {".json", ".geojson"}:
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
