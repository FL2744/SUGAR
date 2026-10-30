from __future__ import annotations

import json
import re
from collections import Counter

from sugar_core import team_catalog
from sugar_core.institutions import list_institutions
from sugar_core.reference_registry import entity_profile, review_claim, upsert_entity
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace


def test_compiled_catalog_integrity_and_activity_coverage():
    catalog = team_catalog._catalog()
    summary = team_catalog.catalog_summary()
    records = [record for dataset in catalog["networks"] for record in dataset["records"]]
    entity_ids = [record["entity_id"] for record in records]

    assert len(records) == 1_291
    assert len(entity_ids) == len(set(entity_ids))
    assert Counter(record["status"] for record in records) == {"active": 1_205, "closed": 72, "unknown": 14}
    assert all(record.get("status_basis") == "source_workbook_assumption" for record in records)
    assert all(record.get("source_status_claim") or record["status"] == "unknown" for record in records)
    assert all(record.get("source_origin") for record in records)
    for record in records:
        latitude, longitude = record.get("latitude"), record.get("longitude")
        assert (latitude is None) == (longitude is None)
        if latitude is not None:
            assert -90 <= float(latitude) <= 90
            assert -180 <= float(longitude) <= 180
    location_lead = next(record for record in records if "baruch" in record["name"].casefold())
    assert location_lead["latitude"] is None and location_lead["longitude"] is None
    assert location_lead["source_coordinates_claim"] == {
        "latitude": 31.7634918,
        "longitude": 35.191497,
        "source_origin": {"file": "Group 4/Confucius Institute Starter Locations.xlsx", "sheet": "United States", "row": 6},
    }
    assert location_lead["location_review"]["source_url"] == "https://www.baruch.cuny.edu/campus-map-and-directions/"

    audit = summary["activity_audit"]
    assert audit["core_records"] == 1_183
    assert audit["supplementary_records"] == 108
    assert audit["core_records_with_last_post_date"] == 0
    assert audit["supplementary_records_with_last_post_date"] == 0
    assert audit["named_site_checks"] == 5
    assert audit["named_site_checks_with_dated_signals"] == 4
    assert len(summary["curated_search_suggestions"]) == 6
    assert len(catalog["source_lists"]["search_terms"]) == 94
    assert len(catalog["source_lists"]["ci_american_spaces_overlap_claims"]) == 144
    assert len(catalog["source_lists"]["program_overlap_interpretations"]) == 8
    status_counts = summary["workbook_status_assumptions"]["by_network"]
    labels = {dataset["id"]: dataset["label"] for dataset in catalog["networks"]}
    assert status_counts[labels["american_spaces"]] == {"active": 536, "closed": 23, "unknown": 0}
    assert status_counts[labels["confucius_institutes"]] == {"active": 586, "closed": 0, "unknown": 0}

    publication_audit = summary["publication_audit"]
    assert publication_audit["rows_searched"] == 1_291
    assert len(publication_audit["records"]) == 1_291
    assert publication_audit["matched_page"] == 1_235
    assert publication_audit["exact_publication_date_candidate"] == 239
    assert publication_audit["relative_search_age_label"] == 952
    assert publication_audit["date_shown_in_result"] == 740
    assert publication_audit["no_relevant_result"] == 56
    assert all(record["entity_id"] in set(entity_ids) for record in publication_audit["records"])
    assert all(record["result"] != "not_searched" for record in publication_audit["records"])
    assert all(record.get("last_publication_search", {}).get("search_performed") for record in records)
    assert all("ref" not in candidate for record in publication_audit["records"] for candidate in record["candidates"])
    assert not re.search(r"turn\d+(?:search|fetch|view)\d+", json.dumps(publication_audit))


def test_import_and_three_layered_html_map_exports(tmp_path):
    project = ResearchProject(SugarWorkspace.create(tmp_path / "workspace", name="Catalog map check"))
    summary = team_catalog.catalog_summary()
    core = [item for item in summary["networks"] if item["default_selected"]]
    selected_ids = [item["id"] for item in core]

    imported = team_catalog.import_catalog(project, selected_ids)
    assert imported["selected_records"] == 1_183
    assert imported["added"] == 1_183
    repeated = team_catalog.import_catalog(project, selected_ids)
    assert repeated["added"] == 0
    assert repeated["skipped_existing"] == 1_183
    source_rows = {row["id"]: row for row in team_catalog._catalog()["networks"]}
    sample_id = source_rows["confucius_institutes"]["records"][0]["entity_id"]
    sample_entity = entity_profile(project.workspace, sample_id)
    assert sample_entity["status"] == "active"
    assert any(
        evidence.get("last_publication_search", {}).get("checked_on") == "2026-10-29"
        for evidence in sample_entity["source_evidence"]
    )
    assert any(
        evidence.get("reported_status") == "Active"
        and evidence.get("status_basis") == "source_workbook_assumption"
        for evidence in sample_entity["source_evidence"]
    )

    reference_id = next(item["id"] for item in core if source_rows[item["id"]]["role"] == "reference")
    subject_ids = [item["id"] for item in core if item["id"] != reference_id]
    comparisons = [[subject_ids[0], reference_id], [subject_ids[1], reference_id], subject_ids + [reference_id]]
    for comparison in comparisons:
        names = [source_rows[item]["network"] for item in comparison]
        result = team_catalog.export_network_map(project, names)
        output = project.workspace.root / result["file"]
        html = output.read_text(encoding="utf-8")
        assert output.is_file()
        assert "Network location comparison" in html
        assert "OpenStreetMap (online)" not in html
        assert "Natural Earth (public domain; de facto)" in html
        assert "fill: false" in html
        assert "sugar-country-label" in html
        assert "labelCountries" in html
        assert "connect-src 'none'" in html
        assert not re.search(r'<(?:script|link)[^>]+(?:src|href)="https?://', html)
        assert "L.tileLayer(" not in html
        assert "setPrefix(false)" in html
        assert "L.control.layers" in html
        assert re.search(r'"maxZoom"\s*:\s*19', html)
        assert "nearest reference" in html
        assert "Original source row" in html
        assert "Original workbook status claim" in html
        assert "working assumptions unless a human-verified registry status takes precedence" in html
        reference_network = source_rows[reference_id]["network"]
        assert result["counts"][reference_network]["status_counts"]
        assert result["counts"]


def test_html_map_keeps_human_verified_renamed_and_relocated_statuses(tmp_path):
    project = ResearchProject(SugarWorkspace.create(tmp_path / "workspace", name="Reviewed status map check"))
    core = [row for row in team_catalog.catalog_summary()["networks"] if row["default_selected"]]
    imported = team_catalog.import_catalog(project, [row["id"] for row in core])
    assert imported["added"] == 1_183
    catalog_rows = {row["id"]: row for row in team_catalog._catalog()["networks"]}
    ci = next(row for row in catalog_rows["confucius_institutes"]["records"] if row.get("latitude") is not None)
    luban = next(row for row in catalog_rows["luban_workshops"]["records"] if row.get("latitude") is not None)
    for record, status in ((ci, "renamed"), (luban, "relocated")):
        upsert_entity(project.workspace, {"entity_id": record["entity_id"], "entity_type": record["entity_type"],
                                          "name": record["name"], "network": record["network"], "status": status},
                      evidence_refs=[{"source_name": "human status review fixture"}])
        entity = entity_profile(project.workspace, record["entity_id"])
        claim = next(row for row in entity["claims"] if row["field"] == "status" and row["value"] == status)
        review_claim(project.workspace, record["entity_id"], claim["claim_id"], "human_verified", actor="Reviewer")

    network_names = [catalog_rows[row["id"]]["network"] for row in core]
    result = team_catalog.export_network_map(project, network_names)
    html = (project.workspace.root / result["file"]).read_text(encoding="utf-8")
    assert "↻" in html and "↗" in html
    assert "human-verified registry status renamed takes precedence" in html
    assert "human-verified registry status relocated takes precedence" in html
    assert result["counts"][catalog_rows["confucius_institutes"]["network"]]["status_counts"]["renamed"] == 1
    assert result["counts"][catalog_rows["luban_workshops"]["network"]]["status_counts"]["relocated"] == 1


def test_map_uses_workbook_status_assumption_for_older_unknown_import_and_honors_review(tmp_path):
    project = ResearchProject(SugarWorkspace.create(tmp_path / "workspace", name="Workbook status map check"))
    record = team_catalog._catalog()["networks"][0]["records"][0]
    legacy = upsert_entity(project.workspace, {
        "entity_id": record["entity_id"], "entity_type": record["entity_type"], "network": record["network"],
        "name": record["name"], "country": record["country"], "status": "unknown",
    }, evidence_refs=[{"source_name": "pre-assumption catalog import"}])

    mapped_active = list_institutions(project, status="active", assume_source_status=True)
    mapped = next(row for row in mapped_active["institutions"] if row["entity_id"] == record["entity_id"])
    assert mapped["status"] == "active"
    assert mapped["source_status_claim"] == "Active"
    assert mapped["status_basis"] == "source_workbook_assumption"

    status_claim = next(claim for claim in legacy["claims"] if claim["field"] == "status")
    review_claim(project.workspace, record["entity_id"], status_claim["claim_id"], "human_verified", actor="Reviewer")
    mapped_unknown = list_institutions(project, status="unknown", assume_source_status=True)
    reviewed = next(row for row in mapped_unknown["institutions"] if row["entity_id"] == record["entity_id"])
    assert reviewed["status"] == "unknown"
    assert reviewed["status_basis"] == "human_verified_registry"
