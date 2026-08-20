"""Local-first SX/APM setup-store ports (SPEC-042)."""

from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import store_ports
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_cli.local.revisions import head


def _sx(root: Path, *, version: int = 2, extra: str = "") -> None:
    (root / "sx.toml").write_text(
        f"""schema_version = {version}
created_by = "sx-test"
future_field = "preserved-in-report"
{extra}
[[assets]]
name = "review"
version = "1.2.3"
type = "skill"
clients = ["codex"]
[assets.source-path]
path = ".sx/versions/review/1.2.3"

[[assets]]
name = "desktop-only"
version = "2.0.0"
type = "future-extension"
[assets.source-path]
path = ".sx/versions/desktop-only/2.0.0"

[[collections]]
name = "quality"
assets = ["review"]
""",
        encoding="utf-8",
    )


def _apm(root: Path) -> None:
    (root / "apm.lock.yaml").write_text(
        """lockfile_version: '2'
apm_version: 0.26.0
future_top: visible
dependencies:
  - repo_url: github.com/acme/review
    name: review
    version: 1.4.0
    package_type: apm_package
    deployed_files:
      - .agents/skills/review
      - .agents/skills/review/SKILL.md
      - .github/prompts/explain.prompt.md
    deployed_file_hashes:
      .agents/skills/review/SKILL.md: >-
        sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    future_dependency_field: visible
""",
        encoding="utf-8",
    )


def test_discovery_and_inspection_are_read_only_and_report_unknowns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sx(tmp_path)

    def absent(_name: str) -> None:
        return None

    monkeypatch.setattr("ai_stp_cli.local.store_ports.shutil.which", absent)
    before = (tmp_path / "sx.toml").read_bytes()

    discovery = store_ports.discover(tmp_path)
    report = store_ports.inspect(tmp_path, "sx")

    assert [item.adapter for item in discovery.stores] == ["sx"]
    assert report.descriptor.contract_version == "2"
    assert report.descriptor.cli_status == "absent"
    assert "$.future_field" in report.unknown_fields
    assert [(item.external_id, item.state, item.component_type) for item in report.mappings] == [
        ("review", "omitted", "skill"),
        ("desktop-only", "omitted", None),
        ("collection:quality", "omitted", None),
    ]
    assert report.mappings[0].local_content_digest is None
    assert (tmp_path / "sx.toml").read_bytes() == before
    assert not configured_path().exists()


def test_sx_import_is_exact_local_only_and_idempotent(tmp_path: Path) -> None:
    skill = tmp_path / ".sx" / "versions" / "review" / "1.2.3"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    unknown = tmp_path / ".sx" / "versions" / "desktop-only" / "2.0.0"
    unknown.mkdir(parents=True)
    (unknown / "plugin.json").write_text("{}\n", encoding="utf-8")
    _sx(tmp_path)
    source_files = [tmp_path / "sx.toml", *list((tmp_path / ".sx").rglob("*"))]
    source_before = {path: path.read_bytes() for path in source_files if path.is_file()}
    planned = store_ports.plan(tmp_path, "sx")
    planned_mapping = next(
        item for item in planned.inspection.mappings if item.state == "component"
    )
    assert planned_mapping.local_content_digest is not None

    with closing(open_registry(configured_path(), create=True)) as connection:
        with transaction(connection):
            first = store_ports.apply(
                connection, tmp_path, "sx", planned.plan_digest, device_id="device_test"
            )
        with transaction(connection):
            second = store_ports.apply(
                connection, tmp_path, "sx", planned.plan_digest, device_id="device_test"
            )
        assert (
            connection.execute("SELECT count(*) FROM entity WHERE kind = 'component'").fetchone()[0]
            == 1
        )
        stored = head(connection, first.imported[0].stable_id)
        assert stored is not None
        passport = stored.envelope.model_dump(mode="json")

    assert [item.state for item in first.imported] == ["imported"]
    assert [item.state for item in second.imported] == ["already_imported"]
    assert first.imported[0].stable_id == second.imported[0].stable_id
    assert first.external_store_changed is False
    assert first.harness_target_changed is False
    assert passport["visibility"] == "private"
    assert passport["facts"]["source_package_name"]["origin"] == "observed"
    assert "author_verified" not in passport
    assert "component_verified" not in passport
    assert {path: path.read_bytes() for path in source_files if path.is_file()} == source_before


def test_changed_snapshot_refuses_stale_plan(tmp_path: Path) -> None:
    skill = tmp_path / ".sx" / "versions" / "review" / "1.2.3"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    unknown = tmp_path / ".sx" / "versions" / "desktop-only" / "2.0.0"
    unknown.mkdir(parents=True)
    (unknown / "plugin.json").write_text("{}\n", encoding="utf-8")
    _sx(tmp_path)
    planned = store_ports.plan(tmp_path, "sx")
    _sx(tmp_path, extra='note = "changed"')

    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        pytest.raises(CliFailure, match="no longer matches") as caught,
        transaction(connection),
    ):
        store_ports.apply(connection, tmp_path, "sx", planned.plan_digest, device_id="device_test")
    assert caught.value.code == "AI_STP_PRECONDITION_FAILED"


def test_changed_component_bytes_refuse_an_otherwise_current_plan(tmp_path: Path) -> None:
    skill = tmp_path / ".sx" / "versions" / "review" / "1.2.3"
    skill.mkdir(parents=True)
    source = skill / "SKILL.md"
    source.write_text("# Review\n", encoding="utf-8")
    unknown = tmp_path / ".sx" / "versions" / "desktop-only" / "2.0.0"
    unknown.mkdir(parents=True)
    (unknown / "plugin.json").write_text("{}\n", encoding="utf-8")
    _sx(tmp_path)
    planned = store_ports.plan(tmp_path, "sx")
    source.write_text("# Changed\n", encoding="utf-8")

    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        pytest.raises(CliFailure, match="snapshot no longer matches") as caught,
        transaction(connection),
    ):
        store_ports.apply(connection, tmp_path, "sx", planned.plan_digest, device_id="device_test")

    assert caught.value.code == "AI_STP_PRECONDITION_FAILED"


def test_local_source_path_cannot_escape_or_traverse_a_link(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-store-component"
    outside.mkdir(exist_ok=True)
    (outside / "SKILL.md").write_text("# Outside\n", encoding="utf-8")
    linked = tmp_path / ".sx" / "versions" / "review"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(outside, target_is_directory=True)
    _sx(tmp_path)
    planned = store_ports.plan(tmp_path, "sx")

    review = next(item for item in planned.inspection.mappings if item.external_id == "review")
    assert review.state == "omitted"
    assert review.local_content_digest is None
    assert review.omissions == ["a setup-store component path cannot traverse a link"]
    assert planned.importable_count == 0


def test_apm_maps_exact_deployed_component_boundaries(tmp_path: Path) -> None:
    skill = tmp_path / ".agents" / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    prompt = tmp_path / ".github" / "prompts" / "explain.prompt.md"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("Explain.\n", encoding="utf-8")
    _apm(tmp_path)

    report = store_ports.inspect(tmp_path, "apm")

    assert report.descriptor.contract_version == "2"
    assert "$.future_top" in report.unknown_fields
    assert "$.dependencies[0].future_dependency_field" in report.unknown_fields
    assert [(item.component_type, item.local_path) for item in report.mappings] == [
        ("command", ".github/prompts/explain.prompt.md"),
        ("skill", ".agents/skills/review"),
    ]


@pytest.mark.parametrize(
    ("adapter", "filename", "payload"),
    [
        ("sx", "sx.toml", "schema_version = 99\n"),
        ("apm", "apm.lock.yaml", "lockfile_version: '99'\ndependencies: []\n"),
    ],
)
def test_incompatible_contract_versions_fail_closed(
    tmp_path: Path, adapter: str, filename: str, payload: str
) -> None:
    (tmp_path / filename).write_text(payload, encoding="utf-8")

    with pytest.raises(CliFailure) as caught:
        store_ports.inspect(tmp_path, adapter)

    assert caught.value.code == "AI_STP_SCHEMA_UNSUPPORTED"


def test_apm_duplicate_yaml_key_is_rejected_without_retry_or_guessing(tmp_path: Path) -> None:
    (tmp_path / "apm.lock.yaml").write_text(
        "lockfile_version: '1'\nlockfile_version: '2'\ndependencies: []\n", encoding="utf-8"
    )

    with pytest.raises(CliFailure) as caught:
        store_ports.inspect(tmp_path, "apm")

    assert caught.value.code == "AI_STP_VALIDATION_ERROR"
