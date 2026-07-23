CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS foods (
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

CREATE TABLE IF NOT EXISTS diet_versions (
    id SERIAL PRIMARY KEY,
    source_pdf_filename TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS diet_meals (
    id SERIAL PRIMARY KEY,
    diet_version_id INTEGER NOT NULL REFERENCES diet_versions(id) ON DELETE CASCADE,
    day_label TEXT NOT NULL,
    meal_name TEXT NOT NULL,
    food_item TEXT NOT NULL,
    quantity_grams NUMERIC NOT NULL,
    matched_food_id INTEGER REFERENCES foods(id)
);

CREATE TABLE IF NOT EXISTS body_metrics (
    id SERIAL PRIMARY KEY,
    source_pdf_filename TEXT NOT NULL,
    measured_on DATE NOT NULL,
    weight_kg NUMERIC,
    body_fat_pct NUMERIC,
    muscle_mass_kg NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    age INTEGER NOT NULL,
    sex TEXT NOT NULL CHECK (sex IN ('M', 'F')),
    height_cm NUMERIC NOT NULL,
    activity_level TEXT NOT NULL
        CHECK (activity_level IN ('sedentario', 'ligero', 'moderado', 'intenso')),
    current_goal TEXT NOT NULL
        CHECK (current_goal IN ('deficit', 'maintenance', 'surplus')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS macro_targets (
    id SERIAL PRIMARY KEY,
    method TEXT NOT NULL CHECK (method IN ('formula', 'agent')),
    goal TEXT NOT NULL CHECK (goal IN ('deficit', 'maintenance', 'surplus')),
    kcal NUMERIC NOT NULL,
    protein_g NUMERIC NOT NULL,
    carbs_g NUMERIC NOT NULL,
    fat_g NUMERIC NOT NULL,
    explanation TEXT,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
