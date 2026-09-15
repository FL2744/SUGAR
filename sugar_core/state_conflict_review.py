from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .observations import ResearchObservation
from .source_conflicts import load_source_conflicts
from .state_conflict_package import export_review_workbook_with_conflicts
from .state_schema import StateAssessment


def export_review_workbook_with_conflict_file(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    output_file: str | Path,
    *,
    source_conflicts_file: str | Path | None = None,
) -> str:
    conflicts = load_source_conflicts(source_conflicts_file) if source_conflicts_file else []
    return export_review_workbook_with_conflicts(
        observations,
        assessments,
        output_file,
        source_conflicts=conflicts,
    )
