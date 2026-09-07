"""The mechanics every evidence slice shares, tested where they are owned.

Three slices prove different things and all four of these behaviours are the
same in each: a bare origin, an envelope, a typed refusal code, and a report that
cannot carry a credential. The last one is why this file exists at its own level
rather than once per slice — a guard copied three times is a guard that stops
matching in one of them, and the artefact it protects is meant to be pasted into
an issue.
"""

from pathlib import Path

import pytest
from release_scripts import _evidence
from release_scripts.verify_config_slice import (
    _scoped_harnesses,  # pyright: ignore[reportPrivateUsage]
    _surface,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.parametrize(
    "refused",
    [
        "http://nddev.asia",
        "https://nddev.asia/v1",
        "https://nddev.asia?query=1",
        "https://nddev.asia#fragment",
        "nddev.asia",
        "",
    ],
)
def test_only_a_bare_https_origin_is_accepted(refused: str) -> None:
    with pytest.raises(_evidence.EvidenceError):
        _evidence.origin(refused)


def test_a_trailing_slash_is_not_a_different_environment() -> None:
    assert _evidence.origin("https://nddev.asia/") == "https://nddev.asia"
    assert _evidence.origin("https://nddev.asia") == "https://nddev.asia"


def test_a_report_that_gained_a_credential_is_refused() -> None:
    clean: dict[str, object] = {"scenarios": {"fast_forward": {"state": "verified"}}}
    assert _evidence.without_credentials(clean) is clean

    for leak in ("Bearer abc", "refresh_token", "ACCESS_TOKEN", "Authorization"):
        with pytest.raises(_evidence.EvidenceError):
            _evidence.without_credentials({"note": leak})


def test_a_refusal_is_read_by_its_typed_code_rather_than_its_message() -> None:
    assert _evidence.error_code({"ok": False, "error": {"code": "AI_STP_CONFLICT"}}) == (
        "AI_STP_CONFLICT"
    )
    assert _evidence.error_code({"ok": True, "data": {}}) == ""
    assert _evidence.error_code({"ok": False, "error": {"message": "no code"}}) == ""


def test_an_envelope_without_data_is_not_evidence() -> None:
    assert _evidence.data({"data": {"state": "up_to_date"}}, "sync preview") == {
        "state": "up_to_date"
    }
    with pytest.raises(_evidence.EvidenceError):
        _evidence.data({"ok": True}, "sync preview")


def test_a_release_draft_patch_names_the_fields_release_requires() -> None:
    patch = _evidence.release_draft_patch(name="probe")
    assert tuple(patch) == _evidence.RELEASE_DRAFT_FIELDS
    for field in _evidence.RELEASE_DRAFT_FIELDS:
        assert patch[field]


def test_a_release_draft_patch_is_a_closed_component_passport_patch() -> None:
    from ai_stp_contracts.component_passport import ComponentPassportPatch

    ComponentPassportPatch.model_validate(_evidence.release_draft_patch(name="probe"))


def test_the_release_draft_update_names_the_current_revision() -> None:
    from pathlib import Path

    argv = _evidence.release_draft_update_arguments(
        "component_01TEST", "revision_01HEAD", Path("/tmp/patch.json")
    )
    assert argv[:3] == ["component", "passport", "update"]
    assert argv[argv.index("--expected-revision") + 1] == "revision_01HEAD"


def test_an_empty_leftover_directory_is_not_the_contributed_component(tmp_path: Path) -> None:
    """0.0.66 remove deletes recorded files, not the namespace they sat in.

    The slice treated any path whose *name* contained `mcp01` as the component
    still being there, so an empty leftover `extensions/mcp01` after a verified
    pi remove failed the row.
    """
    leftover = tmp_path / "extensions" / "mcp01"
    leftover.mkdir(parents=True)
    assert not _evidence.contribution_probe_present(tmp_path, "extensions")
    (leftover / "package.json").write_text("{}\n", encoding="utf-8")
    assert _evidence.contribution_probe_present(tmp_path, "extensions")


def test_a_host_file_holds_the_key_by_its_bytes(tmp_path: Path) -> None:
    host = tmp_path / "config.toml"
    host.write_text('# kept by the person\nmodel = "sibling"\n', encoding="utf-8")
    assert not _evidence.contribution_probe_present(tmp_path, "config.toml")
    host.write_text('[mcp_servers.mcp01]\ncommand = "mcp01-server"\n', encoding="utf-8")
    assert _evidence.contribution_probe_present(tmp_path, "config.toml")


@pytest.mark.parametrize("harness_id", _scoped_harnesses("project"))
def test_every_project_profile_has_a_discoverable_evidence_seed(
    tmp_path: Path, harness_id: str
) -> None:
    """Shared AGENTS.md is a Codex project route without being Codex-owned."""
    from ai_stp_cli.local import components, composition

    seeded, kind, relative, portable = _surface(harness_id, tmp_path, scope="project")
    discovered = components.discover(project=tmp_path / "seed", include_global=False)

    assert any(item.absolute == seeded and item.component_type == kind for item in discovered), (
        harness_id,
        seeded,
    )
    assert any(
        item.absolute == seeded
        and item.component_type == kind
        and item.harness_id == ("" if portable else harness_id)
        for item in discovered
    )
    route = composition.rule_for(kind, harness_id, scope="project")
    assert route is not None and route.relative == relative
