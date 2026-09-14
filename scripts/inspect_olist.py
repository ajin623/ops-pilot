"""Inspect and validate the raw Brazilian Olist datasets.

This script performs structural and business-oriented checks before
the data is cleaned or loaded into PostgreSQL.

It does not modify any files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "olist"

ANALYSIS_WINDOW_START = pd.Timestamp("2017-01-01")
ANALYSIS_WINDOW_END = pd.Timestamp("2018-09-01")

KNOWN_MANUAL_TRANSLATIONS = {
    "pc_gamer",
    "portateis_cozinha_e_preparadores_de_alimentos",
}

DATASETS = {
    "customers": {
        "filename": "olist_customers_dataset.csv",
        "key": ["customer_id"],
        "columns": [
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
        ],
    },
    "orders": {
        "filename": "olist_orders_dataset.csv",
        "key": ["order_id"],
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
    },
    "order_items": {
        "filename": "olist_order_items_dataset.csv",
        "key": [
            "order_id",
            "order_item_id",
        ],
        "columns": [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
        ],
    },
    "products": {
        "filename": "olist_products_dataset.csv",
        "key": ["product_id"],
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
    },
    "sellers": {
        "filename": "olist_sellers_dataset.csv",
        "key": ["seller_id"],
        "columns": [
            "seller_id",
            "seller_zip_code_prefix",
            "seller_city",
            "seller_state",
        ],
    },
    "payments": {
        "filename": "olist_order_payments_dataset.csv",
        "key": [
            "order_id",
            "payment_sequential",
        ],
        "columns": [
            "order_id",
            "payment_sequential",
            "payment_type",
            "payment_installments",
            "payment_value",
        ],
    },
    "reviews": {
        "filename": "olist_order_reviews_dataset.csv",
        "key": [
            "review_id",
            "order_id",
        ],
        "columns": [
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
            "review_creation_date",
            "review_answer_timestamp",
        ],
    },
    "category_translation": {
        "filename": "product_category_name_translation.csv",
        "key": ["product_category_name"],
        "columns": [
            "product_category_name",
            "product_category_name_english",
        ],
    },
}


def normalize_strings(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Strip surrounding whitespace from string values."""

    result = frame.copy()

    for column in result.columns:
        if isinstance(result[column].dtype, pd.StringDtype):
            result[column] = result[column].str.strip()
            result[column] = result[column].replace("", pd.NA)

    return result


def load_datasets() -> tuple[
    dict[str, pd.DataFrame],
    list[str],
]:
    """Load every required dataset and validate its header."""

    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []

    for name, specification in DATASETS.items():
        path = RAW_DIRECTORY / specification["filename"]

        if not path.is_file():
            errors.append(
                f"{name}: required file not found: {path}"
            )
            continue

        frame = pd.read_csv(
            path,
            dtype="string",
        )

        expected_columns = specification["columns"]
        missing_columns = sorted(
            set(expected_columns) - set(frame.columns)
        )
        unexpected_columns = sorted(
            set(frame.columns) - set(expected_columns)
        )

        if missing_columns:
            errors.append(
                f"{name}: missing columns "
                f"{missing_columns}"
            )

        if unexpected_columns:
            errors.append(
                f"{name}: unexpected columns "
                f"{unexpected_columns}"
            )

        if not missing_columns and not unexpected_columns:
            frames[name] = normalize_strings(
                frame[expected_columns]
            )

    return frames, errors


def inspect_structure(
    frames: dict[str, pd.DataFrame],
    errors: list[str],
) -> None:
    """Report rows, columns, missing values and key quality."""

    print(f"Raw data directory: {RAW_DIRECTORY}")

    for name, specification in DATASETS.items():
        frame = frames[name]
        key_columns = specification["key"]

        missing_key_rows = int(
            frame[key_columns]
            .isna()
            .any(axis=1)
            .sum()
        )

        duplicate_key_rows = int(
            frame.duplicated(
                subset=key_columns
            ).sum()
        )

        exact_duplicate_rows = int(
            frame.duplicated().sum()
        )

        status = (
            "OK"
            if missing_key_rows == 0
            and duplicate_key_rows == 0
            else "FAIL"
        )

        print(
            f"\n[{status}] {name}: "
            f"rows={len(frame):,}, "
            f"columns={len(frame.columns):,}, "
            f"duplicate_keys={duplicate_key_rows:,}, "
            f"exact_duplicates={exact_duplicate_rows:,}"
        )

        missing_values = frame.isna().sum()
        missing_values = missing_values[
            missing_values > 0
        ]

        if missing_values.empty:
            print("       Missing values: none")
        else:
            missing_text = ", ".join(
                f"{column}={int(count):,}"
                for column, count
                in missing_values.items()
            )

            print(
                f"       Missing values: {missing_text}"
            )

        if missing_key_rows:
            errors.append(
                f"{name}: {missing_key_rows:,} rows "
                f"have missing key values"
            )

        if duplicate_key_rows:
            errors.append(
                f"{name}: {duplicate_key_rows:,} "
                f"duplicate key rows for {key_columns}"
            )


def validate_foreign_key(
    child: pd.DataFrame,
    child_column: str,
    parent: pd.DataFrame,
    parent_column: str,
    relationship: str,
    errors: list[str],
) -> None:
    """Validate and report one foreign-key relationship."""

    child_values = set(
        child[child_column].dropna()
    )
    parent_values = set(
        parent[parent_column].dropna()
    )

    orphan_values = (
        child_values - parent_values
    )

    status = (
        "OK"
        if not orphan_values
        else "FAIL"
    )

    print(
        f"[{status}] {relationship}: "
        f"orphan keys={len(orphan_values):,}"
    )

    if orphan_values:
        errors.append(
            f"{relationship}: "
            f"{len(orphan_values):,} orphan keys"
        )


def validate_numeric_column(
    frame: pd.DataFrame,
    column: str,
    dataset_name: str,
    errors: list[str],
) -> pd.Series:
    """Convert a numeric column and identify invalid values."""

    converted = pd.to_numeric(
        frame[column],
        errors="coerce",
    )

    invalid_count = int(
        (
            frame[column].notna()
            & converted.isna()
        ).sum()
    )

    if invalid_count:
        errors.append(
            f"{dataset_name}.{column}: "
            f"{invalid_count:,} invalid numeric values"
        )

    return converted


def validate_datetime_column(
    frame: pd.DataFrame,
    column: str,
    dataset_name: str,
    errors: list[str],
) -> pd.Series:
    """Convert a timestamp column and identify invalid values."""

    converted = pd.to_datetime(
        frame[column],
        errors="coerce",
    )

    invalid_count = int(
        (
            frame[column].notna()
            & converted.isna()
        ).sum()
    )

    if invalid_count:
        errors.append(
            f"{dataset_name}.{column}: "
            f"{invalid_count:,} invalid timestamps"
        )

    return converted


def inspect_relationships(
    frames: dict[str, pd.DataFrame],
    errors: list[str],
) -> None:
    """Validate the relational structure of the raw data."""

    print("\nForeign-key validation")

    relationships = [
        (
            frames["orders"],
            "customer_id",
            frames["customers"],
            "customer_id",
            "orders.customer_id -> customers.customer_id",
        ),
        (
            frames["order_items"],
            "order_id",
            frames["orders"],
            "order_id",
            "order_items.order_id -> orders.order_id",
        ),
        (
            frames["order_items"],
            "product_id",
            frames["products"],
            "product_id",
            "order_items.product_id -> products.product_id",
        ),
        (
            frames["order_items"],
            "seller_id",
            frames["sellers"],
            "seller_id",
            "order_items.seller_id -> sellers.seller_id",
        ),
        (
            frames["payments"],
            "order_id",
            frames["orders"],
            "order_id",
            "payments.order_id -> orders.order_id",
        ),
        (
            frames["reviews"],
            "order_id",
            frames["orders"],
            "order_id",
            "reviews.order_id -> orders.order_id",
        ),
    ]

    for relationship in relationships:
        validate_foreign_key(
            *relationship,
            errors,
        )


def inspect_order_coverage(
    frames: dict[str, pd.DataFrame],
) -> None:
    """Report which orders are represented in related datasets."""

    order_ids = set(
        frames["orders"]["order_id"].dropna()
    )

    item_order_ids = set(
        frames["order_items"]["order_id"].dropna()
    )

    payment_order_ids = set(
        frames["payments"]["order_id"].dropna()
    )

    review_order_ids = set(
        frames["reviews"]["order_id"].dropna()
    )

    print("\nOrder coverage")
    print(
        "Orders without items:    "
        f"{len(order_ids - item_order_ids):,}"
    )
    print(
        "Orders without payments: "
        f"{len(order_ids - payment_order_ids):,}"
    )
    print(
        "Orders without reviews:  "
        f"{len(order_ids - review_order_ids):,}"
    )


def inspect_customers(
    frames: dict[str, pd.DataFrame],
) -> None:
    """Report repeat-customer identity information."""

    customers = frames["customers"]

    frequency = (
        customers.groupby(
            "customer_unique_id"
        )
        .size()
    )

    print("\nCustomer identity")
    print(
        "Unique customer_id values:        "
        f"{customers['customer_id'].nunique():,}"
    )
    print(
        "Unique customer identities:       "
        f"{customers['customer_unique_id'].nunique():,}"
    )
    print(
        "Customer identities appearing >1: "
        f"{int((frequency > 1).sum()):,}"
    )
    print(
        "Maximum records for one customer: "
        f"{int(frequency.max()):,}"
    )


def inspect_reviews(
    frames: dict[str, pd.DataFrame],
    errors: list[str],
) -> None:
    """Validate review scores and report review multiplicity."""

    reviews = frames["reviews"]

    review_scores = validate_numeric_column(
        reviews,
        "review_score",
        "reviews",
        errors,
    )

    missing_score_count = int(
        review_scores.isna().sum()
    )

    out_of_range_count = int(
        (
            review_scores.notna()
            & ~review_scores.between(1, 5)
        ).sum()
    )

    if missing_score_count:
        errors.append(
            f"reviews.review_score: "
            f"{missing_score_count:,} missing values"
        )

    if out_of_range_count:
        errors.append(
            f"reviews.review_score: "
            f"{out_of_range_count:,} values outside 1–5"
        )

    review_rows_per_order = (
        reviews.groupby("order_id").size()
    )

    orders_per_review_id = (
        reviews.groupby("review_id")[
            "order_id"
        ].nunique()
    )

    print("\nReview validation")
    print(
        "Review score range:              "
        f"{int(review_scores.min())} to "
        f"{int(review_scores.max())}"
    )
    print(
        "Orders with multiple reviews:    "
        f"{int((review_rows_per_order > 1).sum()):,}"
    )
    print(
        "Maximum reviews for one order:   "
        f"{int(review_rows_per_order.max()):,}"
    )
    print(
        "Review IDs used by >1 order:     "
        f"{int((orders_per_review_id > 1).sum()):,}"
    )

    print("\nReview-score distribution")

    distribution = (
        review_scores.value_counts()
        .sort_index()
    )

    for score, count in distribution.items():
        print(
            f"Score {int(score)}: {int(count):,}"
        )

    for column in [
        "review_creation_date",
        "review_answer_timestamp",
    ]:
        validate_datetime_column(
            reviews,
            column,
            "reviews",
            errors,
        )


def inspect_categories(
    frames: dict[str, pd.DataFrame],
    errors: list[str],
) -> None:
    """Inspect product measurements and category translations."""

    products = frames["products"]

    physical_measurement_columns = [
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]

    product_measurements = products[
        physical_measurement_columns
    ].apply(
        pd.to_numeric,
        errors="coerce",
    )

    expected_nonpositive_counts = {
        "product_weight_g": 4,
        "product_length_cm": 0,
        "product_height_cm": 0,
        "product_width_cm": 0,
    }

    print("\nProduct physical-measurement validation")

    affected_product_mask = pd.Series(
        False,
        index=products.index,
    )

    for column in physical_measurement_columns:
        values = product_measurements[column]

        missing_count = int(values.isna().sum())
        zero_count = int(values.eq(0).sum())
        negative_count = int(values.lt(0).sum())

        nonpositive_mask = (
            values.notna()
            & values.le(0)
        )

        nonpositive_count = int(
            nonpositive_mask.sum()
        )

        affected_product_mask |= nonpositive_mask

        print(
            f"{column:<24} "
            f"missing={missing_count:>3} "
            f"zero={zero_count:>3} "
            f"negative={negative_count:>3}"
        )

        expected_count = expected_nonpositive_counts[
            column
        ]

        if nonpositive_count != expected_count:
            errors.append(
                f"{column} contains "
                f"{nonpositive_count:,} nonpositive values; "
                f"expected {expected_count:,} for the "
                "verified source dataset"
            )

    affected_product_count = int(
        affected_product_mask.sum()
    )

    print(
        "Known products normalized during cleaning: "
        f"{affected_product_count:,}"
    )

    translations = frames[
        "category_translation"
    ]

    product_categories = set(
        products[
            "product_category_name"
        ].dropna()
    )

    translated_categories = set(
        translations[
            "product_category_name"
        ].dropna()
    )

    missing_translations = (
        product_categories
        - translated_categories
    )

    unused_translations = (
        translated_categories
        - product_categories
    )

    unexpected_missing_translations = (
        missing_translations
        - KNOWN_MANUAL_TRANSLATIONS
    )

    print("\nCategory translation coverage")
    print(
        "Product categories:             "
        f"{len(product_categories):,}"
    )
    print(
        "Official translated categories: "
        f"{len(translated_categories):,}"
    )
    print(
        "Categories needing manual mapping:"
    )

    if missing_translations:
        for category in sorted(
            missing_translations
        ):
            print(f"  - {category}")
    else:
        print("  none")

    print(
        "Unused official translations:   "
        f"{len(unused_translations):,}"
    )

    if unexpected_missing_translations:
        errors.append(
            "Unexpected categories without translations: "
            f"{sorted(unexpected_missing_translations)}"
        )


def inspect_payments(
    frames: dict[str, pd.DataFrame],
    errors: list[str],
) -> None:
    """Validate payment values and sequence patterns."""

    payments = frames["payments"].copy()

    payments["payment_sequential"] = (
        validate_numeric_column(
            payments,
            "payment_sequential",
            "payments",
            errors,
        )
    )

    payments["payment_installments"] = (
        validate_numeric_column(
            payments,
            "payment_installments",
            "payments",
            errors,
        )
    )

    payments["payment_value"] = (
        validate_numeric_column(
            payments,
            "payment_value",
            "payments",
            errors,
        )
    )

    negative_value_count = int(
        (
            payments["payment_value"] < 0
        ).sum()
    )

    if negative_value_count:
        errors.append(
            "payments.payment_value contains "
            f"{negative_value_count:,} negative values"
        )

    sequence_statistics = (
        payments.groupby("order_id")[
            "payment_sequential"
        ]
        .agg(["min", "max", "nunique"])
    )

    expected_sequence_count = (
        sequence_statistics["max"]
        - sequence_statistics["min"]
        + 1
    )

    start_missing_count = int(
        (
            sequence_statistics["min"] > 1
        ).sum()
    )

    internal_gap_count = int(
        (
            sequence_statistics["nunique"]
            != expected_sequence_count
        ).sum()
    )

    print("\nPayment validation")
    print(
        "Zero-installment records:      "
        f"{int((payments['payment_installments'] <= 0).sum()):,}"
    )
    print(
        "Zero-value payments:           "
        f"{int((payments['payment_value'] == 0).sum()):,}"
    )
    print(
        "Negative payment values:       "
        f"{negative_value_count:,}"
    )
    print(
        "Sequences starting above one:  "
        f"{start_missing_count:,}"
    )
    print(
        "Orders with internal sequence gaps: "
        f"{internal_gap_count:,}"
    )


def inspect_order_items(
    frames: dict[str, pd.DataFrame],
    errors: list[str],
) -> None:
    """Validate item prices and freight values."""

    order_items = frames["order_items"]

    price = validate_numeric_column(
        order_items,
        "price",
        "order_items",
        errors,
    )

    freight = validate_numeric_column(
        order_items,
        "freight_value",
        "order_items",
        errors,
    )

    nonpositive_prices = int(
        (
            price <= 0
        ).sum()
    )

    negative_freight = int(
        (
            freight < 0
        ).sum()
    )

    if nonpositive_prices:
        errors.append(
            f"order_items.price contains "
            f"{nonpositive_prices:,} nonpositive values"
        )

    if negative_freight:
        errors.append(
            f"order_items.freight_value contains "
            f"{negative_freight:,} negative values"
        )

    print("\nOrder-item validation")
    print(
        "Price range:          "
        f"{price.min():.2f} to {price.max():.2f}"
    )
    print(
        "Freight range:        "
        f"{freight.min():.2f} to {freight.max():.2f}"
    )
    print(
        "Nonpositive prices:   "
        f"{nonpositive_prices:,}"
    )
    print(
        "Negative freight:     "
        f"{negative_freight:,}"
    )
    print(
        "Zero-freight records: "
        f"{int((freight == 0).sum()):,}"
    )


def inspect_purchase_dates(
    frames: dict[str, pd.DataFrame],
    errors: list[str],
) -> None:
    """Validate purchase timestamps and analysis-window coverage."""

    orders = frames["orders"]

    purchase_dates = validate_datetime_column(
        orders,
        "order_purchase_timestamp",
        "orders",
        errors,
    )

    invalid_dates = int(
        (
            orders[
                "order_purchase_timestamp"
            ].notna()
            & purchase_dates.isna()
        ).sum()
    )

    primary_window = (
        purchase_dates.ge(
            ANALYSIS_WINDOW_START
        )
        & purchase_dates.lt(
            ANALYSIS_WINDOW_END
        )
    )

    print("\nPurchase-date coverage")
    print(
        "Earliest purchase: "
        f"{purchase_dates.min()}"
    )
    print(
        "Latest purchase:   "
        f"{purchase_dates.max()}"
    )
    print(
        "Invalid dates:     "
        f"{invalid_dates:,}"
    )
    print(
        "Primary analysis window "
        "(2017-01 through 2018-08): "
        f"{int(primary_window.sum()):,} orders"
    )

    for column in [
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]:
        validate_datetime_column(
            orders,
            column,
            "orders",
            errors,
        )

    validate_datetime_column(
        frames["order_items"],
        "shipping_limit_date",
        "order_items",
        errors,
    )


def main() -> None:
    """Run the complete raw-data inspection."""

    frames, errors = load_datasets()

    if errors:
        print("RESULT: FAILED")

        for error in errors:
            print(f"- {error}")

        raise SystemExit(1)

    inspect_structure(
        frames,
        errors,
    )

    inspect_relationships(
        frames,
        errors,
    )

    inspect_order_coverage(frames)
    inspect_customers(frames)

    inspect_reviews(
        frames,
        errors,
    )

    inspect_categories(
        frames,
        errors,
    )

    inspect_order_items(
        frames,
        errors,
    )

    inspect_payments(
        frames,
        errors,
    )

    inspect_purchase_dates(
        frames,
        errors,
    )

    if errors:
        print("\nRESULT: FAILED")

        for error in errors:
            print(f"- {error}")

        raise SystemExit(1)

    print("\nRESULT: PASSED")


if __name__ == "__main__":
    main()