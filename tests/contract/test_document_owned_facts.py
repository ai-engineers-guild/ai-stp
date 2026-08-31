"""Documents that own a machine fact, and the code that must match them.

`AGENTS.md` gives every normative fact exactly one owner, and for several the
owner is a document rather than a model. That only means something if something
checks: two lists that agree today and are checked by nobody are two lists that
will disagree, and the document is what a reader trusts before the code exists
for them.

`cli-config.md` is held by `tests/contract/test_config_contract.py`. These are
the other two.
"""

import re
from pathlib import Path

from ai_stp_contracts.identity import DeviceSummary
from ai_stp_foundation.errors import ERROR_CODES, VALID_EXIT_CLASSES

CONTRACTS = Path(__file__).parents[2] / "docs" / "contracts"

#: The success code. It is in the document's table and is not an error class,
#: so it is excluded from the comparison rather than added to the registry.
SUCCESS = 0


def _documented_exit_codes() -> set[int]:
    text = (CONTRACTS / "cli-json.md").read_text(encoding="utf-8")
    section = text.split("## Exit codes", 1)[1].split("\n## ", 1)[0]
    return {int(found) for found in re.findall(r"^\|\s*(\d+)\s*\|", section, re.MULTILINE)}


def test_the_exit_classes_are_exactly_the_documented_ones() -> None:
    # A code the CLI can return that the document does not list would be an exit
    # status nobody agreed to, and callers match on these.
    assert _documented_exit_codes() - {SUCCESS} == set(VALID_EXIT_CLASSES)


def test_every_registered_error_maps_into_a_documented_class() -> None:
    documented = _documented_exit_codes()
    for code, entry in ERROR_CODES.items():
        assert entry.exit_class in documented, code


def test_the_document_lists_success_and_the_registry_does_not() -> None:
    # Success is not an error, so it belongs in the table and not in the closed
    # error registry. Stating it keeps the asymmetry deliberate.
    assert SUCCESS in _documented_exit_codes()
    assert SUCCESS not in VALID_EXIT_CLASSES


#: Which fields each bullet of `device-passport.md` carries, in the order the
#: document states them. One structure, not a set and a count: the comment here
#: said "five facts" above a six-member set while a second test asserted the
#: bullets numbered five, and both were green — the five counted bullets, the
#: six counted fields, and the bullet naming two was what reconciled them.
#:
#: The bullets are prose, so the pairing cannot be derived and has to be
#: written. What it must not be is written *twice*: adding a field now forces
#: the editor to say which bullet carries it, and the count follows.
DOCUMENTED_BULLETS: tuple[frozenset[str], ...] = (
    frozenset({"display_name"}),
    frozenset({"operating_system", "architecture"}),
    frozenset({"detected_harnesses"}),
    frozenset({"toolchain_profile_version"}),
    frozenset({"summary_updated_at"}),
)

DOCUMENTED_SUMMARY: frozenset[str] = frozenset(
    name for bullet in DOCUMENTED_BULLETS for name in bullet
)


def test_the_device_summary_carries_exactly_the_closed_list() -> None:
    # `SPEC-002` REQ-214: only the permitted summary leaves the device. A field
    # added to the model without the document would leave it too.
    declared = set(DeviceSummary.model_fields) - {"schema_version"}
    assert declared == DOCUMENTED_SUMMARY


def test_the_document_still_closes_the_summary_to_the_bullets_it_is_paired_with() -> None:
    # The list is prose, so it is read rather than parsed; what is checked is
    # that it is still closed and still as long as the pairing above claims.
    # The length comes from `DOCUMENTED_BULLETS` rather than a literal, so a
    # sixth bullet cannot be reconciled by editing one character.
    text = (CONTRACTS / "device-passport.md").read_text(encoding="utf-8")
    section = text.split("The permitted device summary has a closed field set:", 1)[1]
    bullets: list[str] = []
    for line in section.splitlines():
        if line.startswith("- "):
            bullets.append(line)
        elif bullets and line.strip() == "":
            break
    assert len(bullets) == len(DOCUMENTED_BULLETS)


def test_the_summary_can_hold_no_path_and_no_environment_value() -> None:
    # The document excludes them; the model must make them unrepresentable
    # rather than merely discouraged.
    forbidden = ("path", "env", "environment", "secret", "token", "home")
    for name in DeviceSummary.model_fields:
        assert not any(word in name.lower() for word in forbidden), name


# `DESIGN.md` names `apps/web/src/theme/tokens.json` as its own source of truth,
# so the two disagreeing is not a stale sentence — it is the document pointing
# at a file that says something else.
#
# It happened. Both design documents named Gerstner Programm and FT System Mono
# long after `globals.css` had replaced them with IBM Plex, and `DESIGN.md`
# carried a `last_verified` stamp from after the swap. The licence forced the
# change — the original faces forbid redistribution, which is what this
# repository does by being public — and the swap also fixed Cyrillic, which the
# replaced faces did not carry. None of that reached the documents.
#
# The family names are read from the tokens rather than restated here, for the
# reason the module docstring gives.
WEB_TOKENS = Path(__file__).parents[2] / "apps/web/src/theme/tokens.json"
PRODUCT = Path(__file__).parents[2] / "docs" / "product"


def _token_font_families() -> set[str]:
    import json

    families = json.loads(WEB_TOKENS.read_text(encoding="utf-8"))["font"]["family"]
    # The first entry is the face itself; the rest of each stack is fallback.
    return {stack["$value"][0] for stack in families.values()}


def test_the_design_documents_name_the_faces_the_tokens_load() -> None:
    expected = _token_font_families()
    for document in ("DESIGN.md", "BRAND.md"):
        text = (PRODUCT / document).read_text(encoding="utf-8")
        missing = sorted(face for face in expected if face not in text)
        assert not missing, (
            f"{document} does not name {missing}, which is what "
            "apps/web/src/theme/tokens.json actually loads; a reader trusting "
            "the design system would specify a face the product does not ship"
        )


def test_the_replaced_faces_are_only_mentioned_as_history() -> None:
    # Naming them is allowed and useful — the licence reason is worth keeping.
    # Naming them *as the current face* is the drift, so the check is that
    # neither document still presents one as a family to use.
    for document in ("DESIGN.md", "BRAND.md"):
        text = (PRODUCT / document).read_text(encoding="utf-8")
        for retired in ("gerstnerProgramm", "ftSystemMono"):
            assert retired not in text, (
                f"{document} still names {retired} as a font-family token; it "
                "was replaced in globals.css and no longer exists in the tree"
            )


# The safety pipeline decides what a check result can be; the publication wire
# only carries it. Writing both lists out separately made them drift, and the
# drift did not surface as a mismatch — it surfaced as `500 internal error` on
# `GET /v1/publications/plans/{id}`, because building the response over a
# binding the narrower list could not hold raised inside the handler. The plan
# could then be neither published nor diagnosed.
#
# One corpus component reached it, and only because it was the only one carrying
# a `package.json`: that makes `sca_npm_audit` applicable, and with no manifest
# at the tree root the adapter answers `not_applicable`.
def test_the_wire_can_carry_every_result_a_scan_can_produce() -> None:
    from ai_stp_contracts.publication import EvidenceBindingView
    from ai_stp_contracts.safety_checks import SafetyCheckEntry

    produced = set(SafetyCheckEntry.model_fields["result"].annotation.__value__.__args__)  # type: ignore[union-attr]

    for result in sorted(produced):
        EvidenceBindingView(check_id="sca_npm_audit", result=result, source="platform_safety_scan")


def test_the_wire_also_carries_the_one_state_no_scan_produces() -> None:
    # `expired` is a property of the evidence, not of a scan, so the wire list
    # is the scan vocabulary plus exactly this.
    from ai_stp_contracts.publication import EvidenceBindingView

    EvidenceBindingView(check_id="x", result="expired", source="platform_safety_scan")
