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

SCAFFOLD_GOLDEN = Path(__file__).parents[1] / "golden" / "cli" / "component-scaffold-v1.json"
REFERENCE_CASES = {
    "instruction-none-portable": ("instruction", "none", "portable"),
    "skill-none-codex": ("skill", "none", "codex"),
    "agent-none-claude-code": ("agent", "none", "claude-code"),
    "setting-none-grok-build": ("setting", "none", "grok-build"),
    "mcp-python-portable": ("mcp", "python", "portable"),
    "mcp-javascript-codex": ("mcp", "javascript", "codex"),
    "hook-typescript-pi": ("hook", "typescript", "pi"),
    "hook-go-opencode": ("hook", "go", "opencode"),
    "command-rust-portable": ("command", "rust", "portable"),
    "plugin-dart-flutter-grok-build": ("plugin", "dart-flutter", "grok-build"),
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
    assert ("Claude Code-specific guidance." in first.content) is (harness_id == "claude-code")
    assert ("Codex-specific guidance." in first.content) is (harness_id == "codex")
    assert ("Portable harness guidance." in first.content) is (
        harness_id in {"pi", "opencode", "grok-build"}
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
    ComponentPassportPatch.model_validate(from_json_bytes(files["component-passport.json"]))
    profile = SetupEvalProfile.model_validate(from_json_bytes(files["eval-profile.json"]))
    assert profile.component_types == [component_type]
    assert any(check.method == "deterministic" for check in profile.checks)
    assert any(check.method == "model_assisted" for check in profile.checks)


@pytest.mark.parametrize(
    ("component_type", "language"),
    [("skill", "python"), ("agent", "go"), ("mcp", "none"), ("plugin", "none")],
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

    with pytest.raises(CliFailure) as raised:
        component.scaffold_apply({**parameters, "expected-plan-digest": plan.plan_digest})
    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"

    with pytest.raises(CliFailure, match="digest changed"):
        component.scaffold_apply(
            {**parameters, "expected-plan-digest": "sha256:" + "0" * 64, "confirm": True}
        )

    result = component.scaffold_apply(
        {**parameters, "expected-plan-digest": plan.plan_digest, "confirm": True}
    ).payload
    assert result.output == str(output)
    assert result.files_written == len(plan.files)
    if os.name != "nt":
        assert all(
            path.stat().st_mode & 0o777 == 0o600 for path in output.rglob("*") if path.is_file()
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


def test_versioned_reference_scaffolds_match_the_reviewed_golden(tmp_path: Path) -> None:
    golden = json.loads(SCAFFOLD_GOLDEN.read_text(encoding="utf-8"))
    assert golden["template_version"] == "component-scaffold/1"
    assert golden["generator_version"] == "ai-stp/1"
    observed: dict[str, dict[str, str]] = {}
    for case, (component_type, language, harness) in REFERENCE_CASES.items():
        plan, _files = authoring.scaffold_plan(
            component_type=component_type,
            name="reference-component",
            language=language,
            harness_variant=harness,
            output=tmp_path / "reference-component",
        )
        observed[case] = {item.path: item.digest for item in plan.files}

    assert observed == golden["cases"]


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
