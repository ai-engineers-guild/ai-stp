"""Offline network-intent checks; no DNS or reputation lookups."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ai_stp_platform.safety.adapters.detector_lines import is_detector_line
from ai_stp_platform.safety.adapters.paths import is_test_path
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

URL = re.compile(r"(?i)\b(?:https?|file|javascript|data)://[^\s<>\"']+")
PIPE = re.compile(r"(?i)(?:curl|wget|invoke-webrequest)\b[^\n|;]*(?:\||;)\s*(?:ba)?sh\b")
METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal"}


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    findings: list[Finding] = []
    for rel in manifest.text_files:
        try:
            text = (tree / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            manifest.record_read_error(rel)
            continue
        for line in text.splitlines():
            if is_detector_line(line):
                continue
            if PIPE.search(line):
                findings.append(
                    _finding(
                        spec, "url_pipe_shell", "URL download is piped to shell", rel, "critical"
                    )
                )
            for raw in URL.findall(line):
                findings.extend(_inspect_url(unquote(raw.rstrip(".,);]")), rel, spec))

    blocking = [item for item in findings if not is_test_path(item.path)]
    severity = max((item.severity for item in findings), default="info", key=_rank)
    high = _rank(severity) >= _rank("high")
    if findings and high and blocking:
        result = "failed"
    elif findings:
        result = "warning"
    else:
        result = "passed"
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result=result,
        mandatory=spec.mandatory,
        tool_name="network_intent",
        severity_max=severity,
        findings=findings,
    )


def _inspect_url(value: str, path: str, spec: CheckSpec) -> list[Finding]:
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme in {"file", "javascript"} or (
        scheme == "data" and not value.lower().startswith("data:image/")
    ):
        return [
            _finding(spec, "dangerous_url_scheme", f"Dangerous URL scheme: {scheme}", path, "high")
        ]
    if scheme not in {"http", "https"}:
        return []

    out: list[Finding] = []
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.username is not None or parsed.password is not None:
        out.append(
            _finding(spec, "url_embedded_credentials", "URL embeds credentials", path, "high")
        )
    if host in METADATA_HOSTS:
        out.append(_finding(spec, "metadata_endpoint", "Cloud metadata endpoint", path, "critical"))
    else:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            out.append(
                _finding(
                    spec,
                    "non_public_endpoint",
                    "Loopback, private, or link-local endpoint",
                    path,
                    "high",
                )
            )
    if scheme == "http":
        out.append(_finding(spec, "plain_http", "Unencrypted HTTP endpoint", path, "medium"))
    if host.startswith("xn--") or any(label.startswith("xn--") for label in host.split(".")):
        out.append(
            _finding(spec, "punycode_hostname", "Punycode hostname requires review", path, "medium")
        )
    return out


def _finding(spec: CheckSpec, rule: str, title: str, path: str, severity: str) -> Finding:
    return Finding(
        check_id=spec.check_id,
        family=spec.family,
        rule_id=rule,
        severity=severity,
        title=title,
        path=path,
        message=rule,
        tool_name="network_intent",
    )


def _rank(severity: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(severity, 0)
