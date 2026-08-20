from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from opentelemetry import trace

from ai_stp_api.observability import configure_observability, current_trace_id


def test_configure_observability_accepts_an_otlp_exporter_endpoint() -> None:
    app = FastAPI()

    configure_observability(
        app,
        service_name="ai-stp-test",
        exporter_endpoint="http://127.0.0.1:4318/v1/traces",
        exporter_headers={"x-test": "value"},
    )


def test_current_trace_id_returns_none_for_invalid_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = SimpleNamespace(get_span_context=lambda: SimpleNamespace(is_valid=False))
    monkeypatch.setattr(trace, "get_current_span", lambda: span)

    assert current_trace_id() is None


def test_current_trace_id_formats_valid_context(monkeypatch: pytest.MonkeyPatch) -> None:
    span = SimpleNamespace(get_span_context=lambda: SimpleNamespace(is_valid=True, trace_id=0xABC))
    monkeypatch.setattr(trace, "get_current_span", lambda: span)

    assert current_trace_id() == "00000000000000000000000000000abc"


def test_current_trace_id_swallows_tracing_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise RuntimeError("tracer unavailable")

    monkeypatch.setattr(trace, "get_current_span", fail)

    assert current_trace_id() is None
