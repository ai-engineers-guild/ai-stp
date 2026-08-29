"""Fetch every citation the harness catalogue rests on, and report the dead ones.

A row here says where a product reads, and its `source` says which page decided
that. Nothing in this repository ever fetches one. So a citation that rots is
found by a person opening it, and in no other way — which on 2026-08-28 meant
four had been dead for an unknown length of time, two of them written that same
day from the pattern of their neighbours rather than from a page anybody opened.

Why a slice rather than a gate. `just check` may not depend on a vendor's site
being up: a documentation host having an outage would turn this repository red
for somebody else's reason, and a gate that goes red for that stops being read.
The same argument as `evidence-providers`, and the same shape — run deliberately,
report meant to be pasted.

What a dead link does and does not mean. A 404 says the page moved or went, not
that the row is wrong: the antigravity `agents` page moved to `subagents` and the
route was correct throughout. So this reports and never refuses. The repair is to
find where the page went and cite that, or — if the page is gone because the
behaviour is gone — to measure the product and fix the row.

`403`, `405` and `429` are inconclusive rather than dead. Several vendor hosts
refuse `HEAD` from a script, and reporting those as failures would bury the four
that matter under noise nobody reads.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any, cast

#: A vendor host answering one of these is declining the request, not denying
#: the page. Treated as unproven so the report keeps its signal.
INCONCLUSIVE: frozenset[int] = frozenset({403, 405, 429})

TIMEOUT_SECONDS = 20


def _citations() -> dict[str, list[str]]:
    """Every distinct citation, with the rows that rest on it.

    Imported here rather than at module scope, like the provider slice: this is
    release tooling, and importing the CLI's internals at load time would make
    every other release script depend on them.
    """
    from ai_stp_cli.local import harness_catalog

    found: dict[str, list[str]] = {}
    for definition in harness_catalog.DEFINITIONS:
        if definition.source:
            found.setdefault(definition.source, []).append(f"{definition.harness_id}/<home>")
        for layout in definition.layouts:
            if layout.source:
                found.setdefault(layout.source, []).append(
                    f"{definition.harness_id}/{layout.component_type} -> {layout.relative}"
                )
    return found


def _reach(citation: str) -> tuple[str, str]:
    url = citation if citation.startswith("http") else f"https://{citation}"
    request = urllib.request.Request(
        url,
        method="HEAD",
        # Several hosts answer 403 to an unrecognised agent. This is not evasion
        # — the page is public and a browser reaches it — and a slice that
        # reported those as dead would name pages that are perfectly fine.
        headers={"User-Agent": "Mozilla/5.0 (compatible; ai-stp-citation-slice)"},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context()
        ) as answer:
            return "reachable", str(answer.status)
    except urllib.error.HTTPError as error:
        if error.code in INCONCLUSIVE:
            return "inconclusive", f"HTTP {error.code}"
        return "dead", f"HTTP {error.code}"
    except Exception as error:
        return "inconclusive", type(error).__name__


#: A page that must come back dead, fetched by the same classifier as every
#: real citation. Without it, a run where every fetch failed — a proxy, a
#: resolver, a captive portal — prints `dead: {}` and exits 0, and that green is
#: indistinguishable from a clean estate. An instrument that cannot fail says
#: nothing when it passes.
#:
#: The host is ours, so this proves the classifier rather than a vendor's
#: uptime, and it is a real 404 rather than an unresolvable name: a DNS failure
#: grades `inconclusive`, which is precisely the state this is here to tell
#: apart from a genuine death.
CONTROL_CITATION = "https://nddev.asia/ai-stp-citation-slice-control-404"


def verify_citations() -> dict[str, Any]:
    citations = _citations()
    control, control_detail = _reach(CONTROL_CITATION)
    dead: dict[str, list[str]] = {}
    inconclusive: dict[str, str] = {}
    reachable = 0
    for citation, rows in sorted(citations.items()):
        verdict, detail = _reach(citation)
        if verdict == "reachable":
            reachable += 1
        elif verdict == "dead":
            dead[f"{citation} ({detail})"] = sorted(rows)
        else:
            inconclusive[citation] = detail
    return {
        "schema_version": 1,
        "slice": "catalog-citations",
        # `dead` is the only verdict that proves the classifier can still say
        # "dead". Anything else voids the run rather than reporting a clean one.
        "control": {"verdict": control, "detail": control_detail},
        "checked": len(citations),
        "reachable": reachable,
        "dead": dead,
        "inconclusive": inconclusive,
        "not_verified": {
            "the_page_says_what_the_row_says": (
                "reachability only. A page that still answers can have been "
                "rewritten to describe something else, and no fetch detects that"
            ),
        },
    }


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(arguments)
    report = verify_citations()
    print(json.dumps(report, indent=2, sort_keys=True))
    control = cast(dict[str, str], report["control"])
    if control["verdict"] != "dead":
        # An absent measurement and a measurement of nothing are different
        # states, and only one of them is good news.
        print(
            "citation slice void: the control page did not come back dead "
            f"({control['verdict']}: {control['detail']}), so a clean report "
            "would only mean the classifier stopped classifying",
            file=sys.stderr,
        )
        return 1
    # Red on a dead citation, because that is a fact about this repository
    # rather than about a vendor's uptime — an inconclusive answer is not.
    return 1 if report["dead"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
