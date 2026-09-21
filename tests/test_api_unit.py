"""Environment-free unit tests for the delivery API."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from opspilot_api import service
from opspilot_api.main import app


SAMPLE_ISSUE = {
    "previous_month": date(2018, 1, 1),
    "current_month": date(2018, 2, 1),
    "current_order_count": 6728,
    "current_delivery_kpi_order_count": 6555,
    "current_on_time_delivery_count": 5507,
    "current_on_time_delivery_rate_pct": 84.01,
    "previous_on_time_delivery_rate_pct": 93.44,
    "on_time_delivery_change_pp": -9.43,
    "current_average_delivery_days": 16.95,
    "average_delivery_days_change": 2.87,
    "current_average_order_review_score": 3.83,
    "average_review_score_change": -0.21,
}


class DeliveryApiUnitTests(unittest.TestCase):
    """Validate API behavior without PostgreSQL."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(
            app,
            raise_server_exceptions=False,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def test_month_parser(self) -> None:
        self.assertEqual(
            service.parse_month("2018-08"),
            date(2018, 8, 1),
        )

        for invalid in (
            "2018-8",
            "2018-13",
            "not-a-month",
        ):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    service.parse_month(invalid)

    def test_application_routes_are_read_only(
        self,
    ) -> None:
        custom_routes = [
            route
            for route in app.routes
            if route.path == "/health"
            or route.path.startswith("/api/v1/")
        ]

        self.assertEqual(
            len(custom_routes),
            5,
        )

        for route in custom_routes:
            with self.subTest(path=route.path):
                self.assertEqual(
                    route.methods,
                    {"GET"},
                )

    @patch(
        "opspilot_api.main.service.check_database"
    )
    def test_health_without_database(
        self,
        check_database,
    ) -> None:
        response = self.client.get("/health")

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "database": "available",
            },
        )

        check_database.assert_called_once_with()

    @patch(
        "opspilot_api.main.service.fetch_issues",
        return_value=[SAMPLE_ISSUE],
    )
    def test_issue_list_response_contract(
        self,
        fetch_issues,
    ) -> None:
        response = self.client.get(
            "/api/v1/delivery/issues"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        rows = response.json()

        self.assertEqual(
            len(rows),
            1,
        )

        self.assertEqual(
            rows[0]["current_month"],
            "2018-02-01",
        )

        self.assertEqual(
            rows[0][
                "current_on_time_delivery_rate_pct"
            ],
            84.01,
        )

        fetch_issues.assert_called_once_with()

    def test_invalid_month_does_not_require_database(
        self,
    ) -> None:
        response = self.client.get(
            "/api/v1/delivery/issues/2018-8"
        )

        self.assertEqual(
            response.status_code,
            422,
        )

        self.assertEqual(
            response.json()["detail"],
            "month must use YYYY-MM format",
        )

    @patch(
        "opspilot_api.main.service.fetch_issue",
        return_value=None,
    )
    def test_missing_issue_returns_404(
        self,
        fetch_issue,
    ) -> None:
        response = self.client.get(
            "/api/v1/delivery/issues/2018-04"
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        self.assertIn(
            "No qualifying delivery issue",
            response.json()["detail"],
        )

        fetch_issue.assert_called_once_with(
            date(2018, 4, 1)
        )

    @patch(
        "opspilot_api.main.service.check_database",
        side_effect=psycopg.OperationalError(
            "password=do-not-expose"
        ),
    )
    def test_database_error_is_sanitized(
        self,
        check_database,
    ) -> None:
        response = self.client.get("/health")

        self.assertEqual(
            response.status_code,
            503,
        )

        serialized = response.text

        self.assertIn(
            "analytical database is unavailable",
            serialized,
        )

        self.assertNotIn(
            "do-not-expose",
            serialized,
        )

        check_database.assert_called_once_with()

    def test_openapi_contract_without_database(
        self,
    ) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(
            response.status_code,
            200,
        )

        document = response.json()

        self.assertEqual(
            document["info"]["title"],
            "OpsPilot Delivery API",
        )

        self.assertEqual(
            len(document["paths"]),
            5,
        )


if __name__ == "__main__":
    unittest.main()
