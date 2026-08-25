"""Release trust: a signature is not trust, and a counter nothing can lower."""

import base64
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import release
from ai_stp_foundation.digests import is_digest

CONTRACT = Path("docs/contracts/provider-release.md")

PRIVATE_2026 = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PRIVATE_2025 = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))

VALID_POLICY_TEXT = """\
schema_version = 2
policy_id = "nddev/provider/1"
signature_subject = "ai-stp:provider-release-manifest:v1"
minimum_sequence = 0
allowed_publishers = ["NDDev-it-com"]
allowed_repositories = ["github.com/NDDev-it-com/nddev-claude-app"]
allowed_keys = []
public_keys = {}
revoked_keys = []
supported_protocols = [1]
releases = []
"""


_ALLOWED_REPOSITORY = "github.com/NDDev-it-com/nddev-claude-app"
_PIN_FIELDS = f'provider_id = "nddev-claude-app", repository = "{_ALLOWED_REPOSITORY}"'
_DIGEST_A = "sha256:" + "a" * 64


def _public(private: Ed25519PrivateKey) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


#: The exact release the manifest fixture describes. Every positive case below
#: is a release this policy approved: after `release_not_pinned` exists, a
#: fixture that pins nothing would be testing refusal, not acceptance.
PINNED = release.PinnedRelease(
    provider_id="claude-code",
    repository="github.com/NDDev-it-com/nddev-claude-app",
    artifact_digest="sha256:" + "b" * 64,
)

POLICY = release.TrustPolicy(
    schema_version=release.POLICY_SCHEMA_VERSION,
    policy_id="nddev/provider/1",
    allowed_publishers=frozenset({"NDDev-it-com"}),
    allowed_keys=frozenset({"key-2026"}),
    allowed_repositories=frozenset({"github.com/NDDev-it-com/nddev-claude-app"}),
    pinned_releases=frozenset({PINNED}),
    signature_subject="ai-stp:provider-release-manifest:v1",
    public_keys={"key-2026": _public(PRIVATE_2026)},
    minimum_sequence=5,
)


def _manifest(**overrides: object) -> release.ReleaseManifest:
    explicit_signature = "signature" in overrides
    facts: dict[str, object] = {
        "provider_id": "claude-code",
        "provider_version": "1.0.0",
        "protocol_version": 1,
        "repository": "github.com/NDDev-it-com/nddev-claude-app",
        "commit": "a" * 40,
        "license": "MIT",
        "artifact_url": "https://example.test/releases/1.0.0/provider.tar.gz",
        "artifact_size": 100,
        "artifact_digest": "sha256:" + "b" * 64,
        "entry_point": "provider",
        "supported_os": frozenset({"linux"}),
        "supported_arch": frozenset({"x86_64"}),
        "sequence": 7,
        "policy_id": "nddev/provider/1",
        "publisher": "NDDev-it-com",
        "signing_key": "key-2026",
        "signature_subject": "ai-stp:provider-release-manifest:v1",
        "signature": "",
    }
    facts.update(overrides)
    manifest = release.ReleaseManifest(**facts)  # pyright: ignore[reportArgumentType]
    if explicit_signature:
        return manifest
    private = PRIVATE_2025 if manifest.signing_key == "key-2025" else PRIVATE_2026
    signature = base64.b64encode(private.sign(release.signature_payload(manifest))).decode("ascii")
    return replace(manifest, signature=signature)


def _codes(verdict: release.Verdict) -> tuple[str, ...]:
    return tuple(item.code for item in verdict.refusals)


def _policy(**overrides: object) -> release.TrustPolicy:
    facts = {**POLICY.__dict__}
    facts.update(overrides)
    return release.TrustPolicy(**facts)  # pyright: ignore[reportArgumentType]


def test_a_release_that_meets_the_policy_is_accepted() -> None:
    verdict = release.verify(_manifest(), POLICY, known_sequence=6, platform="linux/x86_64")
    assert verdict.accepted, _codes(verdict)
    assert verdict.next_minimum_sequence == 7


#: One fixture per trust failure the table can express. Held as a constant so
#: the coverage check below reads the same list the parametrisation does.
FIXTURES: list[tuple[release.ReleaseManifest, release.TrustPolicy, str]] = [
    (_manifest(policy_id="some-other-policy"), POLICY, "policy_id_mismatch"),
    (_manifest(publisher="somebody-else"), POLICY, "publisher_not_allowed"),
    (_manifest(signing_key="key-2024"), POLICY, "key_unknown"),
    (_manifest(repository="github.com/elsewhere/app"), POLICY, "repository_not_allowed"),
    (_manifest(signature_subject=""), POLICY, "signature_missing"),
    (_manifest(signature_subject="something-else"), POLICY, "signature_subject_mismatch"),
    (_manifest(signature="not-base64"), POLICY, "signature_invalid"),
    (
        _manifest(),
        _policy(public_keys={"key-2026": "not-base64"}),
        "key_material_invalid",
    ),
    (_manifest(artifact_digest="not-a-digest"), POLICY, "artifact_reference_floating"),
    (
        _manifest(artifact_url="https://example.test/releases/latest"),
        POLICY,
        "artifact_reference_floating",
    ),
    (_manifest(protocol_version=2), POLICY, "protocol_unsupported"),
    (_manifest(sequence=1), POLICY, "sequence_below_minimum"),
    (_manifest(artifact_digest="sha256:" + "d" * 64), POLICY, "release_not_pinned"),
    (_manifest(), _policy(revoked_keys=frozenset({"key-2026"})), "key_revoked"),
    # An older schema, not an invented one: schema 1 pinned bare digests, and a
    # build that binds them cannot read such a policy without guessing.
    (
        _manifest(),
        _policy(schema_version=release.POLICY_SCHEMA_VERSION - 1),
        "policy_schema_unsupported",
    ),
]

#: Reached by their own tests below: each needs an argument the table cannot
#: pass. Named here so the closed set is still asserted whole.
ARGUMENT_ONLY: frozenset[str] = frozenset(
    {
        "sequence_rollback",
        "recovery_artifact_unverified",
        "digest_mismatch",
        "size_mismatch",
        "platform_unsupported",
    }
)


# `REQ-811`: publisher, source, digest and sequence, not just a signature.
@pytest.mark.parametrize(("manifest", "policy", "code"), FIXTURES)
def test_every_trust_failure_has_its_own_code(
    manifest: release.ReleaseManifest, policy: release.TrustPolicy, code: str
) -> None:
    verdict = release.verify(manifest, policy, known_sequence=0)
    assert code in _codes(verdict)
    assert not verdict.accepted


def test_the_fixtures_cover_every_refusal_class() -> None:
    """A class with no fixture is a class nothing proves is detected."""
    assert {code for _, _, code in FIXTURES} | ARGUMENT_ONLY == release.REFUSALS


def test_a_signature_alone_is_not_trust() -> None:
    """The contract says so in as many words, and this is what that means."""
    signed_but_wrong = _manifest(publisher="somebody-else", repository="github.com/elsewhere/app")
    verdict = release.verify(signed_but_wrong, POLICY, known_sequence=0)
    assert not verdict.accepted
    assert "signature_missing" not in _codes(verdict)
    assert {"publisher_not_allowed", "repository_not_allowed"} <= set(_codes(verdict))


def test_tampering_any_signed_field_invalidates_the_signature() -> None:
    signed = _manifest()
    tampered = replace(signed, artifact_size=signed.artifact_size + 1)

    verdict = release.verify(tampered, POLICY, known_sequence=0)

    assert "signature_invalid" in _codes(verdict)
    assert not verdict.accepted


def test_every_failure_comes_back_rather_than_the_first() -> None:
    """Somebody fixing a release deserves the whole list."""
    verdict = release.verify(
        _manifest(publisher="x", signing_key="y", repository="z", sequence=1),
        POLICY,
        known_sequence=0,
    )
    assert len(verdict.refusals) >= 4


def test_an_unreadable_policy_schema_stops_everything_else() -> None:
    """A trust rule half-applied looks like a decision somebody made."""
    verdict = release.verify(_manifest(publisher="x"), _policy(schema_version=99), known_sequence=0)
    assert _codes(verdict) == ("policy_schema_unsupported",)


# Anti-rollback, and the one door through it.
def test_an_older_release_is_refused() -> None:
    verdict = release.verify(_manifest(sequence=6), POLICY, known_sequence=9)
    assert "sequence_rollback" in _codes(verdict)


def test_a_refused_release_never_moves_the_counter() -> None:
    """Otherwise refusing one would make the next rollback easier."""
    verdict = release.verify(_manifest(sequence=99, publisher="x"), POLICY, known_sequence=9)
    assert not verdict.accepted
    assert verdict.next_minimum_sequence == 9


def test_recovery_is_a_separate_decision_and_not_a_signature() -> None:
    older = _manifest(sequence=6)
    assert "sequence_rollback" in _codes(release.verify(older, POLICY, known_sequence=9))
    assert "sequence_rollback" in _codes(
        release.verify(older, POLICY, known_sequence=9, recovery_to_verified=True)
    )
    assert "recovery_artifact_unverified" in _codes(
        release.verify(older, POLICY, known_sequence=9, recovery_requested=True)
    )
    verdict = release.verify(
        older,
        POLICY,
        known_sequence=9,
        recovery_requested=True,
        recovery_to_verified=True,
    )
    assert verdict.accepted, _codes(verdict)


def test_recovery_does_not_reach_below_the_policy_floor() -> None:
    """A floor raised after a compromise is not a machine's to step under."""
    verdict = release.verify(
        _manifest(sequence=1),
        POLICY,
        known_sequence=9,
        recovery_requested=True,
        recovery_to_verified=True,
    )
    assert "sequence_below_minimum" in _codes(verdict)
    assert not verdict.accepted


def test_the_policy_floor_holds_on_a_machine_that_installed_nothing() -> None:
    verdict = release.verify(_manifest(sequence=2), POLICY, known_sequence=0)
    assert "sequence_below_minimum" in _codes(verdict)


# Key rotation and revocation.
def test_an_overlap_period_trusts_both_keys() -> None:
    """Without the overlap every machine that has not updated stops accepting."""
    rotating = _policy(
        allowed_keys=frozenset({"key-2025", "key-2026"}),
        public_keys={
            "key-2025": _public(PRIVATE_2025),
            "key-2026": _public(PRIVATE_2026),
        },
    )
    assert release.verify(_manifest(signing_key="key-2025"), rotating, known_sequence=6).accepted
    assert release.verify(_manifest(signing_key="key-2026"), rotating, known_sequence=6).accepted


def test_a_revoked_key_is_refused_even_while_still_allowed() -> None:
    """Revoking usually leaves it in the allowed set; that is what revoking is."""
    revoked = _policy(revoked_keys=frozenset({"key-2026"}))
    codes = _codes(release.verify(_manifest(), revoked, known_sequence=6))
    assert "key_revoked" in codes
    assert "key_unknown" not in codes


def test_nothing_here_removes_a_target() -> None:
    """`REQ-812`: revocation blocks installs and leaves running targets alone."""
    source = Path("apps/cli/src/ai_stp_cli/provider/release.py").read_text("utf-8")
    for verb in ("rmtree", "unlink", "remove(", "rmdir"):
        assert verb not in source


# The artifact itself.
def test_a_fetched_artifact_that_differs_is_refused() -> None:
    verdict = release.verify(
        _manifest(), POLICY, known_sequence=6, observed_digest="sha256:" + "c" * 64
    )
    assert "digest_mismatch" in _codes(verdict)


def test_a_fetched_artifact_of_the_wrong_size_is_refused() -> None:
    verdict = release.verify(_manifest(), POLICY, known_sequence=6, observed_size=999)
    assert "size_mismatch" in _codes(verdict)


def test_nothing_is_claimed_about_bytes_nobody_fetched() -> None:
    """Verifying a manifest before downloading is legitimate, and says so."""
    verdict = release.verify(_manifest(), POLICY, known_sequence=6)
    assert "digest_mismatch" not in _codes(verdict)
    assert "size_mismatch" not in _codes(verdict)


def test_a_platform_the_release_does_not_support_is_refused() -> None:
    verdict = release.verify(_manifest(), POLICY, known_sequence=6, platform="darwin/arm64")
    assert "platform_unsupported" in _codes(verdict)


# The pinned policy this build ships.
def test_the_shipped_policy_has_no_displaced_offline_release_key() -> None:
    policy = release.pinned_policy()
    assert policy.allowed_keys == frozenset()
    assert policy.public_keys == {}
    verdict = release.verify(_manifest(), policy, known_sequence=0)
    assert "key_unknown" in _codes(verdict)


def test_the_shipped_policy_names_the_publisher_and_repositories() -> None:
    policy = release.pinned_policy()
    assert policy.allowed_publishers == frozenset()
    assert policy.allowed_repositories == frozenset()
    assert "github.com/NDDev-OpenNetwork/claude-setup-system" in policy.build_attestations


def test_the_shipped_policy_marks_opennetwork_attested_builds_verified() -> None:
    """The overlay is the decision; Ed25519 `releases` stay empty."""
    policy = release.pinned_policy()
    opennetwork = {
        repository: rule
        for repository, rule in policy.build_attestations.items()
        if repository.startswith("github.com/NDDev-OpenNetwork/")
    }
    assert opennetwork
    assert all(rule.verified_publisher for rule in opennetwork.values())
    digest = "sha256:" + "e" * 64
    repository = next(iter(opennetwork))
    verdict = release.verify_attested(
        _manifest(
            repository=repository,
            artifact_digest=digest,
            signature="",
        ),
        policy,
        known_sequence=0,
        observed_digest=digest,
        observed_size=100,
        platform="linux/x86_64",
    )
    assert verdict.accepted


def test_the_shipped_policy_pins_one_exact_release_for_every_allowed_repository() -> None:
    """Shape, not a second copy of the digests.

    The digests live in `provider-policy.toml` and nowhere else. A test that
    repeated them would need editing on every release and would still prove
    only that somebody had typed the same string twice — which is exactly what
    the previous version of this test proved while the digests were reaching no
    decision at all.
    """
    policy = release.pinned_policy()
    pins = policy.pinned_releases
    assert {pin.repository for pin in pins} == policy.allowed_repositories
    assert len(pins) == len(policy.allowed_repositories)
    assert len({pin.artifact_digest for pin in pins}) == len(pins)
    assert all(is_digest(pin.artifact_digest) for pin in pins)
    assert all(pin.provider_id for pin in pins)


def test_a_release_outside_the_pinned_set_is_refused_however_well_it_is_signed() -> None:
    """The check a signature cannot make (`SPEC-008` REQ-811).

    Everything else about this release is correct: allowed publisher, allowed
    repository, allowed key, a signature that verifies over the canonical
    manifest, matching bytes, supported platform and a sequence above the floor.
    Only the approval is missing.
    """
    unpinned = _manifest(artifact_digest="sha256:" + "d" * 64, artifact_size=100)
    verdict = release.verify(
        unpinned,
        POLICY,
        known_sequence=6,
        observed_digest="sha256:" + "d" * 64,
        observed_size=100,
        platform="linux/x86_64",
    )
    assert not verdict.accepted
    assert _codes(verdict) == ("release_not_pinned",)
    assert release.verify(_manifest(), POLICY, known_sequence=6, platform="linux/x86_64").accepted


def test_pinned_bytes_are_refused_under_another_provider_identity() -> None:
    """This is what binding buys over a bare digest list.

    The bytes are approved. The claim about whose provider they are is not, and
    a manifest making that claim can be perfectly signed — the signature proves
    who wrote the claim, never that the claim is true.
    """
    # Both repositories are allowed, so nothing but the binding can refuse
    # these: a policy that also refused the repository would hide whether the
    # binding did any work.
    lenient = _policy(
        allowed_repositories=frozenset(
            {
                "github.com/NDDev-it-com/nddev-claude-app",
                "github.com/NDDev-it-com/nddev-codex-app",
            }
        )
    )
    for wrong in (
        _manifest(provider_id="codex"),
        _manifest(repository="github.com/NDDev-it-com/nddev-codex-app"),
    ):
        verdict = release.verify(wrong, lenient, known_sequence=6, platform="linux/x86_64")
        assert _codes(verdict) == ("release_not_pinned",)


def test_a_policy_that_pins_nothing_installs_nothing() -> None:
    """Empty refuses. An approved-bytes list that approves everything when left
    empty would be a control anybody could switch off by deleting lines."""
    empty: frozenset[release.PinnedRelease] = frozenset()
    verdict = release.verify(_manifest(), _policy(pinned_releases=empty), known_sequence=6)
    assert "release_not_pinned" in _codes(verdict)


@pytest.mark.parametrize("missing", sorted(release.POLICY_FIELDS))
def test_a_policy_missing_a_required_field_names_it(missing: str) -> None:
    text = "\n".join(
        line for line in VALID_POLICY_TEXT.splitlines() if not line.startswith(f"{missing} =")
    )
    with pytest.raises(CliFailure) as raised:
        release.load_policy(text)
    assert raised.value.details["field"] == missing


def test_a_policy_that_is_not_toml_is_refused() -> None:
    with pytest.raises(CliFailure) as raised:
        release.load_policy("this is not = = toml")
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_a_policy_field_in_the_wrong_shape_names_it() -> None:
    with pytest.raises(CliFailure) as raised:
        release.load_policy(VALID_POLICY_TEXT.replace("allowed_keys = []", 'allowed_keys = "one"'))
    assert raised.value.details["field"] == "allowed_keys"


@pytest.mark.parametrize(
    ("original", "replacement", "field"),
    [
        ("schema_version = 2", "schema_version = true", "schema_version"),
        ("minimum_sequence = 0", "minimum_sequence = -1", "minimum_sequence"),
        (
            'allowed_publishers = ["NDDev-it-com"]',
            "allowed_publishers = [1]",
            "allowed_publishers",
        ),
        ("supported_protocols = [1]", "supported_protocols = [true]", "supported_protocols"),
        ("releases = []", f"releases = [{{ {_PIN_FIELDS}, artifact_digest = 1 }}]", "releases"),
        (
            "releases = []",
            f'releases = [{{ {_PIN_FIELDS}, artifact_digest = "floating" }}]',
            "releases",
        ),
        ("releases = []", f'releases = [{{ artifact_digest = "{_DIGEST_A}" }}]', "releases"),
        (
            "releases = []",
            f'releases = [{{ provider_id = "", repository = "{_ALLOWED_REPOSITORY}",'
            f' artifact_digest = "{_DIGEST_A}" }}]',
            "releases",
        ),
        (
            "releases = []",
            f'releases = [{{ provider_id = "p", repository = "github.com/other/elsewhere",'
            f' artifact_digest = "{_DIGEST_A}" }}]',
            "releases",
        ),
    ],
)
def test_policy_scalars_lists_and_release_pins_are_strict(
    original: str,
    replacement: str,
    field: str,
) -> None:
    with pytest.raises(CliFailure) as raised:
        release.load_policy(VALID_POLICY_TEXT.replace(original, replacement))
    assert raised.value.details["field"] == field


def test_policy_unknown_fields_and_allowed_keys_without_material_are_refused() -> None:
    with pytest.raises(CliFailure) as unknown:
        release.load_policy(VALID_POLICY_TEXT + "future_trust = true\n")
    assert unknown.value.details["field"] == "unknown_fields"

    with pytest.raises(CliFailure) as missing_material:
        release.load_policy(VALID_POLICY_TEXT.replace("allowed_keys = []", 'allowed_keys = ["k"]'))
    assert missing_material.value.details["field"] == "public_keys"


def test_pinned_releases_are_closed_unique_and_exact() -> None:
    one = f'{{ {_PIN_FIELDS}, artifact_digest = "{_DIGEST_A}" }}'
    policy = release.load_policy(VALID_POLICY_TEXT.replace("releases = []", f"releases = [{one}]"))
    assert policy.pinned_releases == frozenset(
        {
            release.PinnedRelease(
                provider_id="nddev-claude-app",
                repository=_ALLOWED_REPOSITORY,
                artifact_digest=_DIGEST_A,
            )
        }
    )

    with pytest.raises(CliFailure) as repeated:
        release.load_policy(
            VALID_POLICY_TEXT.replace("releases = []", f"releases = [{one}, {one}]")
        )
    assert repeated.value.details["field"] == "releases"


def test_one_artifact_cannot_be_approved_under_two_identities() -> None:
    """The substitution the binding refuses, written into the policy itself.

    Two entries sharing bytes would make the pinned set say that one executable
    is legitimately two different providers, and no later check could tell which
    one a manifest meant.
    """
    twice = (
        f'{{ {_PIN_FIELDS}, artifact_digest = "{_DIGEST_A}" }},'
        f' {{ provider_id = "other", repository = "{_ALLOWED_REPOSITORY}",'
        f' artifact_digest = "{_DIGEST_A}" }}'
    )
    with pytest.raises(CliFailure) as shared:
        release.load_policy(VALID_POLICY_TEXT.replace("releases = []", f"releases = [{twice}]"))
    assert shared.value.details["field"] == "releases"


def test_the_refusal_registry_matches_the_contract() -> None:
    written = set(re.findall(r"^\| `([a-z_]+)` \|", CONTRACT.read_text("utf-8"), re.MULTILINE))
    assert written == release.REFUSALS


def test_the_trust_command_reports_the_policy_without_a_verdict(tmp_path: Path) -> None:
    """Absent is not `false`: nothing was checked."""
    from ai_stp_cli.commands import select

    view = select.provider_trust({}).payload
    assert view.policy_id == release.pinned_policy().policy_id
    assert view.accepted is None
    assert view.refusals == []
    assert view.allowed_keys == []


def test_the_trust_command_checks_a_named_manifest(tmp_path: Path) -> None:
    import json

    from ai_stp_cli.commands import select

    place = tmp_path / "release.json"
    place.write_text(
        json.dumps(
            {
                "provider_id": "claude-code",
                "provider_version": "1.0.0",
                "protocol_version": 1,
                "repository": "github.com/NDDev-it-com/nddev-claude-app",
                "commit": "a" * 40,
                "license": "MIT",
                "artifact_url": "https://example.test/releases/1.0.0/provider.tar.gz",
                "artifact_size": 100,
                "artifact_digest": "sha256:" + "b" * 64,
                "entry_point": "provider",
                "supported_os": ["linux"],
                "supported_arch": ["x86_64"],
                "sequence": 7,
                "policy_id": "nddev/provider/1",
                "publisher": "NDDev-it-com",
                "signing_key": "key-nobody-pinned",
                "signature_subject": "ai-stp:provider-release-manifest:v1",
                "signature": "not-a-real-signature",
            }
        ),
        encoding="utf-8",
    )
    view = select.provider_trust({"manifest": str(place)}).payload
    assert view.accepted is False
    assert "key_unknown" in {item.code for item in view.refusals}


def test_a_manifest_missing_a_field_names_it(tmp_path: Path) -> None:
    import json

    from ai_stp_cli.commands import select

    place = tmp_path / "partial.json"
    place.write_text(json.dumps({"provider_id": "claude-code"}), encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        select.provider_trust({"manifest": str(place)})
    assert "provider_version" in raised.value.details["missing"]


def test_a_manifest_that_is_not_json_is_refused(tmp_path: Path) -> None:
    from ai_stp_cli.commands import select

    place = tmp_path / "broken.json"
    place.write_text("not json at all", encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        select.provider_trust({"manifest": str(place)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


@pytest.mark.parametrize("document", [[], "manifest", 7, True, None])
def test_a_manifest_root_that_is_not_an_object_is_refused(document: object) -> None:
    with pytest.raises(CliFailure) as raised:
        release.parse_manifest(json.dumps(document))
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.details["field"] == "<root>"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_id", 7),
        ("protocol_version", True),
        ("artifact_size", "100"),
        ("artifact_size", -1),
        ("supported_os", "linux"),
        ("supported_arch", ["x86_64", 7]),
        ("supported_os", ["linux", "linux"]),
        ("sequence", -1),
    ],
)
def test_a_manifest_field_in_the_wrong_shape_is_refused(field: str, value: object) -> None:
    document = json.loads(release.serialize_manifest(_manifest()))
    assert isinstance(document, dict)
    document[field] = value

    with pytest.raises(CliFailure) as raised:
        release.parse_manifest(json.dumps(document))

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.details["field"] == field


def test_an_unknown_manifest_field_is_refused() -> None:
    document = json.loads(release.serialize_manifest(_manifest()))
    assert isinstance(document, dict)
    document["future_privilege"] = "allow"

    with pytest.raises(CliFailure) as raised:
        release.parse_manifest(json.dumps(document))

    assert raised.value.details["unknown"] == "future_privilege"


def test_a_duplicate_manifest_field_is_refused_before_signature_verification() -> None:
    canonical = release.serialize_manifest(_manifest())
    duplicated = canonical.replace('"provider_id":', '"provider_id":"other","provider_id":', 1)

    with pytest.raises(CliFailure) as raised:
        release.parse_manifest(duplicated)

    assert "duplicate JSON field: provider_id" in raised.value.details["detail"]


def test_a_canonical_manifest_round_trips_without_changing_identity() -> None:
    manifest = _manifest()
    parsed = release.parse_manifest(release.serialize_manifest(manifest))
    assert parsed == manifest
    assert release.manifest_identity(parsed) == release.manifest_identity(manifest)


def test_a_manifest_that_is_not_there_is_not_found(tmp_path: Path) -> None:
    from ai_stp_cli.commands import select

    with pytest.raises(CliFailure) as raised:
        select.provider_trust({"manifest": str(tmp_path / "absent.json")})
    assert raised.value.code == "AI_STP_NOT_FOUND"
