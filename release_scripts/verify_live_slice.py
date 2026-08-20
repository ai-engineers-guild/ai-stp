"""Prove the anonymous walking slice against a deployed environment.

`#85` describes ten scenarios in prose. Prose is not evidence: the release rules
require exact commands and their results on an exact SHA, and a proof produced
by hand is one nobody can repeat. This script is the repeatable half.

It covers the scenarios that need no human: the deployed identity, the machine
surface, the anonymous catalogue, the parity between what the CLI renders and
what the web reads from the same API, and the offline replay that must serve a
cached exact object without claiming cloud freshness.

It deliberately does not pretend to cover the rest. The login paths through
Google and GitHub, device registration and revocation need either a person or a
deterministic provider test environment, and a skipped line gets `not_verified`
rather than success (`docs/engineering/release-evidence.md`). Those scenarios
are named in the report with the reason, so the gap is visible in the artefact
instead of remembered.

Nothing here authenticates. That is a property worth keeping: the anonymous
slice must be provable without ever holding a credential, and a script that
cannot hold one cannot leak one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from release_scripts._evidence import EvidenceError, cli, data, without_credentials
from release_scripts._evidence import origin as bare_origin

# The kinds the anonymous catalogue serves, paired with the API collection the
# web reads. The parity check is the point of the pairing: one of them rendering
# an object the other does not is the failure this exists to catch.
COLLECTIONS: dict[str, str] = {"component": "components", "setup": "setups"}

# The machine projection of an object, which is the surface an agent reads. It
# is checked separately from the API because it is a different rendering of the
# same fact, and `#162` asks for the two to agree — not for one of them to
# exist. `#371` is exactly the failure this catches: version `1.2` displayed
# beside the digest of `1.0`.
MACHINE_PROJECTION = "/en/ai/catalog/{collection}/{stable_id}"

REQUEST_TIMEOUT = 20.0


def _get(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as answer:
            payload = json.loads(answer.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise EvidenceError(f"{url} did not answer as JSON: {error}") from error
    if not isinstance(payload, dict):
        raise EvidenceError(f"{url} answered a document that is not an object")
    return cast(dict[str, Any], payload)


def _identifiers(rows: Sequence[Any], command: str) -> dict[str, str]:
    """Map every listed object to the exact version it advertises."""
    found: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise EvidenceError(f"{command} listed an entry that is not an object")
        stable_id = row.get("stable_id")
        version = row.get("latest_version")
        if not isinstance(stable_id, str) or not isinstance(version, str):
            raise EvidenceError(f"{command} listed an entry without an exact identity")
        found[stable_id] = version
    return found


def _catalogue(origin: str, collection: str) -> dict[str, str]:
    url = f"{origin}/v1/catalog/{collection}?include_experimental=true"
    payload = _get(url)
    rows: list[Any] = []
    for field in ("items", "experimental"):
        held = payload.get(field)
        if held is None:
            continue
        if not isinstance(held, list):
            raise EvidenceError(f"{url} answered {field} that is not a list")
        rows.extend(cast(list[Any], held))
    return _identifiers(rows, url)


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as answer:
            return answer.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as error:
        raise EvidenceError(f"{url} did not answer: {error}") from error


def _projected_digest(origin: str, collection: str, stable_id: str, version: str) -> str:
    """The digest the machine projection shows beside the exact version.

    Read out of the rendered page rather than out of an API, because the point
    is what the agent-facing surface actually says. A page that names the
    version and shows a digest belonging to another release is worse than one
    that shows neither: it is precise and wrong.
    """
    url = origin + MACHINE_PROJECTION.format(collection=collection, stable_id=stable_id)
    return _single_digest(_fetch_text(url), version, url)


def _single_digest(page: str, version: str, url: str) -> str:
    """The one digest a page showing one exact version is allowed to carry.

    More than one is refused rather than resolved. A page naming a single
    version and carrying two digests has already lost the property being
    checked, and picking one of them here would decide by accident which
    release the evidence describes.
    """
    if version not in page:
        raise EvidenceError(f"{url} does not name the exact version {version}")
    digests = set(re.findall(r"sha256:[0-9a-f]{64}", page))
    if not digests:
        raise EvidenceError(f"{url} shows no digest for {version}")
    if len(digests) > 1:
        raise EvidenceError(f"{url} shows {len(digests)} different digests for one version")
    return digests.pop()


def _exact_digest(kind: str, stable_id: str, version: str, *, home: Path, python: str) -> str:
    """The digest the CLI reports for that same exact version."""
    command = f"registry show --kind {kind} --id {stable_id}"
    envelope = cli(
        ("registry", "show", "--kind", kind, "--id", stable_id),
        home=home,
        python=python,
    )
    rows = data(envelope, command).get("versions")
    if not isinstance(rows, list):
        raise EvidenceError(f"{command} answered no version list")
    for raw in cast(list[Any], rows):
        if isinstance(raw, dict) and raw.get("version") == version:
            digest = raw.get("passport_digest")
            if not isinstance(digest, str) or not digest:
                raise EvidenceError(f"{command} reports {version} without a passport digest")
            return digest
    raise EvidenceError(f"{command} does not list the exact version {version}")


def _search(kind: str, *, home: Path, python: str) -> tuple[dict[str, str], str]:
    command = f"registry search --kind {kind}"
    envelope = cli(
        ("registry", "search", "--kind", kind, "--include-experimental"),
        home=home,
        python=python,
    )
    payload = data(envelope, command)
    source = payload.get("source")
    if source != "online":
        raise EvidenceError(
            f"{command} answered from {source!r}; the deployed catalogue was not read"
        )
    rows: list[Any] = []
    for field in ("items", "experimental"):
        held = payload.get(field)
        if not isinstance(held, list):
            raise EvidenceError(f"{command} answered {field} that is not a list")
        rows.extend(cast(list[Any], held))
    return _identifiers(rows, command), cast(str, payload.get("checked_at", ""))


def _show(kind: str, stable_id: str, *, home: Path, python: str, offline: bool) -> str:
    command = f"registry show --kind {kind} --id {stable_id}"
    envelope = cli(
        ("registry", "show", "--kind", kind, "--id", stable_id),
        home=home,
        python=python,
        offline=offline,
    )
    payload = data(envelope, command)
    summary = payload.get("summary")
    if not isinstance(summary, dict) or summary.get("stable_id") != stable_id:
        raise EvidenceError(f"{command} answered a different object")
    source = payload.get("source")
    if not isinstance(source, str):
        raise EvidenceError(f"{command} answered without naming its source")
    return source


def verify_live_slice(
    origin: str,
    *,
    python: str = sys.executable,
    expected_commit: str | None = None,
    expected_environment: str = "prod",
) -> dict[str, Any]:
    """Execute the anonymous slice and return the evidence it produced."""
    origin = bare_origin(origin)

    identity = _get(f"{origin}/v1/system/version")
    deployed_commit = identity.get("git_commit")
    deployed_environment = identity.get("environment")
    if not isinstance(deployed_commit, str) or not deployed_commit:
        raise EvidenceError("the deployed environment does not report a commit")
    if expected_commit is not None and deployed_commit != expected_commit:
        raise EvidenceError(f"deployed commit is {deployed_commit}, expected {expected_commit}")
    if deployed_environment != expected_environment:
        raise EvidenceError(
            f"deployed environment is {deployed_environment!r}, expected {expected_environment!r}"
        )

    with tempfile.TemporaryDirectory(prefix="ai-stp-live-slice-") as raw:
        # A fresh home per run. The operator's real registry, device identity
        # and cache are never read or written, and the cache observed in the
        # offline step is one this run created rather than one it inherited.
        home = Path(raw)
        (home / "config").mkdir()
        (home / "data").mkdir()

        doctor = data(cli(("doctor",), home=home, python=python), "doctor")
        machine_help = data(cli(("help", "--agent"), home=home, python=python), "help --agent")
        commands = machine_help.get("commands")
        if not isinstance(commands, list) or not commands:
            raise EvidenceError("help --agent listed no commands")

        cli(
            ("config", "set", "--set", f"catalog.url={origin}"),
            home=home,
            python=python,
        )

        kinds: dict[str, Any] = {}
        for kind, collection in COLLECTIONS.items():
            listed, checked_at = _search(kind, home=home, python=python)
            published = _catalogue(origin, collection)
            if listed != published:
                only_cli = sorted(set(listed) - set(published))
                only_api = sorted(set(published) - set(listed))
                disagreed = sorted(
                    name for name in set(listed) & set(published) if listed[name] != published[name]
                )
                raise EvidenceError(
                    f"{kind}: CLI and the published catalogue disagree; "
                    f"only in CLI {only_cli}, only in API {only_api}, "
                    f"different exact version {disagreed}"
                )
            if not listed:
                raise EvidenceError(
                    f"{kind}: the deployed catalogue is empty, so nothing was proved"
                )

            stable_id = sorted(listed)[0]
            online = _show(kind, stable_id, home=home, python=python, offline=False)
            if online != "online":
                raise EvidenceError(
                    f"{kind}: show answered from {online!r} while the network was up"
                )
            cached = _show(kind, stable_id, home=home, python=python, offline=True)
            if cached != "cache":
                raise EvidenceError(
                    f"{kind}: show answered from {cached!r} with the route denied; "
                    "a cached exact object must be served without claiming freshness"
                )

            # `#162` asks that the CLI and the web show the same exact version
            # the same way. Agreeing with the API is necessary and not
            # sufficient: both surfaces read it and can still render it
            # differently, which is `#371`.
            exact_version = listed[stable_id]
            reported = _exact_digest(kind, stable_id, exact_version, home=home, python=python)
            projected = _projected_digest(origin, collection, stable_id, exact_version)
            if reported != projected:
                raise EvidenceError(
                    f"{kind} {stable_id}@{exact_version}: the CLI reports digest "
                    f"{reported} and the machine projection shows {projected}"
                )

            kinds[kind] = {
                "listed": len(listed),
                "checked_at": checked_at,
                "parity_with_published_catalogue": True,
                "parity_with_machine_projection": True,
                "exact_digest": reported,
                "exact_object": stable_id,
                "exact_version": exact_version,
                "online_source": online,
                "offline_source": cached,
            }

    report: dict[str, Any] = {
        "schema_version": 1,
        "origin": origin,
        "deployed_commit": deployed_commit,
        "deployed_environment": deployed_environment,
        "schema_revision": identity.get("schema_revision"),
        "doctor_state": doctor.get("state"),
        "machine_help_commands": len(cast(list[Any], commands)),
        "kinds": kinds,
        "authenticated": False,
        # Named rather than omitted. A scenario nobody ran is `not_verified`,
        # and an artefact that stays silent about it reads as full coverage.
        "not_verified": {
            "google_login_and_device_registration": (
                "needs a person or a deterministic provider test environment"
            ),
            "github_login_on_an_isolated_account": (
                "needs a person or a deterministic provider test environment"
            ),
            "device_revocation_and_relogin": "depends on the two login paths above",
        },
    }

    return without_credentials(report)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--origin", required=True, help="Bare https origin of the deployed environment."
    )
    parser.add_argument("--expected-commit", help="Exact SHA the environment must report.")
    parser.add_argument("--expected-environment", default="prod")
    parser.add_argument("--python", default=sys.executable)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        report = verify_live_slice(
            options.origin,
            python=options.python,
            expected_commit=options.expected_commit,
            expected_environment=options.expected_environment,
        )
    except (EvidenceError, OSError) as error:
        print(f"live-slice: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
