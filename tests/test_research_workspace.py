import csv
import json
from pathlib import Path

from sugar_core.reference_registry import (
    add_relationship,
    entity_profile,
    export_registry,
    import_reference_dataset,
    list_entities,
    preview_reference_import,
)
from sugar_core.reference_templates import write_reference_template
from sugar_core.workspace import SugarWorkspace


def test_source_backed_reference_import_retains_scope_claims_and_relationships(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Research Project")
    template = Path(write_reference_template(workspace, "language_education_centers"))
    with template.open(encoding="utf-8-sig", newline="") as stream:
        assert "source_url" in next(csv.reader(stream))

    source = tmp_path / "reference.csv"
    source.write_text(
        "site_id,name,country,status,program_descriptions,audience_descriptions,delivery_mode_descriptions,source_url\n"
        "center-1,Example Center,Exampleland,active,English language learning,university students,hybrid,https://example.org/center\n"
        "center-2,Example Advising Service,Exampleland,active,education advising,educators,virtual,https://example.org/advising\n",
        encoding="utf-8",
    )
    preview = preview_reference_import(source)
    assert preview["valid_rows"] == 2
    assert preview["suggested_mapping"]["name"] == "name"

    result = import_reference_dataset(
        workspace,
        source,
        mapping={
            "entity_id": "site_id",
            "name": "name",
            "country": "country",
            "status": "status",
            "program_descriptions": "program_descriptions",
            "audience_descriptions": "audience_descriptions",
            "delivery_mode_descriptions": "delivery_mode_descriptions",
            "source_url": "source_url",
        },
        dataset_name="Reviewed reference export",
        network="Language education network",
        geographic_scope="Exampleland",
        known_coverage_limits="Two rows from one documented export.",
        license_notes="Research reuse permitted by source terms.",
        actor="Analyst One",
        review_state="human_verified",
    )

    assert result["added"] == 2
    entities = list_entities(workspace)
    center = next(row for row in entities if row["entity_id"] == "center-1")
    service = next(row for row in entities if row["entity_id"] == "center-2")
    assert center["program_descriptions"] == ["English language learning"]
    assert center["normalized_program_domains"] == ["language_learning"]
    assert center["normalized_audiences"] == ["university_students"]
    assert center["normalized_delivery_modes"] == ["hybrid"]
    assert center["resolved_fields"]["name"]["state"] == "human_verified"
    assert center["claims"][0]["evidence_refs"][0]["source_row"] == 2
    assert json.loads((workspace.path_for("references") / "registry" / "dataset_manifest.json").read_text(encoding="utf-8"))["datasets"][0]["known_coverage_limits"] == "Two rows from one documented export."

    relationship = add_relationship(
        workspace,
        source_entity_id=center["entity_id"],
        target_entity_id=service["entity_id"],
        relationship_type="partner_of",
        evidence_refs=["https://example.org/relationship"],
        actor="Analyst One",
        review_state="human_verified",
    )
    profile = entity_profile(workspace, center["entity_id"])
    assert profile["relationships"][0]["relationship_id"] == relationship["relationship_id"]
    exported = Path(export_registry(workspace, tmp_path / "registry.geojson", format="geojson"))
    assert json.loads(exported.read_text(encoding="utf-8"))["type"] == "FeatureCollection"
