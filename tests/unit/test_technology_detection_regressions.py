"""Real-world manifest shapes and incomplete-scan boundaries for milestone 8."""

from io import BytesIO
from pathlib import Path

import pytest

from ai_stp_cli.local import project_index, tech_detect


@pytest.mark.parametrize(
    ("name", "body", "expected"),
    [
        ("main.mts", "export {};", {("alias", "typescript", None)}),
        ("main.cts", "export {};", {("alias", "typescript", None)}),
        (
            "requirements.txt",
            "FastAPI @ https://fixture:fixture-secret@example.invalid/fastapi.whl\n",
            {("package", "fastapi", None)},
        ),
        (
            "pyproject.toml",
            '[dependency-groups]\ntest = ["pytest>=8"]\n',
            {("package", "pytest", ">=8")},
        ),
        (
            "Cargo.toml",
            '[workspace.dependencies]\nweb = { package = "axum", version = "0.8" }\n',
            {("package", "axum", "0.8")},
        ),
        (
            "Cargo.toml",
            "[target.'cfg(unix)'.dependencies]\nlibc = \"0.2\"\n",
            {("package", "libc", "0.2")},
        ),
        (
            "pnpm-lock.yaml",
            "lockfileVersion: '9.0'\npackages:\n  '@angular/core@20.0.0': {}\n",
            {("package", "@angular/core", None)},
        ),
        (
            "pnpm-lock.yaml",
            "lockfileVersion: 5.4\npackages:\n  /@angular/core/15.0.0: {}\n",
            {("package", "@angular/core", None)},
        ),
        (
            "go.sum",
            "example.com/mod v1.2.3/go.mod h1:fixture\n",
            {("package", "example.com/mod", "v1.2.3")},
        ),
        (
            "docker-compose.prod.yml",
            "services:\n  db:\n    image: postgres:16\n",
            {("image", "postgres", "16")},
        ),
        ("Dockerfile.prod", "FROM python:3.12\n", {("image", "python", "3.12")}),
        (
            "setup.cfg",
            "[options]\ninstall_requires = fastapi>=0.100\n",
            {("package", "fastapi", ">=0.100")},
        ),
    ],
)
def test_manifest_shapes(
    tmp_path: Path, name: str, body: str, expected: set[tuple[str, str, str | None]]
) -> None:
    (tmp_path / name).write_text(body, encoding="utf-8")
    index = project_index.build(tmp_path)
    scan = tech_detect.detect(index)
    assert expected <= {(d.kind, d.coordinate, d.version) for d in scan.detections}
    assert scan == tech_detect.detect(index)
    assert "fixture-secret" not in repr(scan)


def test_rust_edition_is_not_a_compiler_version(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nedition = "2024"\n', encoding="utf-8")
    scan = tech_detect.detect(project_index.build(tmp_path))
    assert all(d.version != "2024" for d in scan.detections)


def test_go_excludes_and_replacements_are_not_requirements(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text(
        "module example.com/app\ngo 1.24 // minimum\n"
        "require example.com/used v1.0.0\n"
        "exclude (\nexample.com/unused v2.0.0\n)\n"
        "replace example.com/old v1.0.0 => ../local\n",
        encoding="utf-8",
    )
    scan = tech_detect.detect(project_index.build(tmp_path))
    assert {d.coordinate for d in scan.detections if d.kind == "package"} == {"example.com/used"}
    assert {d.version for d in scan.detections if d.coordinate == "go"} == {None, "1.24"}


@pytest.mark.parametrize("failure", ["changed", "oversize", "no_digest", "invalid"])
def test_unreadable_manifest_makes_detection_incomplete(tmp_path: Path, failure: str) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text('{"dependencies":{"react":"18"}}', encoding="utf-8")
    if failure == "oversize":
        manifest.write_text(" " * (project_index.MAX_FILE_BYTES + 1), encoding="utf-8")
    elif failure == "invalid":
        manifest.write_text('{"dependencies":', encoding="utf-8")
    index = project_index.build(tmp_path, digests=failure != "no_digest")
    if failure == "changed":
        manifest.write_text('{"dependencies":{"next":"15"}}', encoding="utf-8")
    scan = tech_detect.detect(index)
    assert not scan.complete
    assert scan.stopped_by
    assert not any(d.kind == "package" for d in scan.detections)


def test_dependency_urls_do_not_become_versions(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"react":"https://user:fixture-secret@example.invalid/react.tgz"}}',
        encoding="utf-8",
    )
    scan = tech_detect.detect(project_index.build(tmp_path))
    assert "fixture-secret" not in repr(scan)
    assert next(d for d in scan.detections if d.coordinate == "react").version is None


def test_docker_stage_alias_is_not_an_image(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12 AS base\nFROM base AS runtime\n", encoding="utf-8"
    )
    scan = tech_detect.detect(project_index.build(tmp_path))
    assert {d.coordinate for d in scan.detections if d.kind == "image"} == {"python"}


def test_depth_limit_is_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_stp_sources.project_index.MAX_DEPTH", 1)
    deep = tmp_path / "nested"
    deep.mkdir()
    (deep / "main.py").write_text("pass", encoding="utf-8")
    index = project_index.build(tmp_path)
    assert index.state == "partial"
    assert not tech_detect.detect(index).complete


@pytest.mark.parametrize(
    "name",
    ["token.json", "tokens.json", "credentials-dev.json", "service-account-prod.json", ".mcp.json"],
)
def test_credential_files_are_excluded_without_reading(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_text("fixture-secret", encoding="utf-8")
    index = project_index.build(tmp_path)
    assert not index.entries
    assert index.excluded[0].reason == "looks like a credential"


def test_symlink_cannot_disguise_a_credential_as_a_manifest(tmp_path: Path) -> None:
    secret = tmp_path / ".env"
    secret.write_text('{"dependencies":{"react":"fixture-secret"}}', encoding="utf-8")
    (tmp_path / "package.json").symlink_to(secret)
    index = project_index.build(tmp_path)
    assert not index.entries


def test_detection_time_limit_returns_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    index = project_index.build(tmp_path)
    monkeypatch.setattr("ai_stp_sources.project_index.MAX_SECONDS", 0)
    scan = tech_detect.detect(index)
    assert not scan.complete
    assert scan.stopped_by == "detection time budget"


def test_symlink_loop_is_incomplete_instead_of_crashing(tmp_path: Path) -> None:
    link = tmp_path / "package.json"
    link.symlink_to(link)
    index = project_index.build(tmp_path)
    assert index.state == "partial"
    assert not tech_detect.detect(index).complete


def test_binary_probe_does_not_read_the_rest_of_an_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"\0" + b"x" * 100_000
    (tmp_path / "image.png").write_bytes(content)

    class RecordingStream(BytesIO):
        bytes_read = 0

        def read(self, size: int | None = -1) -> bytes:
            result = super().read(size)
            self.bytes_read += len(result)
            return result

    stream = RecordingStream(content)

    def open_binary(_path: Path, mode: str) -> RecordingStream:
        assert mode == "rb"
        return stream

    monkeypatch.setattr(Path, "open", open_binary)
    assert not project_index.build(tmp_path).entries
    assert stream.bytes_read == project_index.BINARY_PROBE_BYTES
