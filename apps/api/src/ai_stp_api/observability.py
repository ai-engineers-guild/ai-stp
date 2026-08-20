"""OpenTelemetry provider as a shared cross-cutting concern (ADR-0039).

The exporter is config-driven. A missing or unreachable backend must not crash
the app: initialisation failures are swallowed to a warning.
"""

from __future__ import annotations

from fastapi import FastAPI

from ai_stp_platform.logging import get_logger

_log = get_logger("observability")


def configure_observability(
    app: FastAPI,
    *,
    service_name: str,
    exporter_endpoint: str | None,
    exporter_headers: dict[str, str] | None = None,
) -> None:
    """Initialise tracing and instrument the app; never raise on failure."""
    try:
        from opentelemetry import trace

        # opentelemetry-instrumentation-fastapi ships no type stubs.
        from opentelemetry.instrumentation.fastapi import (  # type: ignore[import-untyped]
            FastAPIInstrumentor,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        if exporter_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(endpoint=exporter_endpoint, headers=exporter_headers)
                )
            )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:
        # Observability must never break startup (SPEC-017 REQ-1710).
        _log.warning("observability_init_failed", error=str(exc))


def current_trace_id() -> str | None:
    """Return the active trace id as a hex string, or None if no span is active."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        context = span.get_span_context()
        if not context.is_valid:
            return None
        return format(context.trace_id, "032x")
    except Exception:
        # Tracing is best-effort; absence of a trace id is not an error.
        return None
