"""Qualify the archived native CLI against actual API/PostgreSQL on macOS/Windows."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from functools import partial
from pathlib import Path

from alembic import command
from alembic.config import Config
from tests.native_contract import verify_corporate, verify_ownership
from tests.native_vendor.installation import prepare
from tests.support.api_settings import close_api_log_files
from tests.support.native_postgres import cluster
from tests.support.native_runner import disposable_runner, report_stage
from tests.support.postgres import isolated_database


def main() -> None:
    disposable_runner()
    assert os.environ["RUNNER_OS"] in {"macOS", "Windows"}
    diagnostic = bool(os.environ.get("AI_STP_NATIVE_ENGINE_SOURCE_RUN"))
    if diagnostic:
        assert os.environ["GITHUB_EVENT_NAME"] == "workflow_dispatch"
        assert os.environ["GITHUB_WORKFLOW"] == "desktop"
    else:
        assert not os.environ.get("AI_STP_NATIVE_ENGINE_SOURCE")
        assert os.environ["GITHUB_EVENT_NAME"] in {"push", "workflow_dispatch"}
        assert os.environ["GITHUB_WORKFLOW"] == "check"
    native_os = os.environ["RUNNER_OS"]
    source = os.environ["GITHUB_SHA"]
    assert re.fullmatch(r"[0-9a-f]{40}", source)
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    saved = {key: os.environ.get(key) for key in ["AI_STP_TEST_DB_URL", "AI_STP_DB_URL"]}
    try:
        with tempfile.TemporaryDirectory(
            prefix="ai-stp-native-corporate-", dir=temporary
        ) as location:
            root = Path(location)
            report_stage("archived-cli")
            engine = prepare(root, source)
            assert engine is not None
            binary, identity = engine
            assert identity["diagnostic_only"] is diagnostic
            with cluster() as (template_url, database):
                report_stage("postgresql-ready")
                os.environ["AI_STP_TEST_DB_URL"] = template_url
                cases = [
                    ("ownership", partial(verify_ownership.prove, credential_store="os_keyring")),
                    (
                        "corporate",
                        partial(
                            verify_corporate.prove,
                            credential_store="os_keyring",
                            historical_consumers=native_os != "macOS",
                        ),
                    ),
                ]
                cases.append(
                    (
                        "corporate-usage",
                        partial(
                            verify_corporate.prove,
                            credential_store="os_keyring",
                            historical_consumers=native_os != "macOS",
                            usage_only=True,
                        ),
                    )
                )
                if native_os == "macOS":
                    cases.append(
                        (
                            "corporate-file",
                            partial(
                                verify_corporate.prove,
                                credential_store="file",
                            ),
                        )
                    )
                for name, owner in cases:
                    fixture = root / name
                    fixture.mkdir()
                    with isolated_database(
                        "The admitted native PostgreSQL cluster is required"
                    ) as url:
                        os.environ["AI_STP_DB_URL"] = url
                        report_stage(f"{name}-migrations")
                        command.upgrade(Config("alembic.ini"), "head")
                        report_stage(f"{name}-journey")
                        try:
                            asyncio.run(owner(binary, url, fixture))
                        finally:
                            close_api_log_files(fixture / "api")
                        report_stage(f"{name}-passed")
            report_stage("postgresql-stopped")
            historical_writers: list[dict[str, int | str]] = []
            for schema, suffix in [
                (58, ""),
                (59, "_BINDING"),
                (60, "_LOCATION"),
                (61, "_MISSING_CHECKOUT"),
            ]:
                prefix = f"AI_STP_TEST_PREVIOUS{suffix}_CLI"
                previous = Path(os.environ[prefix + "_BINARY"])
                assert previous.resolve().is_relative_to(temporary)
                assert previous.is_file() and not previous.is_symlink()
                assert 4096 < previous.stat().st_size <= 512 * 1024 * 1024
                previous_source = os.environ[prefix + "_SOURCE"]
                assert re.fullmatch(r"[0-9a-f]{40}", previous_source)
                with previous.open("rb") as stream:
                    previous_digest = hashlib.file_digest(stream, "sha256").hexdigest()
                historical_writers.append(
                    {
                        "registry_schema": schema,
                        "source_sha": previous_source,
                        "binary_sha256": previous_digest,
                        "origin": "pinned_source_build" if schema < 60 else "immutable_release",
                    }
                )
            proof = {
                "schema_version": 1,
                "evidence_kind": "native_cli_corporate_api_postgresql",
                "fixture_source_sha": source,
                "fixture_run_id": os.environ["GITHUB_RUN_ID"],
                "fixture_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
                "engine": identity,
                "source_run_attempt": int(os.environ["AI_STP_NATIVE_ENGINE_SOURCE_ATTEMPT"]),
                "database": database,
                "historical_writers": historical_writers,
                "native_credential_store": "os_keyring",
                "historical_corporate_credential_store": "file"
                if native_os == "macOS"
                else "os_keyring",
                "historical_os_vault_compatibility_qualified": native_os == "Windows",
                "journeys": [name for name, _ in cases],
                "ownership_transfer_journey_passed": True,
                "corporate_journeys_passed": True,
                "database_process_stopped": True,
                "live_sso_account_linking_qualified": False,
                "desktop_gui_qualified": False,
                "release_authorized": False,
            }
            (temporary / "native-corporate-proof.json").write_text(
                json.dumps(proof, indent=2) + "\n", encoding="utf-8"
            )
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()
