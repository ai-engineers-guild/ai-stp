"""Schema generator CLI: write, clean check, drift and orphan detection."""

from pathlib import Path

from ai_stp_contracts.schemas import EXPORTED_MODELS, check_all, main, write_all
from ai_stp_foundation.schemas import check


def test_write_then_check_is_clean(tmp_path: Path) -> None:
    # The generator owns two artifacts now: the per-model schemas and the
    # OpenAPI document. A round trip through only the first would leave the
    # second unchecked, which is how the gate lost nine schemas once already.
    written = write_all(tmp_path)
    assert len(written) == len(EXPORTED_MODELS) + 1
    assert check_all(tmp_path) == []
    assert main(["--check", str(tmp_path)]) == 0


def test_a_missing_openapi_document_fails_the_check(tmp_path: Path) -> None:
    write_all(tmp_path)
    (tmp_path / "openapi.json").unlink()
    assert any("missing generated document" in problem for problem in check_all(tmp_path))


def test_a_drifted_openapi_document_fails_the_check(tmp_path: Path) -> None:
    write_all(tmp_path)
    document = tmp_path / "openapi.json"
    document.write_text(document.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert any("openapi document drifted" in problem for problem in check_all(tmp_path))


def test_main_writes_and_reports_paths(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 0
    assert (tmp_path / "openapi.json").exists()
    assert sorted(path.name for path in tmp_path.glob("*.schema.json")) == sorted(
        f"{name}.schema.json" for name in EXPORTED_MODELS
    )


def test_drift_missing_and_orphan_fail_the_check(tmp_path: Path) -> None:
    write_all(tmp_path)
    drifted = tmp_path / "fact.schema.json"
    drifted.write_text(drifted.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    (tmp_path / "component-ref.schema.json").unlink()
    (tmp_path / "orphan.schema.json").write_text("{}\n", encoding="utf-8")
    problems = check(tmp_path, EXPORTED_MODELS)
    assert any("drifted" in problem for problem in problems)
    assert any("missing" in problem for problem in problems)
    assert any("unexpected schema" in problem for problem in problems)
    assert main(["--check", str(tmp_path)]) == 1


def test_the_foundation_generator_entrypoint_writes_and_checks(tmp_path: Path) -> None:
    # `ai_stp_foundation.schemas` documents its own `python -m` entrypoint. It is
    # not what `just back-gen` calls, so nothing else exercises it, and a
    # broken per-package generator would only be found by whoever ran it.
    from ai_stp_foundation.schemas import EXPORTED_MODELS as FOUNDATION_MODELS
    from ai_stp_foundation.schemas import main as foundation_main

    assert foundation_main([str(tmp_path)]) == 0
    assert sorted(path.stem for path in tmp_path.glob("*.schema.json")) == sorted(
        f"{name}.schema" for name in FOUNDATION_MODELS
    )
    assert foundation_main(["--check", str(tmp_path)]) == 0

    drifted = next(iter(tmp_path.glob("*.schema.json")))
    drifted.write_text(drifted.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert foundation_main(["--check", str(tmp_path)]) == 1
