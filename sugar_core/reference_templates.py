from __future__ import annotations

import csv
from typing import Any

from .workspace import SugarWorkspace


COMMON_FIELDS = [
    "entity_id", "name", "entity_type", "network", "aliases", "status", "status_date",
    "opened_date", "closed_date", "country", "region", "city", "address", "latitude",
    "longitude", "location_precision", "delivery_modes", "coverage_scope", "program_domains",
    "program_descriptions", "normalized_program_domains", "audiences", "audience_descriptions",
    "normalized_audiences", "delivery_mode_descriptions", "normalized_delivery_modes",
    "host_entities", "partner_entities", "accounts", "public_links", "source_url",
    "source_license", "description",
]

REFERENCE_TEMPLATES: dict[str, dict[str, Any]] = {
    "american_spaces": {
        "label": "American Spaces", "network": "American Spaces",
        "extra_fields": ["space_model", "host_organization", "educationusa_center_hosted", "service_region"],
    },
    "educationusa": {
        "label": "EducationUSA", "network": "EducationUSA",
        "extra_fields": ["service_mode", "regional_advising_coordinator", "hosted_at_space", "virtual_service_geography"],
    },
    "language_education_centers": {
        "label": "Language education centers and classrooms", "network": "Language education network",
        "extra_fields": ["host_university", "classroom_affiliation", "sponsoring_organization"],
    },
    "technical_training_workshops": {
        "label": "Technical training workshops", "network": "Technical training network",
        "extra_fields": ["host_vocational_institution", "industry_partner", "technical_domain"],
    },
    "custom": {"label": "Custom engagement network", "network": "", "extra_fields": []},
}


def write_reference_template(workspace: SugarWorkspace, template: str) -> str:
    key = str(template or "custom").strip().casefold().replace("-", "_").replace(" ", "_")
    if key not in REFERENCE_TEMPLATES:
        raise ValueError(f"Choose one of: {', '.join(sorted(REFERENCE_TEMPLATES))}.")
    definition = REFERENCE_TEMPLATES[key]
    fields = COMMON_FIELDS + list(definition["extra_fields"])
    target_dir = workspace.path_for("references") / "templates"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{key}_reference_template.csv"
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        csv.writer(stream).writerow(fields)
    readme = target.with_name("README.txt")
    readme.write_text(
        "These are blank schema templates, not maintained institution inventories.\n"
        "Populate rows only from documented sources. Retain source URL, retrieval/update date,\n"
        "permitted-use notes, geographic and temporal scope, and known coverage limits.\n"
        "Use semicolons for multiple values in list fields. Confirm the field mapping and\n"
        "review invalid rows before importing. Source program/audience/delivery wording is retained;\n"
        "only exact supported labels are normalized, and audiences are never inferred from titles.\n",
        encoding="utf-8",
    )
    workspace.register_artifact("reference_template", target, label=f"Blank {definition['label']} reference schema",
                                metadata={"network": definition["network"], "fields": fields,
                                          "contains_institution_records": False})
    workspace.register_artifact("reference_template_readme", readme, label="Reference template guidance")
    return str(target)
