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
# This remains a conservative fallback for legacy/unknown U.S. records. The current case populates
# per-site uncertainty, and the proximity engine now prefers each site's own value.
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
        or "EducationUSA Kyrgyzstan" not in row.us_overlap.note
    ]
    physical_sites = [site for site in sites if site.is_spatial]
    virtual_sites = [site for site in sites if site.delivery_mode == "virtual"]
    sites_missing_precision = [
        site for site in physical_sites
        if site.location_precision == "unknown"
        or site.location_confidence is None
        or site.location_uncertainty_km is None
        or not site.location_basis
    ]
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
            "code": "language_education_domain_resolved" if not language_fallback else "language_education_domain_gap",
            "severity": "resolved" if not language_fallback else "model_gap",
            "affected_records": len(language_records) if not language_fallback else len(language_fallback),
            "description": (
                "Chinese-language education is now represented by the generic language_education State domain without being equated to English-language programming."
                if not language_fallback else
                "Some Chinese-language education records still fall back to an undifferentiated domain instead of language_education."
            ),
            "recommended_fix": (
                "No further taxonomy fix required for this case; preserve language_education as language-neutral."
                if not language_fallback else
                "Migrate remaining language records to the language_education domain."
            ),
        },
        {
            "code": "direct_service_overlap_semantics_resolved" if not false_english_overlap else "direct_service_overlap_semantics_gap",
            "severity": "resolved" if not false_english_overlap else "model_gap",
            "affected_records": len(language_records) if not false_english_overlap else len(false_english_overlap),
            "description": (
                "Audience similarity no longer manufactures a direct English-language service overlap for Chinese-language activities; audience, thematic, and service overlap remain separate dimensions."
                if not false_english_overlap else
                "At least one Chinese-language record is still being labeled with a direct English-language service overlap because audience and service semantics are conflated."
            ),
            "recommended_fix": (
                "No further fix required for the audience-to-service conflation regression."
                if not false_english_overlap else
                "Restrict direct service overlap to program-domain-supported service tags."
            ),
        },
        {
            "code": "virtual_educationusa_service_resolved" if not missed_virtual_educationusa else "virtual_educationusa_service_gap",
            "severity": "resolved" if not missed_virtual_educationusa else "model_gap",
            "affected_records": len(higher_ed_assessments) if not missed_virtual_educationusa else len(missed_virtual_educationusa),
            "description": (
                "EducationUSA Kyrgyzstan is represented as a virtual, country-scoped service and now contributes higher-education service availability across Kyrgyzstan independently of nearest physical-site geography; the assessment note identifies the virtual service source while the map remains non-spatial."
                if not missed_virtual_educationusa else
                "At least one Kyrgyzstan higher-education assessment still fails to receive the applicable country-scoped virtual EducationUSA service or its source attribution."
            ),
            "recommended_fix": (
                "No further country-scope aggregation fix required for this case; preserve service availability and physical proximity as independent dimensions."
                if not missed_virtual_educationusa else
                "Aggregate applicable U.S. service sources by delivery mode and coverage scope independently of nearest-site geography."
            ),
        },
        {
            "code": "us_site_precision_resolved" if not sites_missing_precision else "us_site_precision_gap",
            "severity": "resolved" if not sites_missing_precision else "model_gap",
            "affected_records": len(physical_sites) if not sites_missing_precision else len(sites_missing_precision),
            "description": (
                f"All physical U.S. presence records now carry explicit location precision, confidence, basis, and uncertainty. {location_summary['address_refined_physical_us_sites']} are site/address refined and {location_summary['city_centroid_physical_us_sites']} remain honestly labeled city-centroid references; proximity consumes the per-site envelope before the legacy fallback."
                if not sites_missing_precision else
                "Some physical U.S. presence records still lack explicit precision/confidence/provenance/uncertainty."
            ),
            "recommended_fix": (
                "No further core precision-field fix required; continue improving individual reference quality as better source data becomes available."
                if not sites_missing_precision else
                "Populate per-site location precision, confidence, basis, and uncertainty."
            ),
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
            "description": "At least one important U.S. public-diplomacy service is explicitly non-spatial and country-scoped; it can contribute service availability without being forced onto a fake map point.",
            "recommended_fix": "Preserve delivery_mode/coverage_scope semantics and source attribution when adding future virtual services.",
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
        or "EducationUSA Kyrgyzstan" not in row.us_overlap.note
        for row in higher_ed_assessments
    )
    sites_missing_precision = sum(
        site.location_precision == "unknown"
        or site.location_confidence is None
        or site.location_uncertainty_km is None
        or not site.location_basis
        for site in sites if site.is_spatial
    )

    summary = {
        "case": CASE_NAME,
        "research_cutoff": "2026-09-14",
        "observations": len(observations),
        "assessments": len(assessments),
        "human_verified_observations": sum(row.verification_state == "human_verified" for row in observations),
        "brief_eligible_assessments": audit.get("brief_eligible", 0),
        "audit_status": audit.get("status"),
        "support_levels": support_summary,
        "language_domain_fallbacks": language_fallbacks,
        "spurious_english_service_overlaps": spurious_english_service_overlaps,
        "higher_ed_assessments": len(higher_ed_assessments),
        "higher_ed_missing_educationusa_service": higher_ed_missing_educationusa,
        "us_sites_missing_precision": sites_missing_precision,
        "physical_us_sites": sum(site.is_spatial for site in sites),
        "nonspatial_us_services": sum(site.delivery_mode == "virtual" for site in sites),
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
        f"Seven source records name a venue/institution that can be refined to site-level geometry with separate public location references; four remain deliberately city-level. The U.S. layer contains eight physical American Spaces, of which two are address-refined while six remain honestly labeled city-centroid references, plus one explicit virtual/country-scoped EducationUSA service. Physical proximity and service availability are now independent: EducationUSA can contribute higher-education service overlap across Kyrgyzstan without becoming a map point or replacing the nearest physical American Space. U.S. proximity consumes each physical site's own precision/confidence/uncertainty metadata rather than treating every coordinate as equally exact. Chinese-language records use the generic language_education domain and remain distinct from English-language programming. The current State EducationUSA directory and American Councils page still conflict about whether the Bishkek advising service has a physical location, so that contradiction is retained explicitly. PRC-support judgments remain evidence-calibrated: {support_summary['probable']} probable and {support_summary['possible']} possible, with none confirmed before human review. The analyst map is available before human verification; the verified-only map contains no PRC observations until review gates are satisfied.",
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
            "Mapped proximity, shared audience categories, thematic similarity, or service availability do not establish competition, displacement, persuasion, coordination, or causal influence. Human review remains required before State-facing judgments.",
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
    assert summary["language_domain_fallbacks"] == 0
    assert summary["spurious_english_service_overlaps"] == 0
    assert summary["higher_ed_assessments"] > 0
    assert summary["higher_ed_missing_educationusa_service"] == 0
    assert summary["us_sites_missing_precision"] == 0
    assert summary["analyst_map_observations"] == 11
    assert summary["verified_map_observations"] == 0
    assert summary["physical_us_sites"] == 8
    assert summary["nonspatial_us_services"] == 1
    assert summary["source_conflicts"] == 1
    assert summary["case_findings"] == 9
    assert summary["location_enrichment"]["site_refined_observations"] == 7
    assert summary["location_enrichment"]["city_level_observations"] == 4
    assert summary["location_enrichment"]["address_refined_physical_us_sites"] == 2
    assert summary["analyst_map_precision_counts"] == {"city": 4, "site": 7}
    assert center_distances and min(center_distances) > 0.1
    assert proximity_ledger and all(row.get("site_precision") == "site" for row in proximity_ledger)
    assert proximity_ledger and all(float(row.get("site_uncertainty_km", 0)) == 0.25 for row in proximity_ledger)
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
