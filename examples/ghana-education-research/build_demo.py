#!/usr/bin/env python3
"""Build a source-backed Ghana education research demo in a fresh workspace."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from sugar_core.handoff import build_handoff_bundle, verify_handoff_bundle
from sugar_core.models import PostRecord
from sugar_core.observation_storage import save_observations
from sugar_core.observations import EvidenceReference, ObservationLocation, ResearchObservation
from sugar_core.reference_registry import (
    export_registry,
    import_reference_dataset,
    list_entities,
    list_relationships,
    preview_reference_import,
    upsert_entity,
)
from sugar_core.research_requirements import (
    ResearchRequirement,
    ResearchTimeframe,
    build_initial_search_plan,
    save_requirement,
    save_search_plan,
)
from sugar_core.storage import save_records
from sugar_core.workspace import SugarWorkspace
from sugar_core.workspace_hub import run_workspace_hub
from sugar_core.workspace_memory import record_project_run
from sugar_core.workspace_runtime import register_handoff_bundle


SNAPSHOT_DATE = "2026-09-28"
INVENTORY = Path(__file__).resolve().with_name("source-inventory.csv")
OPENSTREETMAP = {
    "accra": {
        "latitude": 5.5571096,
        "longitude": -0.2012376,
        "precision": "city",
        "url": "https://www.openstreetmap.org/relation/12803764",
        "title": "Accra city reference point (OpenStreetMap relation 12803764)",
        "note": "City reference point; not a street-address geocode.",
    },
    "university_of_ghana": {
        "latitude": 5.6465979,
        "longitude": -0.1880040,
        "precision": "campus",
        "url": "https://www.openstreetmap.org/way/308668766",
        "title": "University of Ghana campus reference point (OpenStreetMap way 308668766)",
        "note": "Campus reference point; not a building-level coordinate.",
    },
    "kumasi": {
        "latitude": 6.6985605,
        "longitude": -1.6233086,
        "precision": "city",
        "url": "https://www.openstreetmap.org/node/261702404",
        "title": "Kumasi city reference point (OpenStreetMap node 261702404)",
        "note": "City reference point; no street address was supplied by the directory.",
    },
}

SOURCES = [
    {
        "id": "educationusa-accra-embassy",
        "title": "EducationUSA Accra",
        "url": "https://educationusa.state.gov/centers/educationusa-accra",
        "summary": "Official EducationUSA center page listing the Accra advising location at the U.S. Embassy and its published address.",
        "kind": "institution",
        "status": "active",
        "institution": "EducationUSA Accra (U.S. Embassy)",
        "program": "EducationUSA advising",
        "city": "Accra",
        "location": "EducationUSA Accra, Accra city reference point",
        "geo": "accra",
    },
    {
        "id": "educationusa-accra-ace-consult",
        "title": "EducationUSA Accra (ACE Consult)",
        "url": "https://educationusa.state.gov/centers/educationusa-accra-ace-consult",
        "summary": "Official EducationUSA center page listing ACE Consult in Accra and its published street address.",
        "kind": "institution",
        "status": "active",
        "institution": "EducationUSA Accra (ACE Consult)",
        "program": "EducationUSA advising",
        "city": "Accra",
        "location": "ACE Consult, Accra city reference point",
        "geo": "accra",
    },
    {
        "id": "educationusa-kumasi-ace-consult",
        "title": "EducationUSA center directory: Kumasi (ACE Consult)",
        "url": "https://educationusa.state.gov/find-advising-center?field_directory_admissions_couns_value=AR&field_program_page_degree_type_target_id=13&page=24",
        "summary": "Official EducationUSA directory listing an ACE Consult advising center in Kumasi, Ghana.",
        "kind": "institution",
        "status": "active",
        "institution": "EducationUSA Kumasi (ACE Consult)",
        "program": "EducationUSA advising",
        "city": "Kumasi",
        "location": "EducationUSA Kumasi, Kumasi city reference point",
        "geo": "kumasi",
    },
    {
        "id": "american-spaces-ghana-newsletter",
        "title": "American Spaces Ghana newsletter (historical reference)",
        "url": "https://americanspaces.state.gov/wp-content/uploads/sites/292/2301-Newsletter.pdf",
        "summary": "Official historical newsletter referring to an American Center and American Corner in Accra. The report does not establish their current operating status.",
        "kind": "institution",
        "status": "unknown",
        "institution": "American Spaces Ghana locations",
        "program": "American Spaces public programming",
        "city": "Accra",
        "location": "American Spaces Accra references, Accra city reference point",
        "geo": "accra",
    },
    {
        "id": "university-of-ghana-homepage",
        "title": "University of Ghana",
        "url": "https://www.ug.edu.gh/",
        "summary": "Official University of Ghana institutional website; the map shows a campus-level reference point.",
        "kind": "institution",
        "status": "active",
        "institution": "University of Ghana",
        "program": "",
        "city": "",
        "location": "University of Ghana campus reference point",
        "geo": "university_of_ghana",
    },
]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record(source: dict[str, str]) -> PostRecord:
    return PostRecord(
        platform="web",
        native_id=source["id"],
        canonical_url=source["url"],
        query="Ghana education advising American Spaces",
        content_type="webpage",
        source_mode="manual_import",
        source_host=urlparse(source["url"]).netloc,
        source_url=source["url"],
        collected_at=f"{SNAPSHOT_DATE}T12:00:00Z",
        original_text=source["summary"],
    )


def _location(source: dict[str, str]) -> ObservationLocation:
    point = OPENSTREETMAP[source["geo"]]
    return ObservationLocation(
        label=source["location"],
        country="Ghana",
        city=source["city"],
        latitude=point["latitude"],
        longitude=point["longitude"],
        precision="city" if point["precision"] == "city" else "locality",
        basis="map_reference",
        source_ref=point["url"],
        note=point["note"],
    )


def _observation(source: dict[str, str]) -> ResearchObservation:
    point = OPENSTREETMAP[source["geo"]]
    evidence = EvidenceReference(
        url=source["url"],
        title=source["title"],
        source_type="official public webpage or document",
        platform="web",
        native_id=source["id"],
        collected_at=f"{SNAPSHOT_DATE}T12:00:00Z",
        note="Paraphrased source record; inspect the linked source for the original wording.",
    )
    return ResearchObservation(
        observation_type=source["kind"],
        title=source["title"],
        summary=source["summary"],
        observed_at=SNAPSHOT_DATE,
        activity_status=source["status"],
        location_label=source["location"],
        country="Ghana",
        city=source["city"],
        latitude=point["latitude"],
        longitude=point["longitude"],
        location_basis="map_reference",
        locations=[_location(source)],
        institution_name=source["institution"],
        program_name=source["program"],
        evidence=[evidence],
        source_record_keys=[f"web:{source['id']}"],
        verification_state="unreviewed",
        verification_notes="Public-source demo claim; analyst review is still required.",
    )


def build_workspace(target: Path) -> dict[str, object]:
    project_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/FL2744/SUGAR/ghana-education-research"))
    manifest = target / "sugar-project.json"
    if manifest.is_file():
        workspace = SugarWorkspace.open(target)
        if workspace.manifest.project_id != project_id or workspace.manifest.name != "Ghana Education and Cultural Programs":
            raise FileExistsError(f"The existing workspace is not this demo project: {target}")
        if workspace.latest_artifact("handoff_manifest"):
            raise FileExistsError(f"The demo project is already complete: {target}")
        resuming = True
        existing_entity_count = len(list_entities(workspace))
        if existing_entity_count not in {0, 9}:
            raise ValueError(f"Existing demo workspace has an unexpected registry size ({existing_entity_count}): {target}")
    else:
        if target.exists() and any(target.iterdir()):
            raise FileExistsError(f"Refusing to build into a non-empty directory: {target}")
        workspace = SugarWorkspace.create(
            target,
            name="Ghana Education and Cultural Programs",
            description=(
                "A small, evidence-backed public-source demo of EducationUSA, American Spaces, "
                "and a public university in Ghana. Snapshot 2026-09-28."
            ),
            project_id=project_id,
        )
        resuming = False

    inventory_copy = workspace.path_for("references") / "ghana-demo-source-inventory.csv"
    shutil.copy2(INVENTORY, inventory_copy)
    preview = preview_reference_import(inventory_copy)
    if preview["error_count"] or preview["row_count"] != 9:
        raise ValueError(f"Inventory preview did not pass: {preview['errors']}")
    mapping = preview["suggested_mapping"]
    if not resuming or existing_entity_count == 0:
        imported = import_reference_dataset(
            workspace,
            inventory_copy,
            mapping=mapping,
            dataset_name="Ghana sponsor-demo seed inventory",
            network="",
            geographic_scope="Selected sites in Accra and Kumasi and a University of Ghana campus reference point.",
            known_coverage_limits="Non-exhaustive public-source sample; see evidence-gaps.md.",
            license_notes="Facts paraphrased from linked public official sources; source URLs are retained. Map location claims separately cite OpenStreetMap under ODbL.",
            actor="demo builder",
            review_state="unreviewed",
        )
        if imported["entity_count"] != 9 or imported["excluded_rows"]:
            raise ValueError(f"Inventory import did not complete cleanly: {imported}")
        record_project_run(
            workspace,
            command="registry-import",
            config={"dataset_name": "Ghana sponsor-demo seed inventory", "review_state": "unreviewed", "preview_row_count": preview["row_count"]},
            outputs=[inventory_copy, workspace.path_for("references") / "registry" / "dataset_manifest.json"],
        )

    for entity_id, geo_key in (
        ("organization_us_embassy_accra", "accra"),
        ("site_educationusa_accra_embassy", "accra"),
        ("site_educationusa_accra_ace", "accra"),
        ("site_educationusa_kumasi", "kumasi"),
        ("site_american_center_accra", "accra"),
        ("site_american_corner_accra", "accra"),
        ("institution_university_of_ghana", "university_of_ghana"),
    ):
        point = OPENSTREETMAP[geo_key]
        entity = next(row for row in list_entities(workspace) if row["entity_id"] == entity_id)
        upsert_entity(
            workspace,
            {
                "entity_id": entity_id,
                "entity_type": entity["entity_type"],
                "name": entity["name"],
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "location_precision": point["precision"],
            },
            evidence_refs=[{
                "source_url": point["url"],
                "title": point["title"],
                "source_type": "OpenStreetMap location reference",
                "note": point["note"],
            }],
            actor="demo builder",
            reason="Added a separate, approximate map reference; this does not establish an exact venue address.",
            review_state="unreviewed",
            observed_at=f"{SNAPSHOT_DATE}T12:00:00Z",
        )

    requirement = ResearchRequirement(
        question=(
            "Which public-facing education advising and American Spaces activity is documented in Ghana, "
            "where can sources locate those services, and which status and geographic-precision "
            "fields remain unresolved in this small public-source sample?"
        ),
        geographies=["Ghana"],
        timeframe=ResearchTimeframe(start="2023-01-01", end=SNAPSHOT_DATE),
        target_audiences=["Research analyst"],
        known_entities=[
            "American Spaces Ghana",
            "EducationUSA",
            "University of Ghana",
        ],
        excluded_topics=["Influence claims", "Program outcome claims", "Comprehensive national coverage claims"],
        preferred_sources=["Official U.S. Department of State pages", "Official University of Ghana pages"],
        collection_mode="quick",
        notes=(
            "Public-source demonstration only. Keep service/status claims tied to cited pages; distinguish source publication or observation time from lifecycle effective dates. "
            "Do not infer closure from unknown status or exact location from a city/campus reference point."
        ),
    )
    requirement_file = workspace.path_for("state") / "research-requirement.json"
    save_requirement(requirement, requirement_file)
    workspace.register_artifact("research_requirement", requirement_file, label="Ghana sponsor-demo research requirement")
    record_project_run(workspace, command="requirement-create", config={"requirement_id": requirement.requirement_id, "question": requirement.question}, outputs=[requirement_file])

    plan = build_initial_search_plan(requirement)
    plan_file = workspace.path_for("state") / "search-plan.json"
    save_search_plan(plan, plan_file)
    workspace.register_artifact("search_plan", plan_file, label="Initial Ghana demo search plan", metadata={"requirement_id": requirement.requirement_id})
    record_project_run(workspace, command="plan", config={"requirement_id": requirement.requirement_id, "branch_count": len(plan.branches), "collection_mode": requirement.collection_mode}, outputs=[plan_file])

    records_path = workspace.path_for("raw") / "ghana-demo-source-records.csv"
    records = [_record(source) for source in SOURCES]
    save_records(records, records_path, metadata={
        "capture_method": "curated_manual_import",
        "snapshot_date": SNAPSHOT_DATE,
        "sources": sorted({urlparse(item["url"]).netloc for item in SOURCES}),
        "terms": ["Ghana EducationUSA American Spaces University of Ghana"],
        "source_coverage_note": "Five manually curated official webpages/documents; no platform collection was performed.",
    })
    observations_path = workspace.path_for("observations") / "ghana-demo-observations.csv"
    save_observations([_observation(source) for source in SOURCES], observations_path, metadata={"snapshot_date": SNAPSHOT_DATE})
    workspace.register_artifact("evidence", records_path, label="Curated official source records")
    workspace.register_artifact("observations", observations_path, label="Unreviewed public-source observations")

    gap_file = Path(__file__).resolve().with_name("evidence-gaps.md")
    if not gap_file.is_file():
        raise FileNotFoundError(f"Keep the companion evidence-gaps.md beside the build script: {gap_file}")
    gaps_in_workspace = target / "evidence-gaps.md"
    shutil.copy2(gap_file, gaps_in_workspace)
    workspace.register_artifact("demo_methodology", gaps_in_workspace, label="Evidence gaps and interpretation limits")

    registry_export = workspace.path_for("exports") / "ghana-demo-institution-registry.csv"
    export_registry(workspace, registry_export, format="csv")
    map_path = workspace.path_for("maps") / "ghana-education-research.html"
    run_workspace_hub({
        "action": "registry-map",
        "workspace": str(workspace.root),
        "output_file": str(map_path),
        "title": "Ghana Education and Cultural Programs",
        "as_of_date": SNAPSHOT_DATE,
    })
    record_project_run(workspace, command="registry-map", config={"as_of_date": SNAPSHOT_DATE, "mapped_entities": 7, "location_precision": "city/campus reference points"}, outputs=[map_path])

    limitations_file = workspace.path_for("exports") / "limitations.json"
    _write_json(limitations_file, {
        "schema_version": "1.0",
        "snapshot_date": SNAPSHOT_DATE,
        "scope": "Small public-source demonstration sample, not a comprehensive Ghana inventory.",
        "known_gaps": [
            "Current American Spaces site status is unknown.",
            "EducationUSA Accra street addresses are not geocoded at street-level precision.",
            "Kumasi is mapped at city precision; the University of Ghana point is campus-level.",
            "No complete lifecycle dates, outcome data, or evidence of influence were collected.",
            "All imported claims and relationships remain unreviewed.",
        ],
    })
    bundle_parent = workspace.path_for("exports") / "handoff"
    handoff = build_handoff_bundle(
        requirement_file,
        plan_file,
        records_path,
        observations_path,
        bundle_parent,
        name="ghana-education-research",
        limitations_file=limitations_file,
        analytic_outputs=[map_path],
        provenance_files=[inventory_copy, registry_export, gaps_in_workspace],
    )
    register_handoff_bundle(workspace, handoff.manifest, archive_file=handoff.archive)
    verification = verify_handoff_bundle(handoff.directory)
    if verification["status"] != "pass":
        raise RuntimeError(f"Generated handoff did not verify: {verification}")
    record_project_run(workspace, command="handoff", config={"requirement_id": requirement.requirement_id, "handoff": handoff.archive, "verification": verification["status"]}, outputs=[handoff.archive])

    report = {
        "workspace": str(workspace.root),
        "entities": len(list_entities(workspace)),
        "relationships": len(list_relationships(workspace)),
        "mapped_entities": 7,
        "plan_branches": len(plan.branches),
        "records": len(records),
        "observations": len(SOURCES),
        "map": str(map_path),
        "handoff_directory": handoff.directory,
        "handoff_zip": handoff.archive,
        "handoff_verification": verification["status"],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New or empty directory for the generated SUGAR workspace.")
    args = parser.parse_args()
    report = build_workspace(args.output.expanduser().resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
