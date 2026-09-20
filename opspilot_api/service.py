"""Database access for the read-only OpsPilot API."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from scripts import generate_delivery_brief


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVESTIGATION_SQL = (
    PROJECT_ROOT
    / "sql"
    / "investigate_delivery_issue.sql"
)

ISSUES_QUERY = """
SELECT
    previous_month,
    current_month,
    current_order_count,
    current_delivery_kpi_order_count,
    current_on_time_delivery_count,
    current_on_time_delivery_rate_pct,
    previous_on_time_delivery_rate_pct,
    on_time_delivery_change_pp,
    current_average_delivery_days,
    average_delivery_days_change,
    current_average_order_review_score,
    average_review_score_change
FROM opspilot.monthly_delivery_comparison
WHERE is_consecutive_month
  AND on_time_delivery_change_pp <= -5.00
ORDER BY
    on_time_delivery_change_pp ASC,
    current_delivery_kpi_order_count DESC,
    current_month ASC;
"""

ISSUE_QUERY = """
SELECT
    previous_month,
    current_month,
    current_order_count,
    current_delivery_kpi_order_count,
    current_on_time_delivery_count,
    current_on_time_delivery_rate_pct,
    previous_on_time_delivery_rate_pct,
    on_time_delivery_change_pp,
    current_average_delivery_days,
    average_delivery_days_change,
    current_average_order_review_score,
    average_review_score_change
FROM opspilot.monthly_delivery_comparison
WHERE is_consecutive_month
  AND on_time_delivery_change_pp <= -5.00
  AND current_month = %s;
"""


def parse_month(value: str) -> date:
    """Parse an API month in YYYY-MM format."""

    try:
        return generate_delivery_brief.parse_month(value)
    except argparse.ArgumentTypeError as error:
        raise ValueError(
            "month must use YYYY-MM format"
        ) from error


def check_database() -> None:
    """Verify that PostgreSQL is reachable."""

    with psycopg.connect(
        **generate_delivery_brief.connection_arguments()
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")

            if cursor.fetchone() != (1,):
                raise RuntimeError(
                    "Database health query returned "
                    "an unexpected result."
                )


def fetch_issues() -> list[dict[str, Any]]:
    """Return all qualifying delivery issues."""

    with psycopg.connect(
        **generate_delivery_brief.connection_arguments()
    ) as connection:
        with connection.cursor(
            row_factory=dict_row
        ) as cursor:
            cursor.execute(ISSUES_QUERY)
            return list(cursor.fetchall())


def fetch_issue(
    current_month: date,
) -> dict[str, Any] | None:
    """Return one qualifying delivery issue."""

    with psycopg.connect(
        **generate_delivery_brief.connection_arguments()
    ) as connection:
        with connection.cursor(
            row_factory=dict_row
        ) as cursor:
            cursor.execute(
                ISSUE_QUERY,
                (current_month,),
            )
            return cursor.fetchone()


def execute_issue_investigation(
    current_month: date,
) -> list[list[dict[str, Any]]]:
    """Execute the validated five-table investigation."""

    with psycopg.connect(
        **generate_delivery_brief.connection_arguments()
    ) as connection:
        generate_delivery_brief.fetch_selected_issue(
            connection,
            current_month,
        )
        generate_delivery_brief.configure_investigation_target(
            connection,
            current_month,
        )

        return generate_delivery_brief.execute_investigation(
            connection,
            INVESTIGATION_SQL,
        )
