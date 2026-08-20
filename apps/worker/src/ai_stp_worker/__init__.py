"""Background worker for the ai_stp platform custom job queue.

Normative sources: SPEC-018 (worker and job queue), ADR-0038 (custom queue).
"""

from ai_stp_worker.runner import Worker

__all__ = ["Worker"]
