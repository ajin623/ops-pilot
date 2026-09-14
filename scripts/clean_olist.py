"""Clean and validate the Brazilian Olist e-commerce datasets.

The script produces seven analysis-ready CSV files:

- customers
- orders
- order_items
- products
- sellers
- payments
- reviews

Business metrics are not calculated by an LLM. This pipeline produces
deterministic fields and quality flags for later SQL and Python analysis.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "olist"
PROCESSED_DIRECTORY = PROJECT_ROOT / "data" / "processed" / "olist"

ANALYSIS_WINDOW_START = pd.Timestamp("2017-01-01")
ANALYSIS_WINDOW_END = pd.Timestamp("2018-09-01")

RAW_FILES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

EXPECTED_COLUMNS = {
    "customers": [
        "customer_id",
        "customer_unique_id",
        "customer_zip_code_prefix",
        "customer_city",
        "customer_state",
    ],
    "orders": [
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": [
        "order_id",
        "order_item_id",
        "product_id",
        "seller_id",
        "shipping_limit_date",
        "price",
        "freight_value",
    ],
    "products": [
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
    "sellers": [
        "seller_id",
        "seller_zip_code_prefix",
        "seller_city",
        "seller_state",
    ],
    "payments": [
        "order_id",
        "payment_sequential",
        "payment_type",
        "payment_installments",
        "payment_value",
    ],
    "reviews": [
        "review_id",
        "order_id",
        "review_score",
        "review_comment_title",
        "review_comment_message",
        "review_creation_date",
        "review_answer_timestamp",
    ],
    "category_translation": [
        "product_category_name",
        "product_category_name_english",
    ],
}

MANUAL_CATEGORY_TRANSLATIONS = {
    "pc_gamer": "pc_gamer",
    "portateis_cozinha_e_preparadores_de_alimentos": (
        "portable_kitchen_and_food_preparation_appliances"
    ),
}


def load_raw_file(dataset_name: str) -> pd.DataFrame:
    """Load one raw CSV and validate its columns."""

    path = RAW_DIRECTORY / RAW_FILES[dataset_name]

    if not path.is_file():
        raise FileNotFoundError(f"Required raw file was not found: {path}")

    frame = pd.read_csv(path, dtype="string")
    expected = EXPECTED_COLUMNS[dataset_name]

    missing_columns = sorted(set(expected) - set(frame.columns))
    unexpected_columns = sorted(set(frame.columns) - set(expected))

    if missing_columns:
        raise ValueError(
            f"{dataset_name} is missing columns: {missing_columns}"
        )

    if unexpected_columns:
        raise ValueError(
            f"{dataset_name} has unexpected columns: {unexpected_columns}"
        )

    return frame[expected].copy()


def normalize_strings(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove surrounding whitespace and convert empty strings to null."""

    result = frame.copy()

    for column in result.columns:
        if isinstance(result[column].dtype, pd.StringDtype):
            result[column] = result[column].str.strip()
            result[column] = result[column].replace("", pd.NA)

    return result


def convert_integers(
    frame: pd.DataFrame,
    columns: list[str],
) -> None:
    """Convert selected columns to nullable integers."""

    for column in columns:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        ).astype("Int64")


def convert_floats(
    frame: pd.DataFrame,
    columns: list[str],
) -> None:
    """Convert selected columns to nullable floating-point values."""

    for column in columns:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        ).astype("Float64")


def convert_datetimes(
    frame: pd.DataFrame,
    columns: list[str],
) -> None:
    """Convert selected columns to validated timestamps."""

    for column in columns:
        original = frame[column]
        converted = pd.to_datetime(original, errors="coerce")

        invalid_count = int(
            (
                original.notna()
                & converted.isna()
            ).sum()
        )

        if invalid_count:
            raise ValueError(
                f"{column} contains {invalid_count:,} invalid timestamps"
            )

        frame[column] = converted


def validate_key(
    frame: pd.DataFrame,
    key_columns: list[str],
    dataset_name: str,
) -> None:
    """Validate required and unique keys."""

    missing_key_rows = int(
        frame[key_columns].isna().any(axis=1).sum()
    )

    if missing_key_rows:
        raise ValueError(
            f"{dataset_name} contains "
            f"{missing_key_rows:,} rows with missing keys"
        )

    duplicate_key_rows = int(
        frame.duplicated(subset=key_columns).sum()
    )

    if duplicate_key_rows:
        raise ValueError(
            f"{dataset_name} contains "
            f"{duplicate_key_rows:,} duplicate rows for key "
            f"{key_columns}"
        )


def validate_foreign_key(
    child: pd.DataFrame,
    child_column: str,
    parent: pd.DataFrame,
    parent_column: str,
    relationship: str,
) -> None:
    """Validate that child values exist in the parent dataset."""

    child_values = set(child[child_column].dropna())
    parent_values = set(parent[parent_column].dropna())
    orphan_values = child_values - parent_values

    if orphan_values:
        raise ValueError(
            f"{relationship} contains "
            f"{len(orphan_values):,} orphan keys"
        )


def validate_rule(
    failing_condition: pd.Series,
    message: str,
) -> None:
    """Raise an error when a required data rule fails."""

    failure_count = int(
        failing_condition.fillna(False).sum()
    )

    if failure_count:
        raise ValueError(
            f"{message}: {failure_count:,} records"
        )


def prepare_customers(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare customer identifiers and destination locations."""

    customers = normalize_strings(frame)

    convert_integers(
        customers,
        ["customer_zip_code_prefix"],
    )

    validate_key(
        customers,
        ["customer_id"],
        "customers",
    )

    return customers


def prepare_order_items(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare item, seller and monetary fields."""

    order_items = normalize_strings(frame)

    convert_integers(
        order_items,
        ["order_item_id"],
    )

    convert_floats(
        order_items,
        [
            "price",
            "freight_value",
        ],
    )

    convert_datetimes(
        order_items,
        ["shipping_limit_date"],
    )

    validate_key(
        order_items,
        [
            "order_id",
            "order_item_id",
        ],
        "order_items",
    )

    validate_rule(
        order_items["price"] <= 0,
        "Order-item price must be positive",
    )

    validate_rule(
        order_items["freight_value"] < 0,
        "Freight value cannot be negative",
    )

    order_items["item_total"] = (
        order_items["price"]
        + order_items["freight_value"]
    ).astype("Float64")

    return order_items


def prepare_products(
    frame: pd.DataFrame,
    translations: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare product dimensions and category translations."""

    products = normalize_strings(frame)
    translations = normalize_strings(translations)

    products = products.rename(
        columns={
            "product_name_lenght": "product_name_length",
            "product_description_lenght": (
                "product_description_length"
            ),
        }
    )

    convert_integers(
        products,
        [
            "product_name_length",
            "product_description_length",
            "product_photos_qty",
        ],
    )

    physical_measurement_columns = [
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]

    convert_floats(
        products,
        physical_measurement_columns,
    )

    invalid_physical_measurement_mask = products[
        physical_measurement_columns
    ].le(0)

    invalid_physical_measurement_count = int(
        invalid_physical_measurement_mask.any(axis=1).sum()
    )

    products[physical_measurement_columns] = products[
        physical_measurement_columns
    ].mask(invalid_physical_measurement_mask)

    if invalid_physical_measurement_count:
        print(
            "Normalized nonpositive product measurements: "
            f"{invalid_physical_measurement_count:,}"
        )

    validate_key(
        products,
        ["product_id"],
        "products",
    )

    validate_key(
        translations,
        ["product_category_name"],
        "category_translation",
    )

    translation_lookup = (
        translations.set_index("product_category_name")[
            "product_category_name_english"
        ].to_dict()
    )

    products["product_category_name_english"] = products[
        "product_category_name"
    ].map(translation_lookup)

    official_mapping = products[
        "product_category_name_english"
    ].notna()

    manual_mapping = (
        products["product_category_name"].notna()
        & products["product_category_name_english"].isna()
        & products["product_category_name"].isin(
            MANUAL_CATEGORY_TRANSLATIONS
        )
    )

    products.loc[
        manual_mapping,
        "product_category_name_english",
    ] = (
        products.loc[
            manual_mapping,
            "product_category_name",
        ].map(MANUAL_CATEGORY_TRANSLATIONS)
    )

    products["category_translation_source"] = pd.Series(
        pd.NA,
        index=products.index,
        dtype="string",
    )

    products.loc[
        official_mapping,
        "category_translation_source",
    ] = "official"

    products.loc[
        manual_mapping,
        "category_translation_source",
    ] = "manual"

    missing_category = products[
        "product_category_name"
    ].isna()

    products.loc[
        missing_category,
        "category_translation_source",
    ] = "missing"

    unmapped_categories = sorted(
        products.loc[
            products["product_category_name"].notna()
            & products[
                "product_category_name_english"
            ].isna(),
            "product_category_name",
        ]
        .dropna()
        .unique()
        .tolist()
    )

    if unmapped_categories:
        raise ValueError(
            "Product categories still lack translations: "
            f"{unmapped_categories}"
        )

    return products


def prepare_sellers(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare seller identifiers and origin locations."""

    sellers = normalize_strings(frame)

    convert_integers(
        sellers,
        ["seller_zip_code_prefix"],
    )

    validate_key(
        sellers,
        ["seller_id"],
        "sellers",
    )

    return sellers


def prepare_payments(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare payments and explainable payment-quality flags."""

    payments = normalize_strings(frame)

    convert_integers(
        payments,
        [
            "payment_sequential",
            "payment_installments",
        ],
    )

    convert_floats(
        payments,
        ["payment_value"],
    )

    validate_key(
        payments,
        [
            "order_id",
            "payment_sequential",
        ],
        "payments",
    )

    validate_rule(
        payments["payment_sequential"] < 1,
        "Payment sequence must be at least one",
    )

    validate_rule(
        payments["payment_value"] < 0,
        "Payment value cannot be negative",
    )

    payments["is_invalid_installment"] = (
        payments["payment_installments"] <= 0
    )

    payments["is_zero_value_payment"] = (
        payments["payment_value"] == 0
    )

    sequence_statistics = (
        payments.groupby("order_id")["payment_sequential"]
        .agg(["min", "max", "nunique"])
        .rename(
            columns={
                "min": "minimum_sequence",
                "max": "maximum_sequence",
                "nunique": "observed_sequences",
            }
        )
    )

    sequence_statistics["expected_sequences"] = (
        sequence_statistics["maximum_sequence"]
        - sequence_statistics["minimum_sequence"]
        + 1
    )

    start_missing_orders = set(
        sequence_statistics.index[
            sequence_statistics["minimum_sequence"] > 1
        ]
    )

    internal_gap_orders = set(
        sequence_statistics.index[
            sequence_statistics["observed_sequences"]
            != sequence_statistics["expected_sequences"]
        ]
    )

    payments["payment_sequence_start_missing"] = (
        payments["order_id"].isin(start_missing_orders)
    )

    payments["payment_sequence_internal_gap"] = (
        payments["order_id"].isin(internal_gap_orders)
    )

    return payments


def prepare_reviews(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare reviews while retaining multiple reviews per order."""

    reviews = normalize_strings(frame)

    convert_integers(
        reviews,
        ["review_score"],
    )

    convert_datetimes(
        reviews,
        [
            "review_creation_date",
            "review_answer_timestamp",
        ],
    )

    validate_key(
        reviews,
        [
            "review_id",
            "order_id",
        ],
        "reviews",
    )

    validate_rule(
        ~reviews["review_score"].between(1, 5),
        "Review score must be between one and five",
    )

    return reviews


def prepare_orders(
    frame: pd.DataFrame,
    order_items: pd.DataFrame,
    payments: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare orders, durations, eligibility fields and quality flags."""

    orders = normalize_strings(frame)

    timestamp_columns = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]

    convert_datetimes(
        orders,
        timestamp_columns,
    )

    validate_key(
        orders,
        ["order_id"],
        "orders",
    )

    item_order_ids = set(
        order_items["order_id"].dropna()
    )
    payment_order_ids = set(
        payments["order_id"].dropna()
    )

    orders["has_order_items"] = orders[
        "order_id"
    ].isin(item_order_ids)

    orders["has_payment"] = orders[
        "order_id"
    ].isin(payment_order_ids)

    orders["is_primary_analysis_window"] = (
        orders["order_purchase_timestamp"].ge(
            ANALYSIS_WINDOW_START
        )
        & orders["order_purchase_timestamp"].lt(
            ANALYSIS_WINDOW_END
        )
    )

    purchase = orders["order_purchase_timestamp"]
    approved = orders["order_approved_at"]
    carrier = orders["order_delivered_carrier_date"]
    customer_delivery = orders[
        "order_delivered_customer_date"
    ]
    estimated_delivery = orders[
        "order_estimated_delivery_date"
    ]

    delivered = orders["order_status"].eq("delivered")

    missing_operational_timestamp = (
        delivered
        & orders[
            [
                "order_approved_at",
                "order_delivered_carrier_date",
                "order_delivered_customer_date",
            ]
        ]
        .isna()
        .any(axis=1)
    )

    approval_before_purchase = (
        approved.notna()
        & purchase.notna()
        & approved.lt(purchase)
    )

    carrier_before_purchase = (
        carrier.notna()
        & purchase.notna()
        & carrier.lt(purchase)
    )

    carrier_before_approval = (
        carrier.notna()
        & approved.notna()
        & carrier.lt(approved)
    )

    customer_before_purchase = (
        customer_delivery.notna()
        & purchase.notna()
        & customer_delivery.lt(purchase)
    )

    customer_before_carrier = (
        customer_delivery.notna()
        & carrier.notna()
        & customer_delivery.lt(carrier)
    )

    estimated_before_purchase = (
        estimated_delivery.notna()
        & purchase.notna()
        & estimated_delivery.lt(purchase)
    )

    operational_chronology_issue = (
        delivered
        & (
            approval_before_purchase
            | carrier_before_purchase
            | carrier_before_approval
            | customer_before_purchase
            | customer_before_carrier
            | estimated_before_purchase
        )
    )

    orders["has_missing_operational_timestamp"] = (
        missing_operational_timestamp
    )

    orders["has_operational_chronology_issue"] = (
        operational_chronology_issue
    )

    delivery_kpi_eligible = (
        delivered
        & purchase.notna()
        & customer_delivery.notna()
        & estimated_delivery.notna()
        & customer_delivery.ge(purchase)
        & estimated_delivery.ge(purchase)
    )

    orders["is_delivery_kpi_eligible"] = (
        delivery_kpi_eligible
    )

    orders["is_on_time_delivery"] = pd.Series(
        pd.NA,
        index=orders.index,
        dtype="boolean",
    )

    orders.loc[
        delivery_kpi_eligible,
        "is_on_time_delivery",
    ] = (
        customer_delivery.loc[
            delivery_kpi_eligible
        ]
        <= estimated_delivery.loc[
            delivery_kpi_eligible
        ]
    )

    delivery_days = (
        customer_delivery - purchase
    ).dt.total_seconds() / 86_400

    delivery_delay_days = (
        customer_delivery - estimated_delivery
    ).dt.total_seconds() / 86_400

    orders["delivery_days"] = (
        delivery_days.where(
            delivery_kpi_eligible
        ).astype("Float64")
    )

    orders["delivery_delay_days"] = (
        delivery_delay_days.where(
            delivery_kpi_eligible
        ).astype("Float64")
    )

    orders["late_delivery_days"] = (
        delivery_delay_days.clip(lower=0)
        .where(delivery_kpi_eligible)
        .astype("Float64")
    )

    handling_time_eligible = (
        purchase.notna()
        & approved.notna()
        & carrier.notna()
        & approved.ge(purchase)
        & carrier.ge(purchase)
        & carrier.ge(approved)
        & (
            customer_delivery.isna()
            | customer_delivery.ge(carrier)
        )
    )

    orders["is_handling_time_eligible"] = (
        handling_time_eligible
    )

    approval_to_carrier_days = (
        carrier - approved
    ).dt.total_seconds() / 86_400

    orders["approval_to_carrier_days"] = (
        approval_to_carrier_days.where(
            handling_time_eligible
        ).astype("Float64")
    )

    return orders


def write_processed_file(
    name: str,
    frame: pd.DataFrame,
) -> Path:
    """Write one cleaned dataframe to the processed directory."""

    output_path = PROCESSED_DIRECTORY / f"{name}.csv"

    frame.to_csv(
        output_path,
        index=False,
        na_rep="",
        date_format="%Y-%m-%d %H:%M:%S",
        lineterminator="\n",
    )

    return output_path


def main() -> None:
    """Execute the complete cleaning pipeline."""

    PROCESSED_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_frames = {
        name: load_raw_file(name)
        for name in RAW_FILES
    }

    customers = prepare_customers(
        raw_frames["customers"]
    )

    order_items = prepare_order_items(
        raw_frames["order_items"]
    )

    products = prepare_products(
        raw_frames["products"],
        raw_frames["category_translation"],
    )

    sellers = prepare_sellers(
        raw_frames["sellers"]
    )

    payments = prepare_payments(
        raw_frames["payments"]
    )

    reviews = prepare_reviews(
        raw_frames["reviews"]
    )

    orders = prepare_orders(
        raw_frames["orders"],
        order_items,
        payments,
    )

    validate_foreign_key(
        orders,
        "customer_id",
        customers,
        "customer_id",
        "orders.customer_id -> customers.customer_id",
    )

    validate_foreign_key(
        order_items,
        "order_id",
        orders,
        "order_id",
        "order_items.order_id -> orders.order_id",
    )

    validate_foreign_key(
        order_items,
        "product_id",
        products,
        "product_id",
        "order_items.product_id -> products.product_id",
    )

    validate_foreign_key(
        order_items,
        "seller_id",
        sellers,
        "seller_id",
        "order_items.seller_id -> sellers.seller_id",
    )

    validate_foreign_key(
        payments,
        "order_id",
        orders,
        "order_id",
        "payments.order_id -> orders.order_id",
    )

    validate_foreign_key(
        reviews,
        "order_id",
        orders,
        "order_id",
        "reviews.order_id -> orders.order_id",
    )

    output_frames = {
        "customers": customers,
        "orders": orders,
        "order_items": order_items,
        "products": products,
        "sellers": sellers,
        "payments": payments,
        "reviews": reviews,
    }

    output_paths = {
        name: write_processed_file(name, frame)
        for name, frame in output_frames.items()
    }

    delivered = orders["order_status"].eq("delivered")

    carrier_before_purchase = (
        delivered
        & orders["order_delivered_carrier_date"].notna()
        & orders["order_delivered_carrier_date"].lt(
            orders["order_purchase_timestamp"]
        )
    )

    carrier_before_approval = (
        delivered
        & orders["order_delivered_carrier_date"].notna()
        & orders["order_approved_at"].notna()
        & orders["order_delivered_carrier_date"].lt(
            orders["order_approved_at"]
        )
    )

    customer_before_carrier = (
        delivered
        & orders["order_delivered_customer_date"].notna()
        & orders["order_delivered_carrier_date"].notna()
        & orders["order_delivered_customer_date"].lt(
            orders["order_delivered_carrier_date"]
        )
    )

    customer_frequency = (
        customers.groupby("customer_unique_id").size()
    )

    review_frequency = (
        reviews.groupby("order_id").size()
    )

    manual_products = products[
        "category_translation_source"
    ].eq("manual")

    manual_category_count = int(
        products.loc[
            manual_products,
            "product_category_name",
        ].nunique()
    )

    order_ids = set(orders["order_id"])
    review_order_ids = set(reviews["order_id"])

    print("\nCleaned output files")

    for name, frame in output_frames.items():
        relative_path = output_paths[name].relative_to(
            PROJECT_ROOT
        )

        print(
            f"{name:<12} "
            f"{len(frame):>9,} rows -> "
            f"{relative_path}"
        )

    print("\nQuality and scope flags")
    print(
        "Primary-window orders:                  "
        f"{int(orders['is_primary_analysis_window'].sum()):,}"
    )
    print(
        "Orders missing items:                   "
        f"{int((~orders['has_order_items']).sum()):,}"
    )
    print(
        "Orders missing payments:                "
        f"{int((~orders['has_payment']).sum()):,}"
    )
    print(
        "Delivered orders:                       "
        f"{int(delivered.sum()):,}"
    )
    print(
        "Missing operational timestamps:         "
        f"{int(orders['has_missing_operational_timestamp'].sum()):,}"
    )
    print(
        "Operational chronology issues:          "
        f"{int(orders['has_operational_chronology_issue'].sum()):,}"
    )
    print(
        "Carrier before purchase:                "
        f"{int(carrier_before_purchase.sum()):,}"
    )
    print(
        "Carrier before approval:                "
        f"{int(carrier_before_approval.sum()):,}"
    )
    print(
        "Customer delivery before carrier:       "
        f"{int(customer_before_carrier.sum()):,}"
    )
    print(
        "Delivery-KPI eligible orders:           "
        f"{int(orders['is_delivery_kpi_eligible'].sum()):,}"
    )
    print(
        "Handling-time eligible delivered orders:"
        f" {int((delivered & orders['is_handling_time_eligible']).sum()):,}"
    )
    print(
        "Repeat customer identities:             "
        f"{int((customer_frequency > 1).sum()):,}"
    )
    print(
        "Manual translation categories:          "
        f"{manual_category_count:,}"
    )
    print(
        "Products using manual translation:      "
        f"{int(manual_products.sum()):,}"
    )
    print(
        "Products without categories:            "
        f"{int(products['product_category_name'].isna().sum()):,}"
    )
    print(
        "Invalid installment records:            "
        f"{int(payments['is_invalid_installment'].sum()):,}"
    )
    print(
        "Zero-value payments:                    "
        f"{int(payments['is_zero_value_payment'].sum()):,}"
    )
    print(
        "Payment sequences starting >1:          "
        f"{payments.loc[payments['payment_sequence_start_missing'], 'order_id'].nunique():,}"
    )
    print(
        "Payment internal-gap orders:            "
        f"{payments.loc[payments['payment_sequence_internal_gap'], 'order_id'].nunique():,}"
    )
    print(
        "Orders without reviews:                 "
        f"{len(order_ids - review_order_ids):,}"
    )
    print(
        "Orders with multiple reviews:           "
        f"{int((review_frequency > 1).sum()):,}"
    )

    print("\nRESULT: CLEANING COMPLETED")


if __name__ == "__main__":
    main()