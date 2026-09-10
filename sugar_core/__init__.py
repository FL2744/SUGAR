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
    "run_search",
    "run_map",
    "run_analysis",
]

__version__ = "1.1.0"
