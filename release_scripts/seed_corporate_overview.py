"""Run explicitly against the local development database after taking a backup."""

import argparse
import asyncio
import os
from hashlib import sha256
from pathlib import Path

from tests.support.corporate_overview_seed import seed_demo

from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.settings import DatabaseSettings


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--expected-revision", type=int, required=True)
    parser.add_argument("--digest")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    digest = sha256(Path("tests/support/corporate_overview_seed.py").read_bytes()).hexdigest()
    if not args.apply:
        print(f"Plan: populate local Twinby demo in {args.organization}; fixture sha256:{digest}")
        return
    if (
        os.environ.get("API_ENVIRONMENT") not in {"dev", "development", "local"}
        or args.digest != digest
    ):
        raise ValueError("explicit development environment and exact fixture digest required")
    engine = make_engine(DatabaseSettings())  # pyright: ignore[reportCallIssue]
    try:
        async with make_sessionmaker(engine)() as db:
            result = await seed_demo(db, args.organization, args.expected_revision)
            await db.commit()
            print(result)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
