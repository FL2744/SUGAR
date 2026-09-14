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

    assert summary == {"site_refined_observations": 7, "city_level_observations": 4}
    site_rows = [row for row in observations if "source_named_site" in row.location_basis]
    city_rows = [row for row in observations if row.location_basis == "reported_city"]
    assert len(site_rows) == 7
    assert len(city_rows) == 4
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
    museum = next(row for row in observations if row.title == "Chinese painting exhibition at the National Historical Museum")
    assert (museum.latitude, museum.longitude) != (america_borboru.latitude, america_borboru.longitude)
    assert museum.location_basis.startswith("source_named_site")


def test_multi_site_language_day_record_stays_city_level():
    observations = CASE_DATA.build_observations()
    LOCATION.apply_observation_location_enrichment(observations)
    row = next(obs for obs in observations if obs.title == "International Chinese Language Day events at Bishkek universities")
    assert row.location_basis == "reported_city"
    assert row.location_confidence == 0.80
