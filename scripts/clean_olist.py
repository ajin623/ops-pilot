from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "olist"
PROCESSED_DIRECTORY = PROJECT_ROOT / "data" / "processed" / "olist"

ANALYSIS_START = pd.Timestamp("2017-01-01")
ANALYSIS_END = pd.Timestamp("2018-09-01")

EXPECTED_ROWS = {
    "orders": 99_441,
    "order_items": 112_650,
    "products": 32_951,
    "sellers": 3_095,
    "payments": 103_886,
}

PRIMARY_KEYS = {
    "orders": ["order_id"],
    "order_items": ["order_id", "order_item_id"],
    "products": ["product_id"],
    "sellers": ["seller_id"],
    "payments": ["order_id", "payment_sequential"],
}

MANUAL_CATEGORY_TRANSLATIONS = {
    "pc_gamer": "gaming_pc",
    "portateis_cozinha_e_preparadores_de_alimentos": (
        "portable_kitchen_and_food_preparation_appliances"
    ),
}


def read_csv(
    filename: str,
    string_columns: list[str],
) -> pd.DataFrame:
    path = RAW_DIRECTORY / filename

    if not path.is_file():
        raise FileNotFoundError(
            f"Required source file not found: {path}"
        )

    return pd.read_csv(
        path,
        dtype={
            column: "string"
            for column in string_columns
        },
        low_memory=False,
    )


def load_source_tables() -> dict[str, pd.DataFrame]:
    return {
        "orders": read_csv(
            "olist_orders_dataset.csv",
            [
                "order_id",
                "customer_id",
                "order_status",
            ],
        ),
        "order_items": read_csv(
            "olist_order_items_dataset.csv",
            [
                "order_id",
                "product_id",
                "seller_id",
            ],
        ),
        "products": read_csv(
            "olist_products_dataset.csv",
            [
                "product_id",
                "product_category_name",
            ],
        ),
        "sellers": read_csv(
            "olist_sellers_dataset.csv",
            [
                "seller_id",
                "seller_zip_code_prefix",
                "seller_city",
                "seller_state",
            ],
        ),
        "payments": read_csv(
            "olist_order_payments_dataset.csv",
            [
                "order_id",
                "payment_type",
            ],
        ),
        "translations": read_csv(
            "product_category_name_translation.csv",
            [
                "product_category_name",
                "product_category_name_english",
            ],
        ),
    }


def clean_orders(
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    payments: pd.DataFrame,
) -> pd.DataFrame:
    orders = orders.copy()

    date_columns = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]

    for column in date_columns:
        orders[column] = pd.to_datetime(
            orders[column],
            errors="raise",
        )

    orders["order_status"] = (
        orders["order_status"]
        .str.strip()
        .str.lower()
    )

    item_order_ids = set(
        order_items["order_id"].dropna()
    )
    payment_order_ids = set(
        payments["order_id"].dropna()
    )

    orders["item_record_missing"] = (
        ~orders["order_id"].isin(item_order_ids)
    )
    orders["payment_record_missing"] = (
        ~orders["order_id"].isin(payment_order_ids)
    )

    purchase_timestamp = orders[
        "order_purchase_timestamp"
    ]

    orders["is_primary_analysis_window"] = (
        purchase_timestamp.ge(ANALYSIS_START)
        & purchase_timestamp.lt(ANALYSIS_END)
    )

    delivered_orders = orders[
        "order_status"
    ].eq("delivered")

    missing_delivery_information = (
        orders["order_approved_at"].isna()
        | orders[
            "order_delivered_carrier_date"
        ].isna()
        | orders[
            "order_delivered_customer_date"
        ].isna()
    )

    orders["has_delivery_data_issue"] = (
        delivered_orders
        & missing_delivery_information
    )

    return orders


def clean_order_items(
    order_items: pd.DataFrame,
) -> pd.DataFrame:
    order_items = order_items.copy()

    order_items["order_item_id"] = pd.to_numeric(
        order_items["order_item_id"],
        errors="raise",
    ).astype("Int64")

    order_items["shipping_limit_date"] = (
        pd.to_datetime(
            order_items["shipping_limit_date"],
            errors="raise",
        )
    )

    for column in ["price", "freight_value"]:
        order_items[column] = pd.to_numeric(
            order_items[column],
            errors="raise",
        ).astype("Float64")

    if order_items["price"].le(0).any():
        raise ValueError(
            "Order items contain non-positive prices"
        )

    if order_items["freight_value"].lt(0).any():
        raise ValueError(
            "Order items contain negative freight values"
        )

    order_items["item_total_value"] = (
        order_items["price"]
        + order_items["freight_value"]
    ).round(2)

    return order_items


def clean_products(
    products: pd.DataFrame,
    translations: pd.DataFrame,
) -> pd.DataFrame:
    products = products.copy()

    products = products.rename(
        columns={
            "product_name_lenght": (
                "product_name_length"
            ),
            "product_description_lenght": (
                "product_description_length"
            ),
        }
    )

    integer_columns = [
        "product_name_length",
        "product_description_length",
        "product_photos_qty",
    ]

    measurement_columns = [
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]

    for column in integer_columns:
        products[column] = pd.to_numeric(
            products[column],
            errors="raise",
        ).astype("Int64")

    for column in measurement_columns:
        products[column] = pd.to_numeric(
            products[column],
            errors="raise",
        ).astype("Float64")

    products = products.merge(
        translations,
        how="left",
        on="product_category_name",
        validate="many_to_one",
    )

    products["category_translation_method"] = (
        pd.Series(
            pd.NA,
            index=products.index,
            dtype="string",
        )
    )

    dataset_translation = products[
        "product_category_name_english"
    ].notna()

    products.loc[
        dataset_translation,
        "category_translation_method",
    ] = "dataset"

    manual_values = products[
        "product_category_name"
    ].map(MANUAL_CATEGORY_TRANSLATIONS)

    manual_translation = (
        products[
            "product_category_name_english"
        ].isna()
        & manual_values.notna()
    )

    products.loc[
        manual_translation,
        "product_category_name_english",
    ] = manual_values[manual_translation]

    products.loc[
        manual_translation,
        "category_translation_method",
    ] = "manual"

    products["category_translation_missing"] = (
        products[
            "product_category_name"
        ].notna()
        & products[
            "product_category_name_english"
        ].isna()
    )

    return products


def clean_sellers(
    sellers: pd.DataFrame,
) -> pd.DataFrame:
    sellers = sellers.copy()

    sellers["seller_zip_code_prefix"] = (
        sellers["seller_zip_code_prefix"]
        .str.strip()
        .str.zfill(5)
    )

    sellers["seller_city"] = (
        sellers["seller_city"].str.strip()
    )

    sellers["seller_state"] = (
        sellers["seller_state"]
        .str.strip()
        .str.upper()
    )

    return sellers


def clean_payments(
    payments: pd.DataFrame,
) -> pd.DataFrame:
    payments = payments.copy()

    payments["payment_type"] = (
        payments["payment_type"]
        .str.strip()
        .str.lower()
    )

    payments["payment_sequential"] = (
        pd.to_numeric(
            payments["payment_sequential"],
            errors="raise",
        ).astype("Int64")
    )

    payments["payment_installments"] = (
        pd.to_numeric(
            payments["payment_installments"],
            errors="raise",
        ).astype("Int64")
    )

    payments["payment_value"] = (
        pd.to_numeric(
            payments["payment_value"],
            errors="raise",
        ).astype("Float64")
    )

    if payments["payment_value"].lt(0).any():
        raise ValueError(
            "Payments contain negative values"
        )

    payments["invalid_installment_count"] = (
        payments["payment_installments"].le(0)
    )

    payments["is_zero_value_payment"] = (
        payments["payment_value"].eq(0)
    )

    sequence_statistics = payments.groupby(
        "order_id"
    )["payment_sequential"].agg(
        ["min", "max", "nunique"]
    )

    sequence_start_missing_orders = (
        sequence_statistics.index[
            sequence_statistics["min"] != 1
        ]
    )

    sequence_span = (
        sequence_statistics["max"]
        - sequence_statistics["min"]
        + 1
    )

    sequence_internal_gap_orders = (
        sequence_statistics.index[
            sequence_span
            != sequence_statistics["nunique"]
        ]
    )

    payments[
        "payment_sequence_start_missing"
    ] = payments["order_id"].isin(
        sequence_start_missing_orders
    )

    payments[
        "payment_sequence_internal_gap"
    ] = payments["order_id"].isin(
        sequence_internal_gap_orders
    )

    return payments


def validate_cleaned_tables(
    tables: dict[str, pd.DataFrame],
) -> None:
    for table_name, expected_rows in (
        EXPECTED_ROWS.items()
    ):
        frame = tables[table_name]

        if len(frame) != expected_rows:
            raise ValueError(
                f"{table_name}: expected "
                f"{expected_rows:,} rows, "
                f"found {len(frame):,}"
            )

        duplicate_count = int(
            frame.duplicated(
                subset=PRIMARY_KEYS[table_name]
            ).sum()
        )

        if duplicate_count:
            raise ValueError(
                f"{table_name}: found "
                f"{duplicate_count:,} duplicate keys"
            )

    unresolved_categories = int(
        tables["products"][
            "category_translation_missing"
        ].sum()
    )

    if unresolved_categories:
        raise ValueError(
            "Products contain "
            f"{unresolved_categories:,} "
            "unresolved non-null categories"
        )


def write_cleaned_tables(
    tables: dict[str, pd.DataFrame],
) -> None:
    PROCESSED_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_files = {
        "orders": "orders.csv",
        "order_items": "order_items.csv",
        "products": "products.csv",
        "sellers": "sellers.csv",
        "payments": "payments.csv",
    }

    print("\nCleaned output files")

    for table_name, filename in (
        output_files.items()
    ):
        destination = (
            PROCESSED_DIRECTORY / filename
        )

        tables[table_name].to_csv(
            destination,
            index=False,
            date_format="%Y-%m-%d %H:%M:%S",
            lineterminator="\n",
        )

        print(
            f"{table_name:<12} "
            f"{len(tables[table_name]):>8,} "
            "rows -> "
            f"{destination.relative_to(PROJECT_ROOT)}"
        )


def print_quality_summary(
    tables: dict[str, pd.DataFrame],
) -> None:
    orders = tables["orders"]
    products = tables["products"]
    payments = tables["payments"]

    sequence_start_missing_orders = (
        payments.loc[
            payments[
                "payment_sequence_start_missing"
            ],
            "order_id",
        ].nunique()
    )

    sequence_internal_gap_orders = (
        payments.loc[
            payments[
                "payment_sequence_internal_gap"
            ],
            "order_id",
        ].nunique()
    )

    manual_translation_rows = products[
        "category_translation_method"
    ].eq("manual")

    manual_category_count = products.loc[
        manual_translation_rows,
        "product_category_name",
    ].nunique()

    manual_product_count = int(
        manual_translation_rows.sum()
    )

    print("\nQuality and scope flags")

    print(
        "Primary-window orders:         "
        f"{int(orders['is_primary_analysis_window'].sum()):,}"
    )
    print(
        "Orders missing items:          "
        f"{int(orders['item_record_missing'].sum()):,}"
    )
    print(
        "Orders missing payments:       "
        f"{int(orders['payment_record_missing'].sum()):,}"
    )
    print(
        "Delivered-data issues:         "
        f"{int(orders['has_delivery_data_issue'].sum()):,}"
    )
    print(
        "Manual translation categories: "
        f"{manual_category_count:,}"
    )
    print(
        "Products using manual mapping:  "
        f"{manual_product_count:,}"
    )
    print(
        "Products without categories:   "
        f"{int(products['product_category_name'].isna().sum()):,}"
    )
    print(
        "Invalid installment records:   "
        f"{int(payments['invalid_installment_count'].sum()):,}"
    )
    print(
        "Zero-value payments:           "
        f"{int(payments['is_zero_value_payment'].sum()):,}"
    )
    print(
        "Payment sequences starting >1: "
        f"{int(sequence_start_missing_orders):,}"
    )
    print(
        "Payment internal-gap orders:   "
        f"{int(sequence_internal_gap_orders):,}"
    )


def main() -> int:
    try:
        source = load_source_tables()

        cleaned = {
            "orders": clean_orders(
                source["orders"],
                source["order_items"],
                source["payments"],
            ),
            "order_items": clean_order_items(
                source["order_items"]
            ),
            "products": clean_products(
                source["products"],
                source["translations"],
            ),
            "sellers": clean_sellers(
                source["sellers"]
            ),
            "payments": clean_payments(
                source["payments"]
            ),
        }

        validate_cleaned_tables(cleaned)
        write_cleaned_tables(cleaned)
        print_quality_summary(cleaned)

    except (
        FileNotFoundError,
        ValueError,
    ) as error:
        print(
            f"\nRESULT: FAILED — {error}",
            file=sys.stderr,
        )
        return 1

    print("\nRESULT: CLEANING COMPLETED")
    return 0


if __name__ == "__main__":
    sys.exit(main())