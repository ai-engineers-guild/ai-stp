"""The first supported alpha contract must not regress into older promises."""

from pathlib import Path

from release_scripts.build_candidate import PUBLISHABLE


def test_product_contract_names_the_candidate_package_closure() -> None:
    specification = Path("specs/active/SPEC-001-product-contract.md").read_text(encoding="utf-8")

    assert list(PUBLISHABLE) == ["ai-stp-cli"]
    assert "one distribution" in specification
    assert "ai-stp-cli" in specification
    assert "Requires-Dist" in specification


def test_scaffold_apply_uses_the_exact_digest_as_its_confirmation() -> None:
    specification = Path("specs/active/SPEC-041-component-scaffold-framework.md").read_text(
        encoding="utf-8"
    )
    requirement = specification.split("- `REQ-4106`:", maxsplit=1)[1].split(
        "\n- `REQ-4107`", maxsplit=1
    )[0]

    assert "exact digest" in requirement
    assert "--confirm" not in requirement


def test_readme_promises_no_calendar_language_rewrite() -> None:
    for path in (Path("README.md"), Path("README.ru.md")):
        text = path.read_text(encoding="utf-8")
        assert "31 December 2026" not in text
        assert "will be rewritten in Rust" not in text
        assert "0.0.16" in text
