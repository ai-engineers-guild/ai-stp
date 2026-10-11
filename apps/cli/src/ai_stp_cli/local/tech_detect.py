"""Local technology detection over one project index (issue #222).

The implementation lives in ``ai_stp_sources.tech_detect`` so the server-side
worker and the CLI run the same detector. This module keeps the historical
import path.
"""

from ai_stp_sources.tech_detect import (
    BUNDLED_MAPPING_VERSION,
    DETECTOR_VERSION,
    MAX_LINE_CHARS,
    MAX_TRACE_PATHS,
    DetectedScan,
    Detection,
    DetectionKind,
    EvidenceSource,
    MappingSnapshot,
    Trace,
    UsageContext,
    VersionKind,
    bundled_mapping,
    detect,
)

__all__ = [
    "BUNDLED_MAPPING_VERSION",
    "DETECTOR_VERSION",
    "MAX_LINE_CHARS",
    "MAX_TRACE_PATHS",
    "DetectedScan",
    "Detection",
    "DetectionKind",
    "EvidenceSource",
    "MappingSnapshot",
    "Trace",
    "UsageContext",
    "VersionKind",
    "bundled_mapping",
    "detect",
]
