"""Shared deterministic context estimator (SPEC-043, SPEC-049)."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from ai_stp_contracts.component_artifacts import (
    COMPONENT_TREE_FORMAT,
    IMPORTED_COMPONENT_FORMAT,
    MAX_COMPONENT_FILES,
    MAX_COMPONENT_TREE_BYTES,
    expand_component_artifact,
)
from ai_stp_contracts.impact import (
    ComponentTokenMeasurement,
    ContextBudget,
    ExactCoordinate,
    TokenEstimator,
)
from ai_stp_foundation.canonical import from_json_bytes

TOKENIZED_TYPES = frozenset({"instruction", "skill", "agent", "command"})
type TokenizedType = Literal["instruction", "skill", "agent", "command"]
type Loading = Literal["always", "conditional"]

ESTIMATORS: dict[str, TokenEstimator] = {
    "ai-stp:utf8-bytes/1": TokenEstimator(
        profile="ai-stp:utf8-bytes/1", accuracy="exact", method="utf8_byte_count"
    ),
    "ai-stp:unicode-chars-div4/1": TokenEstimator(
        profile="ai-stp:unicode-chars-div4/1",
        accuracy="estimated",
        method="unicode_codepoints_div_4",
    ),
}


@dataclass(frozen=True)
class EstimatorInput:
    """One tokenized component after the caller has proven its exact graph."""

    coordinate: ExactCoordinate
    component_type: str
    files: tuple[bytes, ...]
    missing: bool = False
    missing_reason: str = "artifact_unavailable"


def estimator_for(profile: str) -> TokenEstimator | None:
    """Return a known estimator profile, or None when unsupported."""
    return ESTIMATORS.get(profile)


def extract_file_payloads(payload: bytes, content_format: str | None = None) -> tuple[bytes, ...]:
    """Decode canonical component envelopes; retain bounded legacy file/ZIP reads."""
    if content_format:
        return tuple(item.content for item in expand_component_artifact(payload, content_format))
    if len(payload) > MAX_COMPONENT_TREE_BYTES:
        raise ValueError("component artifact exceeds the context byte limit")
    buffer = io.BytesIO(payload)
    if zipfile.is_zipfile(buffer):
        with zipfile.ZipFile(buffer, "r") as archive:
            if "component.json" in archive.namelist():
                return extract_file_payloads(payload, COMPONENT_TREE_FORMAT)
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if (
                len(infos) > MAX_COMPONENT_FILES
                or len(names) != len(set(names))
                or sum(item.file_size for item in infos) > MAX_COMPONENT_TREE_BYTES
            ):
                raise ValueError("component ZIP exceeds the accepted bounds")
            return tuple(archive.read(item) for item in infos if not item.is_dir())
    if payload.lstrip().startswith(b"{"):
        try:
            document = from_json_bytes(payload)
        except ValueError:
            document = None
        if isinstance(document, dict) and document.get("format") == IMPORTED_COMPONENT_FORMAT:
            return extract_file_payloads(payload, IMPORTED_COMPONENT_FORMAT)
    return (payload,)


def loading_for(component_type: TokenizedType) -> Loading:
    """instruction is always-loaded; skill/agent/command are conditional."""
    return "always" if component_type == "instruction" else "conditional"


def estimate_context(inputs: Sequence[EstimatorInput], estimator: TokenEstimator) -> ContextBudget:
    """Measure tokenized components. Missing/unreadable bytes stay unavailable."""
    measured: list[ComponentTokenMeasurement] = []
    for item in inputs:
        if item.component_type not in TOKENIZED_TYPES:
            continue
        component_type = cast(TokenizedType, item.component_type)
        loading = loading_for(component_type)
        if item.missing:
            measured.append(
                ComponentTokenMeasurement(
                    component=item.coordinate,
                    component_type=component_type,
                    loading=loading,
                    status="unavailable",
                    tokens=None,
                    utf8_bytes=0,
                    reason=item.missing_reason,
                )
            )
            continue
        total_bytes = sum(len(content) for content in item.files)
        try:
            text = "".join(content.decode("utf-8") for content in item.files)
        except UnicodeDecodeError:
            measured.append(
                ComponentTokenMeasurement(
                    component=item.coordinate,
                    component_type=component_type,
                    loading=loading,
                    status="unavailable",
                    tokens=None,
                    utf8_bytes=total_bytes,
                    reason="content_is_not_utf8",
                )
            )
            continue
        tokens = total_bytes if estimator.method == "utf8_byte_count" else (len(text) + 3) // 4
        measured.append(
            ComponentTokenMeasurement(
                component=item.coordinate,
                component_type=component_type,
                loading=loading,
                status=estimator.accuracy,
                tokens=tokens,
                utf8_bytes=total_bytes,
            )
        )
    return ContextBudget(
        always_tokens=sum(
            item.tokens for item in measured if item.loading == "always" and item.tokens is not None
        ),
        conditional_tokens=sum(
            item.tokens
            for item in measured
            if item.loading == "conditional" and item.tokens is not None
        ),
        unavailable_components=sum(item.status == "unavailable" for item in measured),
        components=measured,
    )
