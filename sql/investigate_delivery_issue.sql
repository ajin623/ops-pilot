BEGIN;

/*
Select the most severe detected delivery issue.

The detection rule requires consecutive months and an on-time
delivery deterioration of at least 5 percentage points. Larger
delivery-eligible samples and earlier months provide deterministic
tie-breaking.
*/

CREATE TEMPORARY VIEW investigation_settings AS
SELECT
    comparison.previous_month,
    comparison.current_month,
    50::BIGINT AS minimum_region_orders,
    20::BIGINT AS minimum_seller_orders
FROM opspilot.monthly_delivery_comparison AS comparison
WHERE comparison.is_consecutive_month
  AND comparison.on_time_delivery_change_pp <= -5.00
ORDER BY
    comparison.on_time_delivery_change_pp ASC,
    comparison.current_delivery_kpi_order_count DESC,
    comparison.current_month ASC
LIMIT 1;

CREATE TEMPORARY VIEW investigation_orders AS
SELECT
    facts.*,

    CASE
        WHEN facts.purchase_month
            = settings.previous_month
        THEN 'previous'
        ELSE 'current'
    END AS period_label,

    CASE
        WHEN facts.is_delivery_kpi_eligible
        THEN NOT facts.is_on_time_delivery
        ELSE NULL
    END AS is_late_delivery,

    CASE
        WHEN facts.is_delivery_kpi_eligible
        THEN (
            EXTRACT(
                EPOCH FROM (
                    facts.order_estimated_delivery_date
                    - facts.order_purchase_timestamp
                )
            )
            / 86400.0
        )::NUMERIC(14, 6)
        ELSE NULL
    END AS promise_window_days,

    CASE
        WHEN facts.order_delivered_carrier_date
                IS NOT NULL
         AND facts.order_delivered_customer_date
                IS NOT NULL
         AND facts.order_delivered_customer_date
                >= facts.order_delivered_carrier_date
        THEN (
            EXTRACT(
                EPOCH FROM (
                    facts.order_delivered_customer_date
                    - facts.order_delivered_carrier_date
                )
            )
            / 86400.0
        )::NUMERIC(14, 6)
        ELSE NULL
    END AS carrier_to_customer_days

FROM opspilot.order_facts AS facts

CROSS JOIN investigation_settings AS settings

WHERE facts.purchase_month IN (
    settings.previous_month,
    settings.current_month
);

CREATE TEMPORARY VIEW single_seller_orders AS
SELECT
    order_id,
    MIN(seller_id) AS seller_id
FROM opspilot.order_items
GROUP BY order_id
HAVING COUNT(DISTINCT seller_id) = 1;

DO $validation$
DECLARE
    detected_change NUMERIC;
BEGIN
    SELECT
        comparison.on_time_delivery_change_pp
    INTO detected_change
    FROM opspilot.monthly_delivery_comparison
        AS comparison
    CROSS JOIN investigation_settings AS settings
    WHERE comparison.previous_month
            = settings.previous_month
      AND comparison.current_month
            = settings.current_month;

    IF detected_change IS NULL THEN
        RAISE EXCEPTION
            'The selected month comparison does not exist';
    END IF;

    IF detected_change > -5.00 THEN
        RAISE EXCEPTION
            'The selected comparison does not meet the '
            '5 percentage-point detection threshold';
    END IF;

    RAISE NOTICE
        'Investigating delivery change of % percentage points.',
        detected_change;
END
$validation$;


/*
1. OVERALL DELIVERY-STAGE COMPARISON
*/

SELECT
    period_label,

    COUNT(*) AS all_orders,

    COUNT(*) FILTER (
        WHERE is_delivery_kpi_eligible
    ) AS delivery_eligible_orders,

    COUNT(*) FILTER (
        WHERE is_delivery_kpi_eligible
          AND is_late_delivery
    ) AS late_orders,

    ROUND(
        (
            100.0
            * COUNT(*) FILTER (
                WHERE is_delivery_kpi_eligible
                  AND NOT is_late_delivery
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

    ROUND(
        AVG(late_delivery_days) FILTER (
            WHERE is_delivery_kpi_eligible
              AND is_late_delivery
        ),
        2
    ) AS average_late_days_among_late_orders,

    ROUND(
        AVG(promise_window_days) FILTER (
            WHERE is_delivery_kpi_eligible
        ),
        2
    ) AS average_promise_window_days,

    COUNT(*) FILTER (
        WHERE is_handling_time_eligible
    ) AS handling_eligible_orders,

    ROUND(
        AVG(approval_to_carrier_days) FILTER (
            WHERE is_handling_time_eligible
        ),
        2
    ) AS average_handling_days,

    COUNT(carrier_to_customer_days)
        AS carrier_transport_eligible_orders,

    ROUND(
        AVG(carrier_to_customer_days),
        2
    ) AS average_carrier_to_customer_days,

    COUNT(*) FILTER (
        WHERE review_record_count > 0
    ) AS reviewed_orders,

    ROUND(
        AVG(average_review_score) FILTER (
            WHERE review_record_count > 0
        ),
        2
    ) AS average_order_review_score

FROM investigation_orders

GROUP BY period_label

ORDER BY MIN(purchase_month);


/*
2. OVERALL BUSINESS IMPACT
*/

WITH period_metrics AS (
    SELECT
        period_label,

        COUNT(*) FILTER (
            WHERE is_delivery_kpi_eligible
        ) AS eligible_orders,

        COUNT(*) FILTER (
            WHERE is_delivery_kpi_eligible
              AND is_late_delivery
        ) AS late_orders

    FROM investigation_orders

    GROUP BY period_label
),
comparison AS (
    SELECT
        MAX(eligible_orders) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_eligible_orders,

        MAX(late_orders) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_late_orders,

        MAX(eligible_orders) FILTER (
            WHERE period_label = 'current'
        ) AS current_eligible_orders,

        MAX(late_orders) FILTER (
            WHERE period_label = 'current'
        ) AS current_late_orders

    FROM period_metrics
)
SELECT
    previous_eligible_orders,
    previous_late_orders,

    ROUND(
        (
            100.0
            * previous_late_orders
            / previous_eligible_orders
        ),
        2
    ) AS previous_late_rate_pct,

    current_eligible_orders,
    current_late_orders,

    ROUND(
        (
            100.0
            * current_late_orders
            / current_eligible_orders
        ),
        2
    ) AS current_late_rate_pct,

    ROUND(
        (
            current_eligible_orders
            * previous_late_orders::NUMERIC
            / previous_eligible_orders
        ),
        2
    ) AS expected_current_late_orders,

    ROUND(
        (
            current_late_orders
            - (
                current_eligible_orders
                * previous_late_orders::NUMERIC
                / previous_eligible_orders
            )
        ),
        2
    ) AS excess_late_orders

FROM comparison;


/*
3. CUSTOMER-STATE CONTRIBUTORS

Only states with at least 50 eligible orders in both months
are included in the ranking.
*/

WITH state_period_metrics AS (
    SELECT
        customer_state,
        period_label,

        COUNT(*) FILTER (
            WHERE is_delivery_kpi_eligible
        ) AS eligible_orders,

        COUNT(*) FILTER (
            WHERE is_delivery_kpi_eligible
              AND is_late_delivery
        ) AS late_orders,

        AVG(delivery_days) FILTER (
            WHERE is_delivery_kpi_eligible
        ) AS average_delivery_days,

        AVG(promise_window_days) FILTER (
            WHERE is_delivery_kpi_eligible
        ) AS average_promise_window_days

    FROM investigation_orders

    GROUP BY
        customer_state,
        period_label
),
state_comparison AS (
    SELECT
        customer_state,

        MAX(eligible_orders) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_eligible_orders,

        MAX(late_orders) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_late_orders,

        MAX(average_delivery_days) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_average_delivery_days,

        MAX(average_promise_window_days) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_average_promise_window_days,

        MAX(eligible_orders) FILTER (
            WHERE period_label = 'current'
        ) AS current_eligible_orders,

        MAX(late_orders) FILTER (
            WHERE period_label = 'current'
        ) AS current_late_orders,

        MAX(average_delivery_days) FILTER (
            WHERE period_label = 'current'
        ) AS current_average_delivery_days,

        MAX(average_promise_window_days) FILTER (
            WHERE period_label = 'current'
        ) AS current_average_promise_window_days

    FROM state_period_metrics

    GROUP BY customer_state
),
state_rates AS (
    SELECT
        comparison.*,

        ROUND(
            (
                100.0
                * (
                    previous_eligible_orders
                    - previous_late_orders
                )
                / previous_eligible_orders
            ),
            2
        ) AS previous_on_time_rate_pct,

        ROUND(
            (
                100.0
                * (
                    current_eligible_orders
                    - current_late_orders
                )
                / current_eligible_orders
            ),
            2
        ) AS current_on_time_rate_pct,

        ROUND(
            (
                current_late_orders
                - (
                    current_eligible_orders
                    * previous_late_orders::NUMERIC
                    / previous_eligible_orders
                )
            ),
            2
        ) AS excess_late_orders

    FROM state_comparison AS comparison

    CROSS JOIN investigation_settings AS settings

    WHERE previous_eligible_orders
            >= settings.minimum_region_orders
      AND current_eligible_orders
            >= settings.minimum_region_orders
)
SELECT
    customer_state,

    previous_eligible_orders,
    current_eligible_orders,

    previous_on_time_rate_pct,
    current_on_time_rate_pct,

    ROUND(
        current_on_time_rate_pct
        - previous_on_time_rate_pct,
        2
    ) AS on_time_change_pp,

    current_late_orders,
    excess_late_orders,

    ROUND(
        current_average_delivery_days
        - previous_average_delivery_days,
        2
    ) AS average_delivery_days_change,

    ROUND(
        current_average_promise_window_days
        - previous_average_promise_window_days,
        2
    ) AS promise_window_days_change

FROM state_rates

ORDER BY
    excess_late_orders DESC,
    current_eligible_orders DESC

LIMIT 15;


/*
4. SINGLE-SELLER ANALYSIS COVERAGE

Orders involving multiple sellers are not attributed to one
seller because doing so would create ambiguous responsibility.
*/

SELECT
    orders.period_label,

    COUNT(*) FILTER (
        WHERE orders.is_delivery_kpi_eligible
    ) AS delivery_eligible_orders,

    COUNT(*) FILTER (
        WHERE orders.is_delivery_kpi_eligible
          AND mapping.order_id IS NOT NULL
    ) AS single_seller_eligible_orders,

    ROUND(
        (
            100.0
            * COUNT(*) FILTER (
                WHERE orders.is_delivery_kpi_eligible
                  AND mapping.order_id IS NOT NULL
            )
            / NULLIF(
                COUNT(*) FILTER (
                    WHERE orders.is_delivery_kpi_eligible
                ),
                0
            )
        ),
        2
    ) AS single_seller_coverage_pct

FROM investigation_orders AS orders

LEFT JOIN single_seller_orders AS mapping
    ON mapping.order_id = orders.order_id

GROUP BY orders.period_label

ORDER BY MIN(orders.purchase_month);


/*
5. SINGLE-SELLER CONTRIBUTORS

Only sellers with at least 20 eligible orders in both months
are included. Results show association, not proven causation.
*/

WITH seller_period_metrics AS (
    SELECT
        mapping.seller_id,
        orders.period_label,

        COUNT(*) AS eligible_orders,

        COUNT(*) FILTER (
            WHERE orders.is_late_delivery
        ) AS late_orders,

        AVG(orders.approval_to_carrier_days)
            FILTER (
                WHERE orders.is_handling_time_eligible
            ) AS average_handling_days,

        AVG(orders.delivery_days)
            AS average_delivery_days,

        AVG(orders.average_review_score)
            FILTER (
                WHERE orders.review_record_count > 0
            ) AS average_review_score

    FROM investigation_orders AS orders

    INNER JOIN single_seller_orders AS mapping
        ON mapping.order_id = orders.order_id

    WHERE orders.is_delivery_kpi_eligible

    GROUP BY
        mapping.seller_id,
        orders.period_label
),
seller_comparison AS (
    SELECT
        seller_id,

        MAX(eligible_orders) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_eligible_orders,

        MAX(late_orders) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_late_orders,

        MAX(average_handling_days) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_average_handling_days,

        MAX(average_delivery_days) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_average_delivery_days,

        MAX(average_review_score) FILTER (
            WHERE period_label = 'previous'
        ) AS previous_average_review_score,

        MAX(eligible_orders) FILTER (
            WHERE period_label = 'current'
        ) AS current_eligible_orders,

        MAX(late_orders) FILTER (
            WHERE period_label = 'current'
        ) AS current_late_orders,

        MAX(average_handling_days) FILTER (
            WHERE period_label = 'current'
        ) AS current_average_handling_days,

        MAX(average_delivery_days) FILTER (
            WHERE period_label = 'current'
        ) AS current_average_delivery_days,

        MAX(average_review_score) FILTER (
            WHERE period_label = 'current'
        ) AS current_average_review_score

    FROM seller_period_metrics

    GROUP BY seller_id
),
seller_rates AS (
    SELECT
        comparison.*,

        ROUND(
            (
                100.0
                * (
                    previous_eligible_orders
                    - previous_late_orders
                )
                / previous_eligible_orders
            ),
            2
        ) AS previous_on_time_rate_pct,

        ROUND(
            (
                100.0
                * (
                    current_eligible_orders
                    - current_late_orders
                )
                / current_eligible_orders
            ),
            2
        ) AS current_on_time_rate_pct,

        ROUND(
            (
                current_late_orders
                - (
                    current_eligible_orders
                    * previous_late_orders::NUMERIC
                    / previous_eligible_orders
                )
            ),
            2
        ) AS excess_late_orders

    FROM seller_comparison AS comparison

    CROSS JOIN investigation_settings AS settings

    WHERE previous_eligible_orders
            >= settings.minimum_seller_orders
      AND current_eligible_orders
            >= settings.minimum_seller_orders
)
SELECT
    rates.seller_id,
    sellers.seller_state,

    rates.previous_eligible_orders,
    rates.current_eligible_orders,

    rates.previous_on_time_rate_pct,
    rates.current_on_time_rate_pct,

    ROUND(
        rates.current_on_time_rate_pct
        - rates.previous_on_time_rate_pct,
        2
    ) AS on_time_change_pp,

    rates.current_late_orders,
    rates.excess_late_orders,

    ROUND(
        rates.current_average_handling_days
        - rates.previous_average_handling_days,
        2
    ) AS average_handling_days_change,

    ROUND(
        rates.current_average_delivery_days
        - rates.previous_average_delivery_days,
        2
    ) AS average_delivery_days_change,

    ROUND(
        rates.current_average_review_score
        - rates.previous_average_review_score,
        2
    ) AS average_review_score_change

FROM seller_rates AS rates

INNER JOIN opspilot.sellers AS sellers
    ON sellers.seller_id = rates.seller_id

ORDER BY
    rates.excess_late_orders DESC,
    rates.current_eligible_orders DESC

LIMIT 15;

COMMIT;