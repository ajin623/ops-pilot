"""Environment-free tests for database bootstrap state."""

from __future__ import annotations

import unittest

from scripts import bootstrap_database


class DatabaseBootstrapUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = (
            bootstrap_database.expected_table_rows()
        )

    def test_expected_table_contract(self) -> None:
        self.assertEqual(
            set(self.expected),
            {
                "customers",
                "products",
                "sellers",
                "orders",
                "order_items",
                "payments",
                "reviews",
            },
        )

    def test_empty_database_state(self) -> None:
        empty_counts = {
            table_name: 0
            for table_name in self.expected
        }

        self.assertEqual(
            bootstrap_database.classify_table_counts(
                empty_counts
            ),
            "empty",
        )

    def test_loaded_database_state(self) -> None:
        self.assertEqual(
            bootstrap_database.classify_table_counts(
                self.expected.copy()
            ),
            "loaded",
        )

    def test_incomplete_table_set_is_rejected(
        self,
    ) -> None:
        incomplete = self.expected.copy()
        incomplete.pop("reviews")

        with self.assertRaisesRegex(
            RuntimeError,
            "table set is incomplete",
        ):
            bootstrap_database.classify_table_counts(
                incomplete
            )

    def test_partial_load_is_rejected(self) -> None:
        partial = {
            table_name: 0
            for table_name in self.expected
        }
        partial["customers"] = 1

        with self.assertRaisesRegex(
            RuntimeError,
            "partial or unexpected load",
        ):
            bootstrap_database.classify_table_counts(
                partial
            )

    def test_wrong_complete_count_is_rejected(
        self,
    ) -> None:
        incorrect = self.expected.copy()
        incorrect["orders"] -= 1

        with self.assertRaisesRegex(
            RuntimeError,
            "partial or unexpected load",
        ):
            bootstrap_database.classify_table_counts(
                incorrect
            )


if __name__ == "__main__":
    unittest.main()
