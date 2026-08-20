"""Shared context estimator is deterministic for CLI and server (SPEC-049)."""

from ai_stp_contracts.context_estimator import (
    EstimatorInput,
    estimate_context,
    estimator_for,
    extract_file_payloads,
)
from ai_stp_contracts.impact import ExactCoordinate

COORD = ExactCoordinate(stable_id="component_a", version="1.0", passport_digest="sha256:abc")


def _input(component_type: str, *files: bytes, missing: bool = False) -> EstimatorInput:
    return EstimatorInput(
        coordinate=COORD,
        component_type=component_type,
        files=files,
        missing=missing,
    )


def test_utf8_bytes_are_exact_and_unicode_div4_is_estimated() -> None:
    exact = estimator_for("ai-stp:utf8-bytes/1")
    estimated = estimator_for("ai-stp:unicode-chars-div4/1")
    assert exact is not None and estimated is not None
    payload = "café".encode()
    byte_budget = estimate_context([_input("instruction", payload)], exact)
    char_budget = estimate_context([_input("instruction", payload)], estimated)
    assert byte_budget.always_tokens == len(payload)
    assert byte_budget.components[0].status == "exact"
    assert char_budget.always_tokens == (len("café") + 3) // 4
    assert char_budget.components[0].status == "estimated"


def test_instruction_is_always_loaded_and_skill_is_conditional() -> None:
    estimator = estimator_for("ai-stp:utf8-bytes/1")
    assert estimator is not None
    budget = estimate_context(
        [_input("instruction", b"abcd"), _input("skill", b"ef")],
        estimator,
    )
    assert budget.always_tokens == 4
    assert budget.conditional_tokens == 2
    assert budget.unavailable_components == 0


def test_missing_and_non_utf8_are_unavailable_not_zero() -> None:
    estimator = estimator_for("ai-stp:utf8-bytes/1")
    assert estimator is not None
    budget = estimate_context(
        [
            _input("instruction", missing=True),
            _input("skill", b"\xff"),
            _input("command", b"ok"),
        ],
        estimator,
    )
    assert budget.always_tokens == 0
    assert budget.conditional_tokens == 2
    assert budget.unavailable_components == 2
    assert budget.components[0].tokens is None
    assert budget.components[1].reason == "content_is_not_utf8"


def test_extract_file_payloads_skips_zip_directories() -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("dir/", b"")
        archive.writestr("readme.md", b"hi")
    files = extract_file_payloads(buffer.getvalue())
    assert files == (b"hi",)
    assert extract_file_payloads(b"plain") == (b"plain",)
