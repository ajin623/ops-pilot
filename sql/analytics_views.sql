BEGIN;

CREATE OR REPLACE VIEW opspilot.order_facts AS
WITH item_summary AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        COUNT(DISTINCT product_id) AS product_count,
        COUNT(DISTINCT seller_id) AS seller_count,
        SUM(price) AS merchandise_value,
        SUM(freight_value) AS freight_value,
        SUM(item_total) AS item_total_value
    FROM opspilot.order_items
    GROUP BY order_id
),
payment_summary AS (
    SELECT
        order_id,
        COUNT(*) AS payment_record_count,
        SUM(payment_value) AS recorded_payment_value,
        BOOL_OR(is_invalid_installment)
            AS has_invalid_installment,
        BOOL_OR(is_zero_value_payment)
            AS has_zero_value_payment,
        BOOL_OR(payment_sequence_start_missing)
            AS has_payment_sequence_start_missing,
        BOOL_OR(payment_sequence_internal_gap)
            AS has_payment_sequence_internal_gap
    FROM opspilot.payments
    GROUP BY order_id
),
review_summary AS (
    SELECT
        order_id,
        COUNT(*) AS review_record_count,
        AVG(review_score)::NUMERIC(10, 4)
            AS average_review_score
    FROM opspilot.reviews
    GROUP BY order_id
)
SELECT
    orders.order_id,
    orders.customer_id,
    customers.customer_unique_id,
    customers.customer_city,
    customers.customer_state,

    orders.order_status,
    orders.order_purchase_timestamp,
    orders.order_purchase_timestamp::DATE
        AS purchase_date,
    DATE_TRUNC(
        'month',
        orders.order_purchase_timestamp
    )::DATE AS purchase_month,

    orders.order_approved_at,
    orders.order_delivered_carrier_date,
    orders.order_delivered_customer_date,
    orders.order_estimated_delivery_date,

    orders.has_order_items,
    orders.has_payment,
    orders.is_primary_analysis_window,

    orders.has_missing_operational_timestamp,
    orders.has_operational_chronology_issue,

    orders.is_delivery_kpi_eligible,
    orders.is_on_time_delivery,
    orders.delivery_days,
    orders.delivery_delay_days,
    orders.late_delivery_days,

    orders.is_handling_time_eligible,
    orders.approval_to_carrier_days,

    COALESCE(
        item_summary.item_count,
        0
    ) AS item_count,

    COALESCE(
        item_summary.product_count,
        0
    ) AS product_count,

    COALESCE(
        item_summary.seller_count,
        0
    ) AS seller_count,

    item_summary.merchandise_value,
    item_summary.freight_value,
    item_summary.item_total_value,

    COALESCE(
        payment_summary.payment_record_count,
        0
    ) AS payment_record_count,

    payment_summary.recorded_payment_value,

    COALESCE(
        payment_summary.has_invalid_installment,
        FALSE
    ) AS has_invalid_installment,

    COALESCE(
        payment_summary.has_zero_value_payment,
        FALSE
    ) AS has_zero_value_payment,

    COALESCE(
        payment_summary.has_payment_sequence_start_missing,
        FALSE
    ) AS has_payment_sequence_start_missing,

    COALESCE(
        payment_summary.has_payment_sequence_internal_gap,
        FALSE
    ) AS has_payment_sequence_internal_gap,

    COALESCE(
        review_summary.review_record_count,
        0
    ) AS review_record_count,

    review_summary.average_review_score

FROM opspilot.orders AS orders

INNER JOIN opspilot.customers AS customers
    ON customers.customer_id = orders.customer_id

LEFT JOIN item_summary
    ON item_summary.order_id = orders.order_id

LEFT JOIN payment_summary
    ON payment_summary.order_id = orders.order_id

LEFT JOIN review_summary
    ON review_summary.order_id = orders.order_id;

COMMENT ON VIEW opspilot.order_facts IS
    'One row per order with customer attributes, operational '
    'delivery metrics, pre-aggregated item values, recorded '
    'payment values and order-level review scores. Recorded '
    'payment value must not be described as recognized revenue.';

COMMIT;