from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "olist"

TABLES = {
    "orders": {
        "filename": "olist_orders_dataset.csv",
        "expected_rows": 99_441,
        "columns": [
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        "key": ["order_id"],
    },
    "order_items": {
        "filename": "olist_order_items_dataset.csv",
        "expected_rows": 112_650,
        "columns": [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
        ],
        "key": ["order_id", "order_item_id"],
    },
    "products": {
        "filename": "olist_products_dataset.csv",
        "expected_rows": 32_951,
        "columns": [
            "product_id",
            "product_category_name",
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ],
        "key": ["product_id"],
    },
    "sellers": {
        "filename": "olist_sellers_dataset.csv",
        "expected_rows": 3_095,
        "columns": [
            "seller_id",
            "seller_zip_code_prefix",
            "seller_city",
            "seller_state",
        ],
        "key": ["seller_id"],
    },
    "payments": {
        "filename": "olist_order_payments_dataset.csv",
        "expected_rows": 103_886,
        "columns": [
            "order_id",
            "payment_sequential",
            "payment_type",
            "payment_installments",
            "payment_value",
        ],
        "key": ["order_id", "payment_sequential"],
    },
    "category_translation": {
        "filename": "product_category_name_translation.csv",
        "expected_rows": 71,
        "columns": [
            "product_category_name",
            "product_category_name_english",
        ],
        "key": ["product_category_name"],
    },
}

FOREIGN_KEYS = [
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_items", "seller_id", "sellers", "seller_id"),
    ("payments", "order_id", "orders", "order_id"),
]


def load_and_validate_tables() -> tuple[dict[str, pd.DataFrame], list[str]]:
    frames = {}
    errors = []

    print(f"Raw data directory: {RAW_DIRECTORY}\n")

    for table_name, specification in TABLES.items():
        path = RAW_DIRECTORY / specification["filename"]

        if not path.is_file():
            message = f"{table_name}: missing file {path.name}"
            errors.append(message)
            print(f"[FAIL] {message}")
            continue

        frame = pd.read_csv(path, low_memory=False)
        frames[table_name] = frame

        row_count = len(frame)
        row_count_valid = row_count == specification["expected_rows"]
        schema_valid = list(frame.columns) == specification["columns"]

        if all(column in frame.columns for column in specification["key"]):
            duplicate_keys = int(
                frame.duplicated(subset=specification["key"]).sum()
            )
        else:
            duplicate_keys = -1

        table_valid = (
            row_count_valid
            and schema_valid
            and duplicate_keys == 0
        )

        status = "OK" if table_valid else "FAIL"
        print(
            f"[{status}] {table_name}: "
            f"rows={row_count:,}, "
            f"columns={len(frame.columns)}, "
            f"duplicate_keys={duplicate_keys}"
        )

        if not row_count_valid:
            errors.append(
                f"{table_name}: expected "
                f"{specification['expected_rows']:,} rows, "
                f"found {row_count:,}"
            )

        if not schema_valid:
            errors.append(f"{table_name}: unexpected column structure")

        if duplicate_keys != 0:
            errors.append(
                f"{table_name}: duplicate or unavailable key validation"
            )

        missing_counts = frame.isna().sum()
        missing_counts = missing_counts[missing_counts > 0]

        if missing_counts.empty:
            print("       Missing values: none")
        else:
            summary = ", ".join(
                f"{column}={int(count):,}"
                for column, count in missing_counts.items()
            )
            print(f"       Missing values: {summary}")

    return frames, errors


def validate_foreign_keys(
    frames: dict[str, pd.DataFrame],
    errors: list[str],
) -> None:
    print("\nForeign-key validation")

    for child_table, child_column, parent_table, parent_column in FOREIGN_KEYS:
        if child_table not in frames or parent_table not in frames:
            continue

        child_values = set(frames[child_table][child_column].dropna())
        parent_values = set(frames[parent_table][parent_column].dropna())
        orphan_count = len(child_values - parent_values)

        status = "OK" if orphan_count == 0 else "FAIL"
        print(
            f"[{status}] {child_table}.{child_column} -> "
            f"{parent_table}.{parent_column}: "
            f"orphan keys={orphan_count:,}"
        )

        if orphan_count:
            errors.append(
                f"{child_table}.{child_column}: "
                f"{orphan_count:,} orphan keys"
            )


def report_order_coverage(frames: dict[str, pd.DataFrame]) -> None:
    if not {"orders", "order_items", "payments"} <= frames.keys():
        return

    order_ids = set(frames["orders"]["order_id"])
    item_order_ids = set(frames["order_items"]["order_id"])
    payment_order_ids = set(frames["payments"]["order_id"])

    print("\nOrder coverage")
    print(f"Orders without items: {len(order_ids - item_order_ids):,}")
    print(f"Orders without payments: {len(order_ids - payment_order_ids):,}")


def report_date_coverage(
    frames: dict[str, pd.DataFrame],
    errors: list[str],
) -> None:
    if "orders" not in frames:
        return

    purchase_dates = pd.to_datetime(
        frames["orders"]["order_purchase_timestamp"],
        errors="coerce",
    )

    invalid_dates = int(purchase_dates.isna().sum())
    analysis_window = (
        purchase_dates.ge("2017-01-01")
        & purchase_dates.lt("2018-09-01")
    )

    print("\nPurchase-date coverage")
    print(f"Earliest purchase: {purchase_dates.min()}")
    print(f"Latest purchase:   {purchase_dates.max()}")
    print(f"Invalid dates:     {invalid_dates:,}")
    print(
        "Primary analysis window "
        f"(2017-01 through 2018-08): {int(analysis_window.sum()):,} orders"
    )

    if invalid_dates:
        errors.append(
            f"orders: {invalid_dates:,} invalid purchase timestamps"
        )


def main() -> int:
    frames, errors = load_and_validate_tables()
    validate_foreign_keys(frames, errors)
    report_order_coverage(frames)
    report_date_coverage(frames, errors)

    if errors:
        print("\nRESULT: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nRESULT: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())