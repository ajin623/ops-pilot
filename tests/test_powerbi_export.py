"""Integration tests for deterministic Power BI exports."""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCRIPT = (
    PROJECT_ROOT
    / "scripts"
    / "export_powerbi_data.py"
)

EXPORT_NAMES = (
    "monthly_kpis.csv",
    "delivery_comparisons.csv",
    "delivery_issue_states.csv",
    "delivery_issue_sellers.csv",
)


class PowerBiExportIntegrationTests(unittest.TestCase):
    """Validate the portable Power BI dataset contract."""

    @classmethod
    def setUpClass(cls) -> None:
        required_variables = (
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_PORT",
        )

        missing_variables = [
            name
            for name in required_variables
            if not os.getenv(name, "").strip()
        ]

        if missing_variables:
            raise RuntimeError(
                "Missing database environment variables: "
                + ", ".join(missing_variables)
            )

        cls.temporary_directory = (
            tempfile.TemporaryDirectory(
                prefix="opspilot-powerbi-test-"
            )
        )

        temporary_root = Path(
            cls.temporary_directory.name
        )

        cls.first_output = temporary_root / "first"
        cls.second_output = temporary_root / "second"

        cls.run_export(cls.first_output)
        cls.run_export(cls.second_output)

        cls.datasets = {
            name: cls.read_csv(
                cls.first_output / name
            )
            for name in EXPORT_NAMES
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    @staticmethod
    def run_export(output_directory: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(EXPORT_SCRIPT),
                "--output-dir",
                str(output_directory),
            ],
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Power BI export failed.\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )

    @staticmethod
    def read_csv(
        path: Path,
    ) -> tuple[list[str], list[dict[str, str]]]:
        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as file:
            reader = csv.DictReader(file)

            if reader.fieldnames is None:
                raise RuntimeError(
                    f"{path.name} has no header."
                )

            return reader.fieldnames, list(reader)

    def test_expected_export_files(self) -> None:
        actual_names = {
            path.name
            for path in self.first_output.glob("*.csv")
        }

        self.assertEqual(
            actual_names,
            set(EXPORT_NAMES),
        )

    def test_aggregate_dataset_contracts(self) -> None:
        monthly_columns, monthly_rows = self.datasets[
            "monthly_kpis.csv"
        ]

        comparison_columns, comparison_rows = (
            self.datasets[
                "delivery_comparisons.csv"
            ]
        )

        self.assertEqual(len(monthly_rows), 20)
        self.assertEqual(len(comparison_rows), 19)

        self.assertTrue(
            {
                "purchase_month",
                "order_count",
                "on_time_delivery_rate_pct",
                "average_delivery_days",
                "average_order_review_score",
            }.issubset(monthly_columns)
        )

        self.assertTrue(
            {
                "previous_month",
                "current_month",
                "on_time_delivery_change_pp",
                "is_delivery_issue",
                "issue_severity",
            }.issubset(comparison_columns)
        )

    def test_issue_detail_contracts(self) -> None:
        _, comparison_rows = self.datasets[
            "delivery_comparisons.csv"
        ]
        _, state_rows = self.datasets[
            "delivery_issue_states.csv"
        ]
        _, seller_rows = self.datasets[
            "delivery_issue_sellers.csv"
        ]

        detected_issue_ids = {
            f"delivery-{row['current_month'][:7]}"
            for row in comparison_rows
            if row["is_delivery_issue"].lower()
            == "true"
        }

        self.assertEqual(len(detected_issue_ids), 4)

        state_counts = Counter(
            row["issue_id"]
            for row in state_rows
        )

        seller_counts = Counter(
            row["issue_id"]
            for row in seller_rows
        )

        self.assertEqual(
            set(state_counts),
            detected_issue_ids,
        )
        self.assertEqual(
            set(seller_counts),
            detected_issue_ids,
        )

        for issue_id in detected_issue_ids:
            self.assertGreaterEqual(
                state_counts[issue_id],
                1,
            )
            self.assertLessEqual(
                state_counts[issue_id],
                15,
            )
            self.assertGreaterEqual(
                seller_counts[issue_id],
                1,
            )
            self.assertLessEqual(
                seller_counts[issue_id],
                15,
            )

        state_keys = [
            (
                row["issue_id"],
                row["customer_state"],
            )
            for row in state_rows
        ]

        seller_keys = [
            (
                row["issue_id"],
                row["seller_id"],
            )
            for row in seller_rows
        ]

        self.assertEqual(
            len(state_keys),
            len(set(state_keys)),
        )
        self.assertEqual(
            len(seller_keys),
            len(set(seller_keys)),
        )

    def test_exports_exclude_sensitive_data(self) -> None:
        prohibited_columns = {
            "order_id",
            "customer_id",
            "customer_unique_id",
            "customer_city",
        }

        database_password = os.environ[
            "POSTGRES_PASSWORD"
        ]

        for name, (columns, _) in (
            self.datasets.items()
        ):
            self.assertFalse(
                prohibited_columns.intersection(
                    columns
                ),
                msg=(
                    f"{name} exposes prohibited "
                    "columns."
                ),
            )

            content = (
                self.first_output / name
            ).read_text(encoding="utf-8")

            self.assertNotIn(
                database_password,
                content,
            )

    def test_exports_are_deterministic(self) -> None:
        for name in EXPORT_NAMES:
            first_content = (
                self.first_output / name
            ).read_bytes()

            second_content = (
                self.second_output / name
            ).read_bytes()

            self.assertEqual(
                first_content,
                second_content,
                msg=(
                    f"{name} changed between "
                    "identical exports."
                ),
            )


if __name__ == "__main__":
    unittest.main()
