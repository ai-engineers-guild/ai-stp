"""Strong evidence and false-positive corpus for MCP source discovery."""

from pathlib import Path

import pytest

from ai_stp_cli.local import mcp_sources


def _python_server(root: Path, *, transport: str = "stdio") -> Path:
    (root / "src" / "sample").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        """[project]
name = "sample-mcp"
version = "1.0.0"
dependencies = ["mcp>=1"]

[project.scripts]
sample-mcp = "sample.server:main"
""",
        encoding="utf-8",
    )
    source = root / "src" / "sample" / "server.py"
    source.write_text(
        "from mcp.server.fastmcp import FastMCP\n"
        "server = FastMCP('sample')\n"
        f"server.run(transport={transport!r})\n",
        encoding="utf-8",
    )
    return source


def test_python_stdio_and_http_packages_are_explainable(tmp_path: Path) -> None:
    stdio = tmp_path / "services" / "stdio"
    http = tmp_path / "services" / "http"
    source = _python_server(stdio)
    _python_server(http, transport="streamable-http")
    (stdio / "Dockerfile").write_text('FROM python:3.13\nCMD ["sample.server"]\n', encoding="utf-8")

    report = mcp_sources.discover(tmp_path)

    assert [(item.root, item.transports) for item in report.candidates] == [
        (http, ("http",)),
        (stdio, ("stdio",)),
    ]
    found = next(item for item in report.candidates if item.root == stdio)
    assert found.entry_points == ("sample.server:main",)
    assert found.evidence == ("Dockerfile", "pyproject.toml", source.relative_to(stdio).as_posix())
    assert report.diagnostics == ()


def test_typescript_package_requires_sdk_dependency_and_exact_entry_source(tmp_path: Path) -> None:
    root = tmp_path / "support"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(
        """{
  "name": "sample-mcp",
  "dependencies": {"@modelcontextprotocol/sdk": "1.0.0"},
  "bin": {"sample-mcp": "src/server.ts"}
}
""",
        encoding="utf-8",
    )
    (root / "src" / "server.ts").write_text(
        "import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';\n"
        "new StdioServerTransport();\n",
        encoding="utf-8",
    )

    report = mcp_sources.discover(tmp_path)

    assert len(report.candidates) == 1
    assert report.candidates[0].root == root
    assert report.candidates[0].entry_points == ("src/server.ts",)
    assert report.candidates[0].transports == ("stdio",)


def test_names_docs_tests_and_unlinked_launchers_are_not_evidence(tmp_path: Path) -> None:
    application = tmp_path / "application"
    (application / "src" / "features" / "mcp").mkdir(parents=True)
    (application / "src" / "features" / "mcp" / "server.py").write_text(
        "# documentation example\n", encoding="utf-8"
    )
    (application / "package.json").write_text(
        '{"name":"mcp-ui","scripts":{"test":"node tests/mcp.test.js"}}\n',
        encoding="utf-8",
    )
    (application / "Dockerfile").write_text("FROM node:24\n", encoding="utf-8")

    assert mcp_sources.discover(tmp_path).candidates == ()


def test_symlinks_and_bounded_collections_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    _python_server(outside)
    root = tmp_path / "root"
    root.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    for name in ("a", "b"):
        place = root / name
        place.mkdir()
    monkeypatch.setattr(mcp_sources, "MAX_DIRECTORY_ENTRIES", 1)

    report = mcp_sources.discover(root)

    assert report.candidates == ()
    assert any(item.code == "bounded_limit" for item in report.diagnostics)


def test_malformed_and_oversized_metadata_returns_safe_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken_python = tmp_path / "broken-python"
    broken_python.mkdir()
    (broken_python / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    broken_node = tmp_path / "broken-node"
    broken_node.mkdir()
    (broken_node / "package.json").write_text("{", encoding="utf-8")
    oversized = tmp_path / "oversized"
    oversized.mkdir()
    (oversized / "package.json").write_bytes(b"x" * 32)
    monkeypatch.setattr(mcp_sources, "MAX_MANIFEST_BYTES", 16)

    report = mcp_sources.discover(tmp_path)

    assert report.candidates == ()
    assert {item.code for item in report.diagnostics} == {
        "bounded_limit",
        "invalid_manifest",
    }
    assert all(
        "{" not in item.reason and "[project" not in item.reason for item in report.diagnostics
    )


def test_declared_sdk_without_a_verified_entry_source_is_not_a_server(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.mkdir()
    (python / "pyproject.toml").write_text(
        """[project]
name = "docs-only"
version = "1.0.0"
dependencies = ["mcp"]
[project.scripts]
missing = "missing.server:main"
""",
        encoding="utf-8",
    )
    node = tmp_path / "node"
    node.mkdir()
    (node / "package.json").write_text(
        '{"dependencies":{"@modelcontextprotocol/sdk":"1"},"bin":"../escape.js"}\n',
        encoding="utf-8",
    )

    assert mcp_sources.discover(tmp_path).candidates == ()


def test_typescript_scripts_http_and_unknown_python_transport_are_honest(tmp_path: Path) -> None:
    node = tmp_path / "node"
    (node / "src").mkdir(parents=True)
    (node / "package.json").write_text(
        """{
  "optionalDependencies": {"fastmcp": "1"},
  "scripts": {"serve": "tsx src/server.ts"}
}
""",
        encoding="utf-8",
    )
    (node / "src" / "server.ts").write_text(
        "import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';\n"
        "new SSEServerTransport();\n",
        encoding="utf-8",
    )
    python = tmp_path / "python"
    _python_server(python, transport="custom")

    report = mcp_sources.discover(tmp_path)

    assert [(item.root.name, item.transports) for item in report.candidates] == [
        ("node", ("http",)),
        ("python", ()),
    ]


def test_entry_source_limits_and_directory_budget_stop_without_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    source = _python_server(root)
    source.write_bytes(b"x" * 64)
    monkeypatch.setattr(mcp_sources, "MAX_SOURCE_BYTES", 16)
    first = mcp_sources.discover(root)
    assert first.candidates == ()
    assert any(item.code == "bounded_limit" for item in first.diagnostics)

    source.write_text("from mcp.server.fastmcp import FastMCP\nFastMCP('x')\n", encoding="utf-8")
    (root / "nested").mkdir()
    monkeypatch.setattr(mcp_sources, "MAX_SOURCE_BYTES", 1024)
    monkeypatch.setattr(mcp_sources, "MAX_DIRECTORIES", 1)
    second = mcp_sources.discover(root)
    assert len(second.candidates) == 1
    assert any(item.code == "bounded_limit" for item in second.diagnostics)


@pytest.mark.parametrize(
    "document",
    [
        "[tool.sample]\nvalue = 1\n",
        "[project]\ndependencies = 'mcp'\n",
        "[project]\ndependencies = ['httpx']\n",
        "[project]\ndependencies = ['mcp']\nscripts = []\n",
        "[project]\ndependencies = ['mcp']\n[project.scripts]\nbroken = 1\n",
        "[project]\ndependencies = [1]\n",
    ],
)
def test_python_manifest_shapes_do_not_create_candidates(tmp_path: Path, document: str) -> None:
    (tmp_path / "pyproject.toml").write_text(document, encoding="utf-8")
    assert mcp_sources.discover(tmp_path).candidates == ()


def test_invalid_or_unrelated_exact_sources_do_not_upgrade_declared_packages(
    tmp_path: Path,
) -> None:
    syntax = tmp_path / "syntax"
    syntax_source = _python_server(syntax)
    syntax_source.write_text("from mcp import (\n", encoding="utf-8")
    unrelated = tmp_path / "unrelated"
    unrelated_source = _python_server(unrelated)
    unrelated_source.write_text("import httpx\n", encoding="utf-8")
    node = tmp_path / "node"
    (node / "src").mkdir(parents=True)
    (node / "package.json").write_text(
        '{"dependencies":{"@modelcontextprotocol/sdk":"1"},"bin":"src/server.ts"}\n',
        encoding="utf-8",
    )
    (node / "src" / "server.ts").write_bytes(b"\xff")

    report = mcp_sources.discover(tmp_path)

    assert report.candidates == ()
    assert sum(item.code == "invalid_manifest" for item in report.diagnostics) == 2


@pytest.mark.parametrize(
    "document",
    [
        "[]",
        '{"dependencies":{"@modelcontextprotocol/sdk":"1"},"scripts":{"x":1}}',
    ],
)
def test_node_manifest_shapes_do_not_create_candidates(tmp_path: Path, document: str) -> None:
    (tmp_path / "package.json").write_text(document, encoding="utf-8")
    assert mcp_sources.discover(tmp_path).candidates == ()


def test_depth_and_linked_manifests_are_closed_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside.toml"
    outside.write_text("[project]\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "pyproject.toml").symlink_to(outside)
    nested = root / "nested"
    _python_server(nested)
    monkeypatch.setattr(mcp_sources, "MAX_DEPTH", 0)

    assert mcp_sources.discover(root).candidates == ()
