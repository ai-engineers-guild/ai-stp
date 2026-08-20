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
    section = text.split("## Коды завершения", 1)[1].split("\n## ", 1)[0]
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


#: The five facts `device-passport.md` closes the published summary to, in the
#: order the document states them, mapped to the fields that carry them.
DOCUMENTED_SUMMARY = {
    "display_name",
    "operating_system",
    "architecture",
    "detected_harnesses",
    "toolchain_profile_version",
    "summary_updated_at",
}


def test_the_device_summary_carries_exactly_the_closed_list() -> None:
    # `SPEC-002` REQ-214: only the permitted summary leaves the device. A field
    # added to the model without the document would leave it too.
    declared = set(DeviceSummary.model_fields) - {"schema_version"}
    assert declared == DOCUMENTED_SUMMARY


def test_the_document_still_closes_the_summary_to_five_facts() -> None:
    # The list is prose, so it is read rather than parsed; what is checked is
    # that it is still a closed list of five bullets, because the model above is
    # written against exactly that.
    text = (CONTRACTS / "device-passport.md").read_text(encoding="utf-8")
    section = text.split("Разрешённая сводка устройства закрыта по составу:", 1)[1]
    bullets: list[str] = []
    for line in section.splitlines():
        if line.startswith("- "):
            bullets.append(line)
        elif bullets and line.strip() == "":
            break
    assert len(bullets) == 5


def test_the_summary_can_hold_no_path_and_no_environment_value() -> None:
    # The document excludes them; the model must make them unrepresentable
    # rather than merely discouraged.
    forbidden = ("path", "env", "environment", "secret", "token", "home")
    for name in DeviceSummary.model_fields:
        assert not any(word in name.lower() for word in forbidden), name
