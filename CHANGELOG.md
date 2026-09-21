# Changelog

All notable portfolio releases of OpsPilot are documented here.

## [1.0.0] - 2026-09-21

### Added

- Reproducible inspection and cleaning of the historical Olist datasets.
- Validated PostgreSQL schema, order-level fact model and monthly KPI views.
- Detection of consecutive-month on-time-delivery deterioration.
- Geographic and seller-cohort delivery investigations.
- Deterministic Markdown incident briefs with explicit issue-month selection.
- Portable, validated Power BI export datasets.
- Interactive Power BI delivery-operations report.
- Typed, read-only FastAPI delivery analytics endpoints.
- Environment-free GitHub Actions validation.
- Reproducible Docker Compose stack for PostgreSQL bootstrap and API startup.

### Validation

- Complete 35-test local suite validated against PostgreSQL.
- Environment-free unit tests run in GitHub Actions.
- Container definition, non-root image and API import validated in CI.
- Fresh database loading and repeat bootstrap behavior validated.
- Containerized API and analytical row-count contracts validated end to end.
- Public documentation, relative links, whitespace and secret hygiene checked.

### Analytical boundaries

- Olist is historical portfolio data rather than a live production source.
- Geographic and seller concentration are investigative signals, not proof of causation.
- Carrier and inventory data are unavailable.
- Seller analysis is restricted to single-seller orders.
- The API and Compose stack are intended for local analytical use.
