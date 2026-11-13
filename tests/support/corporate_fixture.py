"""Seed an owned corporate account and project through the actual API/database."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateProjectMember,
    ProjectIdentity,
)


async def seed_corporate(app: Any, origin: str) -> tuple[str, str, str]:
    account, project = new_id("account"), new_id("remote_project")
    async with app.state.sessionmaker() as db:
        db.add(Account(id=account))
        await db.commit()
    async with AsyncClient(base_url=origin, timeout=15, trust_env=False) as client:
        response = await client.post(
            "/v1/corporate/bootstrap",
            json={
                "organization_name": "Installed fixture company",
                "superadmin_account_id": account,
                "idempotency_key": "installed-desktop-corporate-bootstrap",
            },
            headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
        )
        assert response.status_code == 200
        organization = response.json()["organization_id"]
        assert isinstance(organization, str)
    async with app.state.sessionmaker() as db:
        db.add(
            ProjectIdentity(
                id=project,
                organization_id=organization,
                namespace="remote",
                external_key="installed-desktop:shared-project",
                display_name="Installed shared project",
            )
        )
        await db.flush()
        db.add(
            CorporateProject(
                id=project, organization_id=organization, name="Installed shared project"
            )
        )
        await db.flush()
        db.add(
            CorporateProjectMember(
                organization_id=organization, project_id=project, account_id=account, role="owner"
            )
        )
        await db.commit()
    return account, organization, project


def create_checkout_fixture(directory: Path, canary: bytes, environment: dict[str, str]) -> Path:
    """Create an owned committed checkout without reading global Git configuration."""
    executable = shutil.which("git")
    assert executable is not None, "The native runner requires its existing Git executable"
    git = Path(executable).resolve(strict=True)
    assert git.is_absolute() and git.is_file()
    directory.mkdir()
    (directory / ".env").write_bytes(canary)
    (directory / ".env").chmod(0o640)
    for arguments in (
        ["init", "--initial-branch=main"],
        ["commit", "--allow-empty", "-m", "Installed corporate checkout fixture"],
    ):
        subprocess.run(
            [
                str(git),
                "-C",
                str(directory),
                "-c",
                "user.name=Installed fixture",
                "-c",
                "user.email=installed@example.invalid",
                *arguments,
            ],
            check=True,
            capture_output=True,
            env={
                **{
                    key: value
                    for key, value in environment.items()
                    if not key.upper().startswith("GIT_")
                },
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
            },
            timeout=15,
        )
    return git
