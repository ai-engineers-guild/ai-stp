"""The slice's filter, which is the part a well-meant narrowing can empty.

`just evidence-citations` fetches, and a fetch is easy to believe. What decides
whether it finds anything is what it collects and how it grades an answer, and
both are places where a reasonable-looking narrowing quietly makes the check
pass on everything.

Two failures this is aimed at, one of them observed on the provider side:

- **reading prose.** A first pass there swept every `https://` in the baselines
  and reported two 404s, neither a citation: one a URL template with a
  placeholder that cannot resolve by construction, the other a dead URL quoted
  *inside the note recording that it had rotted*. A checker that reads prose
  reports the fix as the defect.
- **grading a refusal as a death.** Several vendor hosts refuse a scripted
  `HEAD`. Counting those as dead would have buried this repository's four real
  findings under a pile nobody reads.

Network is deliberately absent here. The fetch is the easy half and cannot run
in a gate; the filter is the half that decides whether the fetch is pointed at
anything, and it is pure.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from release_scripts import verify_citation_slice as slice_

pytestmark = pytest.mark.cli


def _answering(verdict: tuple[str, str]) -> Callable[[str], tuple[str, str]]:
    """One canned answer for every citation, typed so the checker can read it."""

    def reach(_citation: str) -> tuple[str, str]:
        return verdict

    return reach


def test_citations_come_from_the_declared_fields_rather_than_from_text() -> None:
    """Read off the catalogue's own structures, so prose is unreachable.

    Not a filter over scanned text — there is no text step to narrow wrongly.
    Every value here is a `source` a row declares, which is why the prose
    failure cannot occur rather than being defended against.
    """
    from ai_stp_cli.local import harness_catalog

    declared = {item.source for item in harness_catalog.DEFINITIONS if item.source} | {
        layout.source
        for item in harness_catalog.DEFINITIONS
        for layout in item.layouts
        if layout.source
    }
    assert set(slice_._citations()) == declared  # pyright: ignore[reportPrivateUsage]
    assert declared, "the slice would pass by having nothing to check"


def test_every_citation_names_the_rows_that_rest_on_it() -> None:
    """A dead link is actionable only if the report says what it decided."""
    citations = slice_._citations()  # pyright: ignore[reportPrivateUsage]
    assert all(rows for rows in citations.values())
    borne = sum(len(rows) for rows in citations.values())
    from ai_stp_cli.local import harness_catalog

    rows = sum(
        1 for item in harness_catalog.DEFINITIONS for layout in item.layouts if layout.source
    )
    homes = sum(1 for item in harness_catalog.DEFINITIONS if item.source)
    assert borne == rows + homes


def test_a_refusal_to_answer_a_script_is_not_a_dead_page() -> None:
    """The grading, injured directly rather than through a live host."""
    assert 403 in slice_.INCONCLUSIVE
    assert 405 in slice_.INCONCLUSIVE
    assert 429 in slice_.INCONCLUSIVE
    assert 404 not in slice_.INCONCLUSIVE
    assert 410 not in slice_.INCONCLUSIVE


def test_a_dead_citation_makes_the_slice_exit_non_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proved to detect, rather than trusted because it once did.

    It found four dead citations the day it was written, which demonstrates the
    path — but that was the finding, not a controlled check, and a clean run
    tomorrow on a slice nobody has proved still detects is the same false green
    this repository keeps finding elsewhere.
    """
    monkeypatch.setattr(slice_, "_reach", _answering(("dead", "HTTP 404")))
    assert slice_.main([]) == 1
    report = capsys.readouterr().out
    assert '"dead"' in report

    monkeypatch.setattr(slice_, "_reach", _answering(("reachable", "200")))
    assert slice_.main([]) == 0


def test_an_inconclusive_answer_does_not_fail_the_slice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A vendor's outage is not this repository's defect."""
    monkeypatch.setattr(slice_, "_reach", _answering(("inconclusive", "HTTP 403")))
    assert slice_.main([]) == 0
    assert '"inconclusive"' in capsys.readouterr().out
