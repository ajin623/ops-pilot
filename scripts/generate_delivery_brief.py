#!/usr/bin/env python3
"""Generate an evidence-backed delivery incident brief."""

from __future__ import annotations

import argparse
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


TARGET_QUERY = """
SELECT
    previous_month,
    current_month,
    on_time_delivery_change_pp
FROM opspilot.monthly_delivery_comparison
WHERE is_consecutive_month
  AND on_time_delivery_change_pp <= -5.00
  AND (
      %s::DATE IS NULL
      OR current_month = %s::DATE
  )
ORDER BY
    on_time_delivery_change_pp ASC,
    current_delivery_kpi_order_count DESC,
    current_month ASC
LIMIT 1;
"""

EXPECTED_FIRST_COLUMNS = (
    "period_label",
    "previous_eligible_orders",
    "customer_state",
    "period_label",
    "seller_id",
)


def required_environment_variable(name: str) -> str:
    """Return a required non-empty environment variable."""

    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Required environment variable {name} is missing."
        )

    return value


def connection_arguments() -> dict[str, object]:
    """Build validated PostgreSQL connection arguments."""

    port_text = required_environment_variable("POSTGRES_PORT")

    try:
        port = int(port_text)
    except ValueError as error:
        raise RuntimeError(
            "POSTGRES_PORT must be an integer."
        ) from error

    if not 1 <= port <= 65535:
        raise RuntimeError(
            "POSTGRES_PORT must be between 1 and 65535."
        )

    return {
        "dbname": required_environment_variable("POSTGRES_DB"),
        "user": required_environment_variable("POSTGRES_USER"),
        "password": required_environment_variable(
            "POSTGRES_PASSWORD"
        ),
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": port,
        "autocommit": True,
    }


def decimal_value(value: Any) -> Decimal:
    """Convert a database numeric value to Decimal."""

    if value is None:
        raise RuntimeError(
            "An expected numeric investigation value was null."
        )

    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


def format_decimal(
    value: Any,
    digits: int = 2,
) -> str:
    """Format a numeric value for the report."""

    return f"{decimal_value(value):,.{digits}f}"


def format_signed(
    value: Any,
    digits: int = 2,
    suffix: str = "",
) -> str:
    """Format a signed numeric change."""

    numeric_value = decimal_value(value)
    prefix = "+" if numeric_value > 0 else ""

    return (
        f"{prefix}{numeric_value:,.{digits}f}"
        f"{suffix}"
    )


def format_integer(value: Any) -> str:
    """Format an integer-like database value."""

    return f"{int(value):,}"


def escape_markdown(value: Any) -> str:
    """Escape table-breaking Markdown characters."""

    return str(value).replace("|", "\\|")


def markdown_table(
    headers: tuple[str, ...],
    rows: list[tuple[Any, ...]],
) -> str:
    """Render a compact GitHub-flavored Markdown table."""

    if any(len(row) != len(headers) for row in rows):
        raise RuntimeError(
            "A Markdown table row has an unexpected width."
        )

    lines = [
        "| "
        + " | ".join(
            escape_markdown(header)
            for header in headers
        )
        + " |",
        "| "
        + " | ".join("---" for _ in headers)
        + " |",
    ]

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                escape_markdown(value)
                for value in row
            )
            + " |"
        )

    return "\n".join(lines)


def fetch_selected_issue(
    connection: psycopg.Connection[Any],
    requested_current_month: date | None = None,
) -> dict[str, Any]:
    """Fetch the requested issue or the most severe issue."""

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            TARGET_QUERY,
            (
                requested_current_month,
                requested_current_month,
            ),
        )
        issue = cursor.fetchone()

    if issue is None:
        if requested_current_month is not None:
            raise RuntimeError(
                "No qualifying delivery issue was detected for "
                f"{requested_current_month:%Y-%m}."
            )

        raise RuntimeError(
            "No qualifying delivery issue was detected."
        )

    return issue


def configure_investigation_target(
    connection: psycopg.Connection[Any],
    current_month: date,
) -> None:
    """Set the session-scoped investigation target."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT set_config(
                'opspilot.current_month',
                %s,
                false
            );
            """,
            (current_month.isoformat(),),
        )


def execute_investigation(
    connection: psycopg.Connection[Any],
    sql_path: Path,
) -> list[list[dict[str, Any]]]:
    """Execute the investigation and capture its five tables."""

    investigation_sql = sql_path.read_text(
        encoding="utf-8"
    )

    result_sets: list[list[dict[str, Any]]] = []
    first_columns: list[str] = []

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            investigation_sql,
            prepare=False,
        )

        while True:
            if cursor.description is not None:
                first_columns.append(
                    cursor.description[0].name
                )
                result_sets.append(
                    list(cursor.fetchall())
                )

            if not cursor.nextset():
                break

    if len(result_sets) != 5:
        raise RuntimeError(
            "Expected five investigation result sets, "
            f"received {len(result_sets)}."
        )

    if tuple(first_columns) != EXPECTED_FIRST_COLUMNS:
        raise RuntimeError(
            "The investigation result structure changed. "
            f"Received first columns: {first_columns}"
        )

    if any(not result_set for result_set in result_sets):
        raise RuntimeError(
            "One or more investigation result sets were empty."
        )

    return result_sets


def rows_by_period(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index period-labelled rows."""

    indexed = {
        str(row["period_label"]): row
        for row in rows
    }

    for period in ("previous", "current"):
        if period not in indexed:
            raise RuntimeError(
                f"The {period} period is missing."
            )

    return indexed


def build_report(
    issue: dict[str, Any],
    result_sets: list[list[dict[str, Any]]],
) -> str:
    """Build the operational incident brief."""

    (
        overall_rows,
        impact_rows,
        state_rows,
        coverage_rows,
        seller_rows,
    ) = result_sets

    overall = rows_by_period(overall_rows)
    coverage = rows_by_period(coverage_rows)

    previous = overall["previous"]
    current = overall["current"]
    impact = impact_rows[0]

    previous_month = issue["previous_month"]
    current_month = issue["current_month"]

    on_time_change = decimal_value(
        issue["on_time_delivery_change_pp"]
    )
    delivery_days_change = (
        decimal_value(current["average_delivery_days"])
        - decimal_value(previous["average_delivery_days"])
    )
    handling_days_change = (
        decimal_value(current["average_handling_days"])
        - decimal_value(previous["average_handling_days"])
    )
    carrier_days_change = (
        decimal_value(
            current["average_carrier_to_customer_days"]
        )
        - decimal_value(
            previous["average_carrier_to_customer_days"]
        )
    )
    promise_window_change = (
        decimal_value(
            current["average_promise_window_days"]
        )
        - decimal_value(
            previous["average_promise_window_days"]
        )
    )
    review_score_change = (
        decimal_value(
            current["average_order_review_score"]
        )
        - decimal_value(
            previous["average_order_review_score"]
        )
    )

    late_order_change = (
        int(current["late_orders"])
        - int(previous["late_orders"])
    )
    excess_late_orders = decimal_value(
        impact["excess_late_orders"]
    )

    top_states = state_rows[:5]
    top_sellers = seller_rows[:5]

    top_two_state_excess = sum(
        (
            decimal_value(row["excess_late_orders"])
            for row in state_rows[:2]
        ),
        Decimal("0"),
    )

    if excess_late_orders == 0:
        top_two_state_share = Decimal("0")
    else:
        top_two_state_share = (
            Decimal("100")
            * top_two_state_excess
            / excess_late_orders
        )

    focus_states = ", ".join(
        str(row["customer_state"])
        for row in state_rows[:3]
    )

    if on_time_change <= Decimal("-8"):
        severity = "High"
    else:
        severity = "Moderate"

    if (
        carrier_days_change >= Decimal("1")
        and abs(handling_days_change) <= Decimal("0.5")
    ):
        stage_diagnosis = (
            "The observed deterioration is concentrated after "
            "carrier handoff: carrier-to-customer time increased "
            f"by {format_decimal(carrier_days_change)} days, while "
            "average seller handling time was effectively stable "
            f"at {format_signed(handling_days_change)} days."
        )
    else:
        stage_diagnosis = (
            "Both fulfillment and downstream transport signals "
            "should be examined; the available timing measures do "
            "not isolate one operational stage strongly enough."
        )

    if promise_window_change < 0:
        promise_diagnosis = (
            "The average customer promise window narrowed by "
            f"{format_decimal(abs(promise_window_change))} days, "
            "which likely amplified the measured late-delivery "
            "rate."
        )
    else:
        promise_diagnosis = (
            "The average promise window did not narrow, so tighter "
            "delivery promises do not explain the deterioration."
        )

    metric_rows = [
        (
            "Delivery-eligible orders",
            format_integer(
                previous["delivery_eligible_orders"]
            ),
            format_integer(
                current["delivery_eligible_orders"]
            ),
            format_signed(
                int(current["delivery_eligible_orders"])
                - int(previous["delivery_eligible_orders"]),
                digits=0,
            ),
        ),
        (
            "On-time delivery rate",
            f"{format_decimal(previous['on_time_delivery_rate_pct'])}%",
            f"{format_decimal(current['on_time_delivery_rate_pct'])}%",
            format_signed(
                on_time_change,
                suffix=" pp",
            ),
        ),
        (
            "Late orders",
            format_integer(previous["late_orders"]),
            format_integer(current["late_orders"]),
            format_signed(
                late_order_change,
                digits=0,
            ),
        ),
        (
            "Average delivery days",
            format_decimal(previous["average_delivery_days"]),
            format_decimal(current["average_delivery_days"]),
            format_signed(
                delivery_days_change,
                suffix=" days",
            ),
        ),
        (
            "Average handling days",
            format_decimal(previous["average_handling_days"]),
            format_decimal(current["average_handling_days"]),
            format_signed(
                handling_days_change,
                suffix=" days",
            ),
        ),
        (
            "Carrier-to-customer days",
            format_decimal(
                previous["average_carrier_to_customer_days"]
            ),
            format_decimal(
                current["average_carrier_to_customer_days"]
            ),
            format_signed(
                carrier_days_change,
                suffix=" days",
            ),
        ),
        (
            "Average promise window",
            format_decimal(
                previous["average_promise_window_days"]
            ),
            format_decimal(
                current["average_promise_window_days"]
            ),
            format_signed(
                promise_window_change,
                suffix=" days",
            ),
        ),
        (
            "Average review score",
            format_decimal(
                previous["average_order_review_score"]
            ),
            format_decimal(
                current["average_order_review_score"]
            ),
            format_signed(review_score_change),
        ),
    ]

    state_table_rows = [
        (
            row["customer_state"],
            format_integer(row["current_eligible_orders"]),
            format_integer(row["current_late_orders"]),
            format_signed(
                row["on_time_change_pp"],
                suffix=" pp",
            ),
            format_decimal(row["excess_late_orders"]),
            format_signed(
                row["average_delivery_days_change"],
                suffix=" days",
            ),
            format_signed(
                row["promise_window_days_change"],
                suffix=" days",
            ),
        )
        for row in top_states
    ]

    seller_table_rows = [
        (
            row["seller_id"],
            row["seller_state"],
            format_integer(row["current_eligible_orders"]),
            format_integer(row["current_late_orders"]),
            format_signed(
                row["on_time_change_pp"],
                suffix=" pp",
            ),
            format_decimal(row["excess_late_orders"]),
            format_signed(
                row["average_handling_days_change"],
                suffix=" days",
            ),
            format_signed(
                row["average_delivery_days_change"],
                suffix=" days",
            ),
        )
        for row in top_sellers
    ]

    report_lines = [
        "# OpsPilot Delivery Incident Brief",
        "",
        f"**Period:** {previous_month:%B %Y} → "
        f"{current_month:%B %Y}",
        "",
        f"**Severity:** {severity}",
        "",
        "**Detection rule:** Consecutive-month deterioration of "
        "at least 5 percentage points in on-time delivery.",
        "",
        "## Executive decision",
        "",
        "**Recommended decision: Escalate the delivery-performance "
        "incident for targeted operational review.**",
        "",
        "On-time delivery fell by "
        f"{format_decimal(abs(on_time_change))} percentage points. "
        f"Current late orders exceeded the previous-period rate "
        f"expectation by approximately "
        f"{format_decimal(excess_late_orders)} orders.",
        "",
        f"Initial action should concentrate on {focus_states}. "
        "The two largest state contributors account for "
        f"{format_decimal(top_two_state_share, 1)}% of estimated "
        "excess late orders.",
        "",
        "## KPI impact",
        "",
        markdown_table(
            ("Metric", "Previous", "Current", "Change"),
            metric_rows,
        ),
        "",
        "## Geographic concentration",
        "",
        markdown_table(
            (
                "State",
                "Current eligible",
                "Current late",
                "On-time change",
                "Excess late",
                "Delivery change",
                "Promise change",
            ),
            state_table_rows,
        ),
        "",
        "## Seller signals",
        "",
        "Single-seller orders cover "
        f"{format_decimal(coverage['current']['single_seller_coverage_pct'])}% "
        "of current delivery-eligible orders, making seller-level "
        "segmentation broadly representative of this incident.",
        "",
        markdown_table(
            (
                "Seller",
                "State",
                "Current eligible",
                "Current late",
                "On-time change",
                "Excess late",
                "Handling change",
                "Delivery change",
            ),
            seller_table_rows,
        ),
        "",
        "## Evidence-based diagnosis",
        "",
        f"- {stage_diagnosis}",
        f"- {promise_diagnosis}",
        "- Customer review score changed by "
        f"{format_signed(review_score_change)}, which is consistent "
        "with a poorer customer experience but does not establish "
        "causation.",
        "- The geographic and seller rankings identify where the "
        "incident is concentrated; they do not prove that a state "
        "or seller caused it.",
        "",
        "## Recommended actions",
        "",
        f"1. Prioritize shipment-level review for {focus_states}, "
        "starting with the largest excess-late contributors.",
        "2. Enrich the analysis with carrier and route identifiers "
        "before assigning downstream transport accountability.",
        "3. Recalibrate promised-delivery windows for affected "
        "state and route combinations using observed transit-time "
        "distributions.",
        "4. Monitor the highlighted seller cohorts, but do not apply "
        "a broad seller-handling intervention while average "
        "handling time remains stable.",
        "5. Re-run detection after the next reporting period and "
        "compare on-time rate, excess late orders and customer "
        "review score.",
        "",
        "## Analytical limitations",
        "",
        "- This is observational analysis and supports hypotheses, "
        "not causal conclusions.",
        "- The source data does not provide a carrier identifier, "
        "so carrier-specific attribution is not possible.",
        "- Seller ranking is restricted to single-seller orders.",
        "- Region and seller rankings use minimum sample thresholds "
        "of 50 and 20 eligible orders per period respectively.",
        "- The Olist dataset is historical portfolio data, not a "
        "live production system.",
        "",
        "## Reproducibility",
        "",
        "- Detection source: "
        "`opspilot.monthly_delivery_comparison`",
        "- Investigation source: "
        "`sql/investigate_delivery_issue.sql`",
        "- Report generator: "
        "`scripts/generate_delivery_brief.py`",
        "",
    ]

    return "\n".join(report_lines)


def parse_month(value: str) -> date:
    """Parse a command-line month in YYYY-MM format."""

    parts = value.split("-")

    if (
        len(parts) != 2
        or len(parts[0]) != 4
        or len(parts[1]) != 2
        or not parts[0].isdigit()
        or not parts[1].isdigit()
    ):
        raise argparse.ArgumentTypeError(
            "month must use YYYY-MM format"
        )

    try:
        return date(
            int(parts[0]),
            int(parts[1]),
            1,
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "month must use YYYY-MM format"
        ) from error

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate a Markdown brief for a detected "
            "delivery issue."
        )
    )

    parser.add_argument(
        "--current-month",
        type=parse_month,
        help=(
            "Optional issue month in YYYY-MM format. "
            "The default is the most severe detected issue."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Optional report path. The default is derived from "
            "the selected incident month."
        ),
    )

    return parser.parse_args()


def main() -> int:
    """Generate and save the delivery incident brief."""

    arguments = parse_arguments()

    project_root = Path(__file__).resolve().parents[1]
    investigation_path = (
        project_root
        / "sql"
        / "investigate_delivery_issue.sql"
    )

    with psycopg.connect(
        **connection_arguments()
    ) as connection:
        issue = fetch_selected_issue(
            connection,
            arguments.current_month,
        )

        configure_investigation_target(
            connection,
            issue["current_month"],
        )

        result_sets = execute_investigation(
            connection,
            investigation_path,
        )

    report = build_report(
        issue,
        result_sets,
    )

    if arguments.output is None:
        output_path = (
            project_root
            / "reports"
            / (
                "delivery-incident-"
                f"{issue['current_month']:%Y-%m}.md"
            )
        )
    else:
        output_path = arguments.output.expanduser()

        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        report,
        encoding="utf-8",
    )

    print(
        "Selected issue: "
        f"{issue['previous_month']} -> "
        f"{issue['current_month']} "
        f"({issue['on_time_delivery_change_pp']} pp)"
    )
    print(f"Report written: {output_path}")
    print("RESULT: DELIVERY BRIEF GENERATED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
