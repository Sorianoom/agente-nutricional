# Subsistema 2: Calculadora de macros objetivo — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar este plan tarea por tarea. Los pasos usan sintaxis de checkbox (`- [ ]`) para seguimiento.

**Goal:** A partir del histórico ya cargado (dietas, análisis corporales), dar al usuario dos formas de saber qué macros objetivo debería seguir: un cálculo determinista (TDEE real medido a partir de su propio histórico) y una recomendación con IA (Claude Agent SDK, bajo demanda). Incluye también un perfil de usuario básico y una pantalla para registrar a mano nuevas medidas del gimnasio (ya no hay más PDFs de nutricionista).

**Architecture:** Mismo stack que el Subsistema 1 — FastAPI + Jinja2/HTMX, Postgres vía `psycopg` directo (sin ORM), Docker Compose. El cálculo determinista es Python puro, sin llamadas externas, se recalcula en cada visita. El cálculo con IA usa el Claude Agent SDK con el mismo patrón ya validado en `scripts/ingest_diet_pdfs.py` (`setting_sources=[]`, `cwd` propio, `output_format` JSON schema) pero invocado desde una ruta FastAPI (síncrona) envolviendo `query()` con `anyio.run()`, y solo cuando el usuario pulsa "Recalcular con IA" — nunca automáticamente.

**Tech Stack:** Python 3.13, FastAPI, psycopg 3, PostgreSQL 16, Jinja2, HTMX (CDN), claude-agent-sdk, anyio, pytest.

## Global Constraints

- Sin ORM. Sin build de Node.
- El cálculo con IA nunca se dispara automáticamente al cargar una página — solo por acción explícita del usuario (botón), para no gastar cuota de la suscripción sin necesidad.
- `db/schema.sql` pasa a ser completamente idempotente (`CREATE TABLE IF NOT EXISTS` en todas las tablas, no solo las nuevas) para poder aplicarse repetidamente tanto en tests como, manualmente, sobre la base de datos real ya poblada (nunca se usa `docker compose down -v` para aplicar cambios de esquema — eso destruiría el histórico real).
- Perfil de usuario: fila única (`id = 1` fijo, `CHECK (id = 1)`), guardada vía upsert.
- Todo el código vive en `D:\homeMario\AgenteNutricional`.

---

### Task 1: Esquema de datos — `user_profile` y `macro_targets`

**Files:**
- Modify: `db/schema.sql` (todas las tablas a `CREATE TABLE IF NOT EXISTS`; añadir `user_profile` y `macro_targets`)
- Modify: `tests/conftest.py` (aplicar siempre el esquema completo, ya no hace falta saltárselo)
- Modify: `tests/test_db_schema.py`

**Interfaces:**
- Produces: tablas Postgres `user_profile` (fila única, `id=1`) y `macro_targets` (histórico append-only).

- [ ] **Step 1: Escribe el test que falla**

`tests/test_db_schema.py`:
```python
from app.db import get_connection


def test_expected_tables_exist():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            tables = {row[0] for row in cur.fetchall()}
    assert {
        "foods",
        "diet_versions",
        "diet_meals",
        "body_metrics",
        "user_profile",
        "macro_targets",
    } <= tables
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_db_schema.py -v`
Expected: FAIL (`user_profile`/`macro_targets` no están en `tables`).

- [ ] **Step 3: Reescribe `db/schema.sql` completo, idempotente**

```sql
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
```

- [ ] **Step 4: Simplifica `tests/conftest.py` para aplicar siempre el esquema completo**

Reemplaza `_apply_schema_if_missing` (ya no hace falta comprobar si `foods` existe, porque el `.sql` completo es idempotente):

```python
def _apply_schema() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text())
```

Y al final del archivo:
```python
_create_test_database_if_missing()
_apply_schema()
```

- [ ] **Step 5: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_db_schema.py -v`
Expected: PASS

- [ ] **Step 6: Aplica las tablas nuevas a la base de datos real, sin destruir datos**

**No uses `docker compose down -v`** — el volumen de Postgres tiene el histórico real cargado. En su lugar, aplica el `.sql` completo directamente (es idempotente, las tablas existentes no se tocan):

```bash
docker compose exec -T postgres psql -U nutricion -d nutricion < db/schema.sql
```

Expected: sin errores; `CREATE TABLE` de `foods`/`diet_versions`/`diet_meals`/`body_metrics` se ignora silenciosamente (ya existen), `user_profile` y `macro_targets` se crean.

Verifica:
```bash
docker compose exec postgres psql -U nutricion -d nutricion -c "\dt"
```
Expected: aparecen `user_profile` y `macro_targets` en el listado.

- [ ] **Step 7: Commit**

```bash
git add db/schema.sql tests/conftest.py tests/test_db_schema.py
git commit -m "Add user_profile and macro_targets tables, make schema.sql idempotent"
```

---

### Task 2: Perfil de usuario

**Files:**
- Modify: `app/main.py` (rutas `GET`/`POST /perfil`, `get_user_profile()`, `save_user_profile()`)
- Create: `app/templates/perfil.html`
- Test: `tests/test_perfil.py`

**Interfaces:**
- Produces: `GET /perfil` (formulario, precargado si ya existe perfil), `POST /perfil` (guarda y redirige a `/perfil`).

- [ ] **Step 1: Escribe el test que falla**

`tests/test_perfil.py`:
```python
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _clear_profile():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_profile WHERE id = 1")


def test_get_perfil_empty_shows_form():
    _clear_profile()
    response = client.get("/perfil")
    assert response.status_code == 200
    assert "form" in response.text.lower()


def test_post_perfil_saves_and_get_reflects_it():
    _clear_profile()
    response = client.post(
        "/perfil",
        data={
            "age": "23",
            "sex": "M",
            "height_cm": "178",
            "activity_level": "moderado",
            "current_goal": "maintenance",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT age, sex, activity_level, current_goal FROM user_profile WHERE id = 1"
            )
            row = cur.fetchone()
    assert row == (23, "M", "moderado", "maintenance")
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_perfil.py -v`
Expected: FAIL con `404 Not Found` (la ruta no existe).

- [ ] **Step 3: Añade a `app/main.py`**

```python
from fastapi import Form
from fastapi.responses import RedirectResponse

ACTIVITY_LEVELS = ["sedentario", "ligero", "moderado", "intenso"]
GOALS = ["deficit", "maintenance", "surplus"]


def get_user_profile() -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT age, sex, height_cm, activity_level, current_goal "
                "FROM user_profile WHERE id = 1"
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "age": row[0],
        "sex": row[1],
        "height_cm": float(row[2]),
        "activity_level": row[3],
        "current_goal": row[4],
    }


def save_user_profile(
    age: int, sex: str, height_cm: float, activity_level: str, current_goal: str
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_profile (id, age, sex, height_cm, activity_level, current_goal, updated_at)
                VALUES (1, %s, %s, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                    age = EXCLUDED.age,
                    sex = EXCLUDED.sex,
                    height_cm = EXCLUDED.height_cm,
                    activity_level = EXCLUDED.activity_level,
                    current_goal = EXCLUDED.current_goal,
                    updated_at = now()
                """,
                (age, sex, height_cm, activity_level, current_goal),
            )


@app.get("/perfil")
def perfil_form(request: Request):
    template = templates.get_template("perfil.html")
    return HTMLResponse(
        template.render(
            {
                "request": request,
                "profile": get_user_profile(),
                "activity_levels": ACTIVITY_LEVELS,
                "goals": GOALS,
            }
        )
    )


@app.post("/perfil")
def perfil_save(
    age: int = Form(...),
    sex: str = Form(...),
    height_cm: float = Form(...),
    activity_level: str = Form(...),
    current_goal: str = Form(...),
):
    save_user_profile(age, sex, height_cm, activity_level, current_goal)
    return RedirectResponse("/perfil", status_code=303)
```

- [ ] **Step 4: Crea `app/templates/perfil.html`**

```html
{% extends "base.html" %}
{% block title %}Perfil{% endblock %}
{% block content %}
<h1>Perfil</h1>
<form method="post" action="/perfil">
  <label>Edad
    <input type="number" name="age" value="{{ profile.age if profile else '' }}" required>
  </label>
  <label>Sexo
    <select name="sex" required>
      <option value="M" {% if profile and profile.sex == "M" %}selected{% endif %}>M</option>
      <option value="F" {% if profile and profile.sex == "F" %}selected{% endif %}>F</option>
    </select>
  </label>
  <label>Altura (cm)
    <input type="number" step="0.1" name="height_cm" value="{{ profile.height_cm if profile else '' }}" required>
  </label>
  <label>Nivel de actividad
    <select name="activity_level" required>
      {% for level in activity_levels %}
      <option value="{{ level }}" {% if profile and profile.activity_level == level %}selected{% endif %}>{{ level }}</option>
      {% endfor %}
    </select>
  </label>
  <label>Objetivo actual
    <select name="current_goal" required>
      {% for goal in goals %}
      <option value="{{ goal }}" {% if profile and profile.current_goal == goal %}selected{% endif %}>{{ goal }}</option>
      {% endfor %}
    </select>
  </label>
  <button type="submit">Guardar</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_perfil.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/templates/perfil.html tests/test_perfil.py
git commit -m "Add user profile form"
```

---

### Task 3: Registro manual de medidas corporales

**Files:**
- Modify: `app/main.py` (rutas `GET`/`POST /medidas`, `save_manual_body_metric()`)
- Create: `app/templates/medidas.html`
- Test: `tests/test_medidas.py`

**Interfaces:**
- Produces: `GET /medidas` (formulario + tabla de medidas existentes), `POST /medidas` (inserta fila en `body_metrics` con `source_pdf_filename = 'manual'`, redirige a `/medidas`).

- [ ] **Step 1: Escribe el test que falla**

`tests/test_medidas.py`:
```python
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def test_post_medidas_inserts_manual_row():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM body_metrics WHERE measured_on = '2026-07-20' "
                "AND source_pdf_filename = 'manual'"
            )

    response = client.post(
        "/medidas",
        data={
            "measured_on": "2026-07-20",
            "weight_kg": "78.5",
            "body_fat_pct": "15.2",
            "muscle_mass_kg": "36.0",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT weight_kg, body_fat_pct, muscle_mass_kg, source_pdf_filename "
                "FROM body_metrics WHERE measured_on = '2026-07-20' AND source_pdf_filename = 'manual'"
            )
            row = cur.fetchone()
    assert row is not None
    assert float(row[0]) == 78.5
    assert float(row[1]) == 15.2
    assert float(row[2]) == 36.0
    assert row[3] == "manual"


def test_get_medidas_shows_form():
    response = client.get("/medidas")
    assert response.status_code == 200
    assert "form" in response.text.lower()
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_medidas.py -v`
Expected: FAIL con `404 Not Found`.

- [ ] **Step 3: Añade a `app/main.py`**

```python
def save_manual_body_metric(
    measured_on: str, weight_kg: float, body_fat_pct: float, muscle_mass_kg: float
) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO body_metrics
                    (source_pdf_filename, measured_on, weight_kg, body_fat_pct, muscle_mass_kg)
                VALUES ('manual', %s, %s, %s, %s)
                RETURNING id
                """,
                (measured_on, weight_kg, body_fat_pct, muscle_mass_kg),
            )
            return cur.fetchone()[0]


@app.get("/medidas")
def medidas_form(request: Request):
    template = templates.get_template("medidas.html")
    return HTMLResponse(
        template.render({"request": request, "medidas": get_body_metrics_series()})
    )


@app.post("/medidas")
def medidas_save(
    measured_on: str = Form(...),
    weight_kg: float = Form(...),
    body_fat_pct: float = Form(...),
    muscle_mass_kg: float = Form(...),
):
    save_manual_body_metric(measured_on, weight_kg, body_fat_pct, muscle_mass_kg)
    return RedirectResponse("/medidas", status_code=303)
```

(`get_body_metrics_series()` ya existe en `app/main.py` desde el Subsistema 1.)

- [ ] **Step 4: Crea `app/templates/medidas.html`**

```html
{% extends "base.html" %}
{% block title %}Medidas{% endblock %}
{% block content %}
<h1>Registrar medida del gimnasio</h1>
<form method="post" action="/medidas">
  <label>Fecha
    <input type="date" name="measured_on" required>
  </label>
  <label>Peso (kg)
    <input type="number" step="0.1" name="weight_kg" required>
  </label>
  <label>% grasa corporal
    <input type="number" step="0.1" name="body_fat_pct" required>
  </label>
  <label>Masa musculoesquelética (kg)
    <input type="number" step="0.1" name="muscle_mass_kg" required>
  </label>
  <button type="submit">Guardar</button>
</form>

<h2>Historico</h2>
<table>
  <thead>
    <tr><th>Fecha</th><th>Peso (kg)</th><th>% grasa</th></tr>
  </thead>
  <tbody>
    {% for m in medidas %}
    <tr><td>{{ m.date }}</td><td>{{ m.weight_kg }}</td><td>{{ m.body_fat_pct }}</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 5: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_medidas.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/templates/medidas.html tests/test_medidas.py
git commit -m "Add manual body metrics entry form"
```

---

### Task 4: Cálculo determinista de macros objetivo (funciones puras)

**Files:**
- Create: `app/macros.py`
- Test: `tests/test_macros.py`

**Interfaces:**
- Produces: `app.macros.compute_real_tdee(body_metrics, diet_daily_kcal) -> float | None`, `app.macros.mifflin_st_jeor(age, sex, height_cm, weight_kg, activity_level) -> float`, `app.macros.split_macros(tdee, goal, weight_kg) -> dict`.

Sin dependencias de base de datos — solo lógica, con datos sintéticos en los tests.

- [ ] **Step 1: Escribe el test que falla**

`tests/test_macros.py`:
```python
from datetime import date

from app.macros import compute_real_tdee, mifflin_st_jeor, split_macros


def test_compute_real_tdee_with_single_segment():
    # Peso constante (80kg), pero el % de grasa baja de 20% a 18.75%:
    # masa grasa 16kg -> 15kg, exactamente 1kg perdido en 10 dias comiendo
    # 2000 kcal/dia de media.
    # 1kg * 9300 kcal/kg = 9300 kcal de deficit acumulado -> 930 kcal/dia.
    # TDEE = 2000 (comido) + 930 (deficit cubierto por la grasa perdida) = 2930.
    body_metrics = [
        {"measured_on": date(2026, 1, 1), "weight_kg": 80.0, "body_fat_pct": 20.0},
        {"measured_on": date(2026, 1, 11), "weight_kg": 80.0, "body_fat_pct": 18.75},
    ]
    diet_daily_kcal = [
        {"valid_from": date(2026, 1, 1), "valid_to": None, "daily_kcal": 2000.0},
    ]
    tdee = compute_real_tdee(body_metrics, diet_daily_kcal)
    assert tdee == pytest.approx(2930.0, abs=1.0)


def test_compute_real_tdee_averages_multiple_segments():
    body_metrics = [
        {"measured_on": date(2026, 1, 1), "weight_kg": 80.0, "body_fat_pct": 20.0},
        {"measured_on": date(2026, 1, 11), "weight_kg": 80.0, "body_fat_pct": 18.75},
        {"measured_on": date(2026, 1, 21), "weight_kg": 80.0, "body_fat_pct": 18.75},
    ]
    diet_daily_kcal = [
        {"valid_from": date(2026, 1, 1), "valid_to": None, "daily_kcal": 2000.0},
        {"valid_from": date(2026, 1, 12), "valid_to": None, "daily_kcal": 2930.0},
    ]
    tdee = compute_real_tdee(body_metrics, diet_daily_kcal)
    # Primer tramo: ~2930 (deficit). Segundo tramo: 2930 (mantenimiento, sin cambio de grasa).
    assert tdee == pytest.approx(2930.0, abs=1.0)


def test_compute_real_tdee_returns_none_with_fewer_than_two_measurements():
    assert compute_real_tdee([{"measured_on": date(2026, 1, 1), "weight_kg": 80.0, "body_fat_pct": 20.0}], []) is None


def test_compute_real_tdee_skips_segments_without_diet_data():
    body_metrics = [
        {"measured_on": date(2026, 1, 1), "weight_kg": 80.0, "body_fat_pct": 20.0},
        {"measured_on": date(2026, 1, 11), "weight_kg": 79.0, "body_fat_pct": 18.86},
    ]
    assert compute_real_tdee(body_metrics, []) is None


def test_mifflin_st_jeor_male():
    tdee = mifflin_st_jeor(age=23, sex="M", height_cm=178, weight_kg=75, activity_level="moderado")
    bmr = 10 * 75 + 6.25 * 178 - 5 * 23 + 5
    assert tdee == pytest.approx(bmr * 1.55)


def test_mifflin_st_jeor_female():
    tdee = mifflin_st_jeor(age=30, sex="F", height_cm=165, weight_kg=60, activity_level="sedentario")
    bmr = 10 * 60 + 6.25 * 165 - 5 * 30 - 161
    assert tdee == pytest.approx(bmr * 1.2)


def test_split_macros_deficit():
    result = split_macros(tdee=2500, goal="deficit", weight_kg=80)
    assert result["kcal"] == pytest.approx(2000, abs=1)
    assert result["protein_g"] == pytest.approx(176, abs=1)  # 2.2 g/kg
    assert result["fat_g"] == pytest.approx(2000 * 0.25 / 9, abs=1)
    assert result["kcal"] == pytest.approx(
        result["protein_g"] * 4 + result["carbs_g"] * 4 + result["fat_g"] * 9, abs=2
    )


def test_split_macros_maintenance_and_surplus_use_lower_protein_ratio():
    maintenance = split_macros(tdee=2500, goal="maintenance", weight_kg=80)
    surplus = split_macros(tdee=2500, goal="surplus", weight_kg=80)
    assert maintenance["kcal"] == pytest.approx(2500, abs=1)
    assert surplus["kcal"] == pytest.approx(2750, abs=1)
    assert maintenance["protein_g"] == pytest.approx(144, abs=1)  # 1.8 g/kg
    assert surplus["protein_g"] == pytest.approx(144, abs=1)
```

Añade `import pytest` al principio del archivo.

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_macros.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.macros'`.

- [ ] **Step 3: Implementa `app/macros.py`**

```python
ACTIVITY_MULTIPLIERS = {
    "sedentario": 1.2,
    "ligero": 1.375,
    "moderado": 1.55,
    "intenso": 1.725,
}

GOAL_KCAL_ADJUSTMENTS = {
    "deficit": 0.8,
    "maintenance": 1.0,
    "surplus": 1.1,
}

FAT_MASS_KCAL_PER_KG = 9300
FAT_KCAL_PER_G = 9
PROTEIN_KCAL_PER_G = 4
CARBS_KCAL_PER_G = 4
FAT_PCT_OF_KCAL = 0.25


def compute_real_tdee(body_metrics: list[dict], diet_daily_kcal: list[dict]) -> float | None:
    if len(body_metrics) < 2:
        return None

    segment_tdees = []
    for m1, m2 in zip(body_metrics, body_metrics[1:]):
        days = (m2["measured_on"] - m1["measured_on"]).days
        if days <= 0:
            continue

        versions_in_range = [
            v
            for v in diet_daily_kcal
            if m1["measured_on"] <= v["valid_from"] < m2["measured_on"]
        ]
        if not versions_in_range:
            continue
        avg_daily_kcal = sum(v["daily_kcal"] for v in versions_in_range) / len(
            versions_in_range
        )

        fat_mass_1 = m1["weight_kg"] * m1["body_fat_pct"] / 100
        fat_mass_2 = m2["weight_kg"] * m2["body_fat_pct"] / 100
        fat_energy_change = (fat_mass_1 - fat_mass_2) * FAT_MASS_KCAL_PER_KG

        segment_tdees.append(avg_daily_kcal + fat_energy_change / days)

    if not segment_tdees:
        return None
    return sum(segment_tdees) / len(segment_tdees)


def mifflin_st_jeor(
    age: int, sex: str, height_cm: float, weight_kg: float, activity_level: str
) -> float:
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age
    bmr += 5 if sex == "M" else -161
    return bmr * ACTIVITY_MULTIPLIERS[activity_level]


def split_macros(tdee: float, goal: str, weight_kg: float) -> dict:
    target_kcal = tdee * GOAL_KCAL_ADJUSTMENTS[goal]
    protein_per_kg = 2.2 if goal == "deficit" else 1.8
    protein_g = weight_kg * protein_per_kg
    fat_g = (target_kcal * FAT_PCT_OF_KCAL) / FAT_KCAL_PER_G
    remaining_kcal = target_kcal - protein_g * PROTEIN_KCAL_PER_G - fat_g * FAT_KCAL_PER_G
    carbs_g = remaining_kcal / CARBS_KCAL_PER_G
    return {
        "kcal": round(target_kcal),
        "protein_g": round(protein_g),
        "carbs_g": round(carbs_g),
        "fat_g": round(fat_g),
    }
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_macros.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/macros.py tests/test_macros.py
git commit -m "Add deterministic real-TDEE and macro split calculation"
```

---

### Task 5: Página de macros objetivo (comparación)

**Files:**
- Modify: `app/main.py` (ruta `GET /macros`: junta perfil + body_metrics + kcal diaria de dietas, calcula determinista o cae a Mifflin-St Jeor, muestra junto al último resultado guardado de método `agent`)
- Create: `app/templates/macros.html`
- Test: `tests/test_macros_page.py`

**Interfaces:**
- Consumes: `app.macros.compute_real_tdee`, `app.macros.mifflin_st_jeor`, `app.macros.split_macros`, tabla `macro_targets` (solo lectura del último `method='agent'`).
- Produces: `GET /macros`.

- [ ] **Step 1: Escribe el test que falla**

`tests/test_macros_page.py`:
```python
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _seed_profile():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_profile (id, age, sex, height_cm, activity_level, current_goal)
                VALUES (1, 23, 'M', 178, 'moderado', 'maintenance')
                ON CONFLICT (id) DO UPDATE SET
                    age = EXCLUDED.age, sex = EXCLUDED.sex, height_cm = EXCLUDED.height_cm,
                    activity_level = EXCLUDED.activity_level, current_goal = EXCLUDED.current_goal
                """
            )


def test_macros_page_falls_back_to_mifflin_without_enough_body_metrics():
    _seed_profile()
    response = client.get("/macros")
    assert response.status_code == 200
    assert "mifflin" in response.text.lower() or "formula" in response.text.lower()


def test_macros_page_requires_profile():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_profile WHERE id = 1")
    response = client.get("/macros")
    assert response.status_code == 200
    assert "perfil" in response.text.lower()
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_macros_page.py -v`
Expected: FAIL con `404 Not Found`.

- [ ] **Step 3: Añade a `app/main.py`**

```python
from app.macros import compute_real_tdee, mifflin_st_jeor, split_macros


def get_body_metrics_for_tdee() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT measured_on, weight_kg, body_fat_pct FROM body_metrics "
                "WHERE weight_kg IS NOT NULL AND body_fat_pct IS NOT NULL "
                "ORDER BY measured_on"
            )
            rows = cur.fetchall()
    return [
        {"measured_on": row[0], "weight_kg": float(row[1]), "body_fat_pct": float(row[2])}
        for row in rows
    ]


def get_diet_versions_daily_kcal() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dv.valid_from,
                    dv.valid_to,
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.kcal_100g), 0)
                        / NULLIF(COUNT(DISTINCT dm.day_label), 0) AS daily_kcal
                FROM diet_versions dv
                LEFT JOIN diet_meals dm ON dm.diet_version_id = dv.id
                LEFT JOIN foods f ON f.id = dm.matched_food_id
                GROUP BY dv.id, dv.valid_from, dv.valid_to
                ORDER BY dv.valid_from
                """
            )
            rows = cur.fetchall()
    return [
        {"valid_from": row[0], "valid_to": row[1], "daily_kcal": float(row[2] or 0)}
        for row in rows
    ]


def get_latest_agent_macro_target() -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT goal, kcal, protein_g, carbs_g, fat_g, explanation, computed_at
                FROM macro_targets WHERE method = 'agent'
                ORDER BY computed_at DESC LIMIT 1
                """
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "goal": row[0],
        "kcal": float(row[1]),
        "protein_g": float(row[2]),
        "carbs_g": float(row[3]),
        "fat_g": float(row[4]),
        "explanation": row[5],
        "computed_at": row[6].isoformat(),
    }


def compute_formula_macro_target(profile: dict) -> dict:
    body_metrics = get_body_metrics_for_tdee()
    tdee = compute_real_tdee(body_metrics, get_diet_versions_daily_kcal())
    method_label = "real"
    if tdee is None:
        method_label = "mifflin"
        latest_weight = body_metrics[-1]["weight_kg"] if body_metrics else None
        if latest_weight is None:
            raise ValueError("No hay medidas corporales para calcular Mifflin-St Jeor")
        tdee = mifflin_st_jeor(
            age=profile["age"],
            sex=profile["sex"],
            height_cm=profile["height_cm"],
            weight_kg=latest_weight,
            activity_level=profile["activity_level"],
        )
    latest_weight = body_metrics[-1]["weight_kg"] if body_metrics else profile["height_cm"]
    result = split_macros(tdee, profile["current_goal"], latest_weight)
    result["method_label"] = method_label
    return result


@app.get("/macros")
def macros_page(request: Request):
    profile = get_user_profile()
    template = templates.get_template("macros.html")
    if profile is None:
        return HTMLResponse(
            template.render({"request": request, "profile": None})
        )
    formula_result = compute_formula_macro_target(profile)
    return HTMLResponse(
        template.render(
            {
                "request": request,
                "profile": profile,
                "formula": formula_result,
                "agent": get_latest_agent_macro_target(),
            }
        )
    )
```

- [ ] **Step 4: Crea `app/templates/macros.html`**

```html
{% extends "base.html" %}
{% block title %}Macros objetivo{% endblock %}
{% block content %}
<h1>Macros objetivo</h1>
{% if not profile %}
<p>Falta completar el <a href="/perfil">perfil</a> antes de calcular macros.</p>
{% else %}
<div id="formula-result">
  <h2>Metodo determinista ({{ formula.method_label }})</h2>
  <p>Kcal: {{ formula.kcal }} | Proteina: {{ formula.protein_g }}g | Carbohidratos: {{ formula.carbs_g }}g | Grasa: {{ formula.fat_g }}g</p>
</div>

<div id="agent-result">
  <h2>Metodo IA (Claude Agent SDK)</h2>
  {% if agent %}
  <p>Kcal: {{ agent.kcal }} | Proteina: {{ agent.protein_g }}g | Carbohidratos: {{ agent.carbs_g }}g | Grasa: {{ agent.fat_g }}g</p>
  <p>{{ agent.explanation }}</p>
  <p><small>Calculado el {{ agent.computed_at }}</small></p>
  {% else %}
  <p>Aun no se ha calculado con IA.</p>
  {% endif %}
  <button
    hx-post="/macros/recalcular-ia"
    hx-target="#agent-result"
    hx-swap="outerHTML"
    hx-indicator="#agent-loading">
    Recalcular con IA
  </button>
  <span id="agent-loading" class="htmx-indicator">Calculando...</span>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_macros_page.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/templates/macros.html tests/test_macros_page.py
git commit -m "Add macro targets comparison page with deterministic calculation"
```

---

### Task 6: Cálculo con Agent SDK + botón "Recalcular con IA"

**Files:**
- Create: `app/agent_macros.py`
- Modify: `app/main.py` (ruta `POST /macros/recalcular-ia`, guarda en `macro_targets`, devuelve el fragmento `#agent-result`)
- Modify: `app/templates/macros.html` (extraer el bloque `#agent-result` a un partial reutilizable por la respuesta HTMX)
- Test: `tests/test_agent_macros.py`, extender `tests/test_macros_page.py`

**Interfaces:**
- Produces: `app.agent_macros.compute_agent_macro_target(summary: dict) -> dict` (llama al Agent SDK, devuelve `kcal`/`protein_g`/`carbs_g`/`fat_g`/`explanation`), `POST /macros/recalcular-ia`.

- [ ] **Step 1: Escribe el test que falla (`app/agent_macros.py`)**

`tests/test_agent_macros.py`:
```python
import json

from claude_agent_sdk import ResultMessage

from app.agent_macros import compute_agent_macro_target


def test_compute_agent_macro_target_parses_structured_output(monkeypatch):
    expected = {
        "kcal": 2400,
        "protein_g": 180,
        "carbs_g": 250,
        "fat_g": 67,
        "explanation": "Mantenimiento basado en tu TDEE real reciente.",
    }
    fake_result = ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=90,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        structured_output=expected,
        result=json.dumps(expected),
    )

    async def fake_query(prompt, options):
        yield fake_result

    monkeypatch.setattr("app.agent_macros.query", fake_query)

    result = compute_agent_macro_target(
        {
            "profile": {"age": 23, "sex": "M", "height_cm": 178, "activity_level": "moderado"},
            "goal": "maintenance",
            "real_tdee": 2500,
            "weight_history": [{"date": "2026-01-01", "weight_kg": 80.0, "body_fat_pct": 20.0}],
        }
    )
    assert result == expected
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_agent_macros.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.agent_macros'`.

- [ ] **Step 3: Implementa `app/agent_macros.py`**

```python
import json
import tempfile
from pathlib import Path

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

AGENT_CWD = Path(tempfile.gettempdir()) / "agentenutricional_macro_agent"

MACRO_SCHEMA = {
    "type": "object",
    "properties": {
        "kcal": {"type": "number"},
        "protein_g": {"type": "number"},
        "carbs_g": {"type": "number"},
        "fat_g": {"type": "number"},
        "explanation": {"type": "string"},
    },
    "required": ["kcal", "protein_g", "carbs_g", "fat_g", "explanation"],
    "additionalProperties": False,
}


def compute_agent_macro_target(summary: dict) -> dict:
    AGENT_CWD.mkdir(parents=True, exist_ok=True)
    options = ClaudeAgentOptions(
        system_prompt=(
            "Eres un asistente de nutricion. Con el resumen de perfil e "
            "historico que te doy, recomienda kcal y macros (proteina, "
            "carbohidratos, grasa en gramos) objetivo para el objetivo "
            "indicado, con una explicacion breve."
        ),
        max_turns=3,
        cwd=str(AGENT_CWD),
        setting_sources=[],
        allowed_tools=[],
        output_format={"type": "json_schema", "schema": MACRO_SCHEMA},
    )
    prompt = (
        "Resumen del usuario (JSON):\n"
        f"{json.dumps(summary, ensure_ascii=False)}\n\n"
        "Recomienda kcal y macros objetivo."
    )

    async def _run() -> dict:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.is_error or message.structured_output is None:
                    raise RuntimeError(f"Recomendacion IA fallida: {message.result}")
                return message.structured_output
        raise RuntimeError("Sin respuesta del agente")

    return anyio.run(_run)
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_agent_macros.py -v`
Expected: PASS

- [ ] **Step 5: Extrae el partial `#agent-result` en `app/templates/macros.html`**

Crea `app/templates/_agent_result.html`:
```html
<div id="agent-result">
  {% if agent %}
  <p>Kcal: {{ agent.kcal }} | Proteina: {{ agent.protein_g }}g | Carbohidratos: {{ agent.carbs_g }}g | Grasa: {{ agent.fat_g }}g</p>
  <p>{{ agent.explanation }}</p>
  <p><small>Calculado el {{ agent.computed_at }}</small></p>
  {% else %}
  <p>Aun no se ha calculado con IA.</p>
  {% endif %}
  <button
    hx-post="/macros/recalcular-ia"
    hx-target="#agent-result"
    hx-swap="outerHTML"
    hx-indicator="#agent-loading">
    Recalcular con IA
  </button>
  <span id="agent-loading" class="htmx-indicator">Calculando...</span>
</div>
```

En `app/templates/macros.html`, reemplaza el bloque `<div id="agent-result">...</div>` por:
```html
<h2>Metodo IA (Claude Agent SDK)</h2>
{% include "_agent_result.html" %}
```

- [ ] **Step 6: Añade a `app/main.py` la ruta `POST /macros/recalcular-ia`**

```python
from app.agent_macros import compute_agent_macro_target


def save_agent_macro_target(goal: str, result: dict) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO macro_targets (method, goal, kcal, protein_g, carbs_g, fat_g, explanation)
                VALUES ('agent', %s, %s, %s, %s, %s, %s)
                """,
                (
                    goal,
                    result["kcal"],
                    result["protein_g"],
                    result["carbs_g"],
                    result["fat_g"],
                    result["explanation"],
                ),
            )


@app.post("/macros/recalcular-ia")
def macros_recalcular_ia(request: Request):
    profile = get_user_profile()
    body_metrics = get_body_metrics_for_tdee()
    real_tdee = compute_real_tdee(body_metrics, get_diet_versions_daily_kcal())
    summary = {
        "profile": profile,
        "goal": profile["current_goal"],
        "real_tdee": real_tdee,
        "weight_history": [
            {
                "date": m["measured_on"].isoformat(),
                "weight_kg": m["weight_kg"],
                "body_fat_pct": m["body_fat_pct"],
            }
            for m in body_metrics
        ],
    }
    result = compute_agent_macro_target(summary)
    save_agent_macro_target(profile["current_goal"], result)

    template = templates.get_template("_agent_result.html")
    return HTMLResponse(
        template.render({"request": request, "agent": get_latest_agent_macro_target()})
    )
```

- [ ] **Step 7: Extiende `tests/test_macros_page.py` con un test mockeado del botón**

Añade al archivo:
```python
def test_recalcular_ia_saves_and_returns_partial(monkeypatch):
    _seed_profile()

    async def fake_compute(summary):
        return {
            "kcal": 2400,
            "protein_g": 180,
            "carbs_g": 250,
            "fat_g": 67,
            "explanation": "Recomendacion de prueba.",
        }

    def fake_compute_sync(summary):
        return {
            "kcal": 2400,
            "protein_g": 180,
            "carbs_g": 250,
            "fat_g": 67,
            "explanation": "Recomendacion de prueba.",
        }

    monkeypatch.setattr("app.main.compute_agent_macro_target", fake_compute_sync)

    response = client.post("/macros/recalcular-ia")
    assert response.status_code == 200
    assert "Recomendacion de prueba" in response.text

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM macro_targets WHERE method = 'agent' "
                "AND explanation = 'Recomendacion de prueba.'"
            )
            count = cur.fetchone()[0]
    assert count == 1
```

(Elimina la función `fake_compute` no usada del bloque anterior si el editor la deja huérfana — solo `fake_compute_sync` hace falta, ya que `compute_agent_macro_target` es una función síncrona normal desde el punto de vista de quien la llama.)

- [ ] **Step 8: Ejecuta toda la suite de macros para verificar que pasa**

Run: `python -m pytest tests/test_agent_macros.py tests/test_macros_page.py -v`
Expected: PASS

- [ ] **Step 9: Verifica visualmente en el navegador**

Run: `docker compose up -d --build`
Abre `http://localhost:8000/perfil`, rellena el perfil. Abre `http://localhost:8000/medidas`, registra una medida. Abre `http://localhost:8000/macros`, pulsa "Recalcular con IA" y confirma que aparece una recomendación real (esto sí gasta una llamada real de la suscripción — hazlo una vez para confirmar, no en bucle).

- [ ] **Step 10: Commit**

```bash
git add app/agent_macros.py app/main.py app/templates/macros.html app/templates/_agent_result.html tests/test_agent_macros.py tests/test_macros_page.py
git commit -m "Add Agent SDK-based macro recommendation with on-demand recalculation"
```

---

## Después de este plan

Con el Subsistema 2 completo: `http://localhost:8000/perfil` para configurar el perfil, `http://localhost:8000/medidas` para registrar nuevas medidas del gimnasio, `http://localhost:8000/macros` para ver la comparación entre el cálculo determinista (TDEE real o respaldo Mifflin-St Jeor) y la recomendación bajo demanda del Agent SDK. El Subsistema 3 (generador de dietas variadas) partirá de los macros objetivo calculados aquí.
