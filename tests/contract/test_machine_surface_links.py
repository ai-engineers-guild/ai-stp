"""Every link the machine surfaces publish names a path something serves.

`llms.txt`, `llms-full.txt` and `agents.md` are the entry points an agent reads
before it knows anything else about this estate. A dead link there is worse than
a dead link in prose: the agent has no page to fall back to and no human to ask,
so it either guesses a URL or gives up on the contract entirely.

The defect this was written for shipped exactly that. `llms.txt` advertised
`/schemas/v1/openapi.json` — hedged as "when deployed with platform schemas",
which read like a condition and was in fact a 404 in every deployment. The
document is served at `/openapi.json`, and the edge says so.

Two trees answer "does something serve this": the Next.js route tree, and the
edge, which sends a handful of prefixes to the API instead of the web. A path
neither one claims is served by nobody.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps/web/src/app"
EDGE_TEMPLATE = REPO / "deploy/nginx/ai-stp.conf.template"

#: The surfaces an agent is told to read first.
MACHINE_SURFACES = ("llms.txt/route.ts", "llms-full.txt/route.ts", "agents.md/route.ts")


def _advertised() -> dict[str, list[str]]:
    """Same-origin paths each surface publishes, by surface."""
    found: dict[str, list[str]] = {}
    for surface in MACHINE_SURFACES:
        source = (APP / surface).read_text(encoding="utf-8")
        found[surface] = sorted(set(re.findall(r'absolute\("([^"]+)"\)', source)))
    return found


def _route_pattern(route: Path) -> re.Pattern[str]:
    """Compile one Next.js route directory into a matcher over URL paths.

    Route groups carry no URL segment, a dynamic segment matches one, and a
    catch-all matches the rest. An optional catch-all also matches nothing,
    which is how `/[locale]/ai/[[...path]]` serves `/en/ai`.
    """
    parts = route.relative_to(APP).parent.parts
    expression = ""
    for part in parts:
        if part.startswith("(") and part.endswith(")"):
            continue  # route group: organisation only, no URL segment
        if part.startswith("[[...") and part.endswith("]]"):
            expression += "(?:/[^/]+)*"
        elif part.startswith("[...") and part.endswith("]"):
            expression += "(?:/[^/]+)+"
        elif part.startswith("[") and part.endswith("]"):
            expression += "/[^/]+"
        else:
            expression += "/" + re.escape(part)
    return re.compile(f"^{expression or '/'}$")


def _next_routes() -> list[re.Pattern[str]]:
    handlers = [*APP.rglob("route.ts"), *APP.rglob("page.tsx")]
    return [_route_pattern(route) for route in handlers]


def _edge_prefixes() -> list[str]:
    """Paths the edge routes away from the web app, from the host nginx template."""
    config = EDGE_TEMPLATE.read_text(encoding="utf-8")
    # `location [= ]/prefix {`; the exact-match form drops its `=` and reads the same.
    found = re.findall(r"^\s*location\s+(?:=\s+)?(/\S*)\s*\{", config, flags=re.MULTILINE)
    # The catch-all is the web app itself, not a path routed away from it.
    return [prefix for prefix in found if prefix != "/"]


def _is_served(path: str, routes: list[re.Pattern[str]], edges: list[str]) -> bool:
    if any(pattern.match(path) for pattern in routes):
        return True
    return any(path == edge or path.startswith(edge.rstrip("/") + "/") for edge in edges)


def test_every_machine_surface_link_names_a_path_something_serves() -> None:
    routes, edges = _next_routes(), _edge_prefixes()
    dead = [
        f"{surface} -> {path}"
        for surface, paths in _advertised().items()
        for path in paths
        if not _is_served(path, routes, edges)
    ]
    assert not dead, (
        f"Advertised but served by nothing: {dead}. Neither the Next.js route tree nor "
        f"the edge answers these, so an agent that follows the link gets a 404. "
        f"Edge prefixes: {edges}."
    )


def test_the_index_surface_still_publishes_links() -> None:
    """The sweep is only worth its runtime while it can still see links.

    `llms.txt` is the index; the other two surfaces carry prose and no links
    today, so they contribute nothing to the sweep and cannot detect a parser
    that has gone blind. They stay enumerated above anyway, so that a link added
    to either one later is checked from the moment it appears.
    """
    advertised = _advertised()
    assert set(advertised) == set(MACHINE_SURFACES)
    assert len(advertised["llms.txt/route.ts"]) >= 5
    assert any(pattern.match("/en/catalog") for pattern in _next_routes())
    assert "/openapi.json" in _edge_prefixes()
    assert any("/schemas/provider-protocol" in prefix for prefix in _edge_prefixes())
