"""Line-scoped skip for in-proc scanners: a detector is not a declaration.

A security skill that *compiles* ``curl | sh`` or ``ignore previous
instructions`` as a regex must be able to ship that detector. The same phrase
as an instruction in ``SKILL.md`` still flags. Whole files named ``*_guard.py``
are not skipped.
"""

from __future__ import annotations

import re

_DEFENSIVE = re.compile(
    r"(?i)\b(?:do not|don't|never|avoid|must not|detect|block|"
    r"forbid(?:den)?|unpinned|example of an attack)\b"
)
_SEMGREP_PATTERN = re.compile(
    r"(?i)^\s*-?\s*pattern(?:-either|-regex|-not|-inside|-not-regex)?\s*:"
)
_RE_CALL = re.compile(
    r"(?i)\bre(?:\.compile|\.search|\.match|\.fullmatch|\.findall|\.finditer)\s*\("
)
_RAW_STRING = re.compile(r"(?:r|rf|fr)(?:'''|\"\"\"|'|\")")
_PATTERN_LIST = re.compile(
    r"(?i)\b(?:[A-Z][A-Z0-9_]*(?:PATTERNS?|_RE)|SECRET_PATTERNS|"
    r"PROMPT_INJECTION_PATTERNS|PI_PATTERNS|ENCODED)\b"
)


def is_detector_line(line: str) -> bool:
    """True when ``line`` is pattern/regex/defensive wording, not an instruction."""
    if _DEFENSIVE.search(line):
        return True
    if _SEMGREP_PATTERN.search(line):
        return True
    if _RE_CALL.search(line):
        return True
    if _RAW_STRING.search(line) and (
        "(?i)" in line or r"\b" in line or ".*" in line or "(?:" in line
    ):
        return True
    return bool(_PATTERN_LIST.search(line))


def looks_like_detector_source(text: str) -> bool:
    """True when decoded text is still source/regex rather than a payload."""
    if "re.compile" in text or "re.search" in text or "re.findall" in text:
        return True
    if _SEMGREP_PATTERN.search(text):
        return True
    lines = [line for line in text.splitlines() if line.strip()]
    return bool(lines) and all(is_detector_line(line) for line in lines)
