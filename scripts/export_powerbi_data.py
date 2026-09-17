#!/usr/bin/env python3
"""Export compact, deterministic datasets for Power BI."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

import generate_delivery_brief


MONTHLY_KPIS_QUERY = """
SELECT *
FROM opspilot.monthly_kpis
ORDER BY purchase_month;
"""

DELIVERY_COMPARISONS_QUERY = """
SELECT
    comparison.*,

    (
        comparison.is_consecutive_month
        AND comparison.on_time_delivery_change_pp <= -5.00
    ) AS is_delivery_issue,

    CASE
        WHEN comparison.is_consecutive_month
         AND comparison.on_time_delivery_change_pp <= -8.00
        THEN 'High'

        WHEN comparison.is_consecutive_month
         AND comparison.on_time_delivery_change_pp <= -5.00
        THEN 'Moderate'

        ELSE NULL
    END AS issue_severity

FROM opspilot.monthly_delivery_comparison AS comparison

ORDER BY comparison.current_month;
"""


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Export compact OpsPilot datasets for Power BI."
        )
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Optional export directory. The default is "
            "data/exports/powerbi."
        ),
    )

    return parser.parse_args()


def fetch_rows(
    connection: psycopg.Connection[Any],
    query: str,
) -> list[dict[str, Any]]:
    """Execute a query and return dictionary rows."""

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query)
        rows = list(cursor.fetchall())

    if not rows:
        raise RuntimeError(
            "A required Power BI dataset was empty."
        )

    return rows


def serialize_value(value: Any) -> str:
    """Serialize a database value deterministically."""

    if value is None:
        return ""

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return format(value, "f")

    return str(value)


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    """Write rows to a UTF-8 CSV file atomically."""

    if not rows:
        raise RuntimeError(
            f"Cannot write empty dataset to {path}."
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    fieldnames = tuple(rows[0].keys())

    with temporary_path.open(
        mode="w",
        encoding="utf-8",
        newline="",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=fieldnames,
            extrasaction="raise",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    key: serialize_value(row[key])
                    for key in fieldnames
                }
            )

    temporary_path.replace(path)


def issue_context(
    issue: dict[str, Any],
) -> dict[str, Any]:
    """Return common dimensions for issue detail rows."""

    return {
        "issue_id": (
            "delivery-"
            f"{issue['current_month']:%Y-%m}"
        ),
        "previous_month": issue["previous_month"],
        "current_month": issue["current_month"],
        "issue_change_pp": (
            issue["on_time_delivery_change_pp"]
        ),
        "issue_severity": issue["issue_severity"],
    }


def main() -> int:
    """Export the Power BI analytical datasets."""

    arguments = parse_arguments()

    project_root = Path(__file__).resolve().parents[1]

    if arguments.output_dir is None:
        output_directory = (
            project_root
            / "data"
            / "exports"
            / "powerbi"
        )
    else:
        output_directory = (
            arguments.output_dir.expanduser()
        )

        if not output_directory.is_absolute():
            output_directory = (
                Path.cwd() / output_directory
            )

    connection_parameters = (
        generate_delivery_brief.connection_arguments()
    )

    with psycopg.connect(
        **connection_parameters
    ) as connection:
        monthly_kpis = fetch_rows(
            connection,
            MONTHLY_KPIS_QUERY,
        )

        delivery_comparisons = fetch_rows(
            connection,
            DELIVERY_COMPARISONS_QUERY,
        )

    detected_issues = [
        row
        for row in delivery_comparisons
        if row["is_delivery_issue"]
    ]

    if not detected_issues:
        raise RuntimeError(
            "No delivery issues were available for export."
        )

    state_rows: list[dict[str, Any]] = []
    seller_rows: list[dict[str, Any]] = []

    investigation_path = (
        project_root
        / "sql"
        / "investigate_delivery_issue.sql"
    )

    for detected_issue in detected_issues:
        with psycopg.connect(
            **connection_parameters
        ) as connection:
            issue = (
                generate_delivery_brief.fetch_selected_issue(
                    connection,
                    detected_issue["current_month"],
                )
            )

            issue["issue_severity"] = (
                detected_issue["issue_severity"]
            )

            generate_delivery_brief.configure_investigation_target(
                connection,
                issue["current_month"],
            )

            result_sets = (
                generate_delivery_brief.execute_investigation(
                    connection,
                    investigation_path,
                )
            )

        context = issue_context(issue)

        state_rows.extend(
            {
                **context,
                **row,
            }
            for row in result_sets[2]
        )

        seller_rows.extend(
            {
                **context,
                **row,
            }
            for row in result_sets[4]
        )

    exports = (
        (
            "monthly_kpis.csv",
            monthly_kpis,
        ),
        (
            "delivery_comparisons.csv",
            delivery_comparisons,
        ),
        (
            "delivery_issue_states.csv",
            state_rows,
        ),
        (
            "delivery_issue_sellers.csv",
            seller_rows,
        ),
    )

    for filename, rows in exports:
        output_path = output_directory / filename

        write_csv(
            output_path,
            rows,
        )

        print(
            f"{filename}: {len(rows)} rows"
        )

    print(f"Output directory: {output_directory}")
    print("RESULT: POWER BI EXPORT COMPLETED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
