"""Exact, bounded provenance for globally installed native packages."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_stp_cli.local import component_sources, components
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import NativeComponentProvenance


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _claude_install(
    root: Path,
    *,
    plugin: str = "reviewer",
    marketplace: str = "acme",
    source: object = "./plugins/reviewer",
    revision: str = "1" * 40,
    scope: str = "user",
) -> Path:
    plugin_root = root / "plugins"
    cache = plugin_root / "cache" / marketplace / plugin / "1.2.3"
    (cache / ".claude-plugin").mkdir(parents=True)
    _write(cache / ".claude-plugin" / "plugin.json", {"name": plugin, "version": "1.2.3"})
    _write(
        plugin_root / "known_marketplaces.json",
        {
            marketplace: {
                "source": {"source": "github", "repo": "acme/tools"},
                # Deliberately untrusted and wrong. The adapter reconstructs
                # the documented location instead of following this value.
                "installLocation": "/tmp/not-the-marketplace",
            }
        },
    )
    _write(
        plugin_root / "marketplaces" / marketplace / ".claude-plugin" / "marketplace.json",
        {"name": marketplace, "plugins": [{"name": plugin, "source": source}]},
    )
    _write(
        plugin_root / "installed_plugins.json",
        {
            "version": 2,
            "plugins": {
                f"{plugin}@{marketplace}": [
                    {
                        "scope": scope,
                        "installPath": str(cache),
                        "gitCommitSha": revision,
                        "version": "1.2.3",
                    }
                ]
            },
        },
    )
    return cache


def _pi_checkout(root: Path, *, revision: str = "3" * 40, packed: bool = False) -> Path:
    checkout = root / "git" / "github.com" / "acme" / "pi-tools"
    git = checkout / ".git"
    git.mkdir(parents=True)
    (checkout / "package.json").write_text('{"name":"pi-tools"}\n', encoding="utf-8")
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    if packed:
        (git / "packed-refs").write_text(f"{revision} refs/heads/main\n", encoding="utf-8")
    else:
        ref = git / "refs" / "heads" / "main"
        ref.parent.mkdir(parents=True)
        ref.write_text(f"{revision}\n", encoding="utf-8")
    return checkout


def test_relative_marketplace_plugin_has_exact_github_provenance(tmp_path: Path) -> None:
    root = tmp_path / ".claude"
    cache = _claude_install(root)

    result = component_sources.claude_plugins(root)

    assert result.diagnostics == ()
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.absolute == cache
    assert candidate.kind == "github"
    assert candidate.state == "exact"
    assert candidate.repository == "https://github.com/acme/tools"
    assert candidate.revision == "1" * 40
    assert candidate.subpath == "plugins/reviewer"
    assert candidate.package_name == "reviewer@acme"
    assert candidate.package_version == "1.2.3"


def test_remote_plugin_pin_wins_and_credentialed_url_is_never_reported(tmp_path: Path) -> None:
    root = tmp_path / ".claude"
    pinned = "2" * 40
    _claude_install(
        root,
        source={
            "source": "git-subdir",
            "url": "https://github.com/other/monorepo.git",
            "path": "plugins/reviewer",
            "sha": pinned,
        },
    )
    result = component_sources.claude_plugins(root)
    assert result.candidates[0].repository == "https://github.com/other/monorepo"
    assert result.candidates[0].revision == pinned
    assert result.candidates[0].subpath == "plugins/reviewer"

    _write(
        root / "plugins" / "marketplaces" / "acme" / ".claude-plugin" / "marketplace.json",
        {
            "name": "acme",
            "plugins": [
                {
                    "name": "reviewer",
                    "source": {
                        "source": "url",
                        "url": "https://token@github.com/other/private.git",
                    },
                }
            ],
        },
    )
    rejected = component_sources.claude_plugins(root)
    assert rejected.candidates[0].kind == "package"
    assert rejected.candidates[0].state == "observed"
    assert rejected.candidates[0].repository is None
    assert "token" not in str(rejected)


def test_non_git_package_remains_visible_without_an_exact_source_claim(tmp_path: Path) -> None:
    root = tmp_path / ".claude"
    _claude_install(
        root,
        source={"source": "npm", "package": "@acme/reviewer", "version": "1.2.3"},
    )
    ledger = root / "plugins" / "installed_plugins.json"
    value = json.loads(ledger.read_text(encoding="utf-8"))
    del value["plugins"]["reviewer@acme"][0]["gitCommitSha"]
    _write(ledger, value)

    result = component_sources.claude_plugins(root)
    assert len(result.candidates) == 1
    assert result.candidates[0].kind == "package"
    assert result.candidates[0].state == "observed"
    assert result.candidates[0].repository is None
    assert result.candidates[0].revision is None


def test_missing_marketplace_metadata_keeps_observed_install_visible(tmp_path: Path) -> None:
    root = tmp_path / ".claude"
    _claude_install(root)
    (root / "plugins" / "known_marketplaces.json").unlink()
    (root / "plugins" / "marketplaces" / "acme" / ".claude-plugin" / "marketplace.json").unlink()

    result = component_sources.claude_plugins(root)

    assert len(result.candidates) == 1
    assert result.candidates[0].kind == "package"
    assert result.candidates[0].state == "observed"
    assert [item.code for item in result.diagnostics].count("missing_manifest") == 2
    assert result.candidates[0].evidence == ("claude:installed_plugins:v2",)


def test_source_manifest_symlink_outside_plugin_root_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / ".claude"
    _claude_install(root)
    known = root / "plugins" / "known_marketplaces.json"
    known.unlink()
    outside = tmp_path / "outside.json"
    _write(outside, {"acme": {"source": {"source": "github", "repo": "evil/repo"}}})
    known.symlink_to(outside)

    result = component_sources.claude_plugins(root)

    assert len(result.candidates) == 1
    assert result.candidates[0].kind == "package"
    assert result.candidates[0].repository is None
    assert any(item.code == "invalid_manifest" for item in result.diagnostics)
    assert str(outside) not in str(result.diagnostics)


@pytest.mark.parametrize("packed", [False, True])
def test_pi_git_cache_reports_exact_github_checkout(tmp_path: Path, packed: bool) -> None:
    root = tmp_path / ".pi" / "agent"
    checkout = _pi_checkout(root, packed=packed)

    result = component_sources.pi_git_packages(root)

    assert result.diagnostics == ()
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.absolute == checkout
    assert candidate.kind == "github"
    assert candidate.state == "exact"
    assert candidate.repository == "https://github.com/acme/pi-tools"
    assert candidate.revision == "3" * 40
    assert candidate.package_name == "git:github.com/acme/pi-tools"
    assert candidate.evidence == ("pi:git-cache-layout", "git:checked-out-head")


def test_pi_git_cache_rejects_unsafe_or_inexact_checkout(tmp_path: Path) -> None:
    root = tmp_path / ".pi" / "agent"
    checkout = _pi_checkout(root)
    (checkout / ".git" / "refs" / "heads" / "main").write_text("main\n", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    linked = root / "git" / "github.com" / "acme" / "linked"
    linked.symlink_to(external, target_is_directory=True)

    result = component_sources.pi_git_packages(root)

    assert result.candidates == ()
    assert len(result.diagnostics) == 2
    assert all(item.code == "invalid_record" for item in result.diagnostics)
    assert str(checkout) not in str(result.diagnostics)


def test_pi_git_cache_does_not_claim_non_github_host(tmp_path: Path) -> None:
    root = tmp_path / ".pi" / "agent"
    checkout = root / "git" / "gitlab.example" / "acme" / "tools" / ".git"
    checkout.mkdir(parents=True)
    (checkout / "HEAD").write_text("4" * 40, encoding="utf-8")

    result = component_sources.pi_git_packages(root)

    assert result == component_sources.Result((), ())


def test_pi_git_cache_rejects_ref_traversal_and_entry_overflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".pi" / "agent"
    checkout = _pi_checkout(root)
    (checkout / ".git" / "HEAD").write_text("ref: refs/heads/../../outside\n", encoding="utf-8")
    traversal = component_sources.pi_git_packages(root)
    assert traversal.candidates == ()
    assert traversal.diagnostics[0].code == "invalid_record"

    (root / "git" / "gitlab.example").mkdir()
    monkeypatch.setattr(component_sources, "MAX_SOURCE_ENTRIES", 1)
    overflow = component_sources.pi_git_packages(root)
    assert overflow.candidates == ()
    assert overflow.diagnostics[0].code == "invalid_manifest"


def test_project_scope_and_paths_outside_cache_are_not_global_components(tmp_path: Path) -> None:
    root = tmp_path / ".claude"
    _claude_install(root, scope="project")
    assert component_sources.claude_plugins(root).candidates == ()

    outside = tmp_path / "outside"
    outside.mkdir()
    ledger = root / "plugins" / "installed_plugins.json"
    value = json.loads(ledger.read_text(encoding="utf-8"))
    value["plugins"]["reviewer@acme"][0]["scope"] = "user"
    value["plugins"]["reviewer@acme"][0]["installPath"] = str(outside)
    _write(ledger, value)

    result = component_sources.claude_plugins(root)
    assert result.candidates == ()
    assert any(item.code == "invalid_record" for item in result.diagnostics)
    assert str(outside) not in str(result.diagnostics)


@pytest.mark.parametrize(
    ("installed", "code"),
    [
        ("not json", "invalid_manifest"),
        (json.dumps({"version": 99, "plugins": {}}), "unsupported_manifest"),
    ],
)
def test_malformed_or_unknown_ledgers_fail_closed_with_safe_diagnostics(
    tmp_path: Path, installed: str, code: str
) -> None:
    root = tmp_path / ".claude"
    path = root / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True)
    path.write_text(installed, encoding="utf-8")
    _write(root / "plugins" / "known_marketplaces.json", {})

    result = component_sources.claude_plugins(root)
    assert result.candidates == ()
    assert any(item.code == code for item in result.diagnostics)
    assert installed not in str(result.diagnostics)


def test_oversized_manifest_is_not_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / ".claude"
    path = root / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"secret":"do-not-reflect"}', encoding="utf-8")
    monkeypatch.setattr(component_sources, "MAX_MANIFEST_BYTES", 4)

    result = component_sources.claude_plugins(root)
    assert result.candidates == ()
    assert result.diagnostics[0].code == "invalid_manifest"
    assert "do-not-reflect" not in str(result.diagnostics)


def test_component_discovery_exposes_exact_provenance_and_adoption_preserves_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: sqlite3.Connection
) -> None:
    home = tmp_path / "home"
    cache = _claude_install(home / ".claude")
    # These are implementation buckets, not plugins. The structured ledger is
    # the authority and the old generic directory rule must not report them.
    (home / ".claude" / "plugins" / "data").mkdir()
    monkeypatch.setenv("HOME", str(home))

    first = components.discover_report()
    second = components.discover_report()
    found = [item for item in first.components if item.component_type == "plugin"]
    assert len(found) == 1
    plugin = found[0]
    assert plugin.absolute == cache
    assert plugin.provenance.kind == "github"
    assert plugin.provenance.state == "exact"
    assert plugin.provenance.repository == "https://github.com/acme/tools"
    assert plugin.candidate_id == next(
        item.candidate_id for item in second.components if item.component_type == "plugin"
    )
    assert not any(item.source_path.endswith("/plugins/data") for item in first.components)

    stored = components.adopt(registry, plugin, device_id="device_test")
    facts = stored.envelope.model_dump(mode="json")["facts"]
    assert facts["source_repository"]["value"] == "https://github.com/acme/tools"
    assert facts["source_revision"]["value"] == "1" * 40
    assert facts["source_subpath"]["value"] == "plugins/reviewer"


def test_component_discovery_adopts_pi_git_package_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: sqlite3.Connection
) -> None:
    home = tmp_path / "home"
    checkout = _pi_checkout(home / ".pi" / "agent")
    monkeypatch.setenv("HOME", str(home))

    report = components.discover_report()
    package = next(item for item in report.components if item.absolute == checkout)

    assert package.harness_id == "pi"
    assert package.component_type == "plugin"
    assert package.provenance.repository == "https://github.com/acme/pi-tools"
    assert package.provenance.revision == "3" * 40
    stored = components.adopt(registry, package, device_id="device_test")
    facts = stored.envelope.model_dump(mode="json")["facts"]
    assert facts["source_repository"]["value"] == "https://github.com/acme/pi-tools"
    assert facts["source_revision"]["value"] == "3" * 40
    assert facts["source_package_name"]["value"] == "git:github.com/acme/pi-tools"


def test_machine_command_reports_provenance_and_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.commands import component as command

    home = tmp_path / "home"
    _claude_install(home / ".claude")
    monkeypatch.setenv("HOME", str(home))

    payload = command.discover({}).payload
    plugin = next(item for item in payload.components if item.component_type == "plugin")
    assert plugin.provenance.kind == "github"
    assert plugin.provenance.state == "exact"
    assert plugin.provenance.revision == "1" * 40
    assert payload.diagnostics == []


def test_machine_provenance_rejects_inconsistent_or_floating_claims() -> None:
    observed = NativeComponentProvenance(
        kind="package", state="observed", package_name="reviewer@acme"
    )
    assert observed.repository is None
    with pytest.raises(ValidationError):
        NativeComponentProvenance(kind="github", state="exact")
    with pytest.raises(ValidationError):
        NativeComponentProvenance(
            kind="github",
            state="exact",
            repository="https://github.com/acme/tools",
            revision="main",
        )
    with pytest.raises(ValidationError):
        NativeComponentProvenance(
            kind="filesystem",
            state="local",
            repository="https://github.com/acme/tools",
        )
    with pytest.raises(ValidationError):
        NativeComponentProvenance(
            kind="package",
            state="observed",
            package_name="reviewer@acme",
            repository="https://github.com/acme/tools",
        )
