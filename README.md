# OpsPilot

[![CI](https://github.com/ajin623/ops-pilot/actions/workflows/ci.yml/badge.svg)](https://github.com/ajin623/ops-pilot/actions/workflows/ci.yml)

**Detect. Investigate. Decide.**

OpsPilot is a deterministic operational analytics and decision-support project built on historical e-commerce data. It transforms raw order data into validated business KPIs, detects material delivery deterioration, investigates where the problem is concentrated and generates an evidence-backed incident brief.

The current version uses transparent Python and SQL calculations. It does not use an LLM to calculate metrics or claim unsupported root causes.

## Release

This repository is prepared as the `v1.0.0` portfolio release. It includes the validated analytical pipeline, Power BI report, read-only API, automated CI and reproducible local container stack.

See [CHANGELOG.md](CHANGELOG.md) for the release history.

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
9. Expose typed, read-only delivery analytics through FastAPI.
10. Validate environment-free application behavior in GitHub Actions.
11. Run PostgreSQL, deterministic bootstrap and the API through Docker Compose.

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
| `scripts/bootstrap_database.py` | Initializes or validates the containerized analytical database |
| `scripts/generate_delivery_brief.py` | Generates the decision brief |
| `scripts/export_powerbi_data.py` | Exports validated Power BI datasets |
| `opspilot_api/` | Provides the typed read-only delivery analytics API |
| `tests/test_api.py` | Validates database-backed API routes and response contracts |
| `tests/test_api_unit.py` | Validates API behavior without a database connection |
| `tests/test_bootstrap_unit.py` | Validates database bootstrap state handling |
| `.github/workflows/ci.yml` | Runs environment-free validation in GitHub Actions |
| `Dockerfile` | Builds the non-root API and bootstrap application image |
| `compose.yaml` | Defines PostgreSQL, bootstrap and API services |
| `sql/schema.sql` | Defines the relational schema |
| `sql/analytics_views.sql` | Builds the order fact view |
| `sql/kpis.sql` | Defines monthly KPIs |
| `sql/delivery_detection.sql` | Detects delivery deterioration |
| `sql/investigate_delivery_issue.sql` | Investigates the worst issue |
| `data/exports/powerbi/` | Contains portable aggregate BI datasets |
| `powerbi/OpsPilot_Delivery_Operations.pbix` | Contains the interactive Power BI report |
| `powerbi/README.md` | Documents the report model, refresh process and validation |
| `reports/` | Contains generated decision outputs |
| `CHANGELOG.md` | Documents portfolio release history |
| `.env.example` | Documents database and container port configuration |
| `.dockerignore` | Excludes local data, secrets and development artifacts from image builds |

## Technology

- Python 3.12
- Pandas
- PostgreSQL
- Psycopg 3
- SQL
- Power BI and DAX
- FastAPI, Pydantic and Uvicorn
- Git and GitHub
- Docker and Docker Compose

No vector database or language model is required for the current version.

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

## Run the containerized stack

The local Compose stack contains three services:

| Service | Responsibility |
| --- | --- |
| `db` | Runs PostgreSQL 18 with a persistent named volume |
| `bootstrap` | Creates the schema, loads the processed dataset when necessary, builds the analytical views and validates row counts |
| `api` | Runs the typed read-only FastAPI application |

The processed Olist CSV files must exist in `data/processed/olist/`. They are mounted read-only into the one-time bootstrap service and are never copied into the application image.

Start the complete stack:

~~~bash
docker compose up --build --detach
~~~

The database is exposed only on `127.0.0.1:55432` by default, avoiding the local PostgreSQL port. The API is available on `127.0.0.1:8000`.

Check the services and API:

~~~bash
docker compose ps --all

curl --fail http://127.0.0.1:8000/health
~~~

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

Stop and remove the containers while preserving the database volume:

~~~bash
docker compose down
~~~

To deliberately remove the containerized database and force a clean reload on the next startup:

~~~bash
docker compose down --volumes
~~~

The final command deletes the containerized PostgreSQL volume. It does not affect the separate PostgreSQL installation running on the host.

The application containers run as a non-root user with a read-only filesystem, dropped Linux capabilities and loopback-only published ports. The Compose configuration is intended for reproducible local validation; production deployment requires external secret management and a managed database.

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

## Power BI report

The version-controlled interactive report is available at [`powerbi/OpsPilot_Delivery_Operations.pbix`](powerbi/OpsPilot_Delivery_Operations.pbix).

The report provides:

- A complete monthly on-time-delivery trend
- Selection of any detected delivery-issue month
- Current on-time rate and month-over-month change
- Current and estimated excess late-order counts
- State-level incident concentration
- A prepared seller-level investigation dataset

The report model, relationships, data types, measures and issue-month interactions have been functionally validated. Final visual styling is intentionally deferred.

See [`powerbi/README.md`](powerbi/README.md) for the data model, refresh procedure, verified values and analytical boundaries.

## Read-only API

The FastAPI application exposes verified delivery-detection and investigation results without modifying the database.

Start the local API:

~~~bash
set -a
source .env
set +a

.venv/bin/uvicorn opspilot_api.main:app \
    --host 127.0.0.1 \
    --port 8000
~~~

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Checks API and PostgreSQL availability |
| `GET` | `/api/v1/delivery/issues` | Lists all qualifying delivery issues |
| `GET` | `/api/v1/delivery/issues/{YYYY-MM}` | Returns overall incident metrics and impact |
| `GET` | `/api/v1/delivery/issues/{YYYY-MM}/states` | Returns qualifying state contributors |
| `GET` | `/api/v1/delivery/issues/{YYYY-MM}/sellers` | Returns seller coverage and contributors |

The API creates a new PostgreSQL connection per request, reuses the validated SQL investigation contract and returns typed Pydantic responses. Database errors are returned without exposing connection details.

The current API is intended for local analytical use. Authentication, rate limiting and production deployment configuration are outside the current scope.

## Continuous integration

The GitHub Actions workflow runs on pushes and pull requests targeting `main`. It installs the pinned Python dependencies, checks dependency consistency, compiles the Python modules and runs the environment-free unit suite.

CI also validates the Compose configuration, builds the application image, verifies its non-root runtime identity and confirms that the API imports without opening a database connection. It does not require database credentials, the local Olist dataset or running PostgreSQL services.

## Tests

Run the same environment-free unit suite locally:

~~~bash
env \
    -u POSTGRES_DB \
    -u POSTGRES_USER \
    -u POSTGRES_PASSWORD \
    -u POSTGRES_HOST \
    -u POSTGRES_PORT \
    .venv/bin/python -m unittest \
        discover \
        --start-directory tests \
        --pattern 'test_*_unit.py' \
        --verbose
~~~

The complete integration suite requires the loaded local PostgreSQL dataset. It verifies issue selection, the five-result-set investigation contract, deterministic report generation, Power BI export contracts, read-only API routes, OpenAPI response contracts, analytical findings and secret exclusion.

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
- Typed, read-only API response contracts
- Non-sensitive API database-error responses
- Repeatable database bootstrap with partial-load rejection
- Non-root, read-only application containers
- Loopback-only container port publishing
- Explicit analytical limitations and non-causal language

## Analytical boundaries

- Olist is historical portfolio data, not a live production source.
- Recorded payment value is not described as recognized accounting revenue.
- Carrier identifiers are unavailable, preventing carrier attribution.
- Inventory levels are unavailable, so stockout analysis is outside the current scope.
- Geographic and seller concentration do not prove causation.
- Seller analysis is restricted to single-seller orders.
- The generator selects the most severe qualifying issue by default; `--current-month` can select another detected issue.

## Roadmap

1. Complete final Power BI visual styling and add the seller-detail view.
2. Optionally add an LLM explanation layer constrained to verified results.
3. Deploy the containerized API with production-grade secret handling and managed PostgreSQL.

## Current status

The data pipeline, PostgreSQL model, KPI layer, delivery detection, detailed investigation, deterministic decision brief, Power BI export layer, functional interactive report, typed read-only API, automated CI and validated local container stack are implemented, reproducible and packaged as the `v1.0.0` portfolio release.

## License

This repository is available for portfolio review. No open-source license is granted, and all rights are reserved.
