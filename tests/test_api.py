"""Integration tests for the read-only delivery API."""

from __future__ import annotations

import unittest
from typing import Any

from fastapi.testclient import TestClient

from opspilot_api.main import app


class DeliveryApiIntegrationTests(unittest.TestCase):
    """Validate API behavior against local PostgreSQL."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(
            app,
            raise_server_exceptions=False,
        )

        cls.health = cls.get_json("/health")
        cls.issues = cls.get_json(
            "/api/v1/delivery/issues"
        )
        cls.detail = cls.get_json(
            "/api/v1/delivery/issues/2018-02"
        )
        cls.states = cls.get_json(
            "/api/v1/delivery/issues/2018-02/states"
        )
        cls.sellers = cls.get_json(
            "/api/v1/delivery/issues/2018-02/sellers"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    @classmethod
    def get_json(
        cls,
        path: str,
        expected_status: int = 200,
    ) -> Any:
        response = cls.client.get(path)

        if response.status_code != expected_status:
            raise AssertionError(
                f"Unexpected response for {path}: "
                f"{response.status_code} {response.text}"
            )

        return response.json()

    def test_health(self) -> None:
        self.assertEqual(
            self.health,
            {
                "status": "ok",
                "database": "available",
            },
        )

    def test_detected_issue_order(self) -> None:
        self.assertEqual(
            len(self.issues),
            4,
        )

        self.assertEqual(
            [
                issue["current_month"]
                for issue in self.issues
            ],
            [
                "2018-02-01",
                "2017-11-01",
                "2018-08-01",
                "2018-03-01",
            ],
        )

        self.assertAlmostEqual(
            self.issues[0][
                "on_time_delivery_change_pp"
            ],
            -9.43,
            places=2,
        )

    def test_issue_detail_contract(self) -> None:
        issue = self.detail["issue"]
        periods = self.detail["periods"]
        impact = self.detail["impact"]

        self.assertEqual(
            issue["current_month"],
            "2018-02-01",
        )

        self.assertAlmostEqual(
            issue[
                "current_on_time_delivery_rate_pct"
            ],
            84.01,
            places=2,
        )

        self.assertEqual(
            [
                period["period_label"]
                for period in periods
            ],
            [
                "previous",
                "current",
            ],
        )

        self.assertEqual(
            impact["current_late_orders"],
            1048,
        )

        self.assertAlmostEqual(
            impact["excess_late_orders"],
            617.74,
            places=2,
        )

    def test_state_contributors(self) -> None:
        rows = self.states["states"]

        self.assertEqual(
            len(rows),
            15,
        )

        self.assertEqual(
            rows[0]["customer_state"],
            "RJ",
        )

        self.assertAlmostEqual(
            rows[0]["excess_late_orders"],
            186.74,
            places=2,
        )

    def test_seller_contributors(self) -> None:
        coverage = self.sellers["coverage"]
        rows = self.sellers["sellers"]

        self.assertEqual(
            len(coverage),
            2,
        )

        self.assertEqual(
            len(rows),
            15,
        )

        self.assertEqual(
            rows[0]["seller_id"],
            "4869f7a5dfa277a7dca6462dcf3b52b2",
        )

        self.assertAlmostEqual(
            rows[0]["excess_late_orders"],
            31.55,
            places=2,
        )

    def test_invalid_month_is_rejected(self) -> None:
        result = self.get_json(
            "/api/v1/delivery/issues/2018-8",
            expected_status=422,
        )

        self.assertEqual(
            result["detail"],
            "month must use YYYY-MM format",
        )

    def test_nonqualifying_month_returns_404(
        self,
    ) -> None:
        result = self.get_json(
            "/api/v1/delivery/issues/2018-04",
            expected_status=404,
        )

        self.assertIn(
            "No qualifying delivery issue",
            result["detail"],
        )

    def test_openapi_contract(self) -> None:
        document = self.get_json("/openapi.json")

        expected_paths = {
            "/health",
            "/api/v1/delivery/issues",
            (
                "/api/v1/delivery/issues/"
                "{current_month}"
            ),
            (
                "/api/v1/delivery/issues/"
                "{current_month}/states"
            ),
            (
                "/api/v1/delivery/issues/"
                "{current_month}/sellers"
            ),
        }

        self.assertTrue(
            expected_paths.issubset(
                document["paths"]
            )
        )

        serialized = str(document)

        self.assertNotIn(
            "POSTGRES_PASSWORD",
            serialized,
        )


if __name__ == "__main__":
    unittest.main()
