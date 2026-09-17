# OpsPilot

**Detect. Investigate. Decide.**

OpsPilot is a deterministic operational analytics and decision-support project built on historical e-commerce data. It transforms raw order data into validated business KPIs, detects material delivery deterioration, investigates where the problem is concentrated and generates an evidence-backed incident brief.

The current version uses transparent Python and SQL calculations. It does not use an LLM to calculate metrics or claim unsupported root causes.

## Business problem

Operations teams often have dashboards showing that a KPI changed but still need to answer:

- Is the change large enough to require action?
- How many orders were affected?
- Which regions and seller cohorts contributed most?
- Which operational stage shows the strongest signal?
- What action is justified by the available evidence?
- What cannot be concluded from the available data?

OpsPilot connects KPI monitoring with a reproducible investigation and decision brief.

## Implemented workflow

1. Inspect and validate the source datasets.
2. Clean the data with explicit data-quality rules.
3. Load a relational PostgreSQL model.
4. Build order-level facts and monthly KPI views.
5. Detect consecutive-month delivery deterioration of at least 5 percentage points.
6. Investigate overall, geographic and seller-level contributors.
7. Generate a deterministic Markdown incident brief.
8. Export compact, validated datasets for Power BI.

## Architecture

| Stage | Implementation |
| --- | --- |
| Source data | Brazilian E-Commerce Public Dataset by Olist |
| Validation and cleaning | Python and Pandas |
| Operational data model | PostgreSQL |
| KPI and detection layer | SQL views |
| Investigation layer | Transaction-scoped SQL analysis |
| Decision layer | Deterministic Python Markdown generator |
| BI interface | Deterministic aggregate CSV exports |

## Verified case study

The most severe detected issue compares January 2018 with February 2018.

| Metric | January 2018 | February 2018 | Change |
| --- | ---: | ---: | ---: |
| Delivery-eligible orders | 7,069 | 6,555 | -514 |
| On-time delivery rate | 93.44% | 84.01% | -9.43 pp |
| Late orders | 464 | 1,048 | +584 |
| Average delivery days | 14.08 | 16.95 | +2.87 days |
| Average seller handling days | 3.19 | 3.17 | -0.02 days |
| Carrier-to-customer days | 10.48 | 13.39 | +2.91 days |
| Average promise window | 26.30 | 24.53 | -1.77 days |
| Average review score | 4.04 | 3.83 | -0.21 |

The investigation estimates approximately 617.74 excess late orders relative to the previous-period late rate.

RJ and SP account for 50.1% of estimated excess late orders. Seller handling time remained broadly stable while carrier-to-customer time increased, supporting a downstream transport and promise-setting hypothesis. This is an operational hypothesis, not proof of causation.

The complete generated brief is available at `reports/delivery-incident-2018-02.md`.

## Repository structure

| Path | Purpose |
| --- | --- |
| `scripts/inspect_olist.py` | Profiles and validates source data |
| `scripts/clean_olist.py` | Cleans and validates Olist data |
| `scripts/load_postgres.py` | Loads PostgreSQL and verifies row counts |
| `scripts/generate_delivery_brief.py` | Generates the decision brief |
| `scripts/export_powerbi_data.py` | Exports validated Power BI datasets |
| `sql/schema.sql` | Defines the relational schema |
| `sql/analytics_views.sql` | Builds the order fact view |
| `sql/kpis.sql` | Defines monthly KPIs |
| `sql/delivery_detection.sql` | Detects delivery deterioration |
| `sql/investigate_delivery_issue.sql` | Investigates the worst issue |
| `data/exports/powerbi/` | Contains portable aggregate BI datasets |
| `reports/` | Contains generated decision outputs |
| `.env.example` | Documents database configuration |

## Technology

- Python 3.12
- Pandas
- PostgreSQL
- Psycopg 3
- SQL
- Git and GitHub

No web framework, vector database or language model is required for the current version.

## Local setup

Create the Python environment:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
~~~

Create `.env` from `.env.example`, then replace the example values with local PostgreSQL credentials. Never commit `.env`.

Place the Olist CSV files in `data/raw/olist/`, then run:

~~~bash
.venv/bin/python scripts/inspect_olist.py
.venv/bin/python scripts/clean_olist.py
~~~

Cleaned files are written to `data/processed/olist/`.

## Build the analytical database

Load the environment and define the PostgreSQL command:

~~~bash
set -a
source .env
set +a

export PGPASSWORD="$POSTGRES_PASSWORD"

PSQL_COMMAND=(
    psql
    --host "${POSTGRES_HOST:-127.0.0.1}"
    --port "$POSTGRES_PORT"
    --username "$POSTGRES_USER"
    --dbname "$POSTGRES_DB"
    --no-psqlrc
    --set ON_ERROR_STOP=1
    --pset pager=off
)
~~~

Create the schema, load the cleaned data and build the views:

~~~bash
"${PSQL_COMMAND[@]}" --file sql/schema.sql
.venv/bin/python scripts/load_postgres.py
"${PSQL_COMMAND[@]}" --file sql/analytics_views.sql
"${PSQL_COMMAND[@]}" --file sql/kpis.sql
"${PSQL_COMMAND[@]}" --file sql/delivery_detection.sql
~~~

## Generate the decision brief

Run the complete SQL investigation:

~~~bash
"${PSQL_COMMAND[@]}" \
    --file sql/investigate_delivery_issue.sql
~~~

Generate the Markdown brief:

~~~bash
.venv/bin/python scripts/generate_delivery_brief.py
~~~

Without `--current-month`, the generator selects the most severe qualifying issue and writes the report to its derived month-based path.

Generate a brief for a specific detected issue:

~~~bash
.venv/bin/python scripts/generate_delivery_brief.py \
    --current-month 2018-08
~~~

An alternative output path can also be supplied:

~~~bash
.venv/bin/python scripts/generate_delivery_brief.py \
    --current-month 2018-08 \
    --output /tmp/delivery-incident-brief.md
~~~

## Power BI data export

Generate the portable analytical datasets:

~~~bash
.venv/bin/python scripts/export_powerbi_data.py
~~~

The exporter writes four deterministic CSV files to `data/exports/powerbi/`:

| Dataset | Grain | Purpose |
| --- | --- | --- |
| `monthly_kpis.csv` | One row per month | Monthly order, delivery and review trends |
| `delivery_comparisons.csv` | One row per month-over-month comparison | Delivery changes, issue flags and severity |
| `delivery_issue_states.csv` | Up to 15 qualifying states per detected issue | Geographic concentration of late deliveries |
| `delivery_issue_sellers.csv` | Up to 15 qualifying sellers per detected issue | Seller-cohort investigation signals |

The detail exports retain the investigation's minimum sample thresholds. They contain aggregate analytical results and exclude order IDs and customer identifiers.

An alternative output directory can be supplied with:

~~~bash
.venv/bin/python scripts/export_powerbi_data.py \
    --output-dir /tmp/opspilot-powerbi
~~~

The four files can be imported directly into Power BI Desktop.

## Tests

The integration suite uses Python's standard `unittest` module and the loaded local PostgreSQL dataset. It verifies issue selection, the five-result-set investigation contract, deterministic report generation, Power BI export contracts, analytical findings and secret exclusion.

~~~bash
set -a
source .env
set +a

.venv/bin/python -m unittest \
    discover \
    --start-directory tests \
    --pattern 'test_*.py' \
    --verbose
~~~

## Quality controls

The current implementation includes:

- Required-column, datatype and key validation
- Foreign-key and business-rule checks
- Explicit KPI eligibility rules
- Order-level aggregation to prevent item-level double counting
- Consecutive-month validation
- Minimum region and seller sample thresholds
- Transaction-scoped temporary investigation views
- Database result-set contract validation
- Deterministic report generation
- Environment-based secret handling
- Explicit analytical limitations and non-causal language

## Analytical boundaries

- Olist is historical portfolio data, not a live production source.
- Recorded payment value is not described as recognized accounting revenue.
- Carrier identifiers are unavailable, preventing carrier attribution.
- Inventory levels are unavailable, so stockout analysis is outside the current scope.
- Geographic and seller concentration do not prove causation.
- Seller analysis is restricted to single-seller orders.
- The generator currently reports the most severe qualifying issue.

## Roadmap

1. Build a focused Power BI report from the validated export datasets.
2. Add automated CI for repeatable validation.
3. Add a small API after the analytical interface is stable.
4. Optionally add an LLM explanation layer constrained to verified results.
5. Containerize and deploy after local behavior is fully tested.

## Current status

The data pipeline, PostgreSQL model, KPI layer, delivery detection, detailed investigation, deterministic decision brief and Power BI export layer are implemented and reproducible.
