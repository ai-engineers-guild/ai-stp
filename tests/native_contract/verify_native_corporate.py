"""Qualify the archived native CLI against actual API/PostgreSQL on macOS/Windows."""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
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
    assert os.environ["GITHUB_EVENT_NAME"] == "workflow_dispatch"
    assert os.environ["GITHUB_WORKFLOW"] == "desktop"
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
            assert identity["diagnostic_only"] is True
            with cluster() as (template_url, database):
                report_stage("postgresql-ready")
                os.environ["AI_STP_TEST_DB_URL"] = template_url
                for name, owner in [
                    ("ownership", verify_ownership),
                    ("corporate", verify_corporate),
                ]:
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
                            asyncio.run(
                                owner.prove(binary, url, fixture, credential_store="os_keyring")
                            )
                        finally:
                            close_api_log_files(fixture / "api")
                        report_stage(f"{name}-passed")
            report_stage("postgresql-stopped")
            proof = {
                "schema_version": 1,
                "evidence_kind": "native_cli_corporate_api_postgresql",
                "fixture_source_sha": source,
                "engine": identity,
                "source_run_attempt": int(os.environ["AI_STP_NATIVE_ENGINE_SOURCE_ATTEMPT"]),
                "database": database,
                "native_credential_store": "os_keyring",
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
