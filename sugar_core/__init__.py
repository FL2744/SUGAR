"""Stable SUGAR core for repeatable OSINT collection and analysis."""
from .models import PostRecord, SCHEMA_VERSION, COLLECTOR_VERSION
from .service import run_search, run_map, run_analysis
__all__ = ["PostRecord", "SCHEMA_VERSION", "COLLECTOR_VERSION", "run_search", "run_map", "run_analysis"]
__version__ = "1.1.0"
