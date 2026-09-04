"""Safe deterministic component authoring templates (SPEC-005 and SPEC-041)."""

import json
import os
from pathlib import Path

import pytest

from ai_stp_cli.commands import component
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import authoring
from ai_stp_contracts.authoring import (
    ComponentScaffoldFile,
    ComponentScaffoldPlan,
    ComponentTemplateDescriptor,
)
from ai_stp_contracts.component_passport import ComponentPassportPatch
from ai_stp_contracts.evaluation import SetupEvalProfile
from ai_stp_foundation.canonical import from_json_bytes
from ai_stp_foundation.digests import digest_bytes

SCAFFOLD_GOLDEN = Path(__file__).parents[1] / "golden" / "cli" / "component-scaffold-v3.json"
HISTORICAL_V2_GOLDEN = Path(__file__).parents[1] / "golden" / "cli" / "component-scaffold-v2.json"

#: Kinds a harness has no projection for, so scaffolding one is refused rather
#: than producing a component nothing could install.
#:
#: `claude-code/hook` left on 2026-08-31 and `opencode` kept its own: hooks for
#: claude-code are the `hooks` key inside the owned `settings.json`, which
#: `ADR-0129` compiles as a contribution to that file. Opencode's hook has no
#: owned host of that shape, so its refusal stands for its own reason rather
#: than by sharing a row.
UNSUPPORTED_NATIVE_KINDS = {
    "codex": {"plugin"},
    "pi": {"hook", "agent"},
    "opencode": {"hook"},
    "grok-build": {"command"},
    "cursor": {"agent"},
}


@pytest.mark.parametrize("component_type", sorted(authoring.TYPES))
def test_scaffold_supports_each_closed_component_type(component_type: str) -> None:
    content = authoring.scaffold(component_type, "review-kit")

    assert f"Component type: `{component_type}`." in content
    assert "{{component_root}}" in content


@pytest.mark.parametrize("harness_id", sorted(authoring.HARNESSES))
def test_scaffold_renders_one_deterministic_harness_projection(harness_id: str) -> None:
    source = authoring.scaffold("skill", "review-kit")

    first = authoring.render(
        source,
        harness_id=harness_id,
        component_name="review-kit",
        component_root="skills/review-kit",
    )
    second = authoring.render(
        source,
        harness_id=harness_id,
        component_name="review-kit",
        component_root="skills/review-kit",
    )

    assert first == second
    assert "skills/review-kit" in first.content
    assert harness_id in first.content
    assert "{{" not in first.content
    #: The third set is derived, not listed. It used to be the literal
    #: `{"pi", "opencode", "grok-build"}`, which was the whole beta-and-other
    #: set when there were five harnesses. `cursor` and `antigravity` joined
    #: the enum and fell out of every branch: the template rendered for them
    #: with no guidance line at all, and this assertion stayed green because it
    #: only ever asked about three names it already knew.
    guidance = {
        "Claude Code-specific guidance.": {"claude-code"},
        "Codex-specific guidance.": {"codex"},
        "Portable harness guidance.": set(authoring.HARNESSES) - {"claude-code", "codex"},
    }
    for line, harnesses in guidance.items():
        assert (line in first.content) is (harness_id in harnesses), (
            f"{harness_id} renders the wrong guidance for {line!r}"
        )


def test_fenced_tags_are_literal_and_do_not_open_conditionals() -> None:
    source = """Before {{component_name}}.
```text
{{unknown}}
{{#harness:not-real}}
{{/harness}}
```
After.
"""

    rendered = authoring.render(
        source, harness_id="codex", component_name="sample", component_root="skills/sample"
    )

    assert "Before sample." in rendered.content
    assert "{{unknown}}" in rendered.content
    assert "{{#harness:not-real}}" in rendered.content


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("{{unknown}}\n", "unknown authoring tag"),
        ("{{#harness:nope}}\nx\n{{/harness}}\n", "unknown or duplicate"),
        ("{{#harness:codex,codex}}\nx\n{{/harness}}\n", "unknown or duplicate"),
        ("{{#harness:codex}}\n{{#harness:pi}}\n", "nested"),
        ("{{/harness}}\n", "without an opener"),
        ("{{#harness:codex}}\n", "unclosed harness conditional"),
        ("```\n", "unclosed fenced code block"),
    ],
)
def test_renderer_fails_closed_on_malformed_syntax(source: str, message: str) -> None:
    with pytest.raises(CliFailure, match=message):
        authoring.render(
            source, harness_id="codex", component_name="sample", component_root="skills/sample"
        )


@pytest.mark.parametrize(
    "value", ["", "/skills/sample", "../sample", "skills/../sample", r"skills\sample", "~/.x"]
)
def test_renderer_rejects_unsafe_component_roots(value: str) -> None:
    with pytest.raises(CliFailure, match="relative POSIX path"):
        authoring.render(
            "{{component_root}}\n",
            harness_id="codex",
            component_name="sample",
            component_root=value,
        )


def test_template_reader_refuses_links_and_oversize_files(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("safe\n", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(target)
    with pytest.raises(CliFailure, match="opened safely"):
        authoring.read_template(link)

    large = tmp_path / "large.md"
    large.write_bytes(b"x" * (authoring.MAX_TEMPLATE_BYTES + 1))
    with pytest.raises(CliFailure, match="at most 64 KiB"):
        authoring.read_template(large)


@pytest.mark.parametrize(
    ("component_type", "language"),
    [
        (component_type, language)
        for component_type, languages in authoring.TYPE_LANGUAGE_MATRIX.items()
        for language in languages
    ],
)
@pytest.mark.parametrize("harness", authoring.VARIANTS)
def test_scaffold_matrix_produces_valid_exact_artifacts(
    tmp_path: Path, component_type: str, language: str, harness: str
) -> None:
    unsupported = component_type in UNSUPPORTED_NATIVE_KINDS.get(harness, set()) or (
        component_type == "plugin"
        and harness in {"opencode", "pi"}
        and language not in {"javascript", "typescript"}
    )
    if unsupported:
        with pytest.raises(CliFailure, match=r"cannot be projected|JavaScript or TypeScript"):
            authoring.scaffold_plan(
                component_type=component_type,
                name="review-kit",
                language=language,
                harness_variant=harness,
                output=tmp_path / "review-kit",
            )
        return
    plan, files = authoring.scaffold_plan(
        component_type=component_type,
        name="review-kit",
        language=language,
        harness_variant=harness,
        output=tmp_path / "review-kit",
    )

    assert plan.descriptor.component_type == component_type
    assert plan.descriptor.language == language
    assert plan.descriptor.harness_variant == harness
    assert {item.path for item in plan.files} == set(files)
    assert all(
        item.digest == digest_bytes("ai-stp:artifact:v1", files[item.path])
        and item.byte_length == len(files[item.path])
        and item.mode == 0o600
        for item in plan.files
    )
    assert plan.publication_ready is False
    assert plan.requires_exact_source_before_publication is True
    assert plan.descriptor.template_version == "component-scaffold/4"
    assert plan.descriptor.generator_version == "ai-stp/4"
    assert any(path.startswith("projections/") for path in files) is (harness != "portable")
    assert all(not path.startswith("native/") for path in files)
    assert ".ai-stp-template.json" in files
    assert any(path.startswith("source/") for path in files)
    assert not any(path.startswith("adaptations/") for path in files)
    assert "SAFETY.md" not in files
    assert "PUBLICATION.md" not in files
    ComponentPassportPatch.model_validate(from_json_bytes(files["component-passport.json"]))
    profile = SetupEvalProfile.model_validate(from_json_bytes(files["eval-profile.json"]))
    assert profile.component_types == [component_type]
    assert any(check.method == "deterministic" for check in profile.checks)
    assert any(check.method == "model_assisted" for check in profile.checks)


@pytest.mark.parametrize(
    ("component_type", "language"),
    [
        ("skill", "python"),
        ("agent", "go"),
        ("command", "python"),
        ("mcp", "none"),
        ("hook", "go"),
        ("plugin", "none"),
    ],
)
def test_scaffold_matrix_rejects_meaningless_combinations(
    tmp_path: Path, component_type: str, language: str
) -> None:
    with pytest.raises(CliFailure, match="declarative components"):
        authoring.scaffold_plan(
            component_type=component_type,
            name="review-kit",
            language=language,
            harness_variant="portable",
            output=tmp_path / "review-kit",
        )


def test_scaffold_commands_require_exact_plan_and_never_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "review-kit"
    parameters = {
        "type": "skill",
        "name": "review-kit",
        "language": "none",
        "harness": "portable",
        "output": str(output),
    }
    plan = component.scaffold_plan(parameters).payload
    assert plan == component.scaffold_plan(parameters).payload

    # The digest is the confirmation, and there is no second flag beside it.
    # Creating a new directory is local and reversible, so `ADR-0118` leaves it
    # inside the task's authority; what still has to hold is that the *exact*
    # plan is named. A wrong digest refuses, and a missing one is a malformed
    # call rather than an undecided one.
    with pytest.raises(CliFailure, match="digest changed"):
        component.scaffold_apply({**parameters, "expected-plan-digest": "sha256:" + "0" * 64})

    with pytest.raises(CliFailure, match="scaffold plan digest is required"):
        component.scaffold_apply(parameters)

    result = component.scaffold_apply(
        {**parameters, "expected-plan-digest": plan.plan_digest}
    ).payload
    assert result.output == str(output)
    assert result.files_written == len(plan.files)
    assert result.template_version == "component-scaffold/4"
    if os.name != "nt":
        assert all(
            path.stat().st_mode & 0o777 == 0o600
            for path in output.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(output).parts
        )
    with pytest.raises(CliFailure, match="must not already exist"):
        component.scaffold_plan(parameters)


def test_scaffold_refuses_nonempty_destination_and_missing_parent(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "owned.txt").write_text("keep", encoding="utf-8")
    for output in (occupied, tmp_path / "missing" / "child"):
        with pytest.raises(CliFailure, match="destination"):
            authoring.scaffold_plan(
                component_type="instruction",
                name="review-kit",
                language="none",
                harness_variant="portable",
                output=output,
            )
    assert (occupied / "owned.txt").read_text(encoding="utf-8") == "keep"


def test_scaffold_apply_rejects_bytes_changed_after_plan(tmp_path: Path) -> None:
    output = tmp_path / "review-kit"
    plan, files = authoring.scaffold_plan(
        component_type="skill",
        name="review-kit",
        language="none",
        harness_variant="portable",
        output=output,
    )
    files["README.md"] += b"changed\n"

    with pytest.raises(CliFailure, match="bytes no longer match"):
        authoring.apply_scaffold(plan, files, expected_digest=plan.plan_digest)

    assert not output.exists()


def test_scaffold_contract_rejects_invalid_descriptor_and_paths() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        ComponentTemplateDescriptor(
            component_type="skill",
            language="python",
            harness_variant="portable",
            executable=True,
        )
    with pytest.raises(ValueError, match="executable marker"):
        ComponentTemplateDescriptor(
            component_type="skill",
            language="none",
            harness_variant="portable",
            executable=True,
        )
    with pytest.raises(ValueError, match="relative POSIX"):
        ComponentScaffoldFile(
            path="../escape",
            digest="sha256:" + "0" * 64,
            byte_length=0,
        )


def test_scaffold_skill_declares_the_projection_root_not_the_entry_file(tmp_path: Path) -> None:
    _plan, files = authoring.scaffold_plan(
        component_type="skill",
        name="review-kit",
        language="none",
        harness_variant="portable",
        output=tmp_path / "review-kit",
    )
    passport = json.loads(files["component-passport.json"].decode())
    assert passport["managed_paths"] == ["skills/review-kit"]
    assert passport["entry_points"] == ["SKILL.md"]


@pytest.mark.parametrize(
    ("harness", "command", "managed"),
    [
        ("codex", "python hooks/handler.py", "hooks.json"),
        ("cursor", "python hooks/handler.py", "hooks.json"),
        ("antigravity", "python config/hooks/handler.py", "config/hooks.json"),
        (
            "grok-build",
            "python hooks/review-kit/hooks/handler.py",
            "hooks/review-kit",
        ),
    ],
)
def test_hook_scaffold_preserves_source_event_order_and_failure_in_native_form(
    tmp_path: Path, harness: str, command: str, managed: str
) -> None:
    _plan, files = authoring.scaffold_plan(
        component_type="hook",
        name="review-kit",
        language="python",
        harness_variant=harness,
        output=tmp_path / "review-kit",
    )

    source = json.loads(files["source/hook-source.json"])
    manifest = json.loads(files[f"projections/{harness}/hooks.json"])
    projected = manifest["hooks"][source["event"]]
    assert source == {
        "schema_version": 1,
        "event": "PreToolUse",
        "order": 0,
        "failure": "block",
        "handler": {"command": command},
    }
    assert projected[0]["hooks"] == [{"type": "command", "command": command}]
    assert "handle_event" not in files[f"projections/{harness}/hooks/handler.py"].decode()
    passport = json.loads(files["component-passport.json"])
    assert passport["managed_paths"] == [managed]
    assert passport["entry_points"] == ["hooks/handler.py"]


def test_plugin_scaffold_uses_manifest_packages_and_bare_modules(tmp_path: Path) -> None:
    cases = {
        "claude-code": {
            "projections/claude-code/.claude-plugin/plugin.json",
            "projections/claude-code/src/main.js",
        },
        "cursor": {
            "projections/cursor/.cursor-plugin/plugin.json",
            "projections/cursor/src/main.js",
        },
        "antigravity": {
            "projections/antigravity/plugin.json",
            "projections/antigravity/src/main.js",
        },
        "grok-build": {"projections/grok-build/plugin.json", "projections/grok-build/src/main.js"},
        "opencode": {"projections/opencode/review-kit.js"},
        "pi": {"projections/pi/review-kit.js"},
    }
    for harness, native_paths in cases.items():
        _plan, files = authoring.scaffold_plan(
            component_type="plugin",
            name="review-kit",
            language="javascript",
            harness_variant=harness,
            output=tmp_path / harness,
        )
        assert {path for path in files if path.startswith("projections/")} == native_paths | {
            f"projections/{harness}/GENERATED.md"
        }
        passport = json.loads(files["component-passport.json"])
        if harness == "opencode":
            assert passport["managed_paths"] == ["plugins/review-kit.js"]
            assert not any(path.endswith("plugin.json") for path in files)
        assert "native/settings.json" not in files


def test_marketplace_registration_belongs_to_setting_not_plugin(tmp_path: Path) -> None:
    _plugin_plan, plugin = authoring.scaffold_plan(
        component_type="plugin",
        name="review-kit",
        language="javascript",
        harness_variant="claude-code",
        output=tmp_path / "plugin",
    )
    _setting_plan, setting = authoring.scaffold_plan(
        component_type="setting",
        name="marketplace-registration",
        language="none",
        harness_variant="claude-code",
        output=tmp_path / "setting",
    )

    assert "native/settings.json" not in plugin
    assert json.loads(setting["projections/claude-code/settings.json"]) == {}
    assert json.loads(setting["component-passport.json"])["managed_paths"] == ["settings.json"]


@pytest.mark.parametrize(
    ("component_type", "harness"),
    [("hook", "opencode"), ("command", "grok-build")],
)
def test_scaffold_fails_before_writing_when_native_semantics_do_not_exist(
    tmp_path: Path, component_type: str, harness: str
) -> None:
    language = "python" if component_type == "hook" else "none"
    with pytest.raises(CliFailure, match="without losing semantics"):
        authoring.scaffold_plan(
            component_type=component_type,
            name="review-kit",
            language=language,
            harness_variant=harness,
            output=tmp_path / "review-kit",
        )
    assert not (tmp_path / "review-kit").exists()


def test_historical_v3_reference_scaffolds_remain_a_reviewed_snapshot(tmp_path: Path) -> None:
    golden = json.loads(SCAFFOLD_GOLDEN.read_text(encoding="utf-8"))
    assert golden["template_version"] == "component-scaffold/3"
    assert golden["generator_version"] == "ai-stp/3"
    assert golden["cases"]


def test_historical_v2_golden_remains_a_reviewed_snapshot() -> None:
    golden = json.loads(HISTORICAL_V2_GOLDEN.read_text(encoding="utf-8"))
    assert golden["template_version"] == "component-scaffold/2"
    assert golden["generator_version"] == "ai-stp/2"
    assert any(path.startswith("native/") for case in golden["cases"].values() for path in case)


def test_historical_scaffold_descriptor_versions_remain_validatable() -> None:
    for template, generator in (
        ("component-scaffold/1", "ai-stp/1"),
        ("component-scaffold/2", "ai-stp/2"),
        ("component-scaffold/3", "ai-stp/3"),
        ("component-scaffold/4", "ai-stp/4"),
    ):
        ComponentTemplateDescriptor.model_validate(
            {
                "schema_version": 1,
                "template_version": template,
                "generator_version": generator,
                "component_type": "skill",
                "language": "none",
                "harness_variant": "portable",
                "executable": False,
            }
        )


def test_scaffold_plan_contract_rejects_duplicate_file_paths(tmp_path: Path) -> None:
    plan, _files = authoring.scaffold_plan(
        component_type="skill",
        name="review-kit",
        language="none",
        harness_variant="portable",
        output=tmp_path / "review-kit",
    )
    document = plan.model_dump(mode="json")
    document["files"].append(document["files"][0])

    with pytest.raises(ValueError, match="must be unique"):
        ComponentScaffoldPlan.model_validate(document)


def test_render_command_returns_content_and_stable_digests(tmp_path: Path) -> None:
    source = tmp_path / "template.md"
    source.write_text(
        "{{component_name}} at {{component_root}} for {{harness_id}}\n", encoding="utf-8"
    )
    parameters = {
        "template": str(source),
        "harness": "codex",
        "name": "review-kit",
        "component-root": "skills/review-kit",
    }

    first = component.template_render(parameters).payload
    second = component.template_render(parameters).payload

    assert first == second
    assert first.content == "review-kit at skills/review-kit for codex\n"
    assert first.placeholders == ["component_name", "component_root", "harness_id"]
    assert first.source_digest != first.rendered_digest


@pytest.mark.parametrize("variant", ("portable", *sorted(authoring.HARNESSES)))
def test_every_offered_harness_variant_can_actually_be_scaffolded(
    variant: str, tmp_path: Path
) -> None:
    """The registry offered seven variants and the contract accepted five.

    `registry.py` declares `choices=("portable", *HARNESS_ID_ORDER)`, so machine
    help told an agent that `cursor` and `antigravity` were valid. The runtime
    tuple `AUTHORING_VARIANTS` was a hand-written list of five, so the call came
    back `the scaffold language or harness variant is unsupported`. Both halves
    were internally consistent; the seam between them was not, which is where
    this kind of defect lives.

    Behavioural on purpose: asserting that the tuple equals the enum would pass
    the moment someone rebuilds the tuple by hand from the same enum, and say
    nothing about whether the command works.
    """
    plan, files = authoring.scaffold_plan(
        component_type="skill",
        name="reference-component",
        language="none",
        harness_variant=variant,
        output=tmp_path / "reference-component",
    )

    assert files, f"{variant} produced no scaffold bytes"
    assert any(item.path.startswith("source/") for item in plan.files)
