"""FastAPI /v1 application shell for the ai_stp platform.

Normative sources: SPEC-017 (runtime shell and observability), ADR-0037
(feature-slice architecture), ADR-0039 (observability).
"""

from ai_stp_api.app import create_app

__all__ = ["create_app"]
