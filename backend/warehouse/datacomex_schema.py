"""DataComex (footwear / TARIC chapter 64) warehouse schema.

Shared by the synthetic seed and by test fixtures so both build the exact
same tables. The real ingest pipeline (offline) will populate these.
"""

SCHEMA_DDL = """
CREATE SCHEMA IF NOT EXISTS datacomex;

CREATE TABLE IF NOT EXISTS datacomex.trade_flows (
    flow           VARCHAR NOT NULL,   -- 'IMPORT' | 'EXPORT'
    period         VARCHAR NOT NULL,   -- 'YYYY-MM'
    year           INTEGER NOT NULL,
    month          INTEGER NOT NULL,
    country_code   VARCHAR NOT NULL,   -- ISO a3
    country_name   VARCHAR NOT NULL,
    taric_code     VARCHAR NOT NULL,   -- level 6, e.g. '640411'
    chapter        VARCHAR NOT NULL,   -- '64'
    heading        VARCHAR NOT NULL,   -- '6404'
    value_eur      BIGINT  NOT NULL,
    weight_kg      BIGINT  NOT NULL,
    suppl_units    BIGINT,             -- pairs; NULL when the heading has none
    is_provisional BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS datacomex.taric_tree (
    code        VARCHAR PRIMARY KEY,   -- '64', '6404', '640411'
    parent_code VARCHAR,
    level       INTEGER NOT NULL,      -- 2 | 4 | 6
    description VARCHAR NOT NULL       -- Spanish
);

CREATE TABLE IF NOT EXISTS datacomex.meta_ingestion (
    id          INTEGER PRIMARY KEY,
    loaded_at   TIMESTAMP NOT NULL,
    period_max  VARCHAR NOT NULL,
    rows_loaded INTEGER NOT NULL,
    source      VARCHAR NOT NULL       -- 'api' | 'csv_masiva' | 'synthetic'
);
"""

CHAPTER = "64"

# heading -> (Spanish description, has supplementary units [pairs])
HEADINGS = {
    "6401": ("Calzado impermeable con suela y parte superior de caucho o plástico", True),
    "6402": ("Los demás calzados con suela y parte superior de caucho o plástico", True),
    "6403": ("Calzado con suela de caucho, plástico o cuero y parte superior de cuero", True),
    "6404": ("Calzado con suela de caucho o plástico y parte superior de materia textil", True),
    "6405": ("Los demás calzados", True),
    "6406": ("Partes de calzado; plantillas, taloneras; polainas y artículos análogos", False),
}

# level-6 TARIC codes per heading (a representative subset)
SUBHEADINGS = {
    "6401": ["640110", "640192", "640199"],
    "6402": ["640212", "640219", "640220", "640291", "640299"],
    "6403": ["640312", "640319", "640320", "640340", "640351", "640359", "640391", "640399"],
    "6404": ["640411", "640419", "640420"],
    "6405": ["640510", "640520", "640590"],
    "6406": ["640610", "640620", "640690"],
}
