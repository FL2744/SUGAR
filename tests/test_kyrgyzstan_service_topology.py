from __future__ import annotations

import sys
from pathlib import Path

from sugar_core.state_schema import USPresenceSite

CASE_DIR = Path(__file__).resolve().parents[1] / "examples" / "cases" / "kyrgyzstan_2026"
if str(CASE_DIR) not in sys.path:
    sys.path.insert(0, str(CASE_DIR))

from location_enrichment import apply_us_site_location_enrichment


EDUCATIONUSA_NAME = "EducationUSA Kyrgyzstan (fully online from April 1, 2026)"


def test_educationusa_topology_is_explicit_not_inferred_from_missing_coordinates():
    site = USPresenceSite(
        name=EDUCATIONUSA_NAME,
        network="educationusa",
        country="Kyrgyzstan",
        service_tags=["educationusa", "study_in_the_us", "higher_education"],
        source_url="https://educationusa.state.gov/node/421",
        # Deliberately leave schema defaults here: the case topology declaration, not coordinate
        # absence, must supply the virtual/country semantics.
        latitude=None,
        longitude=None,
    )

    summary = apply_us_site_location_enrichment([site])

    assert site.delivery_mode == "virtual"
    assert site.coverage_scope == "country"
    assert site.latitude is None and site.longitude is None
    assert site.location_basis == "official_service_directory_nonspatial"
    assert summary["nonspatial_us_services"] == 1
    assert summary["unresolved_physical_us_sites"] == 0


def test_missing_coordinates_do_not_turn_physical_site_into_virtual_service():
    site = USPresenceSite(
        name="Unresolved American Space",
        network="american_space",
        country="Kyrgyzstan",
        city="Example City",
        service_tags=["culture"],
        delivery_mode="physical",
        coverage_scope="site",
        latitude=None,
        longitude=None,
    )

    summary = apply_us_site_location_enrichment([site])

    assert site.delivery_mode == "physical"
    assert site.coverage_scope == "site"
    assert not site.is_spatial
    assert site.location_basis == "unresolved_physical_site_missing_coordinates"
    assert summary["nonspatial_us_services"] == 0
    assert summary["unresolved_physical_us_sites"] == 1


def test_missing_coordinates_preserve_hybrid_delivery_and_declared_scope():
    site = USPresenceSite(
        name="Unresolved Hybrid Service",
        network="other_usg",
        country="Kyrgyzstan",
        city="Example City",
        service_tags=["professional_skills"],
        delivery_mode="hybrid",
        coverage_scope="city",
        latitude=None,
        longitude=None,
    )

    summary = apply_us_site_location_enrichment([site])

    assert site.delivery_mode == "hybrid"
    assert site.coverage_scope == "city"
    assert not site.is_spatial
    assert site.location_basis == "unresolved_physical_site_missing_coordinates"
    assert summary["unresolved_physical_us_sites"] == 1
