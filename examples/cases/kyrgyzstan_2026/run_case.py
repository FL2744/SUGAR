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
from case_data import (
    EDUCATIONUSA_SOURCE,
    build_assessments,
    build_observations,
    build_us_presence_sites,
    sources_manifest,
)
from location_enrichment import (
    apply_observation_location_enrichment,
    apply_us_site_location_enrichment,
    location_reference_manifest,
)
from source_conflicts import (
    build_source_conflicts,
    source_conflict_findings,
    source_conflict_manifest,
)
from sugar_core.observation_storage import save_observations
from sugar_core.state_conflict_package import save_state_package_with_conflicts
from sugar_core.state_map import create_state_map
from sugar_core.state_workflow import audit_state_records, save_state_assessments
from sugar_core.workspace import SugarWorkspace

CASE_NAME = "Kyrgyzstan 2026 Public Diplomacy E2E"
CASE_STEM = "kyrgyzstan_2026"
US_SITE_UNCERTAINTY_KM = 12.0
MULTI_SITE_TITLE = "International Chinese Language Day events at Bishkek universities"


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


def _has_structured_educationusa_source(assessment) -> bool:
    """Require structured current-service provenance; never infer it from analyst-note prose."""
    return any(
        source.network == "educationusa"
        and source.delivery_mode == "virtual"
        and source.coverage_scope == "country"
        and source.source_url == EDUCATIONUSA_SOURCE
        and "educationusa" in source.program_service_matches
        for source in assessment.us_overlap.service_sources
    )


def _case_findings(observations, assessments, sites, location_summary: dict[str, int]) -> list[dict]:
    assessment_by_id = {row.observation_id: row for row in assessments}
    language_records = [row for row in observations if "language_education" in row.triage_labels]
    language_fallback = [
        row for row in language_records
        if "other" in assessment_by_id[row.observation_id].program_domains
        or "language_education" not in assessment_by_id[row.observation_id].program_domains
    ]
    false_english_overlap = [
        row for row in language_records
        if "english_language" in assessment_by_id[row.observation_id].us_overlap.service_overlap
    ]
    higher_ed_assessments = [row for row in assessments if "higher_education" in row.program_domains]
    missed_virtual_educationusa = [
        row for row in higher_ed_assessments
        if "educationusa" not in row.us_overlap.service_overlap
        or not _has_structured_educationusa_source(row)
    ]
    physical_sites = [site for site in sites if site.is_spatial]
    unresolved_physical_sites = [
        site for site in sites
        if site.delivery_mode in {"physical", "hybrid"} and not site.is_spatial
    ]
    virtual_sites = [site for site in sites if site.delivery_mode == "virtual"]
    sites_missing_precision = [
        site for site in physical_sites
        if site.location_precision == "unknown"
        or site.location_confidence is None
        or site.location_uncertainty_km is None
        or not site.location_basis
    ]
    us_site_reference_gaps = sites_missing_precision + unresolved_physical_sites
    approximate_reach_records = [
        row for row in observations
        if any(marker in row.summary.casefold() for marker in ("roughly 300", "roughly 200", "more than 1,000", "hundreds"))
    ]
    qualified_reach_missing = []
    for observation in approximate_reach_records:
        assessment = assessment_by_id[observation.observation_id]
        metric = assessment.reach.metric("attendance")
        if (
            metric is None
            or metric.qualifier == "exact"
            or not metric.source_note
            or not metric.source_ref
            or assessment.reach.attendance is not None
            or assessment.reach.observed_total != 0
        ):
            qualified_reach_missing.append(observation)

    multi_site_records = [row for row in observations if row.title == MULTI_SITE_TITLE]
    multi_site_missing = [
        row for row in multi_site_records
        if len(row.locations) != 2
        or len({item.location_id for item in row.locations}) != 2
        or {item.precision for item in row.locations} != {"site", "city"}
        or any(not item.source_ref for item in row.locations)
    ]

    return [
        {
            "code": "language_education_domain_resolved" if not language_fallback else "language_education_domain_gap",
            "severity": "resolved" if not language_fallback else "model_gap",
            "affected_records": len(language_records) if not language_fallback else len(language_fallback),
            "description": (
                "Chinese-language education is represented by the generic language_education State domain without being equated to English-language programming."
                if not language_fallback else
                "Some Chinese-language education records still fall back to an undifferentiated domain instead of language_education."
            ),
            "recommended_fix": "Preserve language_education as language-neutral." if not language_fallback else "Migrate remaining language records to language_education.",
        },
        {
            "code": "direct_service_overlap_semantics_resolved" if not false_english_overlap else "direct_service_overlap_semantics_gap",
            "severity": "resolved" if not false_english_overlap else "model_gap",
            "affected_records": len(language_records) if not false_english_overlap else len(false_english_overlap),
            "description": (
                "Audience similarity no longer manufactures a direct English-language service overlap for Chinese-language activities; audience, thematic, and service overlap remain separate dimensions."
                if not false_english_overlap else
                "At least one Chinese-language record still receives a direct English-language service overlap from audience/service conflation."
            ),
            "recommended_fix": "No further fix required for this regression." if not false_english_overlap else "Restrict direct service overlap to program-domain-supported service tags.",
        },
        {
            "code": "virtual_educationusa_service_resolved" if not missed_virtual_educationusa else "virtual_educationusa_service_gap",
            "severity": "resolved" if not missed_virtual_educationusa else "model_gap",
            "affected_records": len(higher_ed_assessments) if not missed_virtual_educationusa else len(missed_virtual_educationusa),
            "description": (
                "EducationUSA Kyrgyzstan remains a source-declared virtual, country-scoped service with structured State-directory provenance that contributes higher-education service availability independently of nearest physical-site geography."
                if not missed_virtual_educationusa else
                "At least one Kyrgyzstan higher-education assessment still misses the applicable country-scoped EducationUSA service or its structured source attribution."
            ),
            "recommended_fix": "Preserve service availability, structured source attribution, and physical proximity as independent dimensions." if not missed_virtual_educationusa else "Aggregate U.S. service sources by declared delivery mode and coverage scope independently of nearest-site geography.",
        },
        {
            "code": "us_site_precision_resolved" if not us_site_reference_gaps else "us_site_precision_gap",
            "severity": "resolved" if not us_site_reference_gaps else "model_gap",
            "affected_records": len(physical_sites) if not us_site_reference_gaps else len(us_site_reference_gaps),
            "description": (
                f"All physical/hybrid U.S. presence records are spatially resolved with explicit location precision, confidence, basis, and uncertainty. {location_summary['address_refined_physical_us_sites']} are site/address refined and {location_summary['city_centroid_physical_us_sites']} remain honestly labeled city-centroid references; no missing-coordinate physical record is reclassified as virtual."
                if not us_site_reference_gaps else
                "Some physical/hybrid U.S. presence records remain spatially unresolved or lack explicit precision/confidence/provenance/uncertainty."
            ),
            "recommended_fix": "Continue improving individual reference quality when better source data appears; never infer virtual delivery from missing coordinates." if not us_site_reference_gaps else "Resolve spatial data separately from delivery/coverage semantics and keep unresolved physical/hybrid records non-mappable until supported.",
        },
        {
            "code": "qualified_reach_metric_resolved" if not qualified_reach_missing else "qualified_reach_metric_gap",
            "severity": "resolved" if not qualified_reach_missing else "model_gap",
            "affected_records": len(approximate_reach_records) if not qualified_reach_missing else len(qualified_reach_missing),
            "description": (
                "Approximate and bounded attendance claims retain structured qualifiers and sources; none are silently promoted into bare exact integers or exact aggregate totals."
                if not qualified_reach_missing else
                "At least one approximate or bounded attendance claim lacks qualifier/source semantics or leaks into an exact reach field."
            ),
            "recommended_fix": "Preserve source qualifiers for future reach observations." if not qualified_reach_missing else "Encode reported reach using exact/approximate/minimum/maximum/range semantics.",
        },
        {
            "code": "multi_site_observation_resolved" if multi_site_records and not multi_site_missing else "multi_site_observation_gap",
            "severity": "resolved" if multi_site_records and not multi_site_missing else "model_gap",
            "affected_records": len(multi_site_records) if not multi_site_missing else len(multi_site_missing),
            "description": (
                "The International Chinese Language Day activity remains one research observation while carrying two independently sourced activity locations: Bishkek State University at site precision and International University of Kyrgyzstan at deliberately broader city precision because the event-specific campus is unresolved. Map density splits one total activity weight across both defensible locations instead of counting two activities."
                if multi_site_records and not multi_site_missing else
                "The multi-university Chinese Language Day source still collapses into one artificial location or lacks venue-specific precision/provenance."
            ),
            "recommended_fix": "No further multi-site schema fix required for this case; keep venue provenance and activity counts separate." if multi_site_records and not multi_site_missing else "Represent all source-supported venues as structured locations without duplicating the observation.",
        },
        {
            "code": "human_review_gate_working",
            "severity": "expected_guardrail",
            "affected_records": len(observations),
            "description": "All real-world records remain AI-triaged. The analyst map can display them for review, while verified-only outputs do not promote them to human-verified judgments.",
            "recommended_fix": "No fix; preserve this gate.",
        },
        {
            "code": "virtual_us_services_present",
            "severity": "context",
            "affected_records": len(virtual_sites),
            "description": "At least one important U.S. public-diplomacy service is explicitly source-declared as non-spatial and country-scoped; it can contribute service availability without a fake map point.",
            "recommended_fix": "Preserve delivery_mode/coverage_scope semantics and structured source attribution for virtual services.",
        },
    ]


def run_case(output_root: Path, *, clean: bool = False) -> dict:
    output_root = output_root.expanduser().resolve()
    if clean and output_root.exists():
        shutil.rmtree(output_root)

    workspace = SugarWorkspace.create(
        output_root,
        name=CASE_NAME,
        description="Reproducible public-source Kyrgyzstan case through 2026-09-14. Records are AI-triaged, not human verified; intended to exercise collection-to-review-to-map-to-brief guardrails.",
        exist_ok=True,
    )

    observations = build_observations()
    sites = build_us_presence_sites()
    observation_location_summary = apply_observation_location_enrichment(observations)
    us_location_summary = apply_us_site_location_enrichment(sites)
    location_summary = {**observation_location_summary, **us_location_summary}
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
    observation_outputs = [observation_csv, observation_csv.with_suffix(".xlsx"), observation_csv.with_suffix(".metadata.json")]
    workspace.register_outputs(observation_outputs, kind="observations", operation="kyrgyzstan-e2e")

    references_dir = workspace.path_for("references")
    structured_conflicts = build_source_conflicts()
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
        for path in save_state_package_with_conflicts(
            observations,
            assessments,
            state_dir,
            name=CASE_STEM,
            us_sites=sites,
            title="Kyrgyzstan 2026 Public Diplomacy Research Update",
            source_conflicts=structured_conflicts,
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

    record_audit = audit_state_records(observations, assessments)
    audit = _read_json(state_dir / f"{CASE_STEM}.audit.json")
    findings = _case_findings(observations, assessments, sites, location_summary)
    findings.extend(source_conflict_findings())
    analyst_metadata = _read_json(analyst_map.with_suffix(analyst_map.suffix + ".metadata.json"))
    verified_metadata = _read_json(verified_map.with_suffix(verified_map.suffix + ".metadata.json"))
    proximity_ledger = analyst_metadata.get("us_proximity", [])
    center_distances = [float(row["center_distance_km"]) for row in proximity_ledger]

    language_records = [row for row in observations if "language_education" in row.triage_labels]
    assessment_by_id = {row.observation_id: row for row in assessments}
    language_fallbacks = sum(
        "language_education" not in assessment_by_id[row.observation_id].program_domains
        or "other" in assessment_by_id[row.observation_id].program_domains
        for row in language_records
    )
    spurious_english_service_overlaps = sum(
        "english_language" in assessment_by_id[row.observation_id].us_overlap.service_overlap
        for row in language_records
    )
    higher_ed_assessments = [row for row in assessments if "higher_education" in row.program_domains]
    higher_ed_missing_educationusa = sum(
        "educationusa" not in row.us_overlap.service_overlap
        or not _has_structured_educationusa_source(row)
        for row in higher_ed_assessments
    )
    sites_missing_precision = sum(
        site.location_precision == "unknown"
        or site.location_confidence is None
        or site.location_uncertainty_km is None
        or not site.location_basis
        for site in sites if site.is_spatial
    )
    qualified_reach_assessments = [
        row for row in assessments
        if row.reach.metric("attendance") is not None and row.reach.metric("attendance").qualifier != "exact"
    ]
    qualified_reach_missing = sum(
        not row.reach.metric("attendance").source_note
        or not row.reach.metric("attendance").source_ref
        or row.reach.attendance is not None
        or row.reach.observed_total != 0
        for row in qualified_reach_assessments
    )
    multi_site_records = [row for row in observations if row.title == MULTI_SITE_TITLE]

    summary = {
        "case": CASE_NAME,
        "research_cutoff": "2026-09-14",
        "observations": len(observations),
        "assessments": len(assessments),
        "human_verified_observations": sum(row.verification_state == "human_verified" for row in observations),
        "brief_eligible_assessments": audit.get("brief_eligible", 0),
        "record_audit_status": record_audit.get("status"),
        "audit_status": audit.get("status"),
        "support_levels": support_summary,
        "language_domain_fallbacks": language_fallbacks,
        "spurious_english_service_overlaps": spurious_english_service_overlaps,
        "higher_ed_assessments": len(higher_ed_assessments),
        "higher_ed_missing_educationusa_service": higher_ed_missing_educationusa,
        "qualified_reach_assessments": len(qualified_reach_assessments),
        "qualified_reach_missing_source_or_semantics": qualified_reach_missing,
        "qualified_reach_exact_total": sum(row.reach.observed_total for row in qualified_reach_assessments),
        "multi_site_observations": len(multi_site_records),
        "structured_activity_locations": sum(len(row.locations) for row in observations),
        "us_sites_missing_precision": sites_missing_precision,
        "unresolved_physical_us_sites": location_summary.get("unresolved_physical_us_sites", 0),
        "physical_us_sites": sum(site.is_spatial for site in sites),
        "nonspatial_us_services": sum(site.delivery_mode == "virtual" for site in sites),
        "location_enrichment": location_summary,
        "source_conflicts": len(conflicts),
        "source_conflicts_requiring_human_review": audit.get("source_conflicts", {}).get("requiring_human_review", 0),
        "analyst_map_observations": analyst_metadata.get("mapped_observations"),
        "analyst_map_locations": analyst_metadata.get("mapped_locations"),
        "analyst_map_multi_location_observations": analyst_metadata.get("multi_location_observations"),
        "analyst_map_precision_counts": analyst_metadata.get("precision_counts", {}),
        "analyst_map_density_total_weight": analyst_metadata.get("density_total_weight"),
        "analyst_map_density_multi_location_observations": analyst_metadata.get("density_multi_location_observations"),
        "verified_map_observations": verified_metadata.get("mapped_observations"),
        "verified_map_locations": verified_metadata.get("mapped_locations"),
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
    record_audit_json = _write_json(reports_dir / "record-integrity-audit.json", record_audit)

    preliminary = [
        "# Kyrgyzstan 2026 — preliminary analyst note",
        "",
        "**Status:** AI-triaged public-source research exercise. This is not a human-verified State-facing brief.",
        "",
        f"The bounded case contains **{len(observations)}** PRC-linked public-diplomacy observations through September 14, 2026. The record spans Chinese-language education, Confucius Institute activity, university cooperation, cultural exhibitions and performances, literary and city-level exchanges, and governance/civilizational programming.",
        "",
        f"Seven single-site source records are refined to site-level geometry, three other observations remain deliberately city-level, and one Chinese Language Day observation now carries two venue entries without becoming two activities. Bishkek State University is represented at site precision; International University of Kyrgyzstan remains city-level because the event-specific campus is unresolved. The analyst map therefore contains 12 activity locations for 11 observations, while its density layer still totals 11.0 activity units. The U.S. layer contains eight spatially resolved physical American Spaces plus one source-declared virtual/country-scoped EducationUSA service; missing coordinates alone never create virtual-service semantics. Chinese-language records remain language-neutral, qualified attendance retains its original source semantics, and the EducationUSA topology conflict remains explicit. The record-integrity audit passes, while the complete State package is conditional because that source conflict still requires human review. PRC-support judgments remain evidence-calibrated: {support_summary['probable']} probable and {support_summary['possible']} possible, with none confirmed before human review.",
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
            "Mapped proximity, shared audience categories, thematic similarity, service availability, or reported reach do not establish competition, displacement, persuasion, coordination, or causal influence. Human review remains required before State-facing judgments.",
            "",
        ]
    )
    note_path = reports_dir / "preliminary-analyst-note.md"
    note_path.write_text("\n".join(preliminary), encoding="utf-8")
    report_outputs = [summary_json, findings_json, audit_json, record_audit_json, note_path]
    workspace.register_outputs(report_outputs, kind="report", operation="kyrgyzstan-e2e")

    assert len(observations) == 11
    assert summary["human_verified_observations"] == 0
    assert summary["brief_eligible_assessments"] == 0
    assert summary["record_audit_status"] == "pass"
    assert summary["audit_status"] == "conditional"
    assert summary["support_levels"] == {"probable": 9, "possible": 2}
    assert summary["language_domain_fallbacks"] == 0
    assert summary["spurious_english_service_overlaps"] == 0
    assert summary["higher_ed_assessments"] > 0
    assert summary["higher_ed_missing_educationusa_service"] == 0
    assert summary["qualified_reach_assessments"] == 3
    assert summary["qualified_reach_missing_source_or_semantics"] == 0
    assert summary["qualified_reach_exact_total"] == 0
    assert summary["multi_site_observations"] == 1
    assert summary["structured_activity_locations"] == 2
    assert summary["us_sites_missing_precision"] == 0
    assert summary["unresolved_physical_us_sites"] == 0
    assert summary["analyst_map_observations"] == 11
    assert summary["analyst_map_locations"] == 12
    assert summary["analyst_map_multi_location_observations"] == 1
    assert summary["analyst_map_density_total_weight"] == 11.0
    assert summary["analyst_map_density_multi_location_observations"] == 1
    assert summary["verified_map_observations"] == 0
    assert summary["verified_map_locations"] == 0
    assert summary["physical_us_sites"] == 8
    assert summary["nonspatial_us_services"] == 1
    assert summary["source_conflicts"] == 1
    assert summary["source_conflicts_requiring_human_review"] == 1
    assert summary["case_findings"] == 9
    assert summary["location_enrichment"]["site_refined_observations"] == 7
    assert summary["location_enrichment"]["city_level_observations"] == 3
    assert summary["location_enrichment"]["multi_site_observations"] == 1
    assert summary["location_enrichment"]["structured_activity_locations"] == 2
    assert summary["location_enrichment"]["address_refined_physical_us_sites"] == 2
    assert summary["location_enrichment"]["unresolved_physical_us_sites"] == 0
    assert summary["analyst_map_precision_counts"] == {"city": 4, "site": 8}
    assert center_distances and min(center_distances) > 0.1
    assert len(proximity_ledger) == 12
    assert all(row.get("site_precision") == "site" for row in proximity_ledger)
    assert all(float(row.get("site_uncertainty_km", 0)) == 0.25 for row in proximity_ledger)
    assert analyst_metadata.get("mapped_us_sites") == 8
    assert verified_metadata.get("mapped_us_sites") == 8
    assert workspace.status()["missing_artifacts"] == 0

    package_conflict_path = state_dir / f"{CASE_STEM}.source_conflicts.json"
    package_queue = pd.read_csv(state_dir / f"{CASE_STEM}.review_queue.csv")
    affected_conflict_rows = package_queue[
        package_queue["source_conflicts_requiring_human_review"] == 1
    ]
    package_workbook = pd.ExcelFile(state_dir / f"{CASE_STEM}.state.xlsx")
    package_brief = (state_dir / f"{CASE_STEM}.brief.md").read_text(encoding="utf-8")
    assert package_conflict_path.is_file()
    assert str(package_conflict_path.resolve()) in {str(path.resolve()) for path in package_outputs}
    assert len(affected_conflict_rows) == 2
    assert all("higher_education" in value for value in affected_conflict_rows["program_domains"])
    assert "source_conflicts" in package_workbook.sheet_names
    assert "EducationUSA Kyrgyzstan service topology" in package_brief
    assert "not a human adjudication" in package_brief

    finding_codes = {item["code"] for item in findings}
    assert "multi_site_observation_resolved" in finding_codes
    assert "multi_site_observation_gap" not in finding_codes
    assert "virtual_educationusa_service_resolved" in finding_codes
    assert "virtual_educationusa_service_gap" not in finding_codes

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
