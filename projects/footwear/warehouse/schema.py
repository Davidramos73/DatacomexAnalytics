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

-- Componentes de calzado (Bloque A): materias primas/insumos que compran o
-- venden los fabricantes (cauchos, plásticos, textiles, pieles, hormas,
-- hebillas...). Mismo origen (DataComex, España) que trade_flows, pero
-- partidas de otros capítulos arancelarios (no 64), así que va en su propia
-- tabla en vez de mezclarse con calzado terminado.
CREATE TABLE IF NOT EXISTS datacomex.component_flows (
    flow           VARCHAR NOT NULL,   -- 'IMPORT' | 'EXPORT'
    period         VARCHAR NOT NULL,   -- 'YYYY-MM'
    year           INTEGER NOT NULL,
    month          INTEGER NOT NULL,
    country_code   VARCHAR NOT NULL,   -- ISO a3
    country_name   VARCHAR NOT NULL,
    partida        VARCHAR NOT NULL,   -- TARIC 8 dígitos, p. ej. '40011000'
    value_eur      BIGINT  NOT NULL,
    weight_kg      BIGINT  NOT NULL,
    is_provisional BOOLEAN NOT NULL DEFAULT false
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

# short label for legends / pie slices
SHORT_LABEL = {
    "6401": "6401 · impermeable",
    "6402": "6402 · caucho/plástico",
    "6403": "6403 · cuero",
    "6404": "6404 · textil",
    "6405": "6405 · otros",
    "6406": "6406 · partes",
}

# Bloque A — componentes de calzado. Las 70 partidas TARIC (8 dígitos) que
# el cliente identificó como industria auxiliar de Alicante (comercio de
# España, mismo origen DataComex que HEADINGS arriba). Fuente: archivo
# "Análisis DP Alicante por partidas Componentes Calzado" del cliente.
COMPONENT_PARTIDAS = {
    "32050000": "Lacas, colorantes, preparaciones",
    "34039100": "Preparación materias textiles, cueros, otras materias",
    "34051000": "Betunes preparados para calzado",
    "35069110": "Adhesivos transparentes en películas sin soporte",
    "35069190": "Adhesivos a base de polímeros",
    "35069900": "Colas y demás adhesivos",
    "38099300": "Aprestos y productos de acabado",
    "39169010": "Monofilamentos",
    "39209100": "Las demás placas, láminas, hojas",
    "39211900": "Las demás placas, hojas, películas, banda y láminas",
    "39219055": "Las demás placas, hojas, películas, etc.",
    "39219090": "Las demás placas, hojas, películas, etc.",
    "40011000": "Látex de caucho natural, incluso prevulcanizado",
    "40012900": "Caucho natural en otras formas",
    "40021100": "Látex de caucho estireno-butadieno",
    "40023900": "Caucho isobuteno-isopreno",
    "40029910": "Caucho sintético y caucho facticio derivado de aceites",
    "40051000": "Caucho con negro de humo o sílice, sin vulcanizar",
    "40052000": "Disoluciones y dispersiones de caucho",
    "40081100": "Placas, hojas y bandas de caucho celular",
    "40082110": "Placas, hojas y bandas de caucho no celular",
    "40082190": "Placas, hojas y bandas de caucho no celular",
    "40161000": "Las demás manufacturas de caucho celular",
    "41041190": "Cueros y pieles enteros de equino",
    "41062290": "Cueros y pieles depilados de caprino",
    "41063200": "Cueros y pieles depilados de porcino",
    "41071119": "Cueros y pieles enteros",
    "41071211": "Cueros y pieles enteros, preparados en 'box-calf'",
    "41071219": "Cueros y pieles enteros, preparados después del curtido",
    "41079110": "Los demás cueros, incluidas las hojas",
    "41079910": "Los demás cueros, incluidas las hojas",
    "41120000": "Cueros preparados después del curtido",
    "41131000": "Cueros preparados después del curtido o del secado",
    "41132000": "Cueros preparados después del curtido o del secado",
    "41139000": "Cueros preparados después del curtido y del secado",
    "41142000": "Cuero y pieles barnizados",
    "43021980": "Pieles de ovino, curtidas",
    "43022000": "Cabezas, colas, patas",
    "45039000": "Manufacturas de corcho natural",
    "54075100": "Tejidos con un contenido de filamentos de poliéster",
    "55064000": "Fibras sintéticas discontinuas",
    "55069000": "Fibras sintéticas discontinuas",
    "56021019": "Fieltro punzonado de otras materias textiles",
    "56021031": "Productos obtenidos mediante costura por cadeneta",
    "56021038": "Productos obtenidos mediante costura por cadeneta",
    "56031190": "Telas sin tejer de filamento sintético",
    "56031410": "Telas sin tejer de filamento sintético",
    "56039310": "Telas sin tejer recubiertas",
    "58012200": "Terciopelo y felpa",
    "58062000": "Cintas que no sean de terciopelo, felpa",
    "58063900": "Cintas de otras materias que no sean algodón o fibras sintéticas",
    "58110000": "Productos textiles en pieza",
    "59032090": "Tejidos recubiertos, revestidos o estratificados con poliuretano",
    "59039099": "Tejidos recubiertos, revestidos o estratificados con plástico",
    "60019200": "Tejidos de terciopelo o de felpa",
    "60053500": "Tejidos de punto de urdimbre",
    "64061010": "Partes superiores del calzado y sus partes",
    "64061090": "Partes superiores del calzado y sus partes",
    "64062010": "Pisos y tacones de caucho",
    "64062090": "Pisos y tacones de plástico",
    "64069030": "Conjunto formado por la parte superior del calzado fijo",
    "64069050": "Plantillas y demás accesorios amovibles",
    "64069060": "Suelas de cuero natural regenerado",
    "64069090": "Partes de calzado, incluidas las partes superiores fijas a las palmillas",
    "83089000": "Cierres, monturas-cierres, hebillas",
    "84531000": "Máquinas y aparatos para la preparación, curtido o trabajo de cueros",
    "84532000": "Máquinas y aparatos para la fabricación o reparación del calzado",
    "84538000": "Máquinas y aparatos para la fabricación o reparación de otras manufacturas de cuero",
    "84539000": "Partes de máquinas y aparatos para la preparación, curtido o trabajo de cueros",
    "84807100": "Moldes para caucho o plástico",
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
