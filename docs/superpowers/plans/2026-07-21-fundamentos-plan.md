# Subsistema 1: Fundamentos — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir la base de datos (Postgres), el esqueleto web (FastAPI + Jinja2 + HTMX) y los scripts de ingesta única de datos (catálogo de alimentos Mercadona + PDFs históricos de dieta/analíticas) para el programa nutricional personal.

**Architecture:** Docker Compose con dos servicios (`postgres`, `app`) corriendo en el portátil del usuario. FastAPI sirve tanto la API como las páginas Jinja2+HTMX (sin build de Node). Sin ORM: acceso a datos vía `psycopg` directo con SQL parametrizado. La extracción de datos de los PDFs usa la API normal de Claude (`anthropic` SDK, `output_config.format` con JSON schema) — no el Agent SDK.

**Tech Stack:** Python 3.13, FastAPI, psycopg 3, PostgreSQL 16, Jinja2, HTMX (CDN), Chart.js (CDN), anthropic SDK, requests, pytest, Docker Compose.

## Global Constraints

- Python 3.13. Sin ORM — acceso a Postgres vía `psycopg` con SQL parametrizado directo.
- Sin build de Node en ningún punto. HTMX y Chart.js se cargan por `<script src="...">` desde CDN.
- El Agent SDK (`claude-agent-sdk`) NO se usa en este subsistema. Toda llamada a IA aquí es la API normal de Claude (`anthropic` SDK) para extracción de datos estructurados de PDFs.
- Modelo por defecto para llamadas a Claude: `claude-opus-4-8`.
- `requirements.txt` sin pines de versión (proyecto personal de un usuario, sin CI que dependa de reproducibilidad exacta).
- El puerto de Postgres se expone solo en `127.0.0.1` (no accesible desde la red Tailscale); el puerto de la app (8000) sí queda abierto para acceso remoto vía Tailscale.
- Todo el código vive en `D:\homeMario\AgenteNutricional` (git ya inicializado).

---

### Task 1: Scaffolding del proyecto + Docker Compose + endpoint de salud

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Test: `tests/test_main.py`
- Test: `tests/__init__.py`

**Interfaces:**
- Produces: `app.main:app` (instancia de `FastAPI` importable), endpoint `GET /health` → `{"status": "ok"}`.

**Prerrequisito manual (no automatizable desde el agente):** Docker Desktop debe estar instalado en el portátil. Descárgalo de https://www.docker.com/products/docker-desktop/ e instálalo antes de continuar con los pasos de Docker de esta tarea. Verifica con:

```bash
docker --version
docker compose version
```

Expected: ambos comandos devuelven un número de versión (no "command not found").

- [ ] **Step 1: Escribe el test que falla**

`tests/__init__.py`:
```python
```

`tests/test_main.py`:
```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app'` (o similar, porque `app/main.py` no existe todavía).

- [ ] **Step 3: Crea el paquete `app` y la implementación mínima**

`app/__init__.py`:
```python
```

`app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Crea `requirements.txt`**

```
fastapi
uvicorn[standard]
psycopg[binary]
python-dotenv
anthropic
requests
jinja2
python-multipart
pytest
httpx
```

- [ ] **Step 6: Instala las dependencias localmente y vuelve a correr el test**

Run: `pip install -r requirements.txt`
Run: `python -m pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 7: Crea `Dockerfile`**

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 8: Crea `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: nutricion
      POSTGRES_USER: nutricion
      POSTGRES_PASSWORD: nutricion
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"
  app:
    build: .
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_DB: nutricion
      POSTGRES_USER: nutricion
      POSTGRES_PASSWORD: nutricion
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    ports:
      - "8000:8000"
    depends_on:
      - postgres

volumes:
  pgdata:
```

- [ ] **Step 9: Crea `.env.example`**

```
POSTGRES_HOST=localhost
POSTGRES_DB=nutricion
POSTGRES_USER=nutricion
POSTGRES_PASSWORD=nutricion
POSTGRES_PORT=5432
ANTHROPIC_API_KEY=
```

- [ ] **Step 10: Crea `.gitignore`**

```
__pycache__/
*.pyc
.env
.venv/
venv/
pdfs/dietas/*.pdf
pdfs/analiticas/*.pdf
```

- [ ] **Step 11: Levanta los contenedores y verifica el endpoint**

Run: `docker compose up -d --build`
Run: `curl http://localhost:8000/health`
Expected: `{"status":"ok"}`

- [ ] **Step 12: Commit**

```bash
git add Dockerfile docker-compose.yml requirements.txt .env.example .gitignore app tests
git commit -m "Scaffold FastAPI app with Docker Compose and health endpoint"
```

---

### Task 2: Esquema de base de datos

**Files:**
- Create: `db/schema.sql`
- Create: `app/db.py`
- Modify: `docker-compose.yml` (montar `db/schema.sql` en el init de Postgres)
- Test: `tests/test_db_schema.py`

**Interfaces:**
- Consumes: variables de entorno `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`.
- Produces: `app.db.get_connection()` — context manager que entrega una conexión `psycopg.Connection` y hace commit al salir sin error. Tablas Postgres: `foods`, `diet_versions`, `diet_meals`, `body_metrics`.

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
    assert {"foods", "diet_versions", "diet_meals", "body_metrics"} <= tables
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_db_schema.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 3: Crea `app/db.py`**

```python
import os
from contextlib import contextmanager

import psycopg


def _dsn() -> str:
    return (
        f"host={os.environ.get('POSTGRES_HOST', 'localhost')} "
        f"dbname={os.environ.get('POSTGRES_DB', 'nutricion')} "
        f"user={os.environ.get('POSTGRES_USER', 'nutricion')} "
        f"password={os.environ.get('POSTGRES_PASSWORD', 'nutricion')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')}"
    )


@contextmanager
def get_connection():
    conn = psycopg.connect(_dsn())
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Crea `db/schema.sql`**

```sql
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
```

- [ ] **Step 5: Monta el esquema en el init de Postgres**

En `docker-compose.yml`, dentro del servicio `postgres`, añade a `volumes`:

```yaml
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/schema.sql:/docker-entrypoint-initdb.d/schema.sql
```

(Los scripts en `docker-entrypoint-initdb.d` solo se ejecutan la primera vez que el volumen de datos está vacío.)

- [ ] **Step 6: Recrea el contenedor de Postgres desde cero y ejecuta el test**

Run: `docker compose down -v`
Run: `docker compose up -d postgres`
Run: `python -m pytest tests/test_db_schema.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add db/schema.sql app/db.py docker-compose.yml tests/test_db_schema.py
git commit -m "Add Postgres schema and connection helper"
```

---

### Task 3: Sincronización de alimentos desde Mercadona

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/sync_foods.py`
- Test: `tests/test_sync_foods.py`

**Interfaces:**
- Consumes: `app.db.get_connection()`.
- Produces: `scripts.sync_foods.fetch_all_products() -> list[dict]`, `scripts.sync_foods.upsert_foods(products: list[dict]) -> int`.

**Nota de alcance (YAGNI):** no se implementa un parser automático del dump de `datania/mercadona-catalog` como fallback — su formato exacto no está verificado y es un flujo secundario poco probable. Si `mercaapi` falla tras los reintentos, el script lanza un error claro indicando revisar ese repositorio manualmente.

- [ ] **Step 1: Escribe el test que falla**

`scripts/__init__.py`:
```python
```

`tests/test_sync_foods.py`:
```python
from unittest.mock import MagicMock, patch

from app.db import get_connection
from scripts.sync_foods import fetch_all_products, upsert_foods

FAKE_PRODUCT = {
    "id": "test-99999",
    "name": "Producto de prueba",
    "is_food": True,
    "category": {"name": "Categoria de prueba"},
    "nutritional_information": {
        "calories": 100.0,
        "protein": 10.0,
        "total_carbohydrate": 20.0,
        "total_fat": 5.0,
        "dietary_fiber": 2.0,
    },
}


def _fake_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@patch("scripts.sync_foods.requests.get")
def test_fetch_all_products_paginates_until_empty(mock_get):
    mock_get.side_effect = [
        _fake_response([FAKE_PRODUCT]),
        _fake_response([]),
    ]
    products = fetch_all_products()
    assert products == [FAKE_PRODUCT]
    assert mock_get.call_count == 2


def test_upsert_foods_inserts_and_updates_row():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM foods WHERE mercadona_product_id = 'test-99999'")

    count = upsert_foods([FAKE_PRODUCT])
    assert count == 1

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, kcal_100g FROM foods WHERE mercadona_product_id = 'test-99999'"
            )
            row = cur.fetchone()
    assert row[0] == "Producto de prueba"
    assert float(row[1]) == 100.0
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_sync_foods.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'scripts.sync_foods'`.

- [ ] **Step 3: Implementa `scripts/sync_foods.py`**

```python
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402

MERCAAPI_BASE = "https://mercaapi.sgn.space/api/products/"
PAGE_SIZE = 100
MAX_RETRIES = 3


def fetch_all_products() -> list[dict]:
    products: list[dict] = []
    skip = 0
    while True:
        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(
                    MERCAAPI_BASE,
                    params={"limit": PAGE_SIZE, "skip": skip},
                    timeout=10,
                )
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(
                        "No se pudo contactar con mercaapi.sgn.space tras "
                        f"{MAX_RETRIES} intentos. Revisa manualmente el dump "
                        "de https://github.com/datania/mercadona-catalog "
                        "como alternativa."
                    )
                time.sleep(2**attempt)
        page = response.json()
        if not page:
            break
        products.extend(page)
        skip += PAGE_SIZE
    return products


def upsert_foods(products: list[dict]) -> int:
    rows = []
    for product in products:
        if not product.get("is_food"):
            continue
        info = product.get("nutritional_information")
        if not info:
            continue
        rows.append(
            (
                product["id"],
                product["name"],
                product["category"]["name"],
                info["calories"],
                info["protein"],
                info["total_carbohydrate"],
                info["total_fat"],
                info["dietary_fiber"],
            )
        )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO foods (
                    mercadona_product_id, name, category,
                    kcal_100g, protein_100g, carbs_100g, fat_100g, fiber_100g
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (mercadona_product_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    kcal_100g = EXCLUDED.kcal_100g,
                    protein_100g = EXCLUDED.protein_100g,
                    carbs_100g = EXCLUDED.carbs_100g,
                    fat_100g = EXCLUDED.fat_100g,
                    fiber_100g = EXCLUDED.fiber_100g,
                    synced_at = now()
                """,
                rows,
            )
    return len(rows)


if __name__ == "__main__":
    all_products = fetch_all_products()
    inserted = upsert_foods(all_products)
    print(f"Sincronizados {inserted} alimentos.")
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_sync_foods.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/sync_foods.py tests/test_sync_foods.py
git commit -m "Add Mercadona food catalog sync script"
```

---

### Task 4: Ingesta de PDFs de dieta

**Files:**
- Create: `scripts/ingest_diet_pdfs.py`
- Create: `pdfs/dietas/.gitkeep`
- Test: `tests/test_ingest_diet_pdfs.py`

**Interfaces:**
- Consumes: `app.db.get_connection()`, cliente `anthropic.Anthropic`.
- Produces: `scripts.ingest_diet_pdfs.extract_diet(client, pdf_path: Path) -> dict`, `scripts.ingest_diet_pdfs.save_diet(pdf_filename: str, data: dict) -> int` (devuelve `diet_version_id`).

**Nota:** requiere la variable de entorno `ANTHROPIC_API_KEY` (API de pago por token, no la suscripción — esto es extracción de datos con una sola llamada, no un agente).

- [ ] **Step 1: Escribe el test que falla**

`pdfs/dietas/.gitkeep`:
```
```

`tests/test_ingest_diet_pdfs.py`:
```python
import json
from unittest.mock import MagicMock

from app.db import get_connection
from scripts.ingest_diet_pdfs import extract_diet, save_diet


def test_extract_diet_parses_json_response(tmp_path):
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake content")

    expected = {
        "valid_from": "2026-01-01",
        "valid_to": None,
        "meals": [
            {
                "day_label": "lunes",
                "meal_name": "desayuno",
                "food_item": "avena",
                "quantity_grams": 60,
            }
        ],
    }
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(expected)
    fake_response = MagicMock()
    fake_response.content = [text_block]

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    result = extract_diet(fake_client, fake_pdf)
    assert result == expected


def test_save_diet_inserts_version_and_meals():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE source_pdf_filename = 'test_dieta.pdf')"
            )
            cur.execute(
                "DELETE FROM diet_versions WHERE source_pdf_filename = 'test_dieta.pdf'"
            )

    data = {
        "valid_from": "2026-01-01",
        "valid_to": "2026-02-01",
        "meals": [
            {
                "day_label": "lunes",
                "meal_name": "desayuno",
                "food_item": "avena",
                "quantity_grams": 60,
            }
        ],
    }

    diet_version_id = save_diet("test_dieta.pdf", data)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM diet_meals WHERE diet_version_id = %s",
                (diet_version_id,),
            )
            count = cur.fetchone()[0]
    assert count == 1
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_ingest_diet_pdfs.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'scripts.ingest_diet_pdfs'`.

- [ ] **Step 3: Implementa `scripts/ingest_diet_pdfs.py`**

```python
import base64
import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402

PDF_DIR = Path(__file__).resolve().parent.parent / "pdfs" / "dietas"

DIET_SCHEMA = {
    "type": "object",
    "properties": {
        "valid_from": {"type": "string", "format": "date"},
        "valid_to": {
            "anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]
        },
        "meals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day_label": {"type": "string"},
                    "meal_name": {"type": "string"},
                    "food_item": {"type": "string"},
                    "quantity_grams": {"type": "number"},
                },
                "required": [
                    "day_label",
                    "meal_name",
                    "food_item",
                    "quantity_grams",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["valid_from", "valid_to", "meals"],
    "additionalProperties": False,
}


def extract_diet(client: anthropic.Anthropic, pdf_path: Path) -> dict:
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=8000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extrae de este PDF de dieta todas las comidas "
                            "con su cantidad en gramos, agrupadas por dia, "
                            "y el rango de fechas de validez de la dieta. "
                            "Si no se indica fecha de fin, deja valid_to "
                            "como null."
                        ),
                    },
                ],
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": DIET_SCHEMA}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def save_diet(pdf_filename: str, data: dict) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO diet_versions (source_pdf_filename, valid_from, valid_to)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (pdf_filename, data["valid_from"], data["valid_to"]),
            )
            diet_version_id = cur.fetchone()[0]
            cur.executemany(
                """
                INSERT INTO diet_meals
                    (diet_version_id, day_label, meal_name, food_item, quantity_grams)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        diet_version_id,
                        meal["day_label"],
                        meal["meal_name"],
                        meal["food_item"],
                        meal["quantity_grams"],
                    )
                    for meal in data["meals"]
                ],
            )
    return diet_version_id


if __name__ == "__main__":
    client = anthropic.Anthropic()
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        try:
            diet_data = extract_diet(client, pdf_path)
            version_id = save_diet(pdf_path.name, diet_data)
            print(
                f"{pdf_path.name}: version {version_id}, "
                f"{len(diet_data['meals'])} comidas"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR procesando {pdf_path.name}: {exc}")
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_ingest_diet_pdfs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ingest_diet_pdfs.py pdfs/dietas/.gitkeep tests/test_ingest_diet_pdfs.py
git commit -m "Add diet PDF ingestion via Claude structured extraction"
```

---

### Task 5: Ingesta de PDFs de análisis corporal

**Files:**
- Create: `scripts/ingest_body_metrics_pdfs.py`
- Create: `pdfs/analiticas/.gitkeep`
- Test: `tests/test_ingest_body_metrics_pdfs.py`

**Interfaces:**
- Consumes: `app.db.get_connection()`, cliente `anthropic.Anthropic`.
- Produces: `scripts.ingest_body_metrics_pdfs.extract_body_metrics(client, pdf_path: Path) -> dict`, `scripts.ingest_body_metrics_pdfs.save_body_metrics(pdf_filename: str, data: dict) -> int`.

- [ ] **Step 1: Escribe el test que falla**

`pdfs/analiticas/.gitkeep`:
```
```

`tests/test_ingest_body_metrics_pdfs.py`:
```python
import json
from unittest.mock import MagicMock

from app.db import get_connection
from scripts.ingest_body_metrics_pdfs import extract_body_metrics, save_body_metrics


def test_extract_body_metrics_parses_json_response(tmp_path):
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake content")

    expected = {
        "measured_on": "2026-01-01",
        "weight_kg": 80.5,
        "body_fat_pct": 18.2,
        "muscle_mass_kg": 35.0,
    }
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(expected)
    fake_response = MagicMock()
    fake_response.content = [text_block]

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    result = extract_body_metrics(fake_client, fake_pdf)
    assert result == expected


def test_save_body_metrics_inserts_row():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM body_metrics WHERE source_pdf_filename = 'test_analitica.pdf'"
            )

    data = {
        "measured_on": "2026-01-01",
        "weight_kg": 80.5,
        "body_fat_pct": 18.2,
        "muscle_mass_kg": 35.0,
    }

    body_metrics_id = save_body_metrics("test_analitica.pdf", data)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT weight_kg FROM body_metrics WHERE id = %s", (body_metrics_id,)
            )
            row = cur.fetchone()
    assert float(row[0]) == 80.5
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_ingest_body_metrics_pdfs.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'scripts.ingest_body_metrics_pdfs'`.

- [ ] **Step 3: Implementa `scripts/ingest_body_metrics_pdfs.py`**

```python
import base64
import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402

PDF_DIR = Path(__file__).resolve().parent.parent / "pdfs" / "analiticas"

BODY_METRICS_SCHEMA = {
    "type": "object",
    "properties": {
        "measured_on": {"type": "string", "format": "date"},
        "weight_kg": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "body_fat_pct": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "muscle_mass_kg": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    },
    "required": ["measured_on", "weight_kg", "body_fat_pct", "muscle_mass_kg"],
    "additionalProperties": False,
}


def extract_body_metrics(client: anthropic.Anthropic, pdf_path: Path) -> dict:
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extrae de este analisis corporal la fecha de "
                            "la medicion, el peso en kg, el porcentaje de "
                            "grasa corporal y la masa muscular en kg. Si "
                            "un dato no aparece, usa null."
                        ),
                    },
                ],
            }
        ],
        output_config={
            "format": {"type": "json_schema", "schema": BODY_METRICS_SCHEMA}
        },
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def save_body_metrics(pdf_filename: str, data: dict) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO body_metrics
                    (source_pdf_filename, measured_on, weight_kg, body_fat_pct, muscle_mass_kg)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    pdf_filename,
                    data["measured_on"],
                    data["weight_kg"],
                    data["body_fat_pct"],
                    data["muscle_mass_kg"],
                ),
            )
            body_metrics_id = cur.fetchone()[0]
    return body_metrics_id


if __name__ == "__main__":
    client = anthropic.Anthropic()
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        try:
            metrics_data = extract_body_metrics(client, pdf_path)
            metrics_id = save_body_metrics(pdf_path.name, metrics_data)
            print(f"{pdf_path.name}: body_metrics {metrics_id}")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR procesando {pdf_path.name}: {exc}")
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_ingest_body_metrics_pdfs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ingest_body_metrics_pdfs.py pdfs/analiticas/.gitkeep tests/test_ingest_body_metrics_pdfs.py
git commit -m "Add body composition PDF ingestion via Claude structured extraction"
```

---

### Task 6: Enlace de alimentos de las dietas con el catálogo

**Files:**
- Create: `scripts/match_foods.py`
- Test: `tests/test_match_foods.py`

**Interfaces:**
- Consumes: `app.db.get_connection()`, columnas `diet_meals.matched_food_id`, `diet_meals.food_item`, `foods.name`.
- Produces: `scripts.match_foods.match_unlinked_meals() -> int` (número de comidas enlazadas en esta ejecución).

**Nota (best-effort, según la spec):** el emparejamiento es un `ILIKE` de substring por nombre — no bloquea la ingesta si no hay match, y los casos sin enlazar quedan para revisión manual.

- [ ] **Step 1: Escribe el test que falla**

`tests/test_match_foods.py`:
```python
from app.db import get_connection
from scripts.match_foods import match_unlinked_meals


def test_match_unlinked_meals_links_by_substring():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE source_pdf_filename = 'test_match.pdf')"
            )
            cur.execute(
                "DELETE FROM diet_versions WHERE source_pdf_filename = 'test_match.pdf'"
            )
            cur.execute("DELETE FROM foods WHERE mercadona_product_id = 'test-avena'")

            cur.execute(
                """
                INSERT INTO foods
                    (mercadona_product_id, name, category, kcal_100g, protein_100g, carbs_100g, fat_100g)
                VALUES ('test-avena', 'Avena integral', 'Cereales', 350, 13, 60, 7)
                """
            )
            cur.execute(
                """
                INSERT INTO diet_versions (source_pdf_filename, valid_from)
                VALUES ('test_match.pdf', '2026-01-01')
                RETURNING id
                """
            )
            diet_version_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO diet_meals
                    (diet_version_id, day_label, meal_name, food_item, quantity_grams)
                VALUES (%s, 'lunes', 'desayuno', 'avena integral', 50)
                RETURNING id
                """,
                (diet_version_id,),
            )
            meal_id = cur.fetchone()[0]

    matched_count = match_unlinked_meals()
    assert matched_count >= 1

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT matched_food_id FROM diet_meals WHERE id = %s", (meal_id,)
            )
            matched_food_id = cur.fetchone()[0]
    assert matched_food_id is not None
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_match_foods.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'scripts.match_foods'`.

- [ ] **Step 3: Implementa `scripts/match_foods.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402


def match_unlinked_meals() -> int:
    matched = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, food_item FROM diet_meals WHERE matched_food_id IS NULL"
            )
            unmatched = cur.fetchall()

            for meal_id, food_item in unmatched:
                cur.execute(
                    """
                    SELECT id FROM foods
                    WHERE name ILIKE %s
                    ORDER BY length(name) ASC
                    LIMIT 1
                    """,
                    (f"%{food_item}%",),
                )
                row = cur.fetchone()
                if row is None:
                    continue
                cur.execute(
                    "UPDATE diet_meals SET matched_food_id = %s WHERE id = %s",
                    (row[0], meal_id),
                )
                matched += 1
    return matched


if __name__ == "__main__":
    linked = match_unlinked_meals()
    print(f"Enlazados {linked} alimentos.")
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_match_foods.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/match_foods.py tests/test_match_foods.py
git commit -m "Add best-effort food matching for diet meals"
```

---

### Task 7: Dashboard de evolución

**Files:**
- Create: `app/templates/base.html`
- Create: `app/templates/dashboard.html`
- Modify: `app/main.py` (añadir ruta `GET /`, `Jinja2Templates`, funciones de agregación)
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `app.db.get_connection()`, tablas `body_metrics`, `diet_versions`, `diet_meals`, `foods`.
- Produces: ruta `GET /` que renderiza `dashboard.html` con 4 gráficos (peso, grasa corporal, macros en gramos por versión de dieta, kcal por versión de dieta) — un eje por gráfico, sin ejes duplos.

**Notas de diseño (skill dataviz):** peso y grasa corporal son magnitudes de escala distinta → dos gráficos de línea separados, no uno con doble eje. Macros en gramos → barras agrupadas categóricas (proteína/carbos/grasa, colores fijos de paleta validada, slots 1-2-3). Kcal → barra de una sola serie (magnitud). Paleta y specs de marca (2px de grosor de línea, radio de punto 4px, barras con `borderRadius: 4`) tomados de la paleta de referencia validada de la skill `dataviz`.

- [ ] **Step 1: Escribe el test que falla**

`tests/test_dashboard.py`:
```python
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app


def _seed_dashboard_data():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM body_metrics WHERE source_pdf_filename = 'test_dashboard.pdf'"
            )
            cur.execute(
                """
                INSERT INTO body_metrics
                    (source_pdf_filename, measured_on, weight_kg, body_fat_pct)
                VALUES ('test_dashboard.pdf', '2026-01-01', 80.0, 20.0)
                """
            )


def test_dashboard_renders_with_data():
    _seed_dashboard_data()
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "chart-weight" in response.text
    assert "chart-bodyfat" in response.text
    assert "chart-macros" in response.text
    assert "chart-kcal" in response.text
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_dashboard.py -v`
Expected: FAIL con `404 Not Found` en `GET /` (la ruta todavía no existe) o `TemplateNotFound`.

- [ ] **Step 3: Modifica `app/main.py`**

```python
import json

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from app.db import get_connection

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


@app.get("/health")
def health():
    return {"status": "ok"}


def get_body_metrics_series() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT measured_on, weight_kg, body_fat_pct "
                "FROM body_metrics ORDER BY measured_on"
            )
            rows = cur.fetchall()
    return [
        {
            "date": row[0].isoformat(),
            "weight_kg": float(row[1]) if row[1] is not None else None,
            "body_fat_pct": float(row[2]) if row[2] is not None else None,
        }
        for row in rows
    ]


def get_diet_macros_series() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dv.valid_from,
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.kcal_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.protein_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.carbs_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.fat_100g), 0)
                FROM diet_versions dv
                LEFT JOIN diet_meals dm ON dm.diet_version_id = dv.id
                LEFT JOIN foods f ON f.id = dm.matched_food_id
                GROUP BY dv.id, dv.valid_from
                ORDER BY dv.valid_from
                """
            )
            rows = cur.fetchall()
    return [
        {
            "valid_from": row[0].isoformat(),
            "kcal": float(row[1]),
            "protein_g": float(row[2]),
            "carbs_g": float(row[3]),
            "fat_g": float(row[4]),
        }
        for row in rows
    ]


@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "body_metrics_json": json.dumps(get_body_metrics_series()),
            "diet_macros_json": json.dumps(get_diet_macros_series()),
        },
    )
```

- [ ] **Step 4: Crea `app/templates/base.html`**

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>{% block title %}Nutricion{% endblock %}</title>
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4"></script>
</head>
<body>
  {% block content %}{% endblock %}
</body>
</html>
```

- [ ] **Step 5: Crea `app/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}Panel de evolucion{% endblock %}
{% block content %}
<style>
  .viz-root {
    color-scheme: light;
    --surface-1: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #898781;
    --series-1: #2a78d6;
    --series-2: #eb6834;
    --series-3: #1baf7a;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) .viz-root {
      color-scheme: dark;
      --surface-1: #1a1a19;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #898781;
      --series-1: #3987e5;
      --series-2: #d95926;
      --series-3: #199e70;
    }
  }
  :root[data-theme="dark"] .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #898781;
    --series-1: #3987e5;
    --series-2: #d95926;
    --series-3: #199e70;
  }
  .viz-root {
    background: var(--surface-1);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 1.5rem;
  }
  .chart-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1.5rem;
  }
  .chart-card {
    background: var(--surface-1);
    border: 1px solid rgba(11, 11, 11, 0.10);
    border-radius: 8px;
    padding: 1rem;
  }
  .chart-card h2 {
    color: var(--text-secondary);
    font-size: 0.95rem;
    margin: 0 0 0.75rem;
  }
</style>
<div class="viz-root">
  <h1>Evolucion</h1>
  <div class="chart-grid">
    <div class="chart-card">
      <h2>Peso (kg)</h2>
      <canvas id="chart-weight"></canvas>
    </div>
    <div class="chart-card">
      <h2>Grasa corporal (%)</h2>
      <canvas id="chart-bodyfat"></canvas>
    </div>
    <div class="chart-card">
      <h2>Macros por version de dieta (g)</h2>
      <canvas id="chart-macros"></canvas>
    </div>
    <div class="chart-card">
      <h2>Calorias por version de dieta (kcal)</h2>
      <canvas id="chart-kcal"></canvas>
    </div>
  </div>
</div>
<script>
  const bodyMetrics = {{ body_metrics_json | safe }};
  const dietMacros = {{ diet_macros_json | safe }};
  const root = document.querySelector(".viz-root");
  const style = getComputedStyle(root);
  const series1 = style.getPropertyValue("--series-1").trim();
  const series2 = style.getPropertyValue("--series-2").trim();
  const series3 = style.getPropertyValue("--series-3").trim();
  const gridColor = style.getPropertyValue("--muted").trim();

  new Chart(document.getElementById("chart-weight"), {
    type: "line",
    data: {
      labels: bodyMetrics.map((m) => m.date),
      datasets: [
        {
          label: "Peso (kg)",
          data: bodyMetrics.map((m) => m.weight_kg),
          borderColor: series1,
          backgroundColor: series1,
          borderWidth: 2,
          pointRadius: 4,
          tension: 0.2,
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { x: { grid: { color: "transparent" } }, y: { grid: { color: gridColor } } },
    },
  });

  new Chart(document.getElementById("chart-bodyfat"), {
    type: "line",
    data: {
      labels: bodyMetrics.map((m) => m.date),
      datasets: [
        {
          label: "Grasa corporal (%)",
          data: bodyMetrics.map((m) => m.body_fat_pct),
          borderColor: series2,
          backgroundColor: series2,
          borderWidth: 2,
          pointRadius: 4,
          tension: 0.2,
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { x: { grid: { color: "transparent" } }, y: { grid: { color: gridColor } } },
    },
  });

  new Chart(document.getElementById("chart-macros"), {
    type: "bar",
    data: {
      labels: dietMacros.map((d) => d.valid_from),
      datasets: [
        { label: "Proteina (g)", data: dietMacros.map((d) => d.protein_g), backgroundColor: series1, borderRadius: 4 },
        { label: "Carbohidratos (g)", data: dietMacros.map((d) => d.carbs_g), backgroundColor: series2, borderRadius: 4 },
        { label: "Grasa (g)", data: dietMacros.map((d) => d.fat_g), backgroundColor: series3, borderRadius: 4 },
      ],
    },
    options: {
      plugins: { legend: { display: true } },
      scales: { x: { grid: { color: "transparent" } }, y: { grid: { color: gridColor } } },
    },
  });

  new Chart(document.getElementById("chart-kcal"), {
    type: "bar",
    data: {
      labels: dietMacros.map((d) => d.valid_from),
      datasets: [
        { label: "Kcal", data: dietMacros.map((d) => d.kcal), backgroundColor: series1, borderRadius: 4 },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { x: { grid: { color: "transparent" } }, y: { grid: { color: gridColor } } },
    },
  });
</script>
{% endblock %}
```

- [ ] **Step 6: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_dashboard.py -v`
Expected: PASS

- [ ] **Step 7: Verifica visualmente en el navegador**

Run: `docker compose up -d --build`
Abre `http://localhost:8000/` en el navegador.
Expected: página con 4 tarjetas de gráfico, sin errores en la consola del navegador.

- [ ] **Step 8: Commit**

```bash
git add app/main.py app/templates tests/test_dashboard.py
git commit -m "Add evolution dashboard with body metrics and diet macros charts"
```

---

## Después de este plan

Con el Subsistema 1 completo: coloca tus PDFs de dietas en `pdfs/dietas/` y los de analíticas en `pdfs/analiticas/`, exporta `ANTHROPIC_API_KEY`, y ejecuta en orden: `python scripts/sync_foods.py`, `python scripts/ingest_diet_pdfs.py`, `python scripts/ingest_body_metrics_pdfs.py`, `python scripts/match_foods.py`. Luego abre el dashboard en `http://localhost:8000/`. El Subsistema 2 (calculadora de macros objetivo) partirá de estos datos.
