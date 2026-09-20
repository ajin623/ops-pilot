"""Typed API response models."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base model with a strict response contract."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiModel):
    """Service and database health."""

    status: str
    database: str


class DeliveryIssueSummary(ApiModel):
    """Detected month-over-month delivery issue."""

    previous_month: date
    current_month: date
    current_order_count: int
    current_delivery_kpi_order_count: int
    current_on_time_delivery_count: int
    current_on_time_delivery_rate_pct: float
    previous_on_time_delivery_rate_pct: float
    on_time_delivery_change_pp: float
    current_average_delivery_days: float
    average_delivery_days_change: float
    current_average_order_review_score: float | None
    average_review_score_change: float | None


class PeriodMetrics(ApiModel):
    """Operational metrics for one investigation period."""

    period_label: str
    all_orders: int
    delivery_eligible_orders: int
    late_orders: int
    on_time_delivery_rate_pct: float
    average_delivery_days: float
    average_late_days_among_late_orders: float
    average_promise_window_days: float
    handling_eligible_orders: int
    average_handling_days: float
    carrier_transport_eligible_orders: int
    average_carrier_to_customer_days: float
    reviewed_orders: int
    average_order_review_score: float


class LateOrderImpact(ApiModel):
    """Expected and excess late-order calculation."""

    previous_eligible_orders: int
    previous_late_orders: int
    previous_late_rate_pct: float
    current_eligible_orders: int
    current_late_orders: int
    current_late_rate_pct: float
    expected_current_late_orders: float
    excess_late_orders: float


class DeliveryIssueDetail(ApiModel):
    """Overall investigation results for one issue."""

    issue: DeliveryIssueSummary
    periods: list[PeriodMetrics]
    impact: LateOrderImpact


class StateContribution(ApiModel):
    """State-level delivery issue contribution."""

    customer_state: str
    previous_eligible_orders: int
    current_eligible_orders: int
    previous_on_time_rate_pct: float
    current_on_time_rate_pct: float
    on_time_change_pp: float
    current_late_orders: int
    excess_late_orders: float
    average_delivery_days_change: float
    promise_window_days_change: float


class StateContributionResponse(ApiModel):
    """State contributors for one issue."""

    issue: DeliveryIssueSummary
    states: list[StateContribution]


class SellerCoverage(ApiModel):
    """Coverage of the single-seller investigation."""

    period_label: str
    delivery_eligible_orders: int
    single_seller_eligible_orders: int
    single_seller_coverage_pct: float


class SellerContribution(ApiModel):
    """Seller-level delivery issue contribution."""

    seller_id: str
    seller_state: str
    previous_eligible_orders: int
    current_eligible_orders: int
    previous_on_time_rate_pct: float
    current_on_time_rate_pct: float
    on_time_change_pp: float
    current_late_orders: int
    excess_late_orders: float
    average_handling_days_change: float
    average_delivery_days_change: float
    average_review_score_change: float


class SellerContributionResponse(ApiModel):
    """Seller contributors and coverage for one issue."""

    issue: DeliveryIssueSummary
    coverage: list[SellerCoverage]
    sellers: list[SellerContribution]
