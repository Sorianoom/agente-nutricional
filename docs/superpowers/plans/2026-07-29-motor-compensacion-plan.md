# Subsistema 4: Motor de compensación y antojos — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar este plan tarea por tarea. Los pasos usan sintaxis de checkbox (`- [ ]`) para seguimiento.

**Goal:** Registrar comidas fuera de plan, corregir desviaciones de un día ya cerrado, encajar
antojos ajustando el resto del día, y repartir cualquier desvío neto (de más o de menos) entre
los siguientes 3 días de calendario, ajustando el objetivo de macros mientras dure.

**Architecture:** Mismo stack que los Subsistemas 1-3. Reutiliza extensivamente el Subsistema 3
(`app.food_matching.find_matching_food`, `app.diet_generator.remaining_budget`,
`app.diet_generator.generate_day`, `app.diet_generator.within_tolerance`). El único mecanismo
nuevo de datos es `pending_compensation`, una tabla de a lo sumo una fila activa, consultada
desde una fecha de calendario (`created_at`), nunca desde un contador de llamadas — ver la nota
de diseño del Subsistema 4 en la spec.

## Global Constraints

- El margen de ±5% y el patrón de Agent SDK ya validados en el Subsistema 3 se reutilizan tal
  cual, no se reinventan.
- La compensación se calcula **una sola vez por día**, al cerrarlo — nunca en cada registro
  ad-hoc individual ni en cada cálculo de macros (`/macros` recalcula en cada visita).
- Todo el código vive en `D:\homeMario\AgenteNutricional`.

---

### Task 1: Esquema de datos — `pending_compensation`

**Files:**
- Modify: `db/schema.sql` (añadir la tabla nueva, `CREATE TABLE IF NOT EXISTS` como el resto)
- Modify: `tests/test_db_schema.py`

**Interfaces:**
- Produces: tabla Postgres `pending_compensation` (a lo sumo una fila activa a la vez, sin
  constraint de unicidad forzada en BD — la aplicación garantiza que solo haya una).

- [x] **Step 1: Escribe el test que falla**

Añade `"pending_compensation"` al `set` esperado en `tests/test_db_schema.py`:
```python
    assert {
        "foods",
        "diet_versions",
        "diet_meals",
        "body_metrics",
        "user_profile",
        "macro_targets",
        "pending_compensation",
    } <= tables
```

- [x] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_db_schema.py -v`
Expected: FAIL (`pending_compensation` no está en `tables`).

- [x] **Step 3: Añade a `db/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS pending_compensation (
    id SERIAL PRIMARY KEY,
    kcal_delta NUMERIC NOT NULL,
    protein_g_delta NUMERIC NOT NULL,
    carbs_g_delta NUMERIC NOT NULL,
    fat_g_delta NUMERIC NOT NULL,
    days_total INTEGER NOT NULL DEFAULT 3,
    created_at DATE NOT NULL DEFAULT CURRENT_DATE
);
```

- [x] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_db_schema.py -v`
Expected: PASS

- [x] **Step 5: Aplica la tabla nueva a la base de datos real, sin destruir datos**

**No uses `docker compose down -v`.**

```bash
docker compose exec -T postgres psql -U nutricion -d nutricion < db/schema.sql
docker compose exec postgres psql -U nutricion -d nutricion -c "\dt"
```
Expected: `pending_compensation` aparece en el listado, junto con todas las tablas anteriores
intactas.

- [x] **Step 6: Commit**

```bash
git add db/schema.sql tests/test_db_schema.py
git commit -m "Add pending_compensation table for the multi-day macro compensation engine"
```

---

### Task 2: Funciones puras del algoritmo de compensación

**Files:**
- Create: `app/compensation.py`
- Test: `tests/test_compensation.py`

**Interfaces:**
- Produces: `compute_delta(real_totals, target) -> dict`,
  `get_active_compensation() -> dict | None`,
  `create_or_merge_compensation(delta) -> None`,
  `replace_or_clear_after_correction(real_totals, target) -> None`,
  `close_day_and_check_compensation(real_totals, target) -> None`,
  `apply_pending_compensation(target: dict) -> dict`.

**Importante — léelo antes de escribir nada:** `get_active_compensation` deriva los días
transcurridos de `(date.today() - created_at).days`, **nunca** de un contador que se
incrementa en cada llamada — `/macros` recalcula el método determinista en cada visita a la
página, así que un contador de llamadas agotaría la ventana de 3 días en minutos. Si encuentras
alguna tentación de añadir un contador de "veces aplicado", detente: es exactamente el error de
diseño que la spec fue corregida para evitar.

- [x] **Step 1: Escribe el test que falla**

`tests/test_compensation.py`:
```python
from datetime import date, timedelta

from app.db import get_connection
from app.compensation import (
    apply_pending_compensation,
    close_day_and_check_compensation,
    compute_delta,
    create_or_merge_compensation,
    get_active_compensation,
    replace_or_clear_after_correction,
)

TARGET = {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0}


def _clear_compensation():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_compensation")


def test_compute_delta_subtracts_target_from_real():
    real = {"kcal": 2300.0, "protein_g": 140.0, "carbs_g": 210.0, "fat_g": 70.0}
    delta = compute_delta(real, TARGET)
    assert delta == {
        "kcal_delta": 300.0, "protein_g_delta": -10.0,
        "carbs_g_delta": 10.0, "fat_g_delta": 10.0,
    }


def test_close_day_within_tolerance_creates_nothing():
    _clear_compensation()
    real = {k: v * 1.02 for k, v in TARGET.items()}
    close_day_and_check_compensation(real, TARGET)
    assert get_active_compensation() is None


def test_close_day_out_of_tolerance_creates_compensation():
    _clear_compensation()
    real = {"kcal": 2300.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0}
    close_day_and_check_compensation(real, TARGET)
    active = get_active_compensation()
    assert active is not None
    assert active["kcal_delta"] == 300.0
    assert active["days_total"] == 3


def test_apply_pending_compensation_adjusts_target():
    _clear_compensation()
    create_or_merge_compensation({
        "kcal_delta": 300.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0,
    })
    adjusted = apply_pending_compensation(dict(TARGET))
    assert adjusted["kcal"] == 2000.0 - 100.0
    assert adjusted["protein_g"] == 150.0


def test_active_compensation_expires_after_days_total():
    _clear_compensation()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pending_compensation "
                "(kcal_delta, protein_g_delta, carbs_g_delta, fat_g_delta, days_total, created_at) "
                "VALUES (300, 0, 0, 0, 3, %s)",
                ((date.today() - timedelta(days=3)).isoformat(),),
            )
    assert get_active_compensation() is None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pending_compensation")
            assert cur.fetchone()[0] == 0


def test_create_or_merge_sums_remaining_fraction_of_previous_delta():
    _clear_compensation()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pending_compensation "
                "(kcal_delta, protein_g_delta, carbs_g_delta, fat_g_delta, days_total, created_at) "
                "VALUES (300, 0, 0, 0, 3, %s)",
                ((date.today() - timedelta(days=1)).isoformat(),),
            )
    # Quedaba 1 dia transcurrido de 3 -> restante = 300 * (3-1)/3 = 200.
    create_or_merge_compensation({
        "kcal_delta": 150.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0,
    })
    active = get_active_compensation()
    assert active["kcal_delta"] == 350.0
    assert active["days_total"] == 3


def test_replace_or_clear_after_correction_deletes_when_now_within_tolerance():
    _clear_compensation()
    create_or_merge_compensation({
        "kcal_delta": 300.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0,
    })
    replace_or_clear_after_correction(dict(TARGET), TARGET)
    assert get_active_compensation() is None


def test_replace_or_clear_after_correction_updates_delta_when_still_off():
    _clear_compensation()
    create_or_merge_compensation({
        "kcal_delta": 300.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0,
    })
    corrected_real = {"kcal": 2150.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0}
    replace_or_clear_after_correction(corrected_real, TARGET)
    active = get_active_compensation()
    assert active["kcal_delta"] == 150.0
```

- [x] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_compensation.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.compensation'`.

- [x] **Step 3: Implementa `app/compensation.py`**

```python
from datetime import date

from app.db import get_connection
from app.diet_generator import MACRO_KEYS, within_tolerance

DAYS_TOTAL = 3


def compute_delta(real_totals: dict, target: dict) -> dict:
    return {
        "kcal_delta": real_totals["kcal"] - target["kcal"],
        "protein_g_delta": real_totals["protein_g"] - target["protein_g"],
        "carbs_g_delta": real_totals["carbs_g"] - target["carbs_g"],
        "fat_g_delta": real_totals["fat_g"] - target["fat_g"],
    }


def get_active_compensation() -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, kcal_delta, protein_g_delta, carbs_g_delta, fat_g_delta, "
                "days_total, created_at FROM pending_compensation LIMIT 1"
            )
            row = cur.fetchone()
    if row is None:
        return None
    days_elapsed = (date.today() - row[6]).days
    if days_elapsed >= row[5]:
        _delete_compensation(row[0])
        return None
    return {
        "id": row[0],
        "kcal_delta": float(row[1]),
        "protein_g_delta": float(row[2]),
        "carbs_g_delta": float(row[3]),
        "fat_g_delta": float(row[4]),
        "days_total": row[5],
        "created_at": row[6],
        "days_elapsed": days_elapsed,
    }


def _delete_compensation(compensation_id: int) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_compensation WHERE id = %s", (compensation_id,))


def _insert_compensation(delta: dict) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pending_compensation
                    (kcal_delta, protein_g_delta, carbs_g_delta, fat_g_delta, days_total, created_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
                """,
                (
                    delta["kcal_delta"],
                    delta["protein_g_delta"],
                    delta["carbs_g_delta"],
                    delta["fat_g_delta"],
                    DAYS_TOTAL,
                ),
            )


def create_or_merge_compensation(delta: dict) -> None:
    active = get_active_compensation()
    if active is None:
        _insert_compensation(delta)
        return
    remaining_fraction = (active["days_total"] - active["days_elapsed"]) / active["days_total"]
    merged = {
        key: active[key] * remaining_fraction + delta[key]
        for key in ("kcal_delta", "protein_g_delta", "carbs_g_delta", "fat_g_delta")
    }
    _delete_compensation(active["id"])
    _insert_compensation(merged)


def close_day_and_check_compensation(real_totals: dict, target: dict) -> None:
    if within_tolerance(real_totals, target):
        return
    create_or_merge_compensation(compute_delta(real_totals, target))


def replace_or_clear_after_correction(real_totals: dict, target: dict) -> None:
    active = get_active_compensation()
    if active is None:
        close_day_and_check_compensation(real_totals, target)
        return
    if within_tolerance(real_totals, target):
        _delete_compensation(active["id"])
        return
    delta = compute_delta(real_totals, target)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_compensation
                SET kcal_delta = %s, protein_g_delta = %s, carbs_g_delta = %s, fat_g_delta = %s
                WHERE id = %s
                """,
                (
                    delta["kcal_delta"],
                    delta["protein_g_delta"],
                    delta["carbs_g_delta"],
                    delta["fat_g_delta"],
                    active["id"],
                ),
            )


def apply_pending_compensation(target: dict) -> dict:
    active = get_active_compensation()
    if active is None:
        return dict(target)
    days_total = active["days_total"]
    adjusted = dict(target)
    adjusted["kcal"] = target["kcal"] - active["kcal_delta"] / days_total
    adjusted["protein_g"] = target["protein_g"] - active["protein_g_delta"] / days_total
    adjusted["carbs_g"] = target["carbs_g"] - active["carbs_g_delta"] / days_total
    adjusted["fat_g"] = target["fat_g"] - active["fat_g_delta"] / days_total
    return adjusted
```

(`MACRO_KEYS` se importa aunque no se use directamente en todas las funciones — puede quitarse
del import si tu editor se queja de import no usado, no es obligatorio mantenerlo.)

- [x] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_compensation.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add app/compensation.py tests/test_compensation.py
git commit -m "Add multi-day macro compensation engine (pure logic + Postgres persistence)"
```

---

### Task 3: Registrar comida fuera de plan

**Files:**
- Modify: `app/main.py` (funciones `get_or_create_today_diet_version`, `add_ad_hoc_meal`,
  `get_today_totals`; rutas `GET`/`POST /registrar-comida`)
- Create: `app/templates/registrar_comida.html`
- Modify: `app/templates/base.html` (enlace "Registrar comida" en el `<nav>`)
- Test: `tests/test_registrar_comida.py`

**Interfaces:**
- Produces: `app.main.get_or_create_today_diet_version() -> int`,
  `app.main.add_ad_hoc_meal(food_item, quantity_grams) -> None`,
  `app.main.get_today_totals() -> dict`, rutas `GET`/`POST /registrar-comida`.

- [x] **Step 1: Escribe el test que falla**

`tests/test_registrar_comida.py`:
```python
from datetime import date

from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _clear_today_diet_version():
    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE valid_from = %s AND valid_to = %s)",
                (today, today),
            )
            cur.execute(
                "DELETE FROM diet_versions WHERE valid_from = %s AND valid_to = %s",
                (today, today),
            )


def test_get_registrar_comida_shows_form():
    response = client.get("/registrar-comida")
    assert response.status_code == 200
    assert "form" in response.text.lower()


def test_post_registrar_comida_adds_meal_to_todays_diet_version():
    _clear_today_diet_version()

    response = client.post(
        "/registrar-comida",
        data={"food_item": "Pechuga de pollo", "quantity_grams": "200"},
    )
    assert response.status_code == 200

    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT dm.food_item, dm.quantity_grams FROM diet_meals dm "
                "JOIN diet_versions dv ON dv.id = dm.diet_version_id "
                "WHERE dv.valid_from = %s AND dv.valid_to = %s",
                (today, today),
            )
            rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "Pechuga de pollo"


def test_post_registrar_comida_twice_reuses_same_diet_version():
    _clear_today_diet_version()

    client.post("/registrar-comida", data={"food_item": "Avena integral", "quantity_grams": "100"})
    client.post("/registrar-comida", data={"food_item": "Yogur proteico", "quantity_grams": "125"})

    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM diet_versions WHERE valid_from = %s AND valid_to = %s",
                (today, today),
            )
            assert cur.fetchone()[0] == 1
            cur.execute(
                "SELECT count(*) FROM diet_meals dm "
                "JOIN diet_versions dv ON dv.id = dm.diet_version_id "
                "WHERE dv.valid_from = %s AND dv.valid_to = %s",
                (today, today),
            )
            assert cur.fetchone()[0] == 2
```

- [x] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_registrar_comida.py -v`
Expected: FAIL con `404 Not Found`.

- [x] **Step 3: Añade a `app/main.py`**

```python
from datetime import date

from app.food_matching import find_matching_food


def get_or_create_today_diet_version() -> int:
    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM diet_versions WHERE valid_from = %s AND valid_to = %s",
                (today, today),
            )
            row = cur.fetchone()
            if row is not None:
                return row[0]
            cur.execute(
                "INSERT INTO diet_versions (source_pdf_filename, valid_from, valid_to) "
                "VALUES ('manual', %s, %s) RETURNING id",
                (today, today),
            )
            return cur.fetchone()[0]


def add_ad_hoc_meal(food_item: str, quantity_grams: float) -> None:
    diet_version_id = get_or_create_today_diet_version()
    match = find_matching_food(food_item)
    matched_food_id = match["id"] if match else None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO diet_meals
                    (diet_version_id, day_label, meal_name, food_item, quantity_grams, matched_food_id)
                VALUES (%s, 'dia', 'extra', %s, %s, %s)
                """,
                (diet_version_id, food_item, quantity_grams, matched_food_id),
            )


def get_today_totals() -> dict:
    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.kcal_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.protein_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.carbs_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.fat_100g), 0)
                FROM diet_versions dv
                LEFT JOIN diet_meals dm ON dm.diet_version_id = dv.id
                LEFT JOIN foods f ON f.id = dm.matched_food_id
                WHERE dv.valid_from = %s AND dv.valid_to = %s
                GROUP BY dv.id
                """,
                (today, today),
            )
            row = cur.fetchone()
    if row is None:
        return {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    return {
        "kcal": float(row[0]),
        "protein_g": float(row[1]),
        "carbs_g": float(row[2]),
        "fat_g": float(row[3]),
    }


@app.get("/registrar-comida")
def registrar_comida_form(request: Request):
    template = templates.get_template("registrar_comida.html")
    return HTMLResponse(
        template.render({"request": request, "today_totals": get_today_totals()})
    )


@app.post("/registrar-comida")
def registrar_comida_save(
    request: Request,
    food_item: str = Form(...),
    quantity_grams: float = Form(...),
):
    add_ad_hoc_meal(food_item, quantity_grams)
    template = templates.get_template("registrar_comida.html")
    return HTMLResponse(
        template.render(
            {"request": request, "today_totals": get_today_totals(), "saved": True}
        )
    )
```

- [x] **Step 4: Crea `app/templates/registrar_comida.html`**

```html
{% extends "base.html" %}
{% block title %}Registrar comida{% endblock %}
{% block content %}
<h1>Registrar comida fuera de plan</h1>
<div class="card">
  <form method="post" action="/registrar-comida">
    <label>Alimento
      <input type="text" name="food_item" required placeholder="ej. Pechuga de pollo">
    </label>
    <label>Cantidad (g)
      <input type="number" step="0.1" name="quantity_grams" required>
    </label>
    <button type="submit">Registrar</button>
  </form>
</div>

{% if saved %}
<div class="card"><p><span class="badge good">Registrado</span></p></div>
{% endif %}

<div class="card">
  <h2>Total de hoy</h2>
  <hr class="hr-thin">
  <div class="macro-row"><span class="label">Kcal</span><span class="value">{{ "%.0f" | format(today_totals.kcal) }}</span></div>
  <div class="macro-row"><span class="label">Proteina</span><span class="value">{{ "%.1f" | format(today_totals.protein_g) }} g</span></div>
  <div class="macro-row"><span class="label">Carbohidratos</span><span class="value">{{ "%.1f" | format(today_totals.carbs_g) }} g</span></div>
  <div class="macro-row"><span class="label">Grasa</span><span class="value">{{ "%.1f" | format(today_totals.fat_g) }} g</span></div>
</div>
{% endblock %}
```

- [x] **Step 5: Añade el enlace al `<nav>` de `app/templates/base.html`**

```html
<a href="/registrar-comida" {% if request.url.path == '/registrar-comida' %}class="active"{% endif %}>Registrar comida</a>
```

- [x] **Step 6: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_registrar_comida.py -v`
Expected: PASS

- [x] **Step 7: Commit**

```bash
git add app/main.py app/templates/registrar_comida.html app/templates/base.html tests/test_registrar_comida.py
git commit -m "Add ad-hoc off-plan meal logging"
```

---

### Task 4: Cerrar el día de hoy + integrar el cierre en el guardado del Subsistema 3

**Files:**
- Modify: `app/main.py` (ruta `POST /cerrar-dia`; modificar `generar_dieta_guardar` para
  disparar también el chequeo de compensación tras guardar)
- Modify: `app/templates/registrar_comida.html` (botón "Cerrar el día de hoy")
- Test: `tests/test_registrar_comida.py` (extender), `tests/test_generar_dieta_page.py` (extender)

**Interfaces:**
- Produces: ruta `POST /cerrar-dia`.
- Consumes: `app.compensation.close_day_and_check_compensation`.

- [x] **Step 1: Escribe el test que falla**

Añade a `tests/test_registrar_comida.py`:
```python
from app.compensation import get_active_compensation


def _clear_compensation():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_compensation")


def test_cerrar_dia_creates_compensation_when_out_of_tolerance(monkeypatch):
    _clear_today_diet_version()
    _clear_compensation()
    add_meal_response = client.post(
        "/registrar-comida",
        data={"food_item": "Pechuga de pollo", "quantity_grams": "2000"},
    )
    assert add_meal_response.status_code == 200

    monkeypatch.setattr(
        "app.main.compute_formula_macro_target",
        lambda profile: {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0, "method_label": "real"},
    )
    monkeypatch.setattr("app.main.get_user_profile", lambda: {"current_goal": "maintenance"})

    response = client.post("/cerrar-dia")
    assert response.status_code == 200
    assert get_active_compensation() is not None
```

(Importa `add_ad_hoc_meal` desde `app.main` si hace falta para el resto de tests de este
archivo, y añade `from app.main import add_ad_hoc_meal, ...` según corresponda.)

- [x] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_registrar_comida.py -v`
Expected: FAIL con `404 Not Found`.

- [x] **Step 3: Añade a `app/main.py`**

```python
from app.compensation import close_day_and_check_compensation


@app.post("/cerrar-dia")
def cerrar_dia(request: Request):
    profile = get_user_profile()
    if profile is None:
        raise HTTPException(status_code=400, detail="Falta completar el perfil")
    target = compute_formula_macro_target(profile)
    real_totals = get_today_totals()
    close_day_and_check_compensation(real_totals, target)
    return HTMLResponse('<div class="card"><p><span class="badge good">Dia cerrado</span></p></div>')
```

- [x] **Step 4: Modifica `generar_dieta_guardar` para disparar también el chequeo de compensación**

En la ruta `POST /generar-dieta/guardar` (ya existente del Subsistema 3), justo después de
`save_generated_day(meals)` y antes del `return`, añade:

```python
    close_day_and_check_compensation(totals, target)
```

(`totals` y `target` ya están calculados en esa misma función para el chequeo de
`within_tolerance` previo — reutilízalos, no los recalcules.)

- [x] **Step 5: Añade el botón al final de `app/templates/registrar_comida.html`**

```html
<div class="card">
  <button
    hx-post="/cerrar-dia"
    hx-target="this"
    hx-swap="innerHTML">
    Cerrar el dia de hoy
  </button>
</div>
```

- [x] **Step 6: Ejecuta los tests para verificar que pasan**

Run: `python -m pytest tests/test_registrar_comida.py tests/test_generar_dieta_page.py -v`
Expected: PASS

- [x] **Step 7: Commit**

```bash
git add app/main.py app/templates/registrar_comida.html tests/test_registrar_comida.py
git commit -m "Add explicit day-closing action and trigger compensation from Task 3 diet save"
```

---

### Task 5: Aplicar el ajuste de compensación en `/macros` y `/generar-dieta`

**Files:**
- Modify: `app/main.py` (`macros_page`, `_current_macro_target`)
- Modify: `app/templates/macros.html` (aviso visual de compensación activa)
- Test: `tests/test_macros_page.py` (extender), `tests/test_generar_dieta_page.py` (extender)

**Interfaces:**
- Consumes: `app.compensation.apply_pending_compensation`, `app.compensation.get_active_compensation`.

- [ ] **Step 1: Escribe el test que falla**

Añade a `tests/test_macros_page.py`:
```python
from app.compensation import create_or_merge_compensation


def test_macros_page_shows_compensation_adjusted_target(monkeypatch):
    _seed_profile()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_compensation")

    monkeypatch.setattr(
        "app.main.compute_formula_macro_target",
        lambda profile: {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0, "method_label": "real"},
    )
    create_or_merge_compensation(
        {"kcal_delta": 300.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0}
    )

    response = client.get("/macros")
    assert response.status_code == 200
    assert "1900" in response.text
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_macros_page.py -v`
Expected: FAIL (el target mostrado no refleja el ajuste todavía).

- [ ] **Step 3: Modifica `app/main.py`**

```python
from app.compensation import apply_pending_compensation, get_active_compensation


def _current_macro_target(method: str, profile: dict) -> tuple[dict, str] | None:
    if method == "formula":
        try:
            result = compute_formula_macro_target(profile)
        except ValueError:
            return None
        goal = profile["current_goal"]
    else:
        agent_result = get_latest_agent_macro_target()
        if agent_result is None:
            return None
        result = agent_result
        goal = agent_result["goal"]
    return apply_pending_compensation(result), goal


@app.get("/macros")
def macros_page(request: Request):
    profile = get_user_profile()
    template = templates.get_template("macros.html")
    if profile is None:
        return HTMLResponse(
            template.render({"request": request, "profile": None})
        )
    formula_result = apply_pending_compensation(compute_formula_macro_target(profile))
    agent_result = get_latest_agent_macro_target()
    return HTMLResponse(
        template.render(
            {
                "request": request,
                "profile": profile,
                "formula": formula_result,
                "agent": apply_pending_compensation(agent_result) if agent_result else None,
                "compensation": get_active_compensation(),
            }
        )
    )
```

(Sustituye la implementación anterior de `_current_macro_target` y `macros_page` completas por
estas — no dupliques definiciones.)

- [ ] **Step 4: Añade el aviso a `app/templates/macros.html`**

Justo después de `<h1>Macros objetivo</h1>`:
```html
{% if compensation %}
<div class="card">
  <p><span class="badge bad">Compensacion activa</span> ajustando
  {{ "%.0f" | format(compensation.kcal_delta / compensation.days_total) }} kcal/dia durante
  {{ compensation.days_total - compensation.days_elapsed }} dia(s) mas.</p>
</div>
{% endif %}
```

- [ ] **Step 5: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_macros_page.py -v`
Expected: PASS

- [ ] **Step 6: Ejecuta toda la suite para verificar que no hay regresiones**

Run: `python -m pytest tests/ -v`
Expected: todos los tests pasan.

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/templates/macros.html tests/test_macros_page.py
git commit -m "Apply pending macro compensation to the displayed target in /macros"
```

---

### Task 6: Antojo que ajusta el resto del día

**Files:**
- Modify: `app/diet_generator.py` (parametrizar `generate_day`/`_call_agent_for_day` con un
  `meal_names` opcional, para poder generar solo un subconjunto de comidas)
- Modify: `app/main.py` (ruta `GET`/`POST /antojo`)
- Create: `app/templates/antojo.html`
- Modify: `app/templates/base.html` (enlace "Antojo" en el `<nav>`)
- Test: `tests/test_diet_generator.py` (extender), `tests/test_antojo_page.py`

**Interfaces:**
- Produces: `app.diet_generator.generate_day(target, goal, hints, meal_names=MEAL_NAMES) -> dict`
  (mismo comportamiento por defecto, ahora aceptando un subconjunto), rutas `GET`/`POST /antojo`.

**Simplificación deliberada de esta tarea (anótala si la cambias en el futuro):** el antojo
siempre fija **una** comida y regenera **las otras tres** desde cero — no combina el antojo con
ediciones individuales previas de comidas concretas. Es una simplificación razonable para esta
primera versión: para eso ya existe `/generar-dieta` con su regeneración comida a comida.

- [ ] **Step 1: Escribe el test que falla (`generate_day` con subconjunto de comidas)**

Añade a `tests/test_diet_generator.py`:
```python
def test_generate_day_accepts_meal_names_subset(monkeypatch):
    partial_proposal = {
        "comida": {"food_item": "pechuga de pollo", "quantity_grams": 200},
        "cena": {"food_item": "salmon", "quantity_grams": 150},
        "merienda": {"food_item": "yogur proteico", "quantity_grams": 125},
    }
    captured_schemas = []

    async def fake_query(prompt, options):
        captured_schemas.append(options.output_format["schema"])
        yield _fake_result(partial_proposal)

    monkeypatch.setattr("app.diet_generator.query", fake_query)
    monkeypatch.setattr(
        "app.diet_generator.find_matching_food",
        lambda name: FAKE_MATCHES.get(name),
    )

    result = generate_day(
        {"kcal": 700.0, "protein_g": 60.0, "carbs_g": 60.0, "fat_g": 25.0},
        "maintenance",
        {},
        meal_names=("comida", "merienda", "cena"),
    )
    assert {m["meal_name"] for m in result["meals"]} == {"comida", "merienda", "cena"}
    assert "desayuno" not in captured_schemas[0]["properties"]
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_diet_generator.py -v`
Expected: FAIL con `TypeError: generate_day() got an unexpected keyword argument 'meal_names'`.

- [ ] **Step 3: Modifica `app/diet_generator.py`**

Sustituye el `DAY_SCHEMA` fijo por una función que lo construye para el subconjunto de comidas
pedido, y añade el parámetro `meal_names` a `_call_agent_for_day` y `generate_day`:

```python
def _build_day_schema(meal_names: tuple) -> dict:
    return {
        "type": "object",
        "properties": {name: MEAL_PROPOSAL_SCHEMA for name in meal_names},
        "required": list(meal_names),
        "additionalProperties": False,
    }


def _call_agent_for_day(
    target: dict, goal: str, hints: dict, previous_attempt_note: str, meal_names: tuple = MEAL_NAMES
) -> dict:
    AGENT_CWD.mkdir(parents=True, exist_ok=True)
    options = ClaudeAgentOptions(
        system_prompt=(
            "Eres un asistente de nutricion que compone dietas variadas y "
            "realistas con productos de supermercado espanol. Ajusta las "
            "cantidades en gramos para acercarte lo maximo posible a las "
            "kcal y macros objetivo indicadas."
        ),
        max_turns=3,
        cwd=str(AGENT_CWD),
        setting_sources=[],
        allowed_tools=[],
        output_format={"type": "json_schema", "schema": _build_day_schema(meal_names)},
    )
    hints_lines = [f"- {meal}: {hint}" for meal, hint in hints.items() if hint]
    hints_text = ("Directrices por comida (orientacion suave, no exacta):\n" + "\n".join(hints_lines) + "\n") if hints_lines else ""
    prompt = (
        f"Objetivo para estas comidas: {json.dumps(target, ensure_ascii=False)}\n"
        f"Objetivo del usuario: {goal}\n"
        f"Alimentos a evitar: {', '.join(EXCLUDED_FOODS)}\n"
        f"{hints_text}"
        f"{previous_attempt_note}"
        f"Propon {', '.join(meal_names)} con food_item (nombre de producto de "
        "supermercado espanol) y quantity_grams."
    )

    async def _run() -> dict:
        messages = query(prompt=prompt, options=options)
        try:
            async for message in messages:
                if isinstance(message, ResultMessage):
                    if message.is_error or message.structured_output is None:
                        raise RuntimeError(f"Generacion de dieta fallida: {message.result}")
                    return message.structured_output
            raise RuntimeError("Sin respuesta del agente")
        finally:
            await messages.aclose()

    return anyio.run(_run)


def generate_day(target: dict, goal: str, hints: dict, meal_names: tuple = MEAL_NAMES) -> dict:
    note = ""
    meals: list = []
    totals: dict = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        proposal = _call_agent_for_day(target, goal, hints, note, meal_names)
        meals = [_resolve_meal(name, proposal[name]) for name in meal_names]
        totals = _day_totals(meals)
        if within_tolerance(totals, target):
            return {"meals": meals, "totals": totals, "within_tolerance": True, "attempts": attempt}
        note = (
            f"Tu propuesta anterior dio como resultado real {json.dumps(totals, ensure_ascii=False)}, "
            f"que no cuadra con el objetivo dentro de un 5%. Ajusta las cantidades para acercarte mas.\n"
        )
    return {"meals": meals, "totals": totals, "within_tolerance": False, "attempts": MAX_ATTEMPTS}
```

(Reemplaza las definiciones anteriores de `_call_agent_for_day`/`generate_day` completas por
estas — el `try/finally: await messages.aclose()` de la Tarea 5 del Subsistema 3 se mantiene
tal cual, solo se añade el parámetro `meal_names`.)

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_diet_generator.py -v`
Expected: PASS (incluye también los tests ya existentes de `generate_day`, que siguen usando el
valor por defecto `MEAL_NAMES` — confirma que ninguno se rompió).

- [ ] **Step 5: Escribe el test que falla para la página de antojo**

`tests/test_antojo_page.py`:
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


def test_get_antojo_shows_form():
    response = client.get("/antojo")
    assert response.status_code == 200
    assert "form" in response.text.lower()


def test_post_antojo_fits_craving_and_generates_rest(monkeypatch):
    _seed_profile()
    monkeypatch.setattr(
        "app.main.compute_formula_macro_target",
        lambda profile: {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0, "method_label": "real"},
    )

    fake_rest_of_day = {
        "meals": [
            {"meal_name": "desayuno", "food_item": "Avena integral", "quantity_grams": 100, "matched_food_id": 1, "verified": True, "kcal": 350.0, "protein_g": 13.0, "carbs_g": 60.0, "fat_g": 7.0},
            {"meal_name": "comida", "food_item": "Pechuga de pollo", "quantity_grams": 200, "matched_food_id": 2, "verified": True, "kcal": 220.0, "protein_g": 46.0, "carbs_g": 0.0, "fat_g": 4.0},
            {"meal_name": "cena", "food_item": "Salmon", "quantity_grams": 100, "matched_food_id": 4, "verified": True, "kcal": 200.0, "protein_g": 20.0, "carbs_g": 0.0, "fat_g": 13.0},
        ],
        "totals": {"kcal": 770.0, "protein_g": 79.0, "carbs_g": 60.0, "fat_g": 24.0},
        "within_tolerance": True,
        "attempts": 1,
    }
    monkeypatch.setattr(
        "app.main.generate_day",
        lambda target, goal, hints, meal_names: fake_rest_of_day,
    )

    response = client.post(
        "/antojo",
        data={
            "method": "formula",
            "craving_meal_name": "merienda",
            "craving_food_item": "Chocolate negro",
            "craving_quantity_grams": "30",
        },
    )
    assert response.status_code == 200
    assert "Chocolate negro" in response.text
    assert "Salmon" in response.text
```

- [ ] **Step 6: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_antojo_page.py -v`
Expected: FAIL con `404 Not Found`.

- [ ] **Step 7: Añade a `app/main.py`**

```python
@app.get("/antojo")
def antojo_form(request: Request):
    profile = get_user_profile()
    template = templates.get_template("antojo.html")
    return HTMLResponse(
        template.render({"request": request, "profile": profile, "meal_names": MEAL_NAMES, "result": None})
    )


@app.post("/antojo")
def antojo_fit(
    request: Request,
    method: str = Form(...),
    craving_meal_name: str = Form(...),
    craving_food_item: str = Form(...),
    craving_quantity_grams: float = Form(...),
):
    profile = get_user_profile()
    template = templates.get_template("antojo.html")
    if profile is None:
        return HTMLResponse(
            template.render({"request": request, "profile": None, "meal_names": MEAL_NAMES, "result": None})
        )

    target = _current_macro_target(method, profile)
    if target is None:
        return HTMLResponse(
            template.render(
                {
                    "request": request,
                    "profile": profile,
                    "meal_names": MEAL_NAMES,
                    "result": None,
                    "no_target_available": True,
                }
            )
        )
    macro_target, goal = target

    craving_meal = _resolve_meal(craving_food_item, {"food_item": craving_food_item, "quantity_grams": craving_quantity_grams})
    craving_meal["meal_name"] = craving_meal_name
    budget = remaining_budget(macro_target, [craving_meal])

    remaining_names = tuple(name for name in MEAL_NAMES if name != craving_meal_name)
    rest_of_day = generate_day(budget, goal, {}, meal_names=remaining_names)

    all_meals = sorted(
        [craving_meal] + rest_of_day["meals"], key=lambda m: MEAL_NAMES.index(m["meal_name"])
    )
    totals = _day_totals(all_meals)
    result = {
        "meals": all_meals,
        "totals": totals,
        "within_tolerance": within_tolerance(totals, macro_target),
    }

    return HTMLResponse(
        template.render(
            {
                "request": request,
                "profile": profile,
                "meal_names": MEAL_NAMES,
                "result": result,
                "target": macro_target,
            }
        )
    )
```

(Importa `remaining_budget`, `_resolve_meal`, `_day_totals` desde `app.diet_generator` junto al
resto de imports de ese módulo en la cabecera de `app/main.py`. `_resolve_meal` y `_day_totals`
tienen guion bajo — son "privadas" del módulo, pero Python no lo impide; si prefieres no
importar nombres con guion bajo entre módulos, expón wrappers públicos en `app/diet_generator.py`
en su lugar, ej. `resolve_meal = _resolve_meal`.)

- [ ] **Step 8: Crea `app/templates/antojo.html`**

```html
{% extends "base.html" %}
{% block title %}Antojo{% endblock %}
{% block content %}
<h1>Antojo</h1>
{% if not profile %}
<div class="card"><p>Falta completar el <a href="/perfil">perfil</a>.</p></div>
{% else %}
<div class="card">
  <form method="post" action="/antojo">
    <label>Fuente de macros objetivo
      <select name="method" required>
        <option value="formula">Metodo determinista</option>
        <option value="agent">Ultimo resultado de IA guardado</option>
      </select>
    </label>
    <label>Comida a la que corresponde el antojo
      <select name="craving_meal_name" required>
        {% for name in meal_names %}
        <option value="{{ name }}">{{ name | capitalize }}</option>
        {% endfor %}
      </select>
    </label>
    <label>Que te apetece
      <input type="text" name="craving_food_item" required placeholder="ej. Chocolate negro">
    </label>
    <label>Cantidad (g)
      <input type="number" step="0.1" name="craving_quantity_grams" required>
    </label>
    <button type="submit">Encajarlo en el dia</button>
  </form>
</div>

{% if no_target_available %}
<div class="card"><p>No hay ningun objetivo de macros disponible. Ve a <a href="/macros">Macros</a>.</p></div>
{% endif %}

{% if result %}
<div class="card-grid">
  {% for meal in result.meals %}
  <div class="card">
    <h3>{{ meal.meal_name | capitalize }}</h3>
    <hr class="hr-thin">
    <p>{{ meal.food_item }} — {{ meal.quantity_grams }} g</p>
    <div class="macro-row"><span class="label">Kcal</span><span class="value">{{ "%.0f" | format(meal.kcal) }}</span></div>
    <div class="macro-row"><span class="label">Proteina</span><span class="value">{{ "%.1f" | format(meal.protein_g) }} g</span></div>
  </div>
  {% endfor %}
</div>
<div class="card">
  {% if result.within_tolerance %}
  <p><span class="badge good">Dentro de margen (±5%)</span></p>
  {% else %}
  <p><span class="badge bad">Fuera de margen</span></p>
  {% endif %}
</div>
{% endif %}
{% endif %}
{% endblock %}
```

- [ ] **Step 9: Añade el enlace al `<nav>` de `app/templates/base.html`**

```html
<a href="/antojo" {% if request.url.path == '/antojo' %}class="active"{% endif %}>Antojo</a>
```

- [ ] **Step 10: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_antojo_page.py -v`
Expected: PASS

- [ ] **Step 11: Ejecuta toda la suite para verificar que no hay regresiones**

Run: `python -m pytest tests/ -v`
Expected: todos los tests pasan.

- [ ] **Step 12: Verifica visualmente en el navegador**

Run: `docker compose up -d --build`
Abre `http://localhost:8000/antojo`, pide un antojo y confirma que el resto del día se genera
en torno a él. Esto hace una llamada real a la suscripción, hazlo una vez, no en bucle.

- [ ] **Step 13: Commit**

```bash
git add app/diet_generator.py app/main.py app/templates/antojo.html app/templates/base.html tests/test_diet_generator.py tests/test_antojo_page.py
git commit -m "Add craving-fitting that regenerates the rest of the day around a fixed food"
```

---

### Task 7: Corregir una comida del día más reciente cerrado

**Files:**
- Modify: `app/main.py` (rutas `GET`/`POST /corregir`)
- Create: `app/templates/corregir.html`
- Modify: `app/templates/base.html` (enlace "Corregir" en el `<nav>`)
- Test: `tests/test_corregir_page.py`

**Interfaces:**
- Produces: rutas `GET`/`POST /corregir` — opera siempre sobre el `diet_version` más reciente
  (`ORDER BY valid_from DESC LIMIT 1`), no sobre un histórico completo navegable (fuera de
  alcance de esta primera versión).

- [ ] **Step 1: Escribe el test que falla**

`tests/test_corregir_page.py`:
```python
from datetime import date

from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _seed_recent_diet_version():
    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE source_pdf_filename = 'test_corregir')"
            )
            cur.execute("DELETE FROM diet_versions WHERE source_pdf_filename = 'test_corregir'")
            cur.execute(
                "INSERT INTO diet_versions (source_pdf_filename, valid_from, valid_to) "
                "VALUES ('test_corregir', %s, %s) RETURNING id",
                (today, today),
            )
            diet_version_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO diet_meals (diet_version_id, day_label, meal_name, food_item, quantity_grams) "
                "VALUES (%s, 'dia', 'cena', 'Salmon', 150) RETURNING id",
                (diet_version_id,),
            )
            return cur.fetchone()[0]


def test_get_corregir_shows_most_recent_meals():
    _seed_recent_diet_version()
    response = client.get("/corregir")
    assert response.status_code == 200
    assert "Salmon" in response.text


def test_post_corregir_updates_meal():
    meal_id = _seed_recent_diet_version()
    response = client.post(
        f"/corregir/{meal_id}",
        data={"food_item": "Merluza", "quantity_grams": "180"},
    )
    assert response.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT food_item, quantity_grams FROM diet_meals WHERE id = %s", (meal_id,))
            row = cur.fetchone()
    assert row[0] == "Merluza"
    assert float(row[1]) == 180.0
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_corregir_page.py -v`
Expected: FAIL con `404 Not Found`.

- [ ] **Step 3: Añade a `app/main.py`**

```python
from app.compensation import replace_or_clear_after_correction


def get_most_recent_diet_version_meals() -> list[dict] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM diet_versions ORDER BY valid_from DESC, id DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                return None
            diet_version_id = row[0]
            cur.execute(
                "SELECT id, meal_name, food_item, quantity_grams FROM diet_meals "
                "WHERE diet_version_id = %s ORDER BY id",
                (diet_version_id,),
            )
            rows = cur.fetchall()
    return [
        {"id": r[0], "meal_name": r[1], "food_item": r[2], "quantity_grams": float(r[3])}
        for r in rows
    ]


def get_diet_version_totals(diet_version_id: int) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.kcal_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.protein_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.carbs_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.fat_100g), 0)
                FROM diet_meals dm
                LEFT JOIN foods f ON f.id = dm.matched_food_id
                WHERE dm.diet_version_id = %s
                """,
                (diet_version_id,),
            )
            row = cur.fetchone()
    return {
        "kcal": float(row[0]), "protein_g": float(row[1]),
        "carbs_g": float(row[2]), "fat_g": float(row[3]),
    }


@app.get("/corregir")
def corregir_form(request: Request):
    template = templates.get_template("corregir.html")
    return HTMLResponse(
        template.render({"request": request, "meals": get_most_recent_diet_version_meals()})
    )


@app.post("/corregir/{meal_id}")
def corregir_meal(meal_id: int, food_item: str = Form(...), quantity_grams: float = Form(...)):
    match = find_matching_food(food_item)
    matched_food_id = match["id"] if match else None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE diet_meals SET food_item = %s, quantity_grams = %s, matched_food_id = %s "
                "WHERE id = %s RETURNING diet_version_id",
                (food_item, quantity_grams, matched_food_id, meal_id),
            )
            diet_version_id = cur.fetchone()[0]

    profile = get_user_profile()
    if profile is not None:
        target = compute_formula_macro_target(profile)
        real_totals = get_diet_version_totals(diet_version_id)
        replace_or_clear_after_correction(real_totals, target)

    template = templates.get_template("corregir.html")
    return HTMLResponse(
        template.render({"request": None, "meals": get_most_recent_diet_version_meals()})
    )
```

- [ ] **Step 4: Crea `app/templates/corregir.html`**

```html
{% extends "base.html" %}
{% block title %}Corregir{% endblock %}
{% block content %}
<h1>Corregir el dia mas reciente</h1>
{% if not meals %}
<div class="card"><p>No hay ningun dia guardado todavia.</p></div>
{% else %}
<div class="card-grid">
  {% for meal in meals %}
  <div class="card">
    <h3>{{ meal.meal_name | capitalize }}</h3>
    <hr class="hr-thin">
    <form method="post" action="/corregir/{{ meal.id }}">
      <label>Alimento
        <input type="text" name="food_item" value="{{ meal.food_item }}" required>
      </label>
      <label>Cantidad (g)
        <input type="number" step="0.1" name="quantity_grams" value="{{ meal.quantity_grams }}" required>
      </label>
      <button type="submit">Corregir</button>
    </form>
  </div>
  {% endfor %}
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Añade el enlace al `<nav>` de `app/templates/base.html`**

```html
<a href="/corregir" {% if request.url.path == '/corregir' %}class="active"{% endif %}>Corregir</a>
```

- [ ] **Step 6: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_corregir_page.py -v`
Expected: PASS

- [ ] **Step 7: Ejecuta toda la suite del subsistema completo para verificar que no hay regresiones**

Run: `python -m pytest tests/ -v`
Expected: todos los tests pasan (Subsistemas 1-4 completos).

- [ ] **Step 8: Verifica visualmente en el navegador**

Run: `docker compose up -d --build`
Abre `http://localhost:8000/corregir`, corrige una comida de un día reciente, y confirma en
`http://localhost:8000/macros` que si el desvío queda fuera de margen aparece el aviso de
compensación activa. No hace falta ninguna llamada real al Agent SDK para esta verificación.

- [ ] **Step 9: Commit**

```bash
git add app/main.py app/templates/corregir.html app/templates/base.html tests/test_corregir_page.py
git commit -m "Add correction of the most recent closed day's meals, re-triggering compensation"
```

---

## Después de este plan

Con el Subsistema 4 completo, el alcance original de las 4 funcionalidades queda cerrado:
analizar la dieta (Subsistema 1), calcular macros objetivo (Subsistema 2), generar dietas
variadas (Subsistema 3), y compensar excesos/encajar antojos (Subsistema 4). La app cubre el
ciclo completo: perfil → medidas → macros objetivo → generar/registrar comida → corregir
desviaciones → compensar automáticamente los próximos días.
