"""Operator-only local command for official upstream sources (SPEC-056 REQ-5601)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID, SOURCE_ID
from ai_stp_platform.official_upstream.errors import OfficialUpstreamError
from ai_stp_platform.official_upstream.source import (
    SourceUpsert,
    delete_source,
    disable_source,
    upsert_source,
)
from ai_stp_platform.settings import DatabaseSettings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configure independently identified official GitHub and package sources."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    upsert = sub.add_parser("upsert", help="Create or update one official source.")
    upsert.add_argument("--id", dest="source_id", default=SOURCE_ID)
    upsert.add_argument("--kind", choices=("git", "package"), default="git")
    upsert.add_argument("--repository")
    upsert.add_argument("--ref")
    upsert.add_argument("--path")
    upsert.add_argument("--ecosystem")
    upsert.add_argument("--package-name")
    upsert.add_argument("--package-version")
    upsert.add_argument("--package-filename")
    upsert.add_argument("--package-platform")
    upsert.add_argument("--type", dest="component_type", required=True)
    upsert.add_argument("--owner", default=OFFICIAL_ACCOUNT_ID)
    upsert.add_argument("--name", required=True)
    upsert.add_argument("--project-name", required=True)
    upsert.add_argument("--maintainer", required=True)
    upsert.add_argument("--description", required=True)
    upsert.add_argument("--license", required=True)
    upsert.add_argument("--harness-id", required=True)
    upsert.add_argument("--tags", default="code-review")
    upsert.add_argument("--projection-kind", default="native_files")
    upsert.add_argument("--target-scope", choices=("global", "user_root", "project"), required=True)
    upsert.add_argument("--projection-root", required=True)
    upsert.add_argument("--projection-shape", choices=("file", "tree"), required=True)
    upsert.add_argument("--device-id")
    upsert.add_argument("--disable", action="store_true")
    disable = sub.add_parser("disable", help="Stop future enqueue without deleting history.")
    disable.add_argument("--id", dest="source_id", default=SOURCE_ID)
    delete = sub.add_parser("delete", help="Delete the source row; published versions remain.")
    delete.add_argument("--id", dest="source_id", default=SOURCE_ID)
    return parser


async def _execute(args: argparse.Namespace) -> dict[str, object]:
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    sessionmaker = make_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            if args.command == "upsert":
                source = await upsert_source(
                    session,
                    SourceUpsert(
                        source_id=str(args.source_id),
                        kind=str(args.kind),
                        repository_url=str(args.repository or ""),
                        tracked_ref=str(args.ref or ""),
                        component_subpath=str(args.path or ""),
                        ecosystem=None if args.ecosystem is None else str(args.ecosystem),
                        package_name=None if args.package_name is None else str(args.package_name),
                        package_version=None
                        if args.package_version is None
                        else str(args.package_version),
                        package_filename=None
                        if args.package_filename is None
                        else str(args.package_filename),
                        package_platform=None
                        if args.package_platform is None
                        else str(args.package_platform),
                        component_type=args.component_type,
                        owner_account_id=args.owner,
                        name=args.name,
                        upstream_project_name=args.project_name,
                        upstream_maintainer=args.maintainer,
                        reviewed_description=args.description,
                        reviewed_license=args.license,
                        harness_id=args.harness_id,
                        tags=tuple(tag.strip() for tag in str(args.tags).split(",") if tag.strip()),
                        projection_kind=args.projection_kind,
                        target_scope=args.target_scope,
                        projection_root=args.projection_root,
                        projection_shape=args.projection_shape,
                        actor_device_id=args.device_id,
                        enabled=not args.disable,
                    ),
                )
                await session.commit()
                return {
                    "id": source.id,
                    "kind": source.kind,
                    "stable_id": source.stable_id,
                    "enabled": source.enabled,
                    "repository_url": source.repository_url,
                    "ecosystem": source.ecosystem,
                    "package_name": source.package_name,
                }
            source_id = str(args.source_id)
            if args.command == "disable":
                source = await disable_source(session, source_id)
                await session.commit()
                return {"disabled": source is not None, "id": source_id}
            deleted = await delete_source(session, source_id)
            await session.commit()
            return {"deleted": deleted, "id": source_id}
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = asyncio.run(_execute(args))
    except OfficialUpstreamError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
