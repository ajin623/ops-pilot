#!/usr/bin/env python3
"""Initialize and validate the containerized analytical database."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Literal

import psycopg
from psycopg import sql

from scripts import load_postgres


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = PROJECT_ROOT / "sql" / "schema.sql"
VIEW_SQL_FILES = (
    PROJECT_ROOT / "sql" / "analytics_views.sql",
    PROJECT_ROOT / "sql" / "kpis.sql",
    PROJECT_ROOT / "sql" / "delivery_detection.sql",
)
EXPECTED_VIEW_ROWS = {
    "order_facts": 99_441,
    "monthly_kpis": 20,
    "monthly_delivery_comparison": 19,
}


def connection_arguments() -> dict[str, object]:
    """Build validated PostgreSQL connection arguments."""

    port_text = load_postgres.required_environment_variable(
        "POSTGRES_PORT"
    )

    try:
        port = int(port_text)
    except ValueError as error:
        raise RuntimeError(
            "POSTGRES_PORT must be an integer."
        ) from error

    if not 1 <= port <= 65_535:
        raise RuntimeError(
            "POSTGRES_PORT must be between 1 and 65535."
        )

    return {
        "dbname": load_postgres.required_environment_variable(
            "POSTGRES_DB"
        ),
        "user": load_postgres.required_environment_variable(
            "POSTGRES_USER"
        ),
        "password": load_postgres.required_environment_variable(
            "POSTGRES_PASSWORD"
        ),
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": port,
        "connect_timeout": 10,
        "autocommit": True,
    }


def expected_table_rows() -> dict[str, int]:
    """Return the required base-table row counts."""

    return {
        dataset.table_name: dataset.expected_rows
        for dataset in load_postgres.DATASETS
    }


def classify_table_counts(
    table_counts: dict[str, int],
) -> Literal["empty", "loaded"]:
    """Classify a complete base-table set."""

    expected = expected_table_rows()

    if set(table_counts) != set(expected):
        missing = sorted(
            set(expected) - set(table_counts)
        )
        unexpected = sorted(
            set(table_counts) - set(expected)
        )

        raise RuntimeError(
            "Database table set is incomplete. "
            f"Missing: {missing}; "
            f"unexpected: {unexpected}."
        )

    if all(
        row_count == 0
        for row_count in table_counts.values()
    ):
        return "empty"

    if table_counts == expected:
        return "loaded"

    details = ", ".join(
        (
            f"{table_name}={table_counts[table_name]:,}"
            f"/{expected[table_name]:,}"
        )
        for table_name in sorted(expected)
    )

    raise RuntimeError(
        "Database contains a partial or unexpected load. "
        f"Row counts: {details}"
    )


def fetch_existing_tables(
    connection: psycopg.Connection[Any],
) -> set[str]:
    """Return the expected base tables that currently exist."""

    table_names = sorted(expected_table_rows())

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
              AND table_name = ANY(%s)
            ORDER BY table_name;
            """,
            (
                load_postgres.SCHEMA_NAME,
                table_names,
            ),
        )

        return {
            str(row[0])
            for row in cursor.fetchall()
        }


def fetch_table_counts(
    connection: psycopg.Connection[Any],
) -> dict[str, int]:
    """Return current row counts for every base table."""

    counts: dict[str, int] = {}

    with connection.cursor() as cursor:
        for table_name in sorted(expected_table_rows()):
            cursor.execute(
                sql.SQL(
                    "SELECT COUNT(*) FROM {}"
                ).format(
                    load_postgres.qualified_table(
                        table_name
                    )
                )
            )

            counts[table_name] = int(
                cursor.fetchone()[0]
            )

    return counts


def execute_sql_file(
    connection: psycopg.Connection[Any],
    path: Path,
) -> None:
    """Execute a validated multi-statement SQL file."""

    statement = path.read_text(encoding="utf-8")

    print(f"Applying {path.relative_to(PROJECT_ROOT)}")

    with connection.cursor() as cursor:
        cursor.execute(
            statement,
            prepare=False,
        )


def validate_view_rows(
    connection: psycopg.Connection[Any],
) -> None:
    """Validate the analytical view contracts."""

    with connection.cursor() as cursor:
        for view_name, expected_rows in (
            EXPECTED_VIEW_ROWS.items()
        ):
            cursor.execute(
                sql.SQL(
                    "SELECT COUNT(*) FROM {}.{}"
                ).format(
                    sql.Identifier(
                        load_postgres.SCHEMA_NAME
                    ),
                    sql.Identifier(view_name),
                )
            )

            actual_rows = int(
                cursor.fetchone()[0]
            )

            if actual_rows != expected_rows:
                raise RuntimeError(
                    f"{view_name} has "
                    f"{actual_rows:,} rows; expected "
                    f"{expected_rows:,}."
                )

            print(
                f"[OK] {view_name:<28} "
                f"rows={actual_rows:>7,}"
            )


def main() -> int:
    """Bootstrap or validate the analytical database."""

    arguments = connection_arguments()
    expected_tables = set(expected_table_rows())
    should_load = False

    print("Inspecting database state")

    with psycopg.connect(
        **arguments
    ) as connection:
        existing_tables = fetch_existing_tables(
            connection
        )

        if not existing_tables:
            print(
                "No OpsPilot base tables found; "
                "creating schema."
            )
            execute_sql_file(
                connection,
                SCHEMA_SQL,
            )
            existing_tables = fetch_existing_tables(
                connection
            )

        if existing_tables != expected_tables:
            missing_tables = sorted(
                expected_tables - existing_tables
            )

            raise RuntimeError(
                "OpsPilot base-table contract is incomplete. "
                f"Missing tables: {missing_tables}"
            )

        table_counts = fetch_table_counts(
            connection
        )
        database_state = classify_table_counts(
            table_counts
        )

        if database_state == "empty":
            print(
                "Base tables are empty; loading "
                "processed Olist data."
            )
            should_load = True
        else:
            print(
                "Base tables already contain the "
                "validated dataset; load skipped."
            )

    if should_load:
        result = load_postgres.main()

        if result != 0:
            raise RuntimeError(
                "PostgreSQL data loading failed."
            )

    print("\nValidating base-table row counts")

    with psycopg.connect(
        **arguments
    ) as connection:
        loaded_counts = fetch_table_counts(
            connection
        )

        if classify_table_counts(
            loaded_counts
        ) != "loaded":
            raise RuntimeError(
                "Database did not reach the loaded state."
            )

        for table_name in sorted(loaded_counts):
            print(
                f"[OK] {table_name:<12} "
                f"rows={loaded_counts[table_name]:>7,}"
            )

        print("\nBuilding analytical views")

        for sql_path in VIEW_SQL_FILES:
            execute_sql_file(
                connection,
                sql_path,
            )

        print("\nValidating analytical views")
        validate_view_rows(connection)

    print("\nRESULT: DATABASE BOOTSTRAP PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            "\nRESULT: DATABASE BOOTSTRAP FAILED",
            file=sys.stderr,
        )
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)
