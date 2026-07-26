"""Schema constants and column maps."""

from __future__ import annotations

# Long-form master: one row = one sellable configuration
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pricebook (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor TEXT,
    collection TEXT,
    part_number TEXT,
    description TEXT,
    dimensions TEXT,
    option_key TEXT,
    species TEXT,
    species_tier INTEGER,
    finish_state TEXT,
    base_price REAL,
    price_basis TEXT DEFAULT 'wholesale',
    multiplier REAL DEFAULT 2.7,
    adjusted_price REAL,
    unit TEXT,
    notes TEXT,
    source_file TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS vendors (
    name TEXT PRIMARY KEY,
    multiplier REAL DEFAULT 2.7,
    notes TEXT,
    phone TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pricebook_search
    ON pricebook (vendor, collection, part_number, description, species);

CREATE INDEX IF NOT EXISTS idx_pricebook_part
    ON pricebook (part_number);

CREATE INDEX IF NOT EXISTS idx_pricebook_vendor
    ON pricebook (vendor);

CREATE INDEX IF NOT EXISTS idx_pricebook_identity
    ON pricebook (vendor, part_number, species, finish_state, collection);

CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_number TEXT,
    customer_name TEXT,
    customer_phone TEXT,
    customer_email TEXT,
    status TEXT DEFAULT 'draft',
    notes TEXT,
    discount_pct REAL DEFAULT 0,
    tax_pct REAL DEFAULT 0,
    ordertrac_guid TEXT,
    ordertrac_so_id TEXT,
    ordertrac_url TEXT,
    ordertrac_pushed_at TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS quote_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id INTEGER NOT NULL,
    line_no INTEGER DEFAULT 1,
    pricebook_id INTEGER,
    vendor TEXT,
    collection TEXT,
    part_number TEXT,
    description TEXT,
    species TEXT,
    dimensions TEXT,
    finish_state TEXT,
    qty REAL DEFAULT 1,
    unit_base REAL,
    unit_retail REAL,
    line_discount_pct REAL DEFAULT 0,
    line_total REAL,
    notes TEXT,
    FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_quote_lines_quote
    ON quote_lines (quote_id);

-- Multi-user accounts (synced from OrderTrac and/or created locally)
CREATE TABLE IF NOT EXISTS app_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'sales',
    active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    ordertrac_user_guid TEXT,
    ordertrac_display_name TEXT,
    source TEXT DEFAULT 'local',
    last_login_at TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_app_users_username
    ON app_users (username);

CREATE INDEX IF NOT EXISTS idx_app_users_ot_guid
    ON app_users (ordertrac_user_guid);

-- OrderTrac connection status / last sync metadata (credentials stay in secrets)
CREATE TABLE IF NOT EXISTS integrations (
    key TEXT PRIMARY KEY,
    status TEXT,
    last_ok_at TEXT,
    last_error TEXT,
    meta_json TEXT,
    updated_at TEXT
);
"""

# Columns added after early v1 — migrate existing DBs (pricebook table)
NEW_COLUMNS = {
    "vendor": "TEXT",
    "dimensions": "TEXT",
    "option_key": "TEXT",
    "species_tier": "INTEGER",
    "finish_state": "TEXT",
    "price_basis": "TEXT",
}

# Columns added after early v1 — migrate existing DBs (vendors table)
VENDOR_NEW_COLUMNS = {
    "phone": "TEXT",
}

# Columns added for OrderTrac quote push link-back
QUOTE_NEW_COLUMNS = {
    "ordertrac_guid": "TEXT",
    "ordertrac_so_id": "TEXT",
    "ordertrac_url": "TEXT",
    "ordertrac_pushed_at": "TEXT",
}

PRICEBOOK_COLS = [
    "vendor",
    "collection",
    "part_number",
    "description",
    "dimensions",
    "option_key",
    "species",
    "species_tier",
    "finish_state",
    "base_price",
    "price_basis",
    "multiplier",
    "adjusted_price",
    "unit",
    "notes",
    "source_file",
    "imported_at",
]

SELECT_COLS = ["id"] + PRICEBOOK_COLS

# Common column name aliases from Amish / wholesale price lists
COLUMN_ALIASES = {
    "part_number": [
        "part_number", "part number", "part #", "part#", "part no", "part no.",
        "sku", "item", "item #", "item number", "item no", "item no.",
        "style", "style #", "style number", "model", "model #", "code",
        "catalog #", "catalog number", "stock #", "item name",
    ],
    "description": [
        "description", "desc", "item description", "product", "product name",
        "name", "title", "product description", "descr.",
    ],
    "species": [
        "species", "wood", "wood species", "finish wood", "material",
        "wood type", "species/finish",
    ],
    "base_price": [
        "base_price", "base price", "price", "wholesale", "wholesale price",
        "net price", "net", "dealer price", "dealer", "cost", "unit price",
        "list price", "your price", "amount", "retail", "msrp",
        "wholesale $", "price $", "net $", "whsl. price", "regular",
    ],
    "unit": [
        "unit", "uom", "um", "each", "units",
    ],
    "collection": [
        "collection", "series", "line", "product line", "category",
        "group", "family", "brand", "manufacturer",
    ],
    "notes": [
        "notes", "note", "comments", "comment", "remarks", "options",
    ],
    "dimensions": [
        "dimensions", "dimension", "dims", "size", "w x d x h", "overall size",
    ],
    "vendor": [
        "vendor", "builder", "supplier", "manufacturer name",
    ],
}
