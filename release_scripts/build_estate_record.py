"""Build an offline `ai-stp-estate-release/1` record from local identities.

The builder does not fetch GitHub, PyPI, or the host. Provider tags and
commits are supplied as inputs. The stored verdict is always the recomputed
value; this script will not write `complete` for a six-package cut or an
empty evidence matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from ai_stp_contracts.estate_release import (
    EstateConsumer,
    EstateDistribution,
    EstateEvidenceRow,
    EstateProvider,
    EstateRelease,
    computed_verdict,
)
from ai_stp_foundation.canonical import JsonValue, canonize

POLICY = Path("apps/cli/src/ai_stp_cli/provider/provider-policy.toml")
CONSUMER_REPOSITORY: Final[str] = "ai-engineers-guild/ai-stp"
_SUMS = re.compile(r"^([0-9a-f]{64})\s+(\S+)$")
_PROVIDER = re.compile(r"^([^:=]+)[=:]([^@]+)@([0-9a-f]{40})$")


def policy_provider_repositories(policy: Path = POLICY) -> tuple[str, ...]:
    document = tomllib.loads(policy.read_text(encoding="utf-8"))
    rows = document.get("build_attestations")
    if not isinstance(rows, list):
        raise SystemExit("provider-policy.toml has no build_attestations")
    repositories: list[str] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        repository = raw.get("repository")
        if isinstance(repository, str) and repository:
            repositories.append(repository)
    if not repositories:
        raise SystemExit("provider-policy.toml names no attested repositories")
    return tuple(repositories)


def parse_checksums(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _SUMS.match(stripped)
        if match is None:
            raise SystemExit(f"SHA256SUMS line is not digest then filename: {line}")
        digest, filename = match.groups()
        if filename in rows:
            raise SystemExit(f"SHA256SUMS repeats {filename}")
        rows[filename] = f"sha256:{digest}"
    return rows


def distributions_from_checksums(
    checksums: dict[str, str], *, version: str
) -> list[EstateDistribution]:
    found: list[EstateDistribution] = []
    for filename, digest in sorted(checksums.items()):
        if "ai_stp_cli-" not in filename and "ai-stp-cli-" not in filename:
            continue
        if not (filename.endswith(".whl") or filename.endswith(".tar.gz")):
            continue
        found.append(
            EstateDistribution(
                name="ai-stp-cli",
                version=version,
                filename=filename,
                digest=digest,
            )
        )
    if not found:
        raise SystemExit("SHA256SUMS names no ai-stp-cli wheel or sdist")
    return found


def parse_providers(values: list[str]) -> list[EstateProvider]:
    providers: list[EstateProvider] = []
    for item in values:
        match = _PROVIDER.match(item.strip())
        if match is None:
            raise SystemExit(f"provider identity must be repository=tag@<40-char-commit>: {item}")
        repository, tag, commit = match.groups()
        providers.append(EstateProvider(repository=repository, commit=commit, tag=tag))
    return providers


def parse_evidence(path: Path | None) -> list[EstateEvidenceRow]:
    if path is None:
        return []
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("evidence file must be a JSON array")
    return [EstateEvidenceRow.model_validate(item) for item in payload]


def build_record(
    *,
    version: str,
    commit: str,
    tag: str,
    checksums: dict[str, str],
    providers: list[EstateProvider],
    evidence: list[EstateEvidenceRow],
    required_slices: list[str],
    known_limitations: list[str],
    created_at: str,
    checksums_digest: str = "",
    sbom_digest: str = "",
) -> EstateRelease:
    distributions = distributions_from_checksums(checksums, version=version)
    draft = EstateRelease(
        schema_id="ai-stp-estate-release/1",
        record_id="pending",
        created_at=created_at,  # pyright: ignore[reportArgumentType]
        consumer=EstateConsumer(
            repository=CONSUMER_REPOSITORY,
            commit=commit,
            tag=tag,
            release_url=f"https://github.com/{CONSUMER_REPOSITORY}/releases/tag/{tag}",
        ),
        distributions=distributions,
        providers=providers,
        evidence=evidence,
        known_limitations=known_limitations,
        verdict="incomplete",
        required_slices=required_slices,
        checksums_digest=checksums_digest,
        sbom_digest=sbom_digest,
        record_provenance=(
            "release_scripts/build_estate_record.py from local checksums and "
            "supplied provider identities; offline; verdict recomputed"
        ),
    )
    verdict = computed_verdict(draft)
    body = draft.model_dump(mode="json")
    body.pop("record_id")
    record_id = "estate-" + hashlib.sha256(canonize(body)).hexdigest()[:24]
    return draft.model_copy(update={"record_id": record_id, "verdict": verdict})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--provider",
        action="append",
        default=[],
        help="repository=tag@<40-char-commit>, repeatable.",
    )
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--required-slice",
        action="append",
        default=[],
        help="Slice name that must pass on every required leg for complete.",
    )
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument("--created-at")
    parser.add_argument("--checksums-digest")
    parser.add_argument("--sbom-digest")
    return parser


def main(argv: list[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    commit = options.commit.strip().lower()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise SystemExit("commit must be a 40-character lowercase SHA")
    providers = parse_providers(options.provider)
    expected = set(policy_provider_repositories())
    named = {item.repository for item in providers}
    if named and named != expected:
        missing = ", ".join(sorted(expected - named)) or "none"
        extra = ", ".join(sorted(named - expected)) or "none"
        raise SystemExit(
            "provider set must match provider-policy.toml build_attestations: "
            f"missing {missing}; extra {extra}"
        )
    created_at = options.created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    record = build_record(
        version=options.version,
        commit=commit,
        tag=options.tag,
        checksums=parse_checksums(options.checksums),
        providers=providers,
        evidence=parse_evidence(options.evidence),
        required_slices=list(options.required_slice),
        known_limitations=list(options.limitation),
        created_at=created_at,
        checksums_digest=options.checksums_digest or "",
        sbom_digest=options.sbom_digest or "",
    )
    payload: JsonValue = record.model_dump(mode="json")
    options.output.write_text(canonize(payload).decode() + "\n", encoding="utf-8")
    print(record.verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
