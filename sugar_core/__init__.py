"""Stable SUGAR core for repeatable OSINT collection and analysis."""

from .collector_registry import (
    COLLECTORS,
    CollectorCapabilities,
    CollectorRequest,
    CollectorSpec,
    collect_registered_comments,
    collect_registered_source,
    collector_capabilities,
    fetch_registered_item,
    get_collector,
)
from .harvest import (
    HarvestConfig,
    HarvestStore,
    HarvestTask,
    build_harvest_tasks,
    rate_limit_wait_seconds,
    run_harvest,
)
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
    "CollectorCapabilities",
    "CollectorRequest",
    "CollectorSpec",
    "COLLECTORS",
    "get_collector",
    "collector_capabilities",
    "collect_registered_source",
    "fetch_registered_item",
    "collect_registered_comments",
    "HarvestConfig",
    "HarvestStore",
    "HarvestTask",
    "build_harvest_tasks",
    "rate_limit_wait_seconds",
    "run_harvest",
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
