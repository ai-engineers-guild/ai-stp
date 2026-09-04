"""Relative artifact paths and test-tree membership for CLI adapters."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

_TEST_DIR_NAMES = frozenset({"test", "tests"})


def relative_artifact_path(tree: Path, value: object) -> str | None:
    """Return a tree-relative POSIX path, or None when ``value`` is not under tree.

    Gitleaks and ShellCheck often emit absolute worker paths. The public
    projection drops those; relativize before storing the finding.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.replace("\\", "/").strip()
    tree_resolved = tree.resolve()
    candidate = Path(raw)
    try:
        resolved = (
            candidate.resolve() if candidate.is_absolute() else (tree_resolved / raw).resolve()
        )
        return resolved.relative_to(tree_resolved).as_posix()
    except (OSError, ValueError):
        if candidate.is_absolute() or ".." in PurePosixPath(raw).parts:
            return None
        return raw.lstrip("./")


def is_test_path(path: str | None) -> bool:
    """True when a relative path has a ``tests`` or ``test`` directory part."""
    if not path:
        return False
    return any(part in _TEST_DIR_NAMES for part in PurePosixPath(path.replace("\\", "/")).parts)
