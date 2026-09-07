"""Construct a historical CLI registry from its real migration statements."""

import sqlite3
from pathlib import Path

from ai_stp_cli.local.database import MIGRATIONS, schema_version


def historical_registry(path: Path, version: int) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        for migration in MIGRATIONS:
            if migration.version > version:
                break
            connection.execute("BEGIN IMMEDIATE")
            for statement in migration.up:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version={migration.version}")
            connection.execute("COMMIT")
        assert schema_version(connection) == version
        return connection
    except BaseException:
        connection.close()
        raise
