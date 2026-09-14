from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assessment_calibration import calibrate_support_assessments
from case_data import build_assessments, build_observations, build_us_presence_sites, sources_manifest
from location_enrichment import (
    apply_observation_location_enrichment,
    apply_us_site_location_enrichment,
    location_reference_manifest,
)
from source_conflicts import source_conflict_findings, source_conflict_manifest
from sugar_core.observation_storage import save_observations
from sugar_core.state_map import create_state_map
from sugar_core.state_workflow import audit_state_records, save_state_assessments, save_state_package
from sugar_core.workspace import SugarWorkspace

CASE_NAME = "Kyrgyzstan 2026 Public Diplomacy E2E"
CASE_STEM = "kyrgyzstan_2026"
# Current USPresenceSite records do not yet carry per-site precision. Two sites in this case have
# address-refined coordinates and six remain city-centroid references, so the map uses one
# deliberately conservative blanket envelope until the core schema can represent that difference.
US_SITE_UNCERTAINTY_KM = 12.0


def _write_us_sites(sites, output_csv: Path) -> list[Path]:
    rows = [asdict(site) for site in sites]
    frame = pd.DataFrame(rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_csv, index=False, encoding="utf-8-sig")
    output_xlsx = output_csv.with_suffix(".xlsx")
    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="us_presence")
    return [output_csv, output_xlsx]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict | list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _case_findings(observations, assessments, sites, location_summary: dict[str, int]) -> list[dict]:
    assessment_by_id = {row.observation_id: row for row in assessments}
    language_records = [row for row in observations if "language_education" in row.triage_labels]
    language_fallback = [
        row for row in language_records
        if "other" in assessment_by_id[row.observation_id].program_domains
    ]
    higher_ed_assessments = [row for row in assessments if "higher_education" in row.program_domains]
    missed_virtual_educationusa = [
        row for row in higher_ed_assessments
        if "educationusa" not in row.us_overlap.service_overlap
    ]
    physical_sites = [site for site in sites if site.latitude is not None and site.longitude is not None]
    virtual_sites = [site for site in sites if site.latitude is None or site.longitude is None]
    approximate_reach_records = [
        row for row in observations
        if any(marker in row.summary.casefold() for marker in ("roughly 300", "roughly 200", "more than 1,000", "hundreds"))
    ]
    multi_site_records = [
        row for row in observations
        if row.title == "International Chinese Language Day events at Bishkek universities"
    ]
    return [
        {
            "code": "language_education_domain_gap",
            "severity": "model_gap",
            "affected_records": len(language_fallback),
            "description": (
                "Chinese-language education is a first-order activity in this case, but the current State program-domain taxonomy has no generic language-education domain. "
                "The case preserves the concept in triage labels/policy relevance and falls back to program_domains=['other'] where needed."
            ),
            "recommended_fix": "Add a generic language_education State domain and define careful thematic-overlap semantics with U.S. language programming.",
        },
        {
            "code": "virtual_educationusa_service_gap",
            "severity": "model_gap",
            "affected_records": len(missed_virtual_educationusa),
            "description": (
                "EducationUSA Kyrgyzstan is represented as a non-spatial national service. The current overlap model derives service overlap from the nearest physical U.S. site, so nationally available virtual advising is not automatically counted."
            ),
            "recommended_fix": "Separate physical-site proximity from national/virtual service availability and aggregate service overlap by scope.",
        },
        {
            "code": "us_site_precision_gap",
            "severity": "model_gap",
            "affected_records": len(physical_sites),
            "description": (
                f"The current U.S.-presence schema does not store per-site location precision/uncertainty. This case can address-refine {location_summary['address_refined_physical_us_sites']} physical sites while {location_summary['city_centroid_physical_us_sites']} remain city-centroid references, but State proximity must still receive one conservative 12 km envelope for the entire physical U.S. layer."
            ),
            "recommended_fix": "Add per-site location precision, confidence, provenance, and uncertainty fields and let State proximity consume them directly.",
        },
        {
            "code": "qualified_reach_metric_gap",
            "severity": "model_gap",
            "affected_records": len(approximate_reach_records),
            "description": (
                "Several public sources report approximate or bounded attendance ('roughly 200', 'roughly 300', 'more than 1,000'). ReachMetrics currently stores bare integers without qualifiers, so this case leaves those values out of aggregate reach totals rather than converting approximate claims into false exactness."
            ),
            "recommended_fix": "Support exact/approximate/minimum/maximum qualifiers and source notes per reach metric before aggregating them.",
        },
        {
            "code": "multi_site_observation_gap",
            "severity": "model_gap",
            "affected_records": len(multi_site_records),
            "description": (
                "The International Chinese Language Day source describes programming at more than one Bishkek university, but ResearchObservation currently carries a single point/location. The case therefore leaves that record at city precision rather than inventing one canonical venue."
            ),
            "recommended_fix": "Support multiple event locations or a parent activity with venue-specific child observations so multi-site source reporting does not collapse into one artificial point.",
        },
        {
            "code": "human_review_gate_working",
            "severity": "expected_guardrail",
            "affected_records": len(observations),
            "description": (
                "All real-world records remain AI-triaged. The analyst map can display them for review, while the verified-only State map and briefing output must not promote them to human-verified judgments."
            ),
            "recommended_fix": "No fix; preserve this gate and provide a smoother human-review workflow in the desktop clients.",
        },
        {
            "code": "virtual_us_services_present",
            "severity": "context",
            "affected_records": len(virtual_sites),
            "description": "At least one important U.S. public-diplomacy service in the case is non-spatial and should not be forced onto a map point.",
            "recommended_fix": "Represent non-spatial service coverage explicitly in future State network views.",
        },
    ]


def run_case(output_root: Path, *, clean: bool = False) -> dict:
    output_root = output_root.expanduser().resolve()
    if clean and output_root.exists():
        shutil.rmtree(output_root)

    workspace = SugarWorkspace.create(
        output_root,
        name=CASE_NAME,
        description=(
            "Reproducible public-source Kyrgyzstan case through 2026-09-14. Records are AI-triaged, not human verified; intended to exercise collection-to-review-to-map-to-brief guardrails."
        ),
        exist_ok=True,
    )

    observations = build_observations()
    sites = build_us_presence_sites()
    observation_location_summary = apply_observation_location_enrichment(observations)
    us_location_summary = apply_us_site_location_enrichment(sites)
    location_summary = {**observation_location_summary, **us_location_summary}
    # Build assessments only after deterministic location enrichment so downstream State overlap
    # sees the same source-backed geometry used by the map.
    assessments = build_assessments(observations)
    support_summary = calibrate_support_assessments(observations, assessments)

    observation_csv = workspace.path_for("observations") / f"{CASE_STEM}.observations.csv"
    save_observations(
        observations,
        observation_csv,
        metadata={
            "case": CASE_NAME,
            "research_cutoff": "2026-09-14",
            "review_state": "ai_triaged",
            "state_facing": False,
            "location_enrichment": location_summary,
        },
    )
    observation_outputs = [
        observation_csv,
        observation_csv.with_suffix(".xlsx"),
        observation_csv.with_suffix(".metadata.json"),
    ]
    workspace.register_outputs(observation_outputs, kind="observations", operation="kyrgyzstan-e2e")

    references_dir = workspace.path_for("references")
    conflicts = source_conflict_manifest()
    sources = sources_manifest(observations, sites)
    sources["location_references"] = location_reference_manifest()
    sources["source_conflicts"] = conflicts
    sources_path = _write_json(references_dir / "sources.json", sources)
    location_references_path = _write_json(references_dir / "location_references.json", location_reference_manifest())
    source_conflicts_path = _write_json(references_dir / "source_conflicts.json", conflicts)
    us_site_paths = _write_us_sites(sites, references_dir / "us_presence.csv")
    workspace.register_artifact("reference", sources_path, metadata={"operation": "kyrgyzstan-e2e"})
    workspace.register_artifact("reference", location_references_path, metadata={"operation": "kyrgyzstan-e2e"})
    workspace.register_artifact("reference", source_conflicts_path, metadata={"operation": "kyrgyzstan-e2e"})
    workspace.register_outputs(us_site_paths, kind="reference", operation="kyrgyzstan-e2e")

    state_dir = workspace.path_for("state")
    assessments_path = Path(save_state_assessments(assessments, state_dir / f"{CASE_STEM}.state.jsonl"))
    workspace.register_artifact("state_assessments", assessments_path, metadata={"operation": "kyrgyzstan-e2e"})

    package_outputs = [
        Path(path)
        for path in save_state_package(
            observations,
            assessments,
            state_dir,
            name=CASE_STEM,
            us_sites=sites,
            title="Kyrgyzstan 2026 Public Diplomacy Research Update",
        )
    ]
    workspace.register_outputs(package_outputs, kind="state_output", operation="kyrgyzstan-e2e")

    map_dir = workspace.path_for("maps")
    analyst_map = Path(
        create_state_map(
            observations,
            assessments,
            map_dir / f"{CASE_STEM}.analyst.html",
            us_sites=sites,
            verified_only=False,
            include_activity_density=True,
            resolve_missing_locations=False,
            us_site_uncertainty_km=US_SITE_UNCERTAINTY_KM,
        )
    )
    verified_map = Path(
        create_state_map(
            observations,
            assessments,
            map_dir / f"{CASE_STEM}.verified.html",
            us_sites=sites,
            verified_only=True,
            include_activity_density=True,
            resolve_missing_locations=False,
            us_site_uncertainty_km=US_SITE_UNCERTAINTY_KM,
        )
    )
    map_outputs = [
        analyst_map,
        analyst_map.with_suffix(analyst_map.suffix + ".metadata.json"),
        verified_map,
        verified_map.with_suffix(verified_map.suffix + ".metadata.json"),
    ]
    workspace.register_outputs(map_outputs, kind="map", operation="kyrgyzstan-e2e")

    audit = audit_state_records(observations, assessments)
    findings = _case_findings(observations, assessments, sites, location_summary)
    findings.extend(source_conflict_findings())
    analyst_metadata = _read_json(analyst_map.with_suffix(analyst_map.suffix + ".metadata.json"))
    verified_metadata = _read_json(verified_map.with_suffix(verified_map.suffix + ".metadata.json"))
    proximity_ledger = analyst_metadata.get("us_proximity", [])
    center_distances = [float(row["center_distance_km"]) for row in proximity_ledger]

    summary = {
        "case": CASE_NAME,
        "research_cutoff": "2026-09-14",
        "observations": len(observations),
        "assessments": len(assessments),
        "human_verified_observations": sum(row.verification_state == "human_verified" for row in observations),
        "brief_eligible_assessments": audit.get("brief_eligible", 0),
        "audit_status": audit.get("status"),
        "support_levels": support_summary,
        "physical_us_sites": sum(site.latitude is not None and site.longitude is not None for site in sites),
        "nonspatial_us_services": sum(site.latitude is None or site.longitude is None for site in sites),
        "location_enrichment": location_summary,
        "source_conflicts": len(conflicts),
        "analyst_map_observations": analyst_metadata.get("mapped_observations"),
        "analyst_map_precision_counts": analyst_metadata.get("precision_counts", {}),
        "verified_map_observations": verified_metadata.get("mapped_observations"),
        "analyst_map_us_proximity_counts": analyst_metadata.get("us_proximity_counts", {}),
        "verified_map_us_proximity_counts": verified_metadata.get("us_proximity_counts", {}),
        "analyst_map_center_distance_km_min": round(min(center_distances), 3) if center_distances else None,
        "analyst_map_center_distance_km_max": round(max(center_distances), 3) if center_distances else None,
        "workspace_artifacts": workspace.status().get("artifact_count"),
        "case_findings": len(findings),
    }

    reports_dir = workspace.path_for("reports")
    summary_json = _write_json(reports_dir / "case-summary.json", summary)
    findings_json = _write_json(reports_dir / "case-findings.json", findings)
    audit_json = _write_json(reports_dir / "case-audit.json", audit)

    preliminary = [
        "# Kyrgyzstan 2026 — preliminary analyst note",
        "",
        "**Status:** AI-triaged public-source research exercise. This is not a human-verified State-facing brief.",
        "",
        f"The bounded case contains **{len(observations)}** PRC-linked public-diplomacy observations through September 14, 2026. The record spans Chinese-language education, Confucius Institute activity, university cooperation, cultural exhibitions and performances, literary and city-level exchanges, and governance/civilizational programming.",
        "",
        f"Seven source records name a venue/institution that can be refined to site-level geometry with separate public location references; four remain deliberately city-level. The U.S. layer contains eight physical American Spaces, of which two are address-refined in this case while six remain conservative city-centroid references, plus one non-spatial EducationUSA service. The current State EducationUSA directory and American Councils page conflict about whether the Bishkek advising service still has a physical location, so that contradiction is retained explicitly. PRC-support judgments are calibrated by evidence strength rather than assigned uniformly: {support_summary['probable']} are coded probable and {support_summary['possible']} possible, with none promoted to confirmed before human review. The analyst map is available before human verification; the verified-only map contains no PRC observations until review gates are satisfied.",
        "",
        "## Model and source findings from the real case",
        "",
    ]
    preliminary.extend(f"- **{item['code']}** — {item['description']}" for item in findings)
    preliminary.extend(
        [
            "",
            "## Interpretation guardrail",
            "",
            "Mapped proximity, shared audience categories, or thematic similarity do not establish competition, displacement, persuasion, coordination, or causal influence. Human review remains required before State-facing judgments.",
            "",
        ]
    )
    note_path = reports_dir / "preliminary-analyst-note.md"
    note_path.write_text("\n".join(preliminary), encoding="utf-8")
    report_outputs = [summary_json, findings_json, audit_json, note_path]
    workspace.register_outputs(report_outputs, kind="report", operation="kyrgyzstan-e2e")

    # The core purpose of this case is to exercise real public data without weakening review,
    # geographic precision, source conflicts, or evidence calibration merely to make output look complete.
    assert len(observations) == 11
    assert summary["human_verified_observations"] == 0
    assert summary["brief_eligible_assessments"] == 0
    assert summary["support_levels"] == {"probable": 9, "possible": 2}
    assert summary["analyst_map_observations"] == 11
    assert summary["verified_map_observations"] == 0
    assert summary["physical_us_sites"] == 8
    assert summary["nonspatial_us_services"] == 1
    assert summary["source_conflicts"] == 1
    assert summary["case_findings"] == 8
    assert summary["location_enrichment"]["site_refined_observations"] == 7
    assert summary["location_enrichment"]["city_level_observations"] == 4
    assert summary["location_enrichment"]["address_refined_physical_us_sites"] == 2
    assert summary["analyst_map_precision_counts"] == {"city": 4, "site": 7}
    assert center_distances and min(center_distances) > 0.1
    assert analyst_metadata.get("mapped_us_sites") == 8
    assert verified_metadata.get("mapped_us_sites") == 8
    assert workspace.status()["missing_artifacts"] == 0

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the reproducible Kyrgyzstan 2026 SUGAR end-to-end case.")
    parser.add_argument("--output", type=Path, required=True, help="Workspace directory to create or reopen.")
    parser.add_argument("--clean", action="store_true", help="Delete the target directory before running.")
    args = parser.parse_args()
    summary = run_case(args.output, clean=args.clean)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
