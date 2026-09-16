BEGIN;

CREATE OR REPLACE VIEW
    opspilot.monthly_delivery_comparison
AS
WITH lagged_kpis AS (
    SELECT
        purchase_month,

        order_count,
        delivery_kpi_order_count,
        on_time_delivery_count,
        on_time_delivery_rate_pct,
        average_delivery_days,
        reviewed_order_count,
        average_order_review_score,

        LAG(purchase_month) OVER (
            ORDER BY purchase_month
        ) AS previous_month,

        LAG(order_count) OVER (
            ORDER BY purchase_month
        ) AS previous_order_count,

        LAG(delivery_kpi_order_count) OVER (
            ORDER BY purchase_month
        ) AS previous_delivery_kpi_order_count,

        LAG(on_time_delivery_count) OVER (
            ORDER BY purchase_month
        ) AS previous_on_time_delivery_count,

        LAG(on_time_delivery_rate_pct) OVER (
            ORDER BY purchase_month
        ) AS previous_on_time_delivery_rate_pct,

        LAG(average_delivery_days) OVER (
            ORDER BY purchase_month
        ) AS previous_average_delivery_days,

        LAG(reviewed_order_count) OVER (
            ORDER BY purchase_month
        ) AS previous_reviewed_order_count,

        LAG(average_order_review_score) OVER (
            ORDER BY purchase_month
        ) AS previous_average_order_review_score

    FROM opspilot.monthly_kpis
)
SELECT
    purchase_month AS current_month,
    previous_month,

    (
        previous_month
        = (
            purchase_month
            - INTERVAL '1 month'
        )::DATE
    ) AS is_consecutive_month,

    order_count AS current_order_count,
    previous_order_count,

    ROUND(
        (
            100.0
            * (
                order_count
                - previous_order_count
            )
            / NULLIF(
                previous_order_count,
                0
            )
        ),
        2
    ) AS order_volume_change_pct,

    delivery_kpi_order_count
        AS current_delivery_kpi_order_count,

    previous_delivery_kpi_order_count,

    on_time_delivery_count
        AS current_on_time_delivery_count,

    previous_on_time_delivery_count,

    on_time_delivery_rate_pct
        AS current_on_time_delivery_rate_pct,

    previous_on_time_delivery_rate_pct,

    ROUND(
        (
            on_time_delivery_rate_pct
            - previous_on_time_delivery_rate_pct
        ),
        2
    ) AS on_time_delivery_change_pp,

    average_delivery_days
        AS current_average_delivery_days,

    previous_average_delivery_days,

    ROUND(
        (
            average_delivery_days
            - previous_average_delivery_days
        ),
        2
    ) AS average_delivery_days_change,

    reviewed_order_count
        AS current_reviewed_order_count,

    previous_reviewed_order_count,

    average_order_review_score
        AS current_average_order_review_score,

    previous_average_order_review_score,

    ROUND(
        (
            average_order_review_score
            - previous_average_order_review_score
        ),
        2
    ) AS average_review_score_change

FROM lagged_kpis

WHERE previous_month IS NOT NULL;

COMMENT ON VIEW
    opspilot.monthly_delivery_comparison
IS
    'Month-over-month delivery KPI comparisons. This view '
    'calculates observed changes only and does not claim that '
    'changes in delivery time, review score or order volume '
    'caused a change in on-time delivery.';

COMMIT;