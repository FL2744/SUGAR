from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parents[1] / "examples" / "cases" / "kyrgyzstan_2026"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CASE_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CASE_DATA = _load("kyrgyzstan_case_data_location_test", "case_data.py")
LOCATION = _load("kyrgyzstan_location_enrichment_test", "location_enrichment.py")


def test_location_enrichment_refines_supported_venues_without_upgrading_everything():
    observations = CASE_DATA.build_observations()
    summary = LOCATION.apply_observation_location_enrichment(observations)

    assert summary == {
        "site_refined_observations": 7,
        "city_level_observations": 3,
        "multi_site_observations": 1,
        "structured_activity_locations": 2,
    }
    site_rows = [row for row in observations if "source_named_site" in row.location_basis]
    city_rows = [row for row in observations if row.location_basis == "reported_city"]
    multi_rows = [row for row in observations if row.locations]
    assert len(site_rows) == 7
    assert len(city_rows) == 3
    assert len(multi_rows) == 1
    assert all(row.location_confidence == 0.90 for row in site_rows)
    assert all(any(ref.source_type == "location_reference" for ref in row.evidence) for row in site_rows)
    assert all(not any(ref.source_type == "location_reference" for ref in row.evidence) for row in city_rows)


def test_location_enrichment_breaks_city_centroid_collision_with_bishkek_space():
    observations = CASE_DATA.build_observations()
    sites = CASE_DATA.build_us_presence_sites()
    LOCATION.apply_observation_location_enrichment(observations)
    us_summary = LOCATION.apply_us_site_location_enrichment(sites)

    assert us_summary["address_refined_physical_us_sites"] == 2
    america_borboru = next(site for site in sites if site.name == "America Borboru Bishkek")
    museum = next(
        row for row in observations if row.title == "Chinese painting exhibition at the National Historical Museum"
    )
    assert (museum.latitude, museum.longitude) != (america_borboru.latitude, america_borboru.longitude)
    assert museum.location_basis.startswith("source_named_site")
    assert america_borboru.delivery_mode == "physical"
    assert america_borboru.coverage_scope == "site"
    assert america_borboru.location_precision == "site"
    assert america_borboru.location_confidence == 0.95
    assert america_borboru.location_uncertainty_km == 0.25


def test_nonspatial_educationusa_is_explicitly_virtual_and_country_scoped():
    sites = CASE_DATA.build_us_presence_sites()
    summary = LOCATION.apply_us_site_location_enrichment(sites)
    educationusa = next(site for site in sites if site.network == "educationusa")

    assert summary["nonspatial_us_services"] == 1
    assert educationusa.delivery_mode == "virtual"
    assert educationusa.coverage_scope == "country"
    assert educationusa.location_precision == "unknown"
    assert educationusa.location_uncertainty_km is None
    assert not educationusa.is_spatial


def test_city_centroid_us_sites_are_labeled_broad_not_exact():
    sites = CASE_DATA.build_us_presence_sites()
    LOCATION.apply_us_site_location_enrichment(sites)
    jalal_abad = next(site for site in sites if site.city == "Jalal-Abad")

    assert jalal_abad.delivery_mode == "physical"
    assert jalal_abad.location_precision == "city"
    assert jalal_abad.location_confidence == 0.75
    assert jalal_abad.location_uncertainty_km == 12.0
    assert "city_centroid" in jalal_abad.location_basis


def test_multi_site_language_day_record_preserves_two_venues_without_guessing_iuk_campus():
    observations = CASE_DATA.build_observations()
    LOCATION.apply_observation_location_enrichment(observations)
    row = next(
        obs for obs in observations if obs.title == "International Chinese Language Day events at Bishkek universities"
    )

    assert row.location_basis == "multi_site_summary_city"
    assert row.location_confidence == 0.75
    assert len(row.locations) == 2
    assert len({item.location_id for item in row.locations}) == 2

    bsu = next(item for item in row.locations if "Bishkek State University" in item.label)
    iuk = next(item for item in row.locations if "International University of Kyrgyzstan" in item.label)
    assert bsu.precision == "site"
    assert bsu.latitude is not None and bsu.longitude is not None
    assert "bhu.kg" in bsu.source_ref
    assert iuk.precision == "city"
    assert iuk.uncertainty_km == 12.0
    assert "campus_unresolved" in iuk.basis
    assert "china-embassy" in iuk.source_ref
    assert any(ref.url == LOCATION.BSU_OFFICIAL_SOURCE for ref in row.evidence)
    assert any(ref.url == LOCATION.IUK_OFFICIAL_SOURCE for ref in row.evidence)
