"""Shell obfuscation / base64-to-shell side channels."""

from __future__ import annotations

import base64
import binascii
import re
from contextlib import suppress
from pathlib import Path
from urllib.parse import unquote

from ai_stp_platform.safety.adapters.detector_lines import (
    is_detector_line,
    looks_like_detector_source,
)
from ai_stp_platform.safety.adapters.paths import is_test_path
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

PATTERNS = [
    (re.compile(r"(?i)base64\s+-d\s*\|\s*(bash|sh)"), "b64_pipe_shell", "critical"),
    (re.compile(r"(?i)eval\s+\$\("), "eval_subshell", "high"),
    (re.compile(r"(?i)\$'\\x[0-9a-f]{2}"), "hex_escape_obfuscation", "medium"),
    (re.compile(r"(?i)\$\{[a-z_]+:0:1\}"), "char_concat_obfuscation", "medium"),
]
ENCODED = re.compile(r"(?i)(?:curl|wget|bash|sh\s+-c|/dev/tcp|invoke-expression|\biex\b)")
BASE64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
HEX = re.compile(r"(?i)(?:[0-9a-f]{2}){12,}")
MAX_CANDIDATES = 32
MAX_DECODED_BYTES = 64 * 1024
MAX_LAYERS = 2


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    findings: list[Finding] = []
    for rel in manifest.text_files or manifest.shell_files:
        path = tree / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            manifest.record_read_error(rel)
            continue
        seen: set[str] = set()
        for line in text.splitlines():
            if is_detector_line(line):
                continue
            for pattern, rule, sev in PATTERNS:
                if rule in seen:
                    continue
                if pattern.search(line):
                    seen.add(rule)
                    findings.append(
                        Finding(
                            check_id=spec.check_id,
                            family=spec.family,
                            rule_id=rule,
                            severity=sev,
                            title=f"Shell obfuscation: {rule}",
                            path=rel,
                            message=redact_message(rule),
                            tool_name="shell_obfuscation",
                        )
                    )
        if "b64_decoded_shell" not in seen:
            for decoded in _decoded_candidates(text):
                if looks_like_detector_source(decoded):
                    continue
                if ENCODED.search(decoded):
                    seen.add("b64_decoded_shell")
                    findings.append(
                        Finding(
                            check_id=spec.check_id,
                            family=spec.family,
                            rule_id="b64_decoded_shell",
                            severity="critical",
                            title="Encoded payload decodes to shell/network command",
                            path=rel,
                            message=redact_message(decoded[:120]),
                            tool_name="shell_obfuscation",
                        )
                    )
                    break
    blocking = [item for item in findings if not is_test_path(item.path)]
    high = any(_rank(item.severity) >= _rank("high") for item in blocking)
    if findings and high:
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
        tool_name="shell_obfuscation",
        severity_max=max((f.severity for f in findings), default="info", key=_rank),
        findings=findings,
    )


def _decoded_candidates(text: str) -> list[str]:
    """Decode a bounded set of likely payloads, including at most two layers."""
    pending = [text[:MAX_DECODED_BYTES]]
    seen = set(pending)
    decoded: list[str] = []
    for _ in range(MAX_LAYERS):
        next_layer: list[str] = []
        for value in pending:
            candidates = [unquote(value)]
            if "\\x" in value or "\\u" in value:
                with suppress(UnicodeError):
                    candidates.append(value.encode("utf-8").decode("unicode_escape"))
            candidates.extend(_decode_blob(blob) for blob in BASE64.findall(value))
            candidates.extend(_decode_hex(blob) for blob in HEX.findall(value))
            for candidate in candidates:
                candidate = candidate[:MAX_DECODED_BYTES]
                if not candidate or candidate == value or candidate in seen:
                    continue
                seen.add(candidate)
                decoded.append(candidate)
                next_layer.append(candidate)
                if len(decoded) >= MAX_CANDIDATES:
                    return decoded
        pending = next_layer
    return decoded


def _decode_blob(blob: str) -> str:
    try:
        raw = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True)
    except (ValueError, binascii.Error):
        return ""
    encodings = ("utf-16-le", "utf-8") if b"\x00" in raw else ("utf-8", "utf-16-le")
    for encoding in encodings:
        try:
            return raw[:MAX_DECODED_BYTES].decode(encoding)
        except UnicodeError:
            pass
    return ""


def _decode_hex(blob: str) -> str:
    try:
        return bytes.fromhex(blob[: MAX_DECODED_BYTES * 2]).decode("utf-8")
    except (ValueError, UnicodeError):
        return ""


def _rank(severity: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(severity, 0)
