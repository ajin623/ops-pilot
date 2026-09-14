BEGIN;

CREATE SCHEMA IF NOT EXISTS opspilot;

SET search_path TO opspilot, public;


CREATE TABLE opspilot.customers (
    customer_id VARCHAR(32) PRIMARY KEY,
    customer_unique_id VARCHAR(32) NOT NULL,
    customer_zip_code_prefix INTEGER NOT NULL,
    customer_city TEXT NOT NULL,
    customer_state CHAR(2) NOT NULL,

    CONSTRAINT customers_customer_id_length
        CHECK (char_length(customer_id) = 32),

    CONSTRAINT customers_unique_id_length
        CHECK (char_length(customer_unique_id) = 32),

    CONSTRAINT customers_zip_code_range
        CHECK (
            customer_zip_code_prefix
            BETWEEN 0 AND 99999
        ),

    CONSTRAINT customers_state_length
        CHECK (
            char_length(trim(customer_state)) = 2
        )
);


CREATE TABLE opspilot.products (
    product_id VARCHAR(32) PRIMARY KEY,
    product_category_name TEXT,
    product_name_length INTEGER,
    product_description_length INTEGER,
    product_photos_qty INTEGER,
    product_weight_g NUMERIC(12, 2),
    product_length_cm NUMERIC(12, 2),
    product_height_cm NUMERIC(12, 2),
    product_width_cm NUMERIC(12, 2),
    product_category_name_english TEXT,
    category_translation_source VARCHAR(10) NOT NULL,

    CONSTRAINT products_product_id_length
        CHECK (char_length(product_id) = 32),

    CONSTRAINT products_name_length_nonnegative
        CHECK (
            product_name_length IS NULL
            OR product_name_length >= 0
        ),

    CONSTRAINT products_description_length_nonnegative
        CHECK (
            product_description_length IS NULL
            OR product_description_length >= 0
        ),

    CONSTRAINT products_photo_quantity_nonnegative
        CHECK (
            product_photos_qty IS NULL
            OR product_photos_qty >= 0
        ),

    CONSTRAINT products_weight_positive
        CHECK (
            product_weight_g IS NULL
            OR product_weight_g > 0
        ),

    CONSTRAINT products_length_positive
        CHECK (
            product_length_cm IS NULL
            OR product_length_cm > 0
        ),

    CONSTRAINT products_height_positive
        CHECK (
            product_height_cm IS NULL
            OR product_height_cm > 0
        ),

    CONSTRAINT products_width_positive
        CHECK (
            product_width_cm IS NULL
            OR product_width_cm > 0
        ),

    CONSTRAINT products_translation_source
        CHECK (
            category_translation_source
            IN (
                'official',
                'manual',
                'missing'
            )
        ),

    CONSTRAINT products_translation_consistency
        CHECK (
            (
                category_translation_source = 'missing'
                AND product_category_name IS NULL
                AND product_category_name_english IS NULL
            )
            OR
            (
                category_translation_source
                IN ('official', 'manual')
                AND product_category_name IS NOT NULL
                AND product_category_name_english IS NOT NULL
            )
        )
);


CREATE TABLE opspilot.sellers (
    seller_id VARCHAR(32) PRIMARY KEY,
    seller_zip_code_prefix INTEGER NOT NULL,
    seller_city TEXT NOT NULL,
    seller_state CHAR(2) NOT NULL,

    CONSTRAINT sellers_seller_id_length
        CHECK (char_length(seller_id) = 32),

    CONSTRAINT sellers_zip_code_range
        CHECK (
            seller_zip_code_prefix
            BETWEEN 0 AND 99999
        ),

    CONSTRAINT sellers_state_length
        CHECK (
            char_length(trim(seller_state)) = 2
        )
);


CREATE TABLE opspilot.orders (
    order_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    order_purchase_timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    order_approved_at TIMESTAMP WITHOUT TIME ZONE,
    order_delivered_carrier_date TIMESTAMP WITHOUT TIME ZONE,
    order_delivered_customer_date TIMESTAMP WITHOUT TIME ZONE,
    order_estimated_delivery_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,

    has_order_items BOOLEAN NOT NULL,
    has_payment BOOLEAN NOT NULL,
    is_primary_analysis_window BOOLEAN NOT NULL,

    has_missing_operational_timestamp BOOLEAN NOT NULL,
    has_operational_chronology_issue BOOLEAN NOT NULL,

    is_delivery_kpi_eligible BOOLEAN NOT NULL,
    is_on_time_delivery BOOLEAN,

    delivery_days NUMERIC(14, 6),
    delivery_delay_days NUMERIC(14, 6),
    late_delivery_days NUMERIC(14, 6),

    is_handling_time_eligible BOOLEAN NOT NULL,
    approval_to_carrier_days NUMERIC(14, 6),

    CONSTRAINT orders_customer_foreign_key
        FOREIGN KEY (customer_id)
        REFERENCES opspilot.customers (
            customer_id
        ),

    CONSTRAINT orders_order_id_length
        CHECK (char_length(order_id) = 32),

    CONSTRAINT orders_customer_id_length
        CHECK (char_length(customer_id) = 32),

    CONSTRAINT orders_status_values
        CHECK (
            order_status IN (
                'created',
                'approved',
                'invoiced',
                'processing',
                'shipped',
                'delivered',
                'unavailable',
                'canceled'
            )
        ),

    CONSTRAINT orders_analysis_window_consistency
        CHECK (
            is_primary_analysis_window = (
                order_purchase_timestamp
                    >= TIMESTAMP '2017-01-01 00:00:00'
                AND order_purchase_timestamp
                    < TIMESTAMP '2018-09-01 00:00:00'
            )
        ),

    CONSTRAINT orders_missing_timestamp_consistency
        CHECK (
            has_missing_operational_timestamp = (
                order_status = 'delivered'
                AND (
                    order_approved_at IS NULL
                    OR order_delivered_carrier_date IS NULL
                    OR order_delivered_customer_date IS NULL
                )
            )
        ),

    CONSTRAINT orders_chronology_flag_scope
        CHECK (
            NOT has_operational_chronology_issue
            OR order_status = 'delivered'
        ),

    CONSTRAINT orders_delivery_eligibility
        CHECK (
            NOT is_delivery_kpi_eligible
            OR (
                order_status = 'delivered'
                AND order_delivered_customer_date IS NOT NULL
                AND order_estimated_delivery_date IS NOT NULL
                AND order_delivered_customer_date
                    >= order_purchase_timestamp
                AND order_estimated_delivery_date
                    >= order_purchase_timestamp
            )
        ),

    CONSTRAINT orders_delivery_metrics_consistency
        CHECK (
            (
                is_delivery_kpi_eligible
                AND is_on_time_delivery IS NOT NULL
                AND delivery_days IS NOT NULL
                AND delivery_delay_days IS NOT NULL
                AND late_delivery_days IS NOT NULL
            )
            OR
            (
                NOT is_delivery_kpi_eligible
                AND is_on_time_delivery IS NULL
                AND delivery_days IS NULL
                AND delivery_delay_days IS NULL
                AND late_delivery_days IS NULL
            )
        ),

    CONSTRAINT orders_on_time_flag_consistency
        CHECK (
            is_on_time_delivery IS NULL
            OR is_on_time_delivery = (
                order_delivered_customer_date
                <= order_estimated_delivery_date
            )
        ),

    CONSTRAINT orders_delivery_days_nonnegative
        CHECK (
            delivery_days IS NULL
            OR delivery_days >= 0
        ),

    CONSTRAINT orders_late_days_nonnegative
        CHECK (
            late_delivery_days IS NULL
            OR late_delivery_days >= 0
        ),

    CONSTRAINT orders_handling_metrics_consistency
        CHECK (
            (
                is_handling_time_eligible
                AND approval_to_carrier_days IS NOT NULL
                AND approval_to_carrier_days >= 0
            )
            OR
            (
                NOT is_handling_time_eligible
                AND approval_to_carrier_days IS NULL
            )
        )
);


CREATE TABLE opspilot.order_items (
    order_id VARCHAR(32) NOT NULL,
    order_item_id SMALLINT NOT NULL,
    product_id VARCHAR(32) NOT NULL,
    seller_id VARCHAR(32) NOT NULL,
    shipping_limit_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    freight_value NUMERIC(12, 2) NOT NULL,
    item_total NUMERIC(12, 2) NOT NULL,

    CONSTRAINT order_items_primary_key
        PRIMARY KEY (
            order_id,
            order_item_id
        ),

    CONSTRAINT order_items_order_foreign_key
        FOREIGN KEY (order_id)
        REFERENCES opspilot.orders (
            order_id
        ),

    CONSTRAINT order_items_product_foreign_key
        FOREIGN KEY (product_id)
        REFERENCES opspilot.products (
            product_id
        ),

    CONSTRAINT order_items_seller_foreign_key
        FOREIGN KEY (seller_id)
        REFERENCES opspilot.sellers (
            seller_id
        ),

    CONSTRAINT order_items_order_id_length
        CHECK (char_length(order_id) = 32),

    CONSTRAINT order_items_product_id_length
        CHECK (char_length(product_id) = 32),

    CONSTRAINT order_items_seller_id_length
        CHECK (char_length(seller_id) = 32),

    CONSTRAINT order_items_sequence_positive
        CHECK (order_item_id >= 1),

    CONSTRAINT order_items_price_positive
        CHECK (price > 0),

    CONSTRAINT order_items_freight_nonnegative
        CHECK (freight_value >= 0),

    CONSTRAINT order_items_total_consistency
        CHECK (
            item_total = price + freight_value
        )
);


CREATE TABLE opspilot.payments (
    order_id VARCHAR(32) NOT NULL,
    payment_sequential SMALLINT NOT NULL,
    payment_type VARCHAR(20) NOT NULL,
    payment_installments SMALLINT NOT NULL,
    payment_value NUMERIC(12, 2) NOT NULL,

    is_invalid_installment BOOLEAN NOT NULL,
    is_zero_value_payment BOOLEAN NOT NULL,
    payment_sequence_start_missing BOOLEAN NOT NULL,
    payment_sequence_internal_gap BOOLEAN NOT NULL,

    CONSTRAINT payments_primary_key
        PRIMARY KEY (
            order_id,
            payment_sequential
        ),

    CONSTRAINT payments_order_foreign_key
        FOREIGN KEY (order_id)
        REFERENCES opspilot.orders (
            order_id
        ),

    CONSTRAINT payments_order_id_length
        CHECK (char_length(order_id) = 32),

    CONSTRAINT payments_sequence_positive
        CHECK (payment_sequential >= 1),

    CONSTRAINT payments_type_values
        CHECK (
            payment_type IN (
                'credit_card',
                'boleto',
                'voucher',
                'debit_card',
                'not_defined'
            )
        ),

    CONSTRAINT payments_installments_nonnegative
        CHECK (payment_installments >= 0),

    CONSTRAINT payments_value_nonnegative
        CHECK (payment_value >= 0),

    CONSTRAINT payments_invalid_installment_consistency
        CHECK (
            is_invalid_installment = (
                payment_installments <= 0
            )
        ),

    CONSTRAINT payments_zero_value_consistency
        CHECK (
            is_zero_value_payment = (
                payment_value = 0
            )
        )
);


CREATE TABLE opspilot.reviews (
    review_id VARCHAR(32) NOT NULL,
    order_id VARCHAR(32) NOT NULL,
    review_score SMALLINT NOT NULL,
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    review_answer_timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,

    CONSTRAINT reviews_primary_key
        PRIMARY KEY (
            review_id,
            order_id
        ),

    CONSTRAINT reviews_order_foreign_key
        FOREIGN KEY (order_id)
        REFERENCES opspilot.orders (
            order_id
        ),

    CONSTRAINT reviews_review_id_length
        CHECK (char_length(review_id) = 32),

    CONSTRAINT reviews_order_id_length
        CHECK (char_length(order_id) = 32),

    CONSTRAINT reviews_score_range
        CHECK (
            review_score BETWEEN 1 AND 5
        )
);


CREATE INDEX idx_customers_unique_id
    ON opspilot.customers (
        customer_unique_id
    );


CREATE INDEX idx_orders_customer
    ON opspilot.orders (
        customer_id
    );


CREATE INDEX idx_orders_purchase_timestamp
    ON opspilot.orders (
        order_purchase_timestamp
    );


CREATE INDEX idx_orders_delivery_period
    ON opspilot.orders (
        order_purchase_timestamp
    )
    WHERE is_delivery_kpi_eligible;


CREATE INDEX idx_order_items_product
    ON opspilot.order_items (
        product_id
    );


CREATE INDEX idx_order_items_seller
    ON opspilot.order_items (
        seller_id
    );


CREATE INDEX idx_products_category_english
    ON opspilot.products (
        product_category_name_english
    );


CREATE INDEX idx_reviews_order
    ON opspilot.reviews (
        order_id
    );


COMMIT;