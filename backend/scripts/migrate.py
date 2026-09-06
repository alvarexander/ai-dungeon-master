"""Applies the numbered SQL migration files to a MySQL database, in order.

WHAT A MIGRATION RUNNER DOES
The `migrations/` folder holds numbered SQL files. This script applies any that
have not been applied yet, in order, and records each one in the
`schema_migrations` table along with a checksum of its contents.

The checksum matters. If a file that has already run is later edited, the
checksums no longer agree and this script stops, because your database and your
migration files have silently diverged — which is much harder to diagnose later
than it is to fix now.

WHY THIS IS NOT ALEMBIC'S AUTOGENERATE
Alembic can generate migrations by comparing Python models to the database.
That is convenient and wrong for this project: it cannot see stored procedures,
and it does not understand that a VARBINARY column is a deliberate encrypted
field — given a model saying "email is a string" it would offer to convert the
ciphertext column to VARCHAR and corrupt every row. So migrations are written
by hand and this applies them.

PHASE 1 STATUS
Not used yet. Phase 1 runs with no database. This exists so that the schema is
runnable rather than hypothetical, and so Phase 2 is a configuration change
rather than a project.

RUN IT WITH
    uv sync --extra db
    DATABASE_URL='mysql+aiomysql://user:pass@host:3306/dungeon_master' \
        uv run python scripts/migrate.py
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def split_statements(sql: str) -> list[str]:
    """Split a migration file into individual statements.

    Handles the ``DELIMITER`` instruction, which stored procedures need. A
    procedure body contains semicolons, but a semicolon is also how a statement
    ends, so ``DELIMITER $$`` temporarily changes the end-of-statement marker.
    It is a client instruction rather than SQL, so the database driver does not
    understand it and this function must.

    Args:
        sql: The complete contents of a migration file.

    Returns:
        The statements, in order, ready to execute one at a time.
    """
    statements: list[str] = []
    delimiter = ";"
    buffer: list[str] = []

    for line in sql.splitlines():
        stripped = line.strip()

        if stripped.startswith("--") or not stripped:
            continue

        delimiter_change = re.match(r"^DELIMITER\s+(\S+)$", stripped, re.IGNORECASE)
        if delimiter_change:
            # Flush anything pending before the marker changes.
            if buffer:
                statements.append("\n".join(buffer).strip())
                buffer = []
            delimiter = delimiter_change.group(1)
            continue

        buffer.append(line)
        if stripped.endswith(delimiter):
            statement = "\n".join(buffer).strip()
            statement = statement[: -len(delimiter)].strip()
            if statement:
                statements.append(statement)
            buffer = []

    if buffer:
        remaining = "\n".join(buffer).strip()
        if remaining:
            statements.append(remaining)

    return statements


async def run(database_url: str) -> int:
    """Apply every pending migration.

    Args:
        database_url: A SQLAlchemy connection string.

    Returns:
        0 on success, 1 on failure.
    """
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError:
        print("Database libraries are not installed. Run: uv sync --extra db")  # noqa: T201
        return 1

    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  version VARCHAR(64) NOT NULL PRIMARY KEY,"
                "  applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),"
                "  checksum CHAR(64) NOT NULL"
                ") ENGINE=InnoDB"
            )
        )
        rows = await connection.execute(text("SELECT version, checksum FROM schema_migrations"))
        applied = {row[0]: row[1] for row in rows}

    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        print(f"No migration files found in {MIGRATIONS_DIR}")  # noqa: T201
        return 1

    for path in files:
        version = path.name.split("_", 1)[0]
        body = path.read_text()
        checksum = hashlib.sha256(body.encode()).hexdigest()

        if version in applied:
            if applied[version] != checksum:
                print(  # noqa: T201
                    f"REFUSING TO CONTINUE: migration {path.name} has already been applied, "
                    "but its contents have changed since.\n"
                    "An already-applied migration must never be edited — your database and "
                    "your files have diverged. Write a NEW numbered migration instead, and "
                    "restore this file to its original contents."
                )
                return 1
            print(f"  {path.name}: already applied")  # noqa: T201
            continue

        print(f"  {path.name}: applying...")  # noqa: T201
        statements = split_statements(body)
        async with engine.begin() as connection:
            for statement in statements:
                if statement.upper().startswith("INSERT INTO SCHEMA_MIGRATIONS"):
                    continue  # recorded below, with the real checksum
                await connection.execute(text(statement))
            await connection.execute(
                text(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (:v, :c) "
                    "ON DUPLICATE KEY UPDATE checksum = :c"
                ),
                {"v": version, "c": checksum},
            )
        print(f"  {path.name}: done ({len(statements)} statements)")  # noqa: T201

    await engine.dispose()
    print("\nAll migrations applied.")  # noqa: T201
    return 0


if __name__ == "__main__":
    import asyncio

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print(  # noqa: T201
            "DATABASE_URL is not set. Example:\n"
            "  DATABASE_URL='mysql+aiomysql://dm_app:PASSWORD@host:3306/dungeon_master' \\\n"
            "      uv run python scripts/migrate.py"
        )
        sys.exit(1)
    sys.exit(asyncio.run(run(url)))
