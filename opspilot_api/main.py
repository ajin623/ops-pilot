"""FastAPI application for OpsPilot delivery analytics."""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, status

from opspilot_api import service
from opspilot_api.models import (
    DeliveryIssueDetail,
    DeliveryIssueSummary,
    HealthResponse,
    SellerContributionResponse,
    StateContributionResponse,
)


app = FastAPI(
    title="OpsPilot Delivery API",
    description=(
        "Read-only access to verified delivery issue "
        "detection and investigation results."
    ),
    version="0.1.0",
)


def parsed_month(value: str) -> date:
    """Convert a path month into a date."""

    try:
        return service.parse_month(value)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


def database_unavailable(error: Exception) -> HTTPException:
    """Create a non-sensitive database error response."""

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The analytical database is unavailable.",
    )


def issue_or_404(
    current_month: date,
) -> dict[str, Any]:
    """Fetch one issue or return HTTP 404."""

    try:
        issue = service.fetch_issue(current_month)
    except (psycopg.Error, RuntimeError) as error:
        raise database_unavailable(error) from error

    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No qualifying delivery issue was found "
                f"for {current_month:%Y-%m}."
            ),
        )

    return issue


def investigation_or_503(
    current_month: date,
) -> list[list[dict[str, Any]]]:
    """Execute an investigation or return HTTP 503."""

    try:
        return service.execute_issue_investigation(
            current_month
        )
    except (psycopg.Error, RuntimeError) as error:
        raise database_unavailable(error) from error


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
)
def health() -> HealthResponse:
    """Report API and database availability."""

    try:
        service.check_database()
    except (psycopg.Error, RuntimeError) as error:
        raise database_unavailable(error) from error

    return HealthResponse(
        status="ok",
        database="available",
    )


@app.get(
    "/api/v1/delivery/issues",
    response_model=list[DeliveryIssueSummary],
    tags=["delivery"],
)
def delivery_issues() -> list[dict[str, Any]]:
    """List all detected delivery issues."""

    try:
        return service.fetch_issues()
    except (psycopg.Error, RuntimeError) as error:
        raise database_unavailable(error) from error


@app.get(
    "/api/v1/delivery/issues/{current_month}",
    response_model=DeliveryIssueDetail,
    tags=["delivery"],
)
def delivery_issue(
    current_month: str,
) -> dict[str, Any]:
    """Return overall investigation results."""

    month = parsed_month(current_month)
    issue = issue_or_404(month)
    result_sets = investigation_or_503(month)

    return {
        "issue": issue,
        "periods": result_sets[0],
        "impact": result_sets[1][0],
    }


@app.get(
    "/api/v1/delivery/issues/{current_month}/states",
    response_model=StateContributionResponse,
    tags=["delivery"],
)
def delivery_issue_states(
    current_month: str,
) -> dict[str, Any]:
    """Return qualifying state contributors."""

    month = parsed_month(current_month)
    issue = issue_or_404(month)
    result_sets = investigation_or_503(month)

    return {
        "issue": issue,
        "states": result_sets[2],
    }


@app.get(
    "/api/v1/delivery/issues/{current_month}/sellers",
    response_model=SellerContributionResponse,
    tags=["delivery"],
)
def delivery_issue_sellers(
    current_month: str,
) -> dict[str, Any]:
    """Return seller coverage and contributors."""

    month = parsed_month(current_month)
    issue = issue_or_404(month)
    result_sets = investigation_or_503(month)

    return {
        "issue": issue,
        "coverage": result_sets[3],
        "sellers": result_sets[4],
    }
