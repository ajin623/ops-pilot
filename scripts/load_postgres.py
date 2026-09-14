#!/usr/bin/env python3

from __future__ import annotations

import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIRECTORY = PROJECT_ROOT / "data" / "processed" / "olist"
SCHEMA_NAME = "opspilot"
COPY_BLOCK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class Dataset:
    table_name: str
    filename: str
    expected_rows: int


DATASETS = (
    Dataset("customers", "customers.csv", 99_441),
    Dataset("products", "products.csv", 32_951),
    Dataset("sellers", "sellers.csv", 3_095),
    Dataset("orders", "orders.csv", 99_441),
    Dataset("order_items", "order_items.csv", 112_650),
    Dataset("payments", "payments.csv", 103_886),
    Dataset("reviews", "reviews.csv", 99_224),
)


def required_environment_variable(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Required environment variable is missing: {name}"
        )

    return value


def inspect_csv(path: Path) -> tuple[list[str], int]:
    if not path.is_file():
        raise FileNotFoundError(f"Processed CSV does not exist: {path}")

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file_handle:
        reader = csv.reader(file_handle)

        try:
            header = next(reader)
        except StopIteration as error:
            raise RuntimeError(f"CSV file is empty: {path}") from error

        if not header or any(not column.strip() for column in header):
            raise RuntimeError(f"CSV has an invalid header: {path}")

        if len(header) != len(set(header)):
            raise RuntimeError(
                f"CSV contains duplicate column names: {path}"
            )

        row_count = sum(1 for _ in reader)

    return header, row_count


def qualified_table(table_name: str) -> sql.Identifier:
    return sql.Identifier(SCHEMA_NAME, table_name)


def main() -> int:
    database_name = required_environment_variable("POSTGRES_DB")
    database_user = required_environment_variable("POSTGRES_USER")
    database_password = required_environment_variable(
        "POSTGRES_PASSWORD"
    )

    database_host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    database_port_text = required_environment_variable("POSTGRES_PORT")

    try:
        database_port = int(database_port_text)
    except ValueError as error:
        raise RuntimeError(
            "POSTGRES_PORT must be an integer"
        ) from error

    if not 1 <= database_port <= 65_535:
        raise RuntimeError(
            "POSTGRES_PORT must be between 1 and 65535"
        )

    print(f"Processed data directory: {PROCESSED_DIRECTORY}")
    print("\nCSV preflight")

    csv_metadata: dict[str, tuple[Path, list[str], int]] = {}

    for dataset in DATASETS:
        csv_path = PROCESSED_DIRECTORY / dataset.filename
        header, row_count = inspect_csv(csv_path)

        if row_count != dataset.expected_rows:
            raise RuntimeError(
                f"{dataset.filename} has {row_count:,} rows; "
                f"expected {dataset.expected_rows:,}"
            )

        csv_metadata[dataset.table_name] = (
            csv_path,
            header,
            row_count,
        )

        print(
            f"[OK] {dataset.table_name:<12} "
            f"rows={row_count:>7,} columns={len(header)}"
        )

    connection_arguments = {
        "host": database_host,
        "port": database_port,
        "dbname": database_name,
        "user": database_user,
        "password": database_password,
        "connect_timeout": 10,
    }

    with psycopg.connect(**connection_arguments) as connection:
        with connection.cursor() as cursor:
            print("\nDatabase preflight")

            cursor.execute(
                """
                SELECT schema_owner
                FROM information_schema.schemata
                WHERE schema_name = %s
                """,
                (SCHEMA_NAME,),
            )

            schema_record = cursor.fetchone()

            if schema_record is None:
                raise RuntimeError(
                    f"Database schema does not exist: {SCHEMA_NAME}"
                )

            print(
                f"[OK] schema={SCHEMA_NAME} "
                f"owner={schema_record[0]}"
            )

            existing_rows: dict[str, int] = {}

            for dataset in DATASETS:
                csv_path, csv_columns, _ = csv_metadata[
                    dataset.table_name
                ]

                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (SCHEMA_NAME, dataset.table_name),
                )

                database_columns = [
                    row[0]
                    for row in cursor.fetchall()
                ]

                if not database_columns:
                    raise RuntimeError(
                        "Database table does not exist: "
                        f"{SCHEMA_NAME}.{dataset.table_name}"
                    )

                if database_columns != csv_columns:
                    raise RuntimeError(
                        f"Column mismatch for {dataset.table_name}\n"
                        f"Database columns: {database_columns}\n"
                        f"CSV columns:      {csv_columns}\n"
                        f"CSV file:         {csv_path}"
                    )

                cursor.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(
                        qualified_table(dataset.table_name)
                    )
                )

                existing_rows[dataset.table_name] = int(
                    cursor.fetchone()[0]
                )

                print(
                    f"[OK] {dataset.table_name:<12} "
                    f"columns={len(database_columns)} "
                    f"existing_rows="
                    f"{existing_rows[dataset.table_name]:,}"
                )

            nonempty_tables = {
                table_name: row_count
                for table_name, row_count in existing_rows.items()
                if row_count != 0
            }

            if nonempty_tables:
                details = ", ".join(
                    f"{table_name}={row_count:,}"
                    for table_name, row_count
                    in nonempty_tables.items()
                )

                raise RuntimeError(
                    "Refusing to load into nonempty tables. "
                    f"Existing rows: {details}"
                )

            print("\nLoading processed data")

            for dataset in DATASETS:
                csv_path, csv_columns, expected_rows = csv_metadata[
                    dataset.table_name
                ]

                column_identifiers = sql.SQL(", ").join(
                    sql.Identifier(column)
                    for column in csv_columns
                )

                copy_statement = sql.SQL(
                    """
                    COPY {} ({})
                    FROM STDIN
                    WITH (
                        FORMAT CSV,
                        HEADER TRUE,
                        NULL ''
                    )
                    """
                ).format(
                    qualified_table(dataset.table_name),
                    column_identifiers,
                )

                with csv_path.open("rb") as file_handle:
                    with cursor.copy(copy_statement) as copy:
                        while True:
                            block = file_handle.read(COPY_BLOCK_SIZE)

                            if not block:
                                break

                            copy.write(block)

                cursor.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(
                        qualified_table(dataset.table_name)
                    )
                )

                loaded_rows = int(cursor.fetchone()[0])

                if loaded_rows != expected_rows:
                    raise RuntimeError(
                        f"Row-count validation failed for "
                        f"{dataset.table_name}: loaded "
                        f"{loaded_rows:,}, expected "
                        f"{expected_rows:,}"
                    )

                print(
                    f"[LOADED] {dataset.table_name:<12} "
                    f"rows={loaded_rows:>7,}"
                )

            print("\nUpdating PostgreSQL statistics")

            for dataset in DATASETS:
                cursor.execute(
                    sql.SQL("ANALYZE {}").format(
                        qualified_table(dataset.table_name)
                    )
                )

            print("[OK] PostgreSQL statistics updated")

    print("\nFinal row counts")

    with psycopg.connect(**connection_arguments) as connection:
        with connection.cursor() as cursor:
            for dataset in DATASETS:
                cursor.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(
                        qualified_table(dataset.table_name)
                    )
                )

                row_count = int(cursor.fetchone()[0])

                print(
                    f"{dataset.table_name:<12} {row_count:>7,}"
                )

    print("\nRESULT: POSTGRESQL LOAD PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            "\nRESULT: POSTGRESQL LOAD FAILED",
            file=sys.stderr,
        )
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)