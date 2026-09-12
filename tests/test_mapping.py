from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sugar_core.mapping import (
    MapOptions,
    _normalize_reference_rows,
    _normalize_rows,
    _popup_html,
    create_map,
    detect_dataset_type,
    load_map_frame,
)
from sugar_core.service import _map_options, run_map


def _observation_frame() -> pd.DataFrame:
    now = pd.Timestamp.now(tz="UTC").floor("s").isoformat()
    return pd.DataFrame(
        [
            {
                "observation_id": "obs_verified",
                "observation_type": "program",
                "title": "Public technology workshop",
                "summary": "A public workshop for university students.",
                "observed_at": now,
                "activity_status": "active",
                "location_label": "Bishkek, Kyrgyzstan",
                "country": "Kyrgyzstan",
                "city": "Bishkek",
                "latitude": 42.8746,
                "longitude": 74.5698,
                "location_basis": "source_stated",
                "location_confidence": 0.98,
                "institution_name": "Example Center",
                "program_name": "Technology Workshop",
                "actors": '["Example Center", "Partner University"]',
                "audiences": '["students", "emerging leaders"]',
                "themes": '["technology", "education"]',
                "us_overlap": '["American Space nearby"]',
                "overlap_note": "Same city as an American Space.",
                "verification_state": "human_verified",
                "triage_labels": '["prc_public_diplomacy"]',
                "ai_confidence": 0.91,
                "primary_source_url": "https://example.test/source",
            },
            {
                "observation_id": "obs_followup",
                "observation_type": "institution",
                "title": "Institution record",
                "summary": "Needs additional verification.",
                "observed_at": now,
                "location_label": "Osh, Kyrgyzstan",
                "country": "Kyrgyzstan",
                "city": "Osh",
                "latitude": 40.5139,
                "longitude": 72.8161,
                "location_basis": "geocoded_city",
                "location_confidence": 0.72,
                "verification_state": "needs_followup",
                "primary_source_url": "javascript:alert(1)",
            },
            {
                "observation_id": "obs_unmapped",
                "observation_type": "event",
                "title": "No coordinates",
                "summary": "Should count as unmapped.",
                "country": "Kyrgyzstan",
                "latitude": None,
                "longitude": None,
                "verification_state": "unreviewed",
            },
        ]
    )


def test_detects_observation_and_source_record_datasets():
    assert detect_dataset_type(_observation_frame()) == "research_observations"
    assert detect_dataset_type(
        pd.DataFrame([{"platform": "weibo", "latitude": 1, "longitude": 2}])
    ) == "source_records"


def test_normalization_filters_invalid_coordinates_and_parses_lists():
    frame = _observation_frame()
    frame.loc[len(frame)] = {
        "observation_id": "bad",
        "observation_type": "event",
        "title": "Invalid coordinate",
        "latitude": 190,
        "longitude": 500,
    }

    normalized, dataset_type = _normalize_rows(frame)

    assert dataset_type == "research_observations"
    assert set(normalized["_record_id"]) == {"obs_verified", "obs_followup"}
    verified = normalized.loc[normalized["_record_id"].eq("obs_verified")].iloc[0]
    assert verified["_audiences"] == ["students", "emerging leaders"]
    assert verified["_us_overlap"] == ["American Space nearby"]
    assert verified["_verification"] == "human_verified"
    assert set(normalized["_kind"]) == {"program", "institution"}


def test_observation_workbook_is_loaded_from_observations_sheet(tmp_path: Path):
    path = tmp_path / "observations.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _observation_frame().to_excel(writer, sheet_name="observations", index=False)
        pd.DataFrame([{"ignore": True}]).to_excel(writer, sheet_name="other", index=False)

    loaded = load_map_frame(path)

    assert "observation_id" in loaded.columns
    assert loaded.iloc[0]["observation_id"] == "obs_verified"


def test_source_record_workbook_falls_back_to_posts_sheet(tmp_path: Path):
    path = tmp_path / "posts.xlsx"
    expected = pd.DataFrame(
        [
            {
                "platform": "bilibili",
                "native_id": "BV1",
                "content_type": "video",
                "original_text": "Example",
                "latitude": 39.9,
                "longitude": 116.4,
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        expected.to_excel(writer, sheet_name="posts", index=False)

    loaded = load_map_frame(path)

    assert loaded.iloc[0]["platform"] == "bilibili"


def test_popup_semantics_and_safety_are_independent_of_folium_serialization():
    frame = _observation_frame()
    frame.loc[0, "title"] = "<script>alert('x')</script>"
    normalized, _ = _normalize_rows(frame)

    verified = normalized.loc[normalized["_record_id"].eq("obs_verified")].iloc[0]
    followup = normalized.loc[normalized["_record_id"].eq("obs_followup")].iloc[0]
    verified_popup = _popup_html(verified, 2200)
    followup_popup = _popup_html(followup, 2200)

    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in verified_popup
    assert "Open source evidence" in verified_popup
    assert "students, emerging leaders" in verified_popup
    assert "American Space nearby" in verified_popup
    assert "location confidence: 0.98" in verified_popup
    assert "javascript:alert(1)" not in followup_popup
    assert "<script>" not in verified_popup


def test_create_map_smoke_contains_plain_analytical_panel_content(tmp_path: Path):
    frame = _observation_frame()
    rejected = frame.iloc[0].copy()
    rejected["observation_id"] = "obs_rejected"
    rejected["title"] = "Rejected record"
    rejected["verification_state"] = "rejected"
    rejected["latitude"] = 41.2
    rejected["longitude"] = 74.2
    frame = pd.concat([frame, pd.DataFrame([rejected])], ignore_index=True)
    path = tmp_path / "research_map.html"

    result = create_map(
        frame,
        path,
        options=MapOptions(
            title="Diplomacy Lab Map",
            heat_windows=(30, 90),
            default_heat_window=90,
        ),
    )

    assert result == str(path.resolve())
    text = path.read_text(encoding="utf-8")
    assert "Diplomacy Lab Map" in text
    assert "Research observations" in text
    assert "rejected observations excluded from default density" in text
    assert "records tagged for U.S. overlap" in text
    assert "not influence" in text
    assert "CartoDB" not in text


def test_create_map_supports_raw_source_records_and_platform_semantics(tmp_path: Path):
    now = pd.Timestamp.now(tz="UTC").floor("s").isoformat()
    frame = pd.DataFrame(
        [
            {
                "platform": "weibo",
                "native_id": "123",
                "content_type": "post",
                "published_at": now,
                "author_name": "Example account",
                "translated_text": "Public post",
                "inferred_location": "Beijing, China",
                "location_confidence": 0.8,
                "latitude": 39.9042,
                "longitude": 116.4074,
                "canonical_url": "https://m.weibo.cn/detail/123",
                "source_mode": "weibo_public_status_anonymous",
            }
        ]
    )
    normalized, dataset_type = _normalize_rows(frame)
    row = normalized.iloc[0]

    assert dataset_type == "source_records"
    assert row["_platform"] == "weibo"
    assert row["_kind"] == "post"
    popup = _popup_html(row, 2200)
    assert "Weibo Post" in popup
    assert "weibo_public_status_anonymous" in popup

    path = tmp_path / "posts_map.html"
    create_map(frame, path)
    text = path.read_text(encoding="utf-8")
    assert "Source records" in text
    assert "Source platforms" in text


def test_map_option_parser_preserves_custom_heat_windows():
    options = _map_options(
        {
            "map": {
                "title": "American Spaces / PRC Activity",
                "heat_windows": [30, 180],
                "default_heat_window": 180,
            }
        }
    )
    assert options.title == "American Spaces / PRC Activity"
    assert options.heat_windows == (30, 180)
    assert options.default_heat_window == 180


def test_run_map_accepts_observation_xlsx_and_custom_title(tmp_path: Path):
    source = tmp_path / "observations.xlsx"
    output = tmp_path / "map.html"
    with pd.ExcelWriter(source, engine="openpyxl") as writer:
        _observation_frame().to_excel(writer, sheet_name="observations", index=False)

    outputs = run_map(
        {
            "source_file": str(source),
            "output_file": str(output),
            "map": {
                "title": "American Spaces / PRC Activity",
                "heat_windows": [30, 180],
                "default_heat_window": 180,
            },
        }
    )

    assert outputs == [str(output.resolve())]
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "American Spaces / PRC Activity" in text


def test_run_map_supports_generic_reference_layers(tmp_path: Path):
    source = tmp_path / "observations.csv"
    reference = tmp_path / "american_spaces.csv"
    output = tmp_path / "overlap_map.html"
    _observation_frame().to_csv(source, index=False)
    reference_frame = pd.DataFrame(
        [
            {
                "name": "American Space Bishkek",
                "category": "American Space",
                "city": "Bishkek",
                "country": "Kyrgyzstan",
                "latitude": 42.87,
                "longitude": 74.60,
                "url": "https://example.test/american-space",
            }
        ]
    )
    reference_frame.to_csv(reference, index=False)

    normalized_reference = _normalize_reference_rows(reference_frame)
    assert normalized_reference.iloc[0]["_title"] == "American Space Bishkek"
    assert normalized_reference.iloc[0]["_category"] == "American Space"

    outputs = run_map(
        {
            "source_file": str(source),
            "output_file": str(output),
            "map": {
                "reference_layers": [
                    {
                        "name": "American Spaces",
                        "file": str(reference),
                    }
                ]
            },
        }
    )

    assert outputs == [str(output.resolve())]
    text = output.read_text(encoding="utf-8")
    assert "American Spaces reference" in text
    assert "external reference points" in text


def test_create_map_rejects_dataset_without_coordinates(tmp_path: Path):
    with pytest.raises(ValueError, match="No valid coordinates"):
        create_map(pd.DataFrame([{"title": "unmapped"}]), tmp_path / "map.html")
