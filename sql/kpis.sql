BEGIN;

CREATE OR REPLACE VIEW opspilot.monthly_kpis AS
SELECT
    purchase_month,

    COUNT(*) AS order_count,

    COUNT(*) FILTER (
        WHERE payment_record_count > 0
    ) AS orders_with_payment_records,

    ROUND(
        SUM(recorded_payment_value),
        2
    ) AS recorded_payment_value,

    ROUND(
        AVG(recorded_payment_value) FILTER (
            WHERE payment_record_count > 0
        ),
        2
    ) AS average_order_value,

    COUNT(*) FILTER (
        WHERE is_delivery_kpi_eligible
    ) AS delivery_kpi_order_count,

    COUNT(*) FILTER (
        WHERE is_delivery_kpi_eligible
          AND is_on_time_delivery
    ) AS on_time_delivery_count,

    ROUND(
        (
            100.0
            * COUNT(*) FILTER (
                WHERE is_delivery_kpi_eligible
                  AND is_on_time_delivery
            )
            / NULLIF(
                COUNT(*) FILTER (
                    WHERE is_delivery_kpi_eligible
                ),
                0
            )
        ),
        2
    ) AS on_time_delivery_rate_pct,

    ROUND(
        AVG(delivery_days) FILTER (
            WHERE is_delivery_kpi_eligible
        ),
        2
    ) AS average_delivery_days,

    COUNT(*) FILTER (
        WHERE review_record_count > 0
    ) AS reviewed_order_count,

    ROUND(
        AVG(average_review_score) FILTER (
            WHERE review_record_count > 0
        ),
        2
    ) AS average_order_review_score

FROM opspilot.order_facts

WHERE is_primary_analysis_window

GROUP BY purchase_month;

COMMENT ON VIEW opspilot.monthly_kpis IS
    'Monthly business KPIs for the primary analysis window '
    'from January 2017 through August 2018. Payment value is '
    'recorded customer payment value, not recognized revenue. '
    'Delivery KPIs use only delivery-eligible orders. Review '
    'scores are first averaged within each order so every '
    'reviewed order has equal weight.';

COMMIT;