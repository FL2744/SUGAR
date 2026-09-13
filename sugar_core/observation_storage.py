from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .observations import OBSERVATION_SCHEMA_VERSION, ResearchObservation
from .utils import safe_cell, utc_iso

PREFERRED_OBSERVATION_COLUMNS = [
    "observation_id",
    "observation_type",
    "title",
    "summary",
    "observed_at",
    "activity_status",
    "location_label",
    "country",
    "region",
    "city",
    "latitude",
    "longitude",
    "location_basis",
    "location_confidence",
    "institution_name",
    "program_name",
    "actors",
    "audiences",
    "themes",
    "us_overlap",
    "overlap_note",
    "triage_labels",
    "ai_confidence",
    "ai_model",
    "ai_reason",
    "verification_state",
    "reviewer",
    "reviewed_at",
    "verification_notes",
    "primary_source_url",
    "evidence",
    "source_record_keys",
    "created_at",
    "updated_at",
    "schema_version",
]

_NUMERIC_COLUMNS = {"latitude", "longitude", "location_confidence", "ai_confidence"}
_LONG_TEXT_COLUMNS = {"summary", "overlap_note", "ai_reason", "verification_notes", "evidence"}


def observations_to_frame(observations: Iterable[ResearchObservation]) -> pd.DataFrame:
    frame = pd.DataFrame([observation.export_dict() for observation in observations])
    if frame.empty:
        return frame
    for column in frame.columns:
        if column not in _NUMERIC_COLUMNS:
            frame[column] = frame[column].map(lambda value: safe_cell(value, formula_safe=True))
    ordered = [column for column in PREFERRED_OBSERVATION_COLUMNS if column in frame.columns]
    ordered.extend(column for column in frame.columns if column not in ordered)
    return frame[ordered]


def save_observations(
    observations: Iterable[ResearchObservation],
    output_file: str | Path,
    *,
    metadata: dict | None = None,
) -> pd.DataFrame:
    observations = list(observations)
    if not observations:
        raise ValueError("No research observations were provided.")

    frame = observations_to_frame(observations)
    output_file = Path(output_file)
    csv_path = output_file if output_file.suffix.lower() == ".csv" else output_file.with_suffix(".csv")
    xlsx_path = csv_path.with_suffix(".xlsx")
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    frame.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="observations")
        worksheet = writer.sheets["observations"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        fill = PatternFill("solid", fgColor="D9EAF7")
        font = Font(bold=True)
        for cell in worksheet[1]:
            cell.fill = fill
            cell.font = font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for index, name in enumerate(frame.columns, 1):
            width = 20
            if name in _LONG_TEXT_COLUMNS:
                width = 60
            elif name in {"primary_source_url"}:
                width = 45
            elif name in {"actors", "audiences", "themes", "us_overlap", "triage_labels"}:
                width = 35
            worksheet.column_dimensions[get_column_letter(index)].width = width
        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    metadata_path = csv_path.with_suffix(".metadata.json")
    payload = {
        "generated_at": utc_iso(),
        "records": len(frame),
        "dataset_type": "research_observations",
        "observation_schema_version": OBSERVATION_SCHEMA_VERSION,
        "csv": csv_path.name,
        "xlsx": xlsx_path.name,
        **(metadata or {}),
    }
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return frame


def load_observation_frame(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, sheet_name="observations")
    raise ValueError("Observation dataset must be CSV or XLSX.")


def load_observations(path: str | Path) -> list[ResearchObservation]:
    frame = load_observation_frame(path)
    observations: list[ResearchObservation] = []
    for raw in frame.to_dict(orient="records"):
        cleaned = {
            key: ("" if pd.isna(value) else value)
            for key, value in raw.items()
            if key in ResearchObservation.__dataclass_fields__ or key == "primary_source_url"
        }
        observations.append(ResearchObservation.from_export_dict(cleaned))
    return observations
