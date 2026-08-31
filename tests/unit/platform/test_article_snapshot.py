"""Deterministic repository article snapshot (SPEC-054 REQ-5403)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.unit.platform.article_fixtures import COMMIT

from ai_stp_foundation.canonical import canonize
from ai_stp_platform.content.errors import ContentError
from ai_stp_platform.content.snapshot import build_repository_snapshot, parse_frontmatter
from ai_stp_platform.content.snapshot_cli import main as snapshot_cli_main

pytestmark = pytest.mark.platform

NOW = datetime(2026, 8, 29, tzinfo=UTC)
HUB = Path("docs-user-facing/content")


def _write_entry(root: Path, name: str, body: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_snapshot_is_byte_identical_across_file_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    en = """---
type: article
slug: alpha
locale: en
title: Alpha EN
description: Alpha description EN
published_at: 2026-08-12
tags: [one]
draft: false
---

Body EN.
"""
    ru = """---
type: article
slug: alpha
locale: ru
title: Alpha RU
description: Alpha description RU
published_at: 2026-08-12
tags: [one]
draft: false
---

Body RU.
"""
    _write_entry(first, "en/article-alpha.md", en)
    _write_entry(first, "ru/article-alpha.md", ru)
    _write_entry(second, "ru/article-alpha.md", ru)
    _write_entry(second, "en/article-alpha.md", en)
    left = build_repository_snapshot(first, commit=COMMIT, now=NOW)
    right = build_repository_snapshot(second, commit=COMMIT, now=NOW)
    assert left.snapshot_digest == right.snapshot_digest
    assert canonize(left.model_dump(mode="json")) == canonize(right.model_dump(mode="json"))
    assert {entry.source_path for entry in left.entries} == {
        "docs-user-facing/content/en/article-alpha.md",
        "docs-user-facing/content/ru/article-alpha.md",
    }


def test_snapshot_skips_drafts_and_requires_locale_parity(tmp_path: Path) -> None:
    _write_entry(
        tmp_path,
        "en/article-alpha.md",
        """---
type: article
slug: alpha
locale: en
title: Alpha EN
description: Alpha description EN
published_at: 2026-08-12
tags:
  - one
draft: false
---

Body EN.
""",
    )
    _write_entry(
        tmp_path,
        "en/article-draft.md",
        """---
type: article
slug: draft-item
locale: en
title: Draft
description: Draft description
published_at: 2026-08-12
tags:
  - internal
draft: true
---

Hidden.
""",
    )
    with pytest.raises(ContentError) as error:
        build_repository_snapshot(tmp_path, commit=COMMIT, now=NOW)
    assert error.value.code == "AI_STP_CONTENT_INVALID"
    assert "locale parity" in error.value.message


def test_real_hub_builds_without_drafts() -> None:
    snapshot = build_repository_snapshot(HUB, commit=COMMIT, now=NOW)
    identities = {(entry.type, entry.slug) for entry in snapshot.entries}
    assert ("article", "safe-setup") in identities
    assert ("article", "internal-draft") not in identities
    assert snapshot.commit == COMMIT
    assert snapshot.entries


def test_snapshot_rejects_empty_hub(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("not markdown", encoding="utf-8")
    with pytest.raises(ContentError) as error:
        build_repository_snapshot(tmp_path, commit=COMMIT, now=NOW)
    assert error.value.code == "AI_STP_CONTENT_INVALID"
    assert "no markdown files" in error.value.message


def test_snapshot_rejects_missing_hub(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    with pytest.raises(ContentError) as error:
        build_repository_snapshot(missing, commit=COMMIT, now=NOW)
    assert error.value.code == "AI_STP_CONTENT_INVALID"
    assert "missing" in error.value.message


def test_snapshot_rejects_zero_commit_placeholder(tmp_path: Path) -> None:
    with pytest.raises(ContentError) as error:
        build_repository_snapshot(tmp_path, commit="0" * 40, now=NOW)
    assert error.value.code == "AI_STP_CONTENT_INVALID"
    assert "placeholder" in error.value.message


def test_snapshot_cli_reports_empty_hub(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "snapshot.json"
    argv = ["--hub", str(tmp_path), "--commit", COMMIT, "--out", str(out)]
    assert snapshot_cli_main(argv) == 1
    captured = capsys.readouterr()
    assert "AI_STP_CONTENT_INVALID" in captured.err
    assert "no markdown files" in captured.err
    assert not out.exists()


def test_frontmatter_rejects_unknown_fields() -> None:
    with pytest.raises(ContentError) as error:
        parse_frontmatter(
            """---
type: article
slug: alpha
locale: en
title: Alpha
description: Desc
published_at: 2026-08-12
tags: []
draft: false
author: hidden
---

Body.
"""
        )
    assert error.value.code == "AI_STP_CONTENT_INVALID"
