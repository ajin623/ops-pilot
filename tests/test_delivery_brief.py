"""Integration tests for the delivery decision brief."""

from __future__ import annotations

import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from scripts import generate_delivery_brief


class DeliveryBriefIntegrationTests(unittest.TestCase):
    """Validate the database-to-report contract."""

    connection: psycopg.Connection[Any]
    issue: dict[str, Any]
    result_sets: list[list[dict[str, Any]]]
    report: str

    @classmethod
    def setUpClass(cls) -> None:
        project_root = Path(__file__).resolve().parents[1]
        investigation_path = (
            project_root
            / "sql"
            / "investigate_delivery_issue.sql"
        )

        cls.connection = psycopg.connect(
            **generate_delivery_brief.connection_arguments()
        )

        cls.issue = (
            generate_delivery_brief.fetch_selected_issue(
                cls.connection
            )
        )

        cls.result_sets = (
            generate_delivery_brief.execute_investigation(
                cls.connection,
                investigation_path,
            )
        )

        cls.report = generate_delivery_brief.build_report(
            cls.issue,
            cls.result_sets,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def test_selected_issue(self) -> None:
        self.assertEqual(
            self.issue["previous_month"],
            date(2018, 1, 1),
        )
        self.assertEqual(
            self.issue["current_month"],
            date(2018, 2, 1),
        )
        self.assertEqual(
            self.issue["on_time_delivery_change_pp"],
            Decimal("-9.43"),
        )

    def test_five_result_set_contract(self) -> None:
        self.assertEqual(
            len(self.result_sets),
            5,
        )

        self.assertEqual(
            [
                len(result_set)
                for result_set in self.result_sets
            ],
            [2, 1, 15, 2, 15],
        )

        required_keys = (
            {"period_label", "late_orders"},
            {
                "previous_eligible_orders",
                "excess_late_orders",
            },
            {"customer_state", "excess_late_orders"},
            {
                "period_label",
                "single_seller_coverage_pct",
            },
            {"seller_id", "excess_late_orders"},
        )

        for result_set, expected_keys in zip(
            self.result_sets,
            required_keys,
            strict=True,
        ):
            self.assertTrue(
                expected_keys.issubset(result_set[0])
            )

    def test_report_is_deterministic(self) -> None:
        second_report = (
            generate_delivery_brief.build_report(
                self.issue,
                self.result_sets,
            )
        )

        self.assertEqual(
            self.report,
            second_report,
        )

    def test_report_contains_verified_findings(self) -> None:
        expected_text = (
            "On-time delivery fell by 9.43 "
            "percentage points.",
            "approximately 617.74 orders",
            "RJ, SP, MG",
            "carrier-to-customer time increased "
            "by 2.91 days",
            "average seller handling time was "
            "effectively stable",
        )

        for text in expected_text:
            with self.subTest(text=text):
                self.assertIn(text, self.report)

    def test_report_contains_analytical_boundaries(
        self,
    ) -> None:
        expected_text = (
            "observational analysis",
            "not causal conclusions",
            "does not provide a carrier identifier",
            "historical portfolio data",
        )

        for text in expected_text:
            with self.subTest(text=text):
                self.assertIn(text, self.report)

    def test_report_excludes_database_password(
        self,
    ) -> None:
        password = os.environ["POSTGRES_PASSWORD"]

        self.assertNotIn(
            password,
            self.report,
        )


if __name__ == "__main__":
    unittest.main()
