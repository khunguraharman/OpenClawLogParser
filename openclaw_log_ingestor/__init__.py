"""OpenClaw log ingestion service."""

from .config import IngestorConfig
from .service import IngestorService

__all__ = ["IngestorConfig", "IngestorService"]
