# OpsPilot

**Detect. Investigate. Decide.**

OpsPilot is a cloud-native AI operations platform that detects business problems, investigates their root causes using operational data and business policies, and provides evidence-backed recommendations.

## Business problem

Retail and e-commerce teams often have operational data but still struggle to identify which problems require immediate attention, why they happened, and what action should be taken.

## Version 1 scope

OpsPilot V1 will focus on:

- Order and revenue performance
- Delivery performance
- Seller performance
- Derived inventory and stockout risk
- Evidence-backed operational investigations

The core workflow is:

1. Detect an operational issue.
2. Investigate it using controlled data tools.
3. Explain the evidence and deterministic calculations.
4. Recommend an appropriate business action.

## Data 

OpsPilot uses the Brazilian E-Commerce Public Dataset by Olist as its real historical data source.

Olist does not provide real-time inventory data. Inventory levels, replenishment assumptions, and stock thresholds will therefore be clearly identified as derived or synthetic data generated from documented rules and historical demand.

## Planned technology stack

- Python and Pandas
- FastAPI and Pydantic
- PostgreSQL and pgvector
- Azure-hosted language model
- Next.js, React and TypeScript
- Docker and Docker Compose
- Microsoft Azure

## Current

The project is under active development and is being built incrementally with testing, documentation, and reproducibility as priorities.