"""Stable SUGAR core for repeatable OSINT collection and analysis."""

from .models import COLLECTOR_VERSION, SCHEMA_VERSION, PostRecord
from .observation_storage import load_observations, observations_to_frame, save_observations
from .observations import (
    OBSERVATION_SCHEMA_VERSION,
    EvidenceReference,
    ResearchObservation,
    observation_from_post,
    observations_from_posts,
)
from .service import run_analysis, run_map, run_search
from .triage import (
    DEFAULT_PROJECT_CONTEXT,
    GroundedEvidence,
    TriageResult,
    observation_from_triage,
    parse_triage_result,
    triage_post,
    triage_posts,
)
from .triage_io import load_post_records, post_record_from_mapping, triage_dataset

__all__ = [
    "PostRecord",
    "SCHEMA_VERSION",
    "COLLECTOR_VERSION",
    "ResearchObservation",
    "EvidenceReference",
    "OBSERVATION_SCHEMA_VERSION",
    "observation_from_post",
    "observations_from_posts",
    "observations_to_frame",
    "save_observations",
    "load_observations",
    "GroundedEvidence",
    "TriageResult",
    "DEFAULT_PROJECT_CONTEXT",
    "parse_triage_result",
    "triage_post",
    "triage_posts",
    "observation_from_triage",
    "post_record_from_mapping",
    "load_post_records",
    "triage_dataset",
    "run_search",
    "run_map",
    "run_analysis",
]

__version__ = "1.1.0"
