from __future__ import annotations

import json

from sugar_core.official_baselines import normalize_american_spaces, normalize_language_centers


def test_normalize_american_spaces_preserves_source_status_without_overstating_temporary_closure():
    rows = normalize_american_spaces([{
        "id": 986,
        "name": "American Corner Biratnagar",
        "uri": "acbiratnagar",
        "type_of_space": "AC",
        "country_name": "Nepal",
        "country": "NP",
        "region": "SCA",
        "city": "Biratnagar",
        "address": "Example address",
        "latitude": "26.4671285",
        "longitude": "87.286788",
        "status": "Temporarily Closed",
        "locator_use_generic_coordinates": None,
    }])
    assert len(rows) == 1
    row = rows[0]
    assert row["entity_id"] == "american-space:986"
    assert row["network"] == "American Spaces"
    assert row["status"] == "unknown"
    assert row["source_native_status"] == "Temporarily Closed"
    assert row["latitude"] == "26.4671285"
    assert "Official locator status: Temporarily Closed" in row["description"]


def test_normalize_language_centers_excludes_cms_root_and_preserves_partners():
    source = {
        "siteId": "abc",
        "siteKey": "2011001000",
        "name": "Language Center at Example University",
        "countryName": "Exampleland",
        "continentName": "Asia",
        "cooperationName": "Chinese Partner University",
        "enable": "1",
        "visible": "1",
        "deleted": "0",
        "updateTime": "2026-09-01 10:00:00",
        "jsonData": json.dumps({
            "establish": "2025-04-25",
            "cooperative_1": "Chinese Partner University",
            "local_cooperative_1": "Example University",
        }),
    }
    rows = normalize_language_centers([
        {"siteKey": "www", "name": "1", "countryName": None},
        source,
    ])
    assert len(rows) == 1
    row = rows[0]
    assert row["entity_id"] == "language-center:2011001000"
    assert row["network"] == "Language Education Centers"
    assert row["status"] == "unknown"
    assert row["opened_date"] == "2025-04-25"
    assert row["host_entities"] == "Example University"
    assert row["partner_entities"] == "Chinese Partner University"
