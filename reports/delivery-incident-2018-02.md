# OpsPilot Delivery Incident Brief

**Period:** January 2018 → February 2018

**Severity:** High

**Detection rule:** Consecutive-month deterioration of at least 5 percentage points in on-time delivery.

## Executive decision

**Recommended decision: Escalate the delivery-performance incident for targeted operational review.**

On-time delivery fell by 9.43 percentage points. Current late orders exceeded the previous-period rate expectation by approximately 617.74 orders.

Initial action should concentrate on RJ, SP, MG. The two largest state contributors account for 50.1% of estimated excess late orders.

## KPI impact

| Metric | Previous | Current | Change |
| --- | --- | --- | --- |
| Delivery-eligible orders | 7,069 | 6,555 | -514 |
| On-time delivery rate | 93.44% | 84.01% | -9.43 pp |
| Late orders | 464 | 1,048 | +584 |
| Average delivery days | 14.08 | 16.95 | +2.87 days |
| Average handling days | 3.19 | 3.17 | -0.02 days |
| Carrier-to-customer days | 10.48 | 13.39 | +2.91 days |
| Average promise window | 26.30 | 24.53 | -1.77 days |
| Average review score | 4.04 | 3.83 | -0.21 |

## Geographic concentration

| State | Current eligible | Current late | On-time change | Excess late | Delivery change | Promise change |
| --- | --- | --- | --- | --- | --- | --- |
| RJ | 879 | 316 | -21.24 pp | 186.74 | +5.46 days | -3.60 days |
| SP | 2,632 | 227 | -4.65 pp | 122.60 | +1.47 days | -1.06 days |
| MG | 790 | 83 | -6.73 pp | 53.12 | +2.99 days | -1.21 days |
| SC | 254 | 66 | -14.40 pp | 36.60 | +2.53 days | -2.37 days |
| BA | 208 | 45 | -14.17 pp | 29.49 | +4.33 days | -2.34 days |

## Seller signals

Single-seller orders cover 99.24% of current delivery-eligible orders, making seller-level segmentation broadly representative of this incident.

| Seller | State | Current eligible | Current late | On-time change | Excess late | Handling change | Delivery change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4869f7a5dfa277a7dca6462dcf3b52b2 | SP | 87 | 34 | -36.26 pp | 31.55 | +0.17 days | +10.12 days |
| 8b321bb669392f5163d04c59e235e066 | SP | 163 | 34 | -18.41 pp | 30.00 | +0.88 days | +6.50 days |
| 4a3ca9315b744ce9f8e9374361493884 | SP | 108 | 33 | -24.81 pp | 26.79 | -0.13 days | +3.30 days |
| cc419e0650a3c5ba77189a1882b7556a | SP | 92 | 20 | -19.82 pp | 18.23 | +0.58 days | +6.49 days |
| 955fee9216a65b617aa5c0531780ce60 | SP | 84 | 19 | -20.00 pp | 16.80 | -0.48 days | +3.45 days |

## Evidence-based diagnosis

- The observed deterioration is concentrated after carrier handoff: carrier-to-customer time increased by 2.91 days, while average seller handling time was effectively stable at -0.02 days.
- The average customer promise window narrowed by 1.77 days, which likely amplified the measured late-delivery rate.
- Customer review score changed by -0.21, which is consistent with a poorer customer experience but does not establish causation.
- The geographic and seller rankings identify where the incident is concentrated; they do not prove that a state or seller caused it.

## Recommended actions

1. Prioritize shipment-level review for RJ, SP, MG, starting with the largest excess-late contributors.
2. Enrich the analysis with carrier and route identifiers before assigning downstream transport accountability.
3. Recalibrate promised-delivery windows for affected state and route combinations using observed transit-time distributions.
4. Monitor the highlighted seller cohorts, but do not apply a broad seller-handling intervention while average handling time remains stable.
5. Re-run detection after the next reporting period and compare on-time rate, excess late orders and customer review score.

## Analytical limitations

- This is observational analysis and supports hypotheses, not causal conclusions.
- The source data does not provide a carrier identifier, so carrier-specific attribution is not possible.
- Seller ranking is restricted to single-seller orders.
- Region and seller rankings use minimum sample thresholds of 50 and 20 eligible orders per period respectively.
- The Olist dataset is historical portfolio data, not a live production system.

## Reproducibility

- Detection source: `opspilot.monthly_delivery_comparison`
- Investigation source: `sql/investigate_delivery_issue.sql`
- Report generator: `scripts/generate_delivery_brief.py`
