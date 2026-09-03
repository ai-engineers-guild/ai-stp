"""Prove the publication and authorisation surface against a deployed environment.

`#182` asks that the machine commands for publication, author attestation,
grants, reports and owner reads pass the contract against the deployed
environment, and that they carry neither credentials nor source code out of the
allowed set. The client half has been implemented for a while; what was missing
is a run somebody else can repeat.

The split here is deliberate and is the whole design. Reading what an account
owns changes nothing and runs by default. Publishing a version, inviting a
person, or filing a report changes the deployed catalogue or somebody's access,
and one of them is irreversible in the way that matters — a published `X.Y` is
immutable. Those are reported as `not_verified` with the reason unless the
operator names the object and passes `--allow-writes`, which is a decision the
script must not make on their behalf.

Authentication is not automated, for the same reason as the sync slice: the
device-code flow needs a person, and a script able to mint a session would prove
a path nobody ships.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

from release_scripts._evidence import (
    EvidenceError,
    cli,
    data,
    error_code,
    login_commands,
    without_credentials,
)
from release_scripts._evidence import origin as bare_origin

# Read-only commands, each named with the surface it proves. A command that
# changes nothing can run against production without a decision.
READS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("owner_objects", ("owner", "objects")),
    ("grant_list", ("grant", "list")),
    ("report_list", ("report", "list")),
)

# Everything that mutates the deployed environment. `attestation sign` and
# `report preview` used to sit here and no longer do: both are local, so gating
# them treated a signature written to this machine as if it were an immutable
# published version, and left half the surface unproven for nothing.
#
# Two of the three are driven under `--allow-writes` since 2026-09-01. The
# subject is the repository's own claude-code skill projection — adopted,
# completed and released under the operator's account — because a published
# passport demands a true source and a concrete harness, which the scaffold
# probe cannot honestly claim. Publishing it creates an immutable X.Y (absent
# from the anonymous listing until verified), and an invitation on it is
# created and revoked. The third stays undriven on purpose: a fabricated
# moderation case is durable moderator noise, not evidence, and its command is
# already proven reachable above.
WRITES: tuple[tuple[str, str], ...] = (
    (
        "publication",
        "publication plan/confirm writes an immutable X.Y into the deployed catalogue",
    ),
    ("grants", "grant invite/direct/revoke changes another person's access to an object"),
    ("report_confirm", "report confirm files a durable moderation case against a version"),
)


def _point_at(home: Path, origin: str, *, python: str) -> None:
    cli(
        ["config", "set", "--set", "sync.enabled=true", "--set", f"catalog.url={origin}"],
        home=home,
        python=python,
    )


def _auth_state(home: Path, *, python: str) -> str:
    state = data(cli(["auth", "status"], home=home, python=python), "auth status").get("state")
    if not isinstance(state, str):
        raise EvidenceError("auth status answered without a state")
    return state


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for field in ("items", "objects", "grants", "reports"):
        held = payload.get(field)
        if isinstance(held, list):
            return [row for row in cast(list[Any], held) if isinstance(row, dict)]
    return []


def _read(name: str, arguments: Sequence[str], home: Path, *, python: str) -> dict[str, Any]:
    envelope = cli(list(arguments), home=home, python=python, allow_failure=True)
    if envelope.get("ok") is not True:
        return {
            "state": "failed",
            "command": " ".join(arguments),
            "error_code": error_code(envelope),
        }
    payload = data(envelope, " ".join(arguments))
    rows = _rows(payload)
    return {
        "state": "verified",
        "command": " ".join(arguments),
        # Identities and counts only. The criterion forbids carrying source code
        # out, and a report that pasted an object's content would be the thing it
        # is meant to rule out.
        "rows": len(rows),
        # Kind travels with the identity. `owner objects` returns both kinds and
        # `owner object show` demands one, so an identity on its own is not
        # enough to read it back — a setup asked for as a component is answered
        # `AI_STP_NOT_FOUND`, correctly, and the slice would call a healthy
        # deployment broken.
        #
        # A row that does not state its kind is still carried, defaulted, rather
        # than dropped: dropping it would empty this list, and an empty list is
        # read downstream as "the account owns nothing yet" — a quiet success
        # standing in for a failure.
        "identities": [_identity(row) for row in rows if isinstance(row.get("stable_id"), str)][:5],
    }


def _identity(row: dict[str, Any]) -> str:
    """`kind:stable_id`, which is what it takes to address an owned object."""
    kind = row.get("object_kind")
    return f"{kind if isinstance(kind, str) else 'component'}:{row['stable_id']}"


def _split(identity: str) -> tuple[str, str]:
    """`kind:stable_id` as the listing reports it, tolerating a bare id."""
    kind, _, stable_id = identity.partition(":")
    return (kind, stable_id) if stable_id else ("component", kind)


def _owned_detail(home: Path, identities: Sequence[str], *, python: str) -> dict[str, Any]:
    """One owned object read whole, which is the authorised-read half of `#182`."""
    if not identities:
        return {
            "state": "not_verified",
            "reason": "the account owns no object yet, so there is nothing to read back",
        }
    kind, stable_id = _split(identities[0])
    envelope = cli(
        ["owner", "object", "show", "--kind", kind, "--id", stable_id],
        home=home,
        python=python,
        allow_failure=True,
    )
    if envelope.get("ok") is not True:
        return {
            "state": "failed",
            "object_kind": kind,
            "stable_id": stable_id,
            "error_code": error_code(envelope),
        }
    payload = data(envelope, "owner object show")
    return {
        "state": "verified",
        "object_kind": kind,
        "stable_id": stable_id,
        "versions": len(cast(list[Any], payload.get("versions") or [])),
    }


def _first_release(home: Path, identities: Sequence[str], *, python: str) -> tuple[str, str, str]:
    """One owned released component: its id, exact version and content digest.

    A component specifically: what follows it signs and reports a component
    version. Setups in the listing are skipped rather than asked for under the
    wrong kind.

    Asked for by kind rather than filtered out of the sample. The sample is the
    first five rows of one unfiltered page, and when those five are setups this
    returned nothing and the caller reported "the account owns no released
    component version" — which was false: the account owned thirty-three, all
    of them past the first page. A partial read presented as a total, and the
    listing takes `--kind`, so the question could have been asked directly.
    """
    listed = cli(
        ["owner", "objects", "--kind", "component"],
        home=home,
        python=python,
        allow_failure=True,
    )
    owned: list[str] = []
    if listed.get("ok") is True:
        rows = cast(list[Any], data(listed, "owner objects").get("items") or [])
        owned = [
            f"component:{row['stable_id']}"
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("stable_id"), str)
        ]
    for identity in [*owned, *identities]:
        kind, stable_id = _split(identity)
        if kind != "component":
            continue
        envelope = cli(
            ["owner", "object", "show", "--kind", "component", "--id", stable_id],
            home=home,
            python=python,
            allow_failure=True,
        )
        if envelope.get("ok") is not True:
            continue
        versions = cast(list[Any], data(envelope, "owner object show").get("versions") or [])
        for item in versions:
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            number, digest = row.get("version"), row.get("content_digest") or row.get("digest")
            if isinstance(number, str) and isinstance(digest, str):
                return stable_id, number, digest
    return "", "", ""


#: A component this device released itself. `attestation sign` records evidence
#: about a local release and refuses a published stable id with "that component
#: has no such released local version", so the driver seeds its own rather than
#: signing somebody else's number. Placed inside the home because adoption
#: records `source_path` through `redact_home`.
_PROBE = "publication-slice-probe"


def _seed_local_release(home: Path, *, python: str) -> tuple[str, str]:
    """Scaffold, adopt and release one component here, and return id and version."""
    project = home / "work"
    scaffold = home / "scaffold" / _PROBE
    target = project / ".claude" / "skills" / _PROBE
    scaffold.parent.mkdir(parents=True, exist_ok=True)
    if scaffold.exists():
        shutil.rmtree(scaffold)
    shape = [
        "--type",
        "skill",
        "--language",
        "none",
        "--harness",
        "portable",
        "--name",
        _PROBE,
        "--output",
        str(scaffold),
    ]
    planned = data(
        cli(["component", "scaffold", "plan", *shape], home=home, python=python),
        "component scaffold plan",
    )
    cli(
        [
            "component",
            "scaffold",
            "apply",
            *shape,
            "--expected-plan-digest",
            str(planned["plan_digest"]),
        ],
        home=home,
        python=python,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    # The portable skill scaffold's adoptable package is `source/`. Same defect
    # and same fix as the sync slice: the first real-account run refused with
    # "this directory holds no manifest to adopt", and the refusal was correct.
    native = scaffold / "source"
    if not native.is_dir():
        raise EvidenceError(f"the scaffold at {scaffold} has no source/ half to adopt")
    shutil.copytree(native, target)
    adopted = data(
        cli(
            ["component", "adopt", "--path", str(target), "--root", str(project)],
            home=home,
            python=python,
        ),
        "component adopt",
    )
    stable_id = str(adopted["stable_id"])
    # `attestation sign` requires a publication-ready passport and names what is
    # missing: description, license, name, projection_kind and tags. A bare
    # scaffold has none of them, so the probe declares them before releasing.
    shown = data(
        cli(["component", "passport", "show", "--id", stable_id], home=home, python=python),
        "component passport show",
    )
    patch = home / "publication-slice-patch.json"
    patch.write_text(
        json.dumps(
            {
                "name": "Publication slice probe",
                "description": "Local probe used to prove attestation signing.",
                "license": {"spdx_id": "AGPL-3.0-or-later", "redistribution_allowed": True},
                "projection_kind": "native_files",
                "tags": ["conformance"],
            }
        ),
        encoding="utf-8",
    )
    cli(
        [
            "component",
            "passport",
            "update",
            "--id",
            stable_id,
            "--expected-revision",
            str(shown["revision_id"]),
            "--from",
            str(patch),
        ],
        home=home,
        python=python,
    )
    released = data(
        cli(
            ["component", "version", "release", "--id", stable_id],
            home=home,
            python=python,
        ),
        "component version release",
    )
    numbers = [str(item["version"]) for item in released.get("versions", [])]
    if not numbers:
        raise EvidenceError("component version release answered without a version")
    return stable_id, numbers[-1]


def _local_writes(
    home: Path,
    identities: Sequence[str],
    seeded: tuple[str, str],
    *,
    python: str,
) -> dict[str, dict[str, Any]]:
    """The two write commands that change nothing outside this machine.

    `attestation sign` writes an owner-only file with the active device key and
    `report preview` builds the bounded payload without sending it — neither
    reaches the deployed catalogue. Leaving them behind `--allow-writes` with
    the irreversible three treated a local signature as if it were an immutable
    published version, and left the whole half unproven for no gain.
    """
    stable_id, version, digest = _first_release(home, identities, python=python)
    if not stable_id:
        reason = "the account owns no released component version to sign or report against"
        return {
            "attestation": {"state": "not_verified", "reason": reason},
            "report_preview": {"state": "not_verified", "reason": reason},
        }

    local_id, local_version = seeded
    # `attestation sign` refuses to replace an existing output — "the attestation
    # output already exists and will not be replaced" — and it is right to: an
    # attestation is evidence, and silently overwriting one is how evidence
    # stops meaning anything. So the run removes its own previous artefact
    # rather than asking the command to be less careful. A slice that passes
    # once and fails on the next run is not evidence either.
    signed = home / "attestation-evidence.json"
    signed.unlink(missing_ok=True)
    attestation = cli(
        [
            "attestation",
            "sign",
            "--id",
            local_id,
            "--version",
            local_version,
            "--check-id",
            "publication-slice",
            "--policy-version",
            "1.0",
            "--harness-id",
            "claude-code",
            "--harness-version",
            "0.0.0",
            "--provider-version",
            "0.0.0",
            "--test-case-id",
            "publication-slice-read",
            "--result",
            "passed",
            "--output",
            str(signed),
            "--confirm",
        ],
        home=home,
        python=python,
        allow_failure=True,
    )
    previewed = cli(
        [
            "report",
            "preview",
            "--kind",
            "component",
            "--id",
            stable_id,
            "--version",
            version,
            "--content-digest",
            digest,
            "--idempotency-key",
            "publication-slice-preview-0001",
        ],
        home=home,
        python=python,
        allow_failure=True,
    )
    return {
        "attestation": {
            "state": "verified" if attestation.get("ok") is True else "failed",
            "stable_id": local_id,
            "version": local_version,
            "error_code": error_code(attestation),
            "note": "signs locally with the active device key and sends nothing",
        },
        "report_preview": {
            "state": "verified" if previewed.get("ok") is True else "failed",
            "stable_id": stable_id,
            "version": version,
            "error_code": error_code(previewed),
            "note": "builds the exact bounded payload without filing a case",
        },
    }


#: The three mutating commands, probed with an identifier that cannot exist.
#: A typed `AI_STP_NOT_FOUND` proves the command is wired end to end — argv
#: parsed, session used, server reached, request validated — while changing
#: nothing. It is not the same as running the mutation, and the report says so;
#: it is the difference between knowing nothing about a command and knowing
#: everything except its effect.
ABSENT: Final[str] = "0" * 26
UNREACHABLE_DIGEST: Final[str] = "sha256:" + "0" * 64

REACHABILITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "publication_reachable",
        (
            "publication",
            "confirm",
            "--plan-id",
            f"publication_plan_{ABSENT}",
            "--plan-hash",
            UNREACHABLE_DIGEST,
            "--confirm",
        ),
    ),
    (
        "grants_reachable",
        (
            "grant",
            "revoke",
            "--grant-id",
            f"grant_{ABSENT}",
            "--idempotency-key",
            "publication-slice-revoke-0001",
            "--confirm",
        ),
    ),
    (
        "report_confirm_reachable",
        (
            "report",
            "confirm",
            "--plan-id",
            f"report_plan_{ABSENT}",
            "--plan-digest",
            UNREACHABLE_DIGEST,
            "--confirm",
        ),
    ),
)


def _reachability(home: Path, *, python: str) -> dict[str, dict[str, Any]]:
    """Each mutating command answered for an object that does not exist."""
    answers: dict[str, dict[str, Any]] = {}
    for name, arguments in REACHABILITY:
        envelope = cli(list(arguments), home=home, python=python, allow_failure=True)
        code = error_code(envelope)
        answers[name] = {
            "state": "verified" if code == "AI_STP_NOT_FOUND" else "failed",
            "command": " ".join(arguments[:2]),
            "error_code": code or "accepted",
            "note": "reached and refused an absent object; the mutation itself stays gated",
        }
    return answers


#: Where the driven-write subject lives in this repository, and the marker that
#: makes a rerun read the previous publication back instead of minting a second
#: immutable version. The scaffold probe cannot be the subject: a published
#: passport requires a true `source` (repository, commit, path) and a concrete
#: harness, and the probe is generated bytes in a scratch home — any source
#: coordinates it claimed would be fabricated. The repository's own claude-code
#: skill projection carries all of that truthfully.
_SUBJECT_PATH: Final[str] = "skills/projections/claude-code"
_SUBJECT_MARKER: Final[str] = "publishable-subject.json"


def _seed_publishable(home: Path, *, python: str) -> tuple[str, str]:
    """Adopt, complete and release the repo-sourced subject; reuse it on rerun."""
    marker = home / _SUBJECT_MARKER
    if marker.is_file():
        held = cast(dict[str, Any], json.loads(marker.read_text(encoding="utf-8")))
        return str(held["stable_id"]), str(held["version"])

    repo = Path.cwd()
    subject = repo / _SUBJECT_PATH
    if not subject.is_dir():
        raise EvidenceError(
            f"{_SUBJECT_PATH} is not here; the driven writes run from the repository checkout"
        )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    adopted = data(
        cli(
            ["component", "adopt", "--path", str(subject), "--root", str(repo)],
            home=home,
            python=python,
        ),
        "component adopt",
    )
    stable_id = str(adopted["stable_id"])
    shown = data(
        cli(["component", "passport", "show", "--id", stable_id], home=home, python=python),
        "component passport show",
    )
    patch = home / "publishable-subject-patch.json"
    patch.write_text(
        json.dumps(
            {
                "name": "ai-stp skill for Claude Code",
                "description": (
                    "The ai-stp skill projection for Claude Code as shipped in the "
                    "public repository."
                ),
                "license": {"spdx_id": "AGPL-3.0-or-later", "redistribution_allowed": True},
                "projection_kind": "native_files",
                "harness_id": "claude-code",
                "tags": ["conformance"],
                "source": {
                    "repository": "https://github.com/ai-engineers-guild/ai-stp",
                    "commit": commit,
                    "path": _SUBJECT_PATH,
                },
            }
        ),
        encoding="utf-8",
    )
    cli(
        [
            "component",
            "passport",
            "update",
            "--id",
            stable_id,
            "--expected-revision",
            str(shown["revision_id"]),
            "--from",
            str(patch),
        ],
        home=home,
        python=python,
    )
    released = data(
        cli(
            ["component", "version", "release", "--id", stable_id],
            home=home,
            python=python,
        ),
        "component version release",
    )
    numbers = [str(item["version"]) for item in released.get("versions", [])]
    if not numbers:
        raise EvidenceError("component version release answered without a version")
    marker.write_text(
        json.dumps({"stable_id": stable_id, "version": numbers[-1]}), encoding="utf-8"
    )
    return stable_id, numbers[-1]


def _publication_state(home: Path, plan_id: str, *, python: str) -> str:
    status = cli(
        ["publication", "status", "--plan-id", plan_id],
        home=home,
        python=python,
        allow_failure=True,
    )
    if status.get("ok") is not True:
        return ""
    return str(data(status, "publication status").get("state", ""))


def _driven_writes(
    home: Path,
    invite_email: str,
    *,
    python: str,
) -> dict[str, dict[str, Any]]:
    """The two irreversible writes, run for real against the deployed catalogue.

    The subject is the repository's own claude-code skill projection, adopted
    and released under the operator's account: publishing it creates an
    immutable X.Y whose source coordinates are true, and the grant cycle
    creates an invitation on that published object and revokes it before it can
    be accepted. Nothing here touches an object the operator does not own.
    """
    publication: dict[str, Any] = {}
    try:
        stable_id, version = _seed_publishable(home, python=python)
    except EvidenceError as error:
        publication.update(state="failed", step="seed", reason=str(error))
        return {
            "publication": publication,
            "grants": {
                "state": "not_verified",
                "reason": "the grant cycle needs the published subject, and seeding failed",
            },
        }
    publication.update(stable_id=stable_id, version=version)

    marker = home / _SUBJECT_MARKER
    held = cast(dict[str, Any], json.loads(marker.read_text(encoding="utf-8")))
    plan_id = str(held.get("plan_id", ""))
    if not (plan_id and _publication_state(home, plan_id, python=python) == "published"):
        planned = cli(
            ["publication", "plan", "--id", stable_id, "--version", version],
            home=home,
            python=python,
            allow_failure=True,
        )
        if planned.get("ok") is not True:
            publication.update(state="failed", step="plan", error_code=error_code(planned))
            plan_id = ""
        else:
            plan_view = data(planned, "publication plan")
            plan_id = str(plan_view.get("plan_id", ""))
            confirmed = cli(
                [
                    "publication",
                    "confirm",
                    "--plan-id",
                    plan_id,
                    "--plan-hash",
                    str(plan_view.get("plan_hash", "")),
                    "--confirm",
                ],
                home=home,
                python=python,
                allow_failure=True,
            )
            if confirmed.get("ok") is not True:
                publication.update(
                    state="failed",
                    step="confirm",
                    plan_id=plan_id,
                    error_code=error_code(confirmed),
                )
                plan_id = ""
    if plan_id:
        # Validation runs server-side (structure, scanning, catalogue write);
        # `published` is the terminal success and anything else terminal is a
        # refusal worth reading. A run that never reaches a terminal state is
        # reported as exactly that rather than guessed either way.
        server_state = ""
        for _ in range(24):
            server_state = _publication_state(home, plan_id, python=python)
            if server_state not in {"", "ready", "validating", "confirmed"}:
                break
            time.sleep(5)
        if server_state == "published":
            held.update(plan_id=plan_id)
            marker.write_text(json.dumps(held), encoding="utf-8")
            publication.update(
                state="verified",
                plan_id=plan_id,
                server_state=server_state,
                note="an immutable X.Y with a true repository source is in the deployed catalogue",
            )
        elif server_state in {"", "ready", "validating", "confirmed"}:
            publication.update(
                state="not_verified",
                plan_id=plan_id,
                server_state=server_state,
                reason="confirm was accepted and validation did not reach a terminal "
                "state within two minutes",
            )
        else:
            publication.update(
                state="failed", step="validate", plan_id=plan_id, server_state=server_state
            )

    grants: dict[str, Any] = {"stable_id": stable_id}
    if not invite_email:
        grants.update(
            state="not_verified",
            reason="no --invite-email was given, and inventing a recipient is not this "
            "script's decision",
        )
    elif publication.get("state") != "verified":
        grants.update(
            state="not_verified",
            reason="the grant cycle needs the published subject, and publication did not verify",
        )
    else:
        # Fresh keys on purpose: an idempotency key exists to make a retry of
        # one intent safe, and each run of this cycle is a new intent — a
        # replayed key would hand back the previous run's already-revoked
        # invitation and prove nothing about this one.
        run_key = time.strftime("%Y%m%dT%H%M%S")
        invited = cli(
            [
                "grant",
                "invite",
                "--kind",
                "component",
                "--id",
                stable_id,
                "--major",
                version.partition(".")[0],
                "--email",
                invite_email,
                "--ttl-seconds",
                "3600",
                "--idempotency-key",
                f"publication-slice-invite-{run_key}",
                "--confirm",
            ],
            home=home,
            python=python,
            allow_failure=True,
        )
        if invited.get("ok") is not True:
            grants.update(state="failed", step="invite", error_code=error_code(invited))
        else:
            invitation_id = str(data(invited, "grant invite").get("invitation_id", ""))
            revoked = cli(
                [
                    "grant",
                    "invitation",
                    "revoke",
                    "--invitation-id",
                    invitation_id,
                    "--reason",
                    "publication slice cycle",
                    "--idempotency-key",
                    f"publication-slice-revoke-{run_key}",
                    "--confirm",
                ],
                home=home,
                python=python,
                allow_failure=True,
            )
            if revoked.get("ok") is not True:
                grants.update(
                    state="failed",
                    step="invitation revoke",
                    invitation_id=invitation_id,
                    error_code=error_code(revoked),
                )
            else:
                grants.update(
                    state="verified",
                    invitation_id=invitation_id,
                    note="an invitation on the published subject was created and revoked "
                    "before acceptance",
                )

    return {"publication": publication, "grants": grants}


def verify_publication_slice(
    origin: str,
    home: Path,
    *,
    python: str,
    allow_writes: bool = False,
    invite_email: str = "",
) -> dict[str, Any]:
    home.mkdir(parents=True, exist_ok=True)
    _point_at(home, origin, python=python)
    state = _auth_state(home, python=python)

    scenarios: dict[str, Any] = {}
    # Bound before the branch, not inside it. It used to be assigned only in the
    # `else`, and read later under a separately written `state == "authenticated"`
    # guard — safe only for as long as two conditions nobody has to keep together
    # stay complementary.
    owned: list[str] = []
    if state != "authenticated":
        reason = f"the home reports auth state {state!r}"
        commands = login_commands(home)
        for name, _arguments in READS:
            scenarios[name] = {"state": "not_verified", "reason": reason, "commands": commands}
        scenarios["owner_object_show"] = {
            "state": "not_verified",
            "reason": reason,
            "commands": commands,
        }
    else:
        for name, arguments in READS:
            result = _read(name, arguments, home, python=python)
            if name == "owner_objects":
                owned = cast(list[str], result.get("identities") or [])
            scenarios[name] = result
        scenarios["owner_object_show"] = _owned_detail(home, owned, python=python)

    if state == "authenticated":
        seeded = _seed_local_release(home, python=python)
        scenarios.update(_local_writes(home, owned, seeded, python=python))
        scenarios.update(_reachability(home, python=python))
        if allow_writes:
            scenarios.update(_driven_writes(home, invite_email, python=python))

    for name, reason in WRITES:
        if name in scenarios:
            continue
        if name == "report_confirm" and allow_writes:
            scenarios[name] = {
                "state": "not_verified",
                "reason": reason + ". Deliberately not driven: a fabricated moderation "
                "case is durable moderator noise, and the command is proven reachable "
                "above",
            }
            continue
        scenarios[name] = {
            "state": "not_verified",
            "reason": reason + ". Pass --allow-writes with the exact object to run it",
        }

    return without_credentials(
        {
            "schema_version": 1,
            "origin": origin,
            "auth_state": state,
            "writes_allowed": allow_writes,
            "scenarios": scenarios,
        }
    )


def refused(report: Mapping[str, Any]) -> bool:
    """A run that proved none of the read surface must not exit zero.

    An undriven write scenario is `not_verified` by design rather than by
    accident, so it never decides the exit code: a code that is always red is a
    code nobody reads. A *driven* write that failed is a different animal — the
    operator allowed it, the slice ran it, and a quiet zero over that failure
    would be the exact defect this script exists to rule out.
    """
    writes = {name for name, _reason in WRITES}
    scenarios = cast(Mapping[str, Mapping[str, Any]], report["scenarios"])
    for name, held in scenarios.items():
        if name in writes:
            if held.get("state") == "failed":
                return True
            continue
        if held.get("state") in {"failed", "not_verified"}:
            return True
    return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--origin", default="https://ai-stp.aiguild.space", help="Bare https origin."
    )
    parser.add_argument("--home", required=True, help="Device home, already signed in.")
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="Permit the scenarios that change the deployed catalogue or somebody's access.",
    )
    parser.add_argument(
        "--invite-email",
        default="",
        help="Recipient for the driven grant-invitation cycle; the invitation is "
        "revoked before it can be accepted. Without it the grant scenario stays "
        "not_verified — inventing a recipient is not this script's decision.",
    )
    parser.add_argument("--python", default=sys.executable, help="Interpreter running the CLI.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = verify_publication_slice(
            bare_origin(arguments.origin),
            Path(arguments.home).expanduser(),
            python=arguments.python,
            allow_writes=arguments.allow_writes,
            invite_email=arguments.invite_email,
        )
    except EvidenceError as error:
        print(f"publication-slice: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if refused(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
