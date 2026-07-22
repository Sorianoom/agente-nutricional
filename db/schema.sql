CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE foods (
    id SERIAL PRIMARY KEY,
    mercadona_product_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT,
    kcal_100g NUMERIC,
    protein_100g NUMERIC,
    carbs_100g NUMERIC,
    fat_100g NUMERIC,
    fiber_100g NUMERIC,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE diet_versions (
    id SERIAL PRIMARY KEY,
    source_pdf_filename TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE diet_meals (
    id SERIAL PRIMARY KEY,
    diet_version_id INTEGER NOT NULL REFERENCES diet_versions(id) ON DELETE CASCADE,
    day_label TEXT NOT NULL,
    meal_name TEXT NOT NULL,
    food_item TEXT NOT NULL,
    quantity_grams NUMERIC NOT NULL,
    matched_food_id INTEGER REFERENCES foods(id)
);

CREATE TABLE body_metrics (
    id SERIAL PRIMARY KEY,
    source_pdf_filename TEXT NOT NULL,
    measured_on DATE NOT NULL,
    weight_kg NUMERIC,
    body_fat_pct NUMERIC,
    muscle_mass_kg NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
