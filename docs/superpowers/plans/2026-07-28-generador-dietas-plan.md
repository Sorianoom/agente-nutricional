# Subsistema 3: Generador de dietas variadas — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar este plan tarea por tarea. Los pasos usan sintaxis de checkbox (`- [ ]`) para seguimiento.

**Goal:** Generar, día a día, una propuesta de dieta variada (desayuno/comida/merienda/cena) que cuadre con los macros objetivo dentro de un ±5%, con directrices opcionales por comida, regeneración de una sola comida, y un botón explícito para guardarla como comida real en el histórico. Además, un sistema de diseño compartido cuidado para toda la app (hasta ahora sin CSS salvo el dashboard).

**Architecture:** Mismo stack que los Subsistemas 1-2 — FastAPI + Jinja2/HTMX, Postgres (psycopg directo, sin ORM), Docker Compose (con el CLI de Claude Code ya instalado desde el Subsistema 2). El motor de generación es el Claude Agent SDK con el patrón ya validado (`setting_sources=[]`, `cwd` propio, `output_format` JSON schema, `anyio.run()`). Sin estado en servidor: el "día actual" viaja en la propia página como campos ocultos de formulario.

**Tech Stack:** Python 3.13, FastAPI, psycopg 3, PostgreSQL 16, Jinja2, HTMX (CDN), Chart.js (CDN), claude-agent-sdk, anyio, pytest, Google Fonts (CDN, Barlow + Barlow Condensed).

## Global Constraints

- Sin ORM. Sin build de Node. Fuentes vía Google Fonts CDN (esto NO es un Artifact, no aplican las restricciones de CSP de Artifacts — un `<link>` normal a Google Fonts funciona igual que ya funcionan los `<script src="...">` de HTMX/Chart.js).
- Todo uso de Claude va vía Claude Agent SDK con la suscripción — nunca API de pago.
- El cálculo con IA (macros objetivo del Subsistema 2) y la generación de dietas de este subsistema nunca se disparan automáticamente — solo por acción explícita del usuario.
- ±5% de margen de tolerancia en las 4 magnitudes (kcal, proteína, carbos, grasa), con reintento interno (máx. 5 intentos) antes de rendirse. Nunca se puede guardar un día fuera de margen, ni desde el cliente ni si la petición llega igual al backend.
- La dieta generada no se persiste hasta que el usuario pulsa explícitamente "Guardar este día como comido".
- Todo el código vive en `D:\homeMario\AgenteNutricional`.

---

### Task 1: Sistema de diseño compartido + retrofit de páginas existentes

**Files:**
- Modify: `app/templates/base.html` (tokens de color/tipografía, barra de navegación, wrapper `.page`)
- Modify: `app/templates/dashboard.html` (usar las clases compartidas en vez de su propio `<style>` con tokens duplicados)
- Modify: `app/templates/perfil.html`, `app/templates/medidas.html`, `app/templates/macros.html`, `app/templates/_agent_result.html` (envolver en `.card`, usar `.macro-row` para las cifras)
- Test: ninguno nuevo — este task NO debe romper ningún test existente (`tests/test_dashboard.py`, `tests/test_perfil.py`, `tests/test_medidas.py`, `tests/test_macros_page.py`, `tests/test_agent_macros.py`)

**Contexto de diseño (ya acordado con el usuario, no lo reinventes):** concepto "etiqueta nutricional, elevada" — fondo cálido tipo papel, tinta cálida casi negra, un dorado mostaza como acento de interacción (distinto de los azules/naranjas/verdes que ya usan las gráficas), verde/rojo semánticos para estados de margen, Barlow Condensed en negrita para títulos, Barlow normal para el resto, cifras con `tabular-nums`. Sin selector de tema manual — solo `prefers-color-scheme` (el usuario no pidió un toggle, no lo añadas).

**Interfaces:**
- Produces: clases CSS reutilizables (`.nav`, `.page`, `.card`, `.card-grid`, `.hr-thin`, `.macro-row`, `.badge.good`/`.badge.bad`, estilos de elemento para `form`/`label`/`input`/`select`/`button`/`table`) definidas una sola vez en `base.html`, usadas por todas las páginas.

- [x] **Step 1: Verifica que la suite completa pasa ANTES de tocar nada (línea base)**

Run: `python -m pytest tests/test_dashboard.py tests/test_perfil.py tests/test_medidas.py tests/test_macros_page.py tests/test_agent_macros.py -v`
Expected: todos PASS (línea base antes del retrofit visual).

- [x] **Step 2: Reescribe `app/templates/base.html`**

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Nutricion{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4"></script>
  <style>
    :root {
      --surface-page: #f7f3ea;
      --surface-card: #fffdf7;
      --ink: #1a1712;
      --ink-secondary: #5c5548;
      --border: #dcd4c2;
      --accent: #a8760f;
      --accent-ink: #fffdf7;
      --good: #2f8f5b;
      --bad: #c23b30;
      --series-1: #2a78d6;
      --series-2: #eb6834;
      --series-3: #1baf7a;
      color-scheme: light;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --surface-page: #17140f;
        --surface-card: #211d16;
        --ink: #f2ede0;
        --ink-secondary: #b8ae98;
        --border: #3a3427;
        --accent: #d9a441;
        --accent-ink: #17140f;
        --good: #4caf7d;
        --bad: #e2564a;
        --series-1: #3987e5;
        --series-2: #d95926;
        --series-3: #199e70;
        color-scheme: dark;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--surface-page);
      color: var(--ink);
      font-family: "Barlow", system-ui, -apple-system, "Segoe UI", sans-serif;
      font-size: 16px;
      line-height: 1.5;
    }
    h1, h2, h3 {
      font-family: "Barlow Condensed", system-ui, sans-serif;
      font-weight: 700;
      letter-spacing: 0.01em;
      text-wrap: balance;
      margin: 0 0 0.5rem;
    }
    h1 { font-size: 2rem; }
    h2 { font-size: 1.25rem; color: var(--ink-secondary); }
    a { color: var(--accent); }
    .nav {
      display: flex;
      gap: 1.5rem;
      align-items: center;
      padding: 1rem 1.5rem;
      border-bottom: 1px solid var(--border);
      background: var(--surface-card);
    }
    .nav a {
      color: var(--ink-secondary);
      text-decoration: none;
      font-weight: 600;
      font-size: 0.95rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .nav a:hover, .nav a:focus-visible { color: var(--accent); }
    .nav a.active {
      color: var(--ink);
      border-bottom: 2px solid var(--accent);
      padding-bottom: 0.2rem;
    }
    .page {
      max-width: 960px;
      margin: 0 auto;
      padding: 2rem 1.5rem 4rem;
    }
    .card {
      background: var(--surface-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 1.5rem;
    }
    .card-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1.5rem;
    }
    .hr-thin { border: none; border-top: 1px solid var(--border); margin: 0.75rem 0; }
    .macro-row {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      font-variant-numeric: tabular-nums;
      padding: 0.35rem 0;
    }
    .macro-row .label { color: var(--ink-secondary); }
    .macro-row .value { font-weight: 600; }
    form { display: flex; flex-direction: column; gap: 1rem; max-width: 420px; }
    label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.9rem; color: var(--ink-secondary); }
    input, select, textarea {
      font: inherit;
      padding: 0.5rem 0.65rem;
      border: 1px solid var(--border);
      border-radius: 4px;
      background: var(--surface-page);
      color: var(--ink);
    }
    input:focus-visible, select:focus-visible, textarea:focus-visible, button:focus-visible, a:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }
    button, .btn {
      font: inherit;
      font-weight: 600;
      border: none;
      border-radius: 4px;
      padding: 0.6rem 1.1rem;
      background: var(--accent);
      color: var(--accent-ink);
      cursor: pointer;
      width: fit-content;
    }
    button:hover, .btn:hover { filter: brightness(1.08); }
    button:disabled, .btn:disabled { opacity: 0.5; cursor: not-allowed; filter: none; }
    button.secondary, .btn.secondary { background: transparent; color: var(--ink); border: 1px solid var(--border); }
    table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
    th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
    th { color: var(--ink-secondary); font-weight: 600; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.03em; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.2rem 0.6rem;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
    }
    .badge.good { background: color-mix(in srgb, var(--good) 18%, transparent); color: var(--good); }
    .badge.bad { background: color-mix(in srgb, var(--bad) 18%, transparent); color: var(--bad); }
    .htmx-indicator { display: none; color: var(--ink-secondary); font-size: 0.85rem; }
    .htmx-request .htmx-indicator { display: inline; }
  </style>
</head>
<body>
  <nav class="nav">
    <a href="/" {% if request.url.path == '/' %}class="active"{% endif %}>Dashboard</a>
    <a href="/perfil" {% if request.url.path == '/perfil' %}class="active"{% endif %}>Perfil</a>
    <a href="/medidas" {% if request.url.path == '/medidas' %}class="active"{% endif %}>Medidas</a>
    <a href="/macros" {% if request.url.path == '/macros' %}class="active"{% endif %}>Macros</a>
  </nav>
  <main class="page">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

(El enlace "Generar dieta" se añade al `<nav>` en la Tarea 4, cuando la ruta ya exista — no lo añadas todavía, sería un enlace muerto.)

- [x] **Step 3: Reescribe `app/templates/dashboard.html`** (quita su `<style>` propio, usa las clases compartidas y lee los tokens de `:root` en vez de `.viz-root`)

```html
{% extends "base.html" %}
{% block title %}Panel de evolucion{% endblock %}
{% block content %}
<h1>Evolucion</h1>
<div class="card-grid">
  <div class="card">
    <h2>Peso (kg)</h2>
    <canvas id="chart-weight"></canvas>
  </div>
  <div class="card">
    <h2>Grasa corporal (%)</h2>
    <canvas id="chart-bodyfat"></canvas>
  </div>
  <div class="card">
    <h2>Macros por version de dieta (g)</h2>
    <canvas id="chart-macros"></canvas>
  </div>
  <div class="card">
    <h2>Calorias por version de dieta (kcal)</h2>
    <canvas id="chart-kcal"></canvas>
  </div>
</div>
<script>
  const bodyMetrics = {{ body_metrics_json | safe }};
  const dietMacros = {{ diet_macros_json | safe }};
  const style = getComputedStyle(document.documentElement);
  const series1 = style.getPropertyValue("--series-1").trim();
  const series2 = style.getPropertyValue("--series-2").trim();
  const series3 = style.getPropertyValue("--series-3").trim();
  const gridColor = style.getPropertyValue("--border").trim();

  new Chart(document.getElementById("chart-weight"), {
    type: "line",
    data: {
      labels: bodyMetrics.map((m) => m.date),
      datasets: [
        { label: "Peso (kg)", data: bodyMetrics.map((m) => m.weight_kg), borderColor: series1, backgroundColor: series1, borderWidth: 2, pointRadius: 4, tension: 0.2 },
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
        { label: "Grasa corporal (%)", data: bodyMetrics.map((m) => m.body_fat_pct), borderColor: series2, backgroundColor: series2, borderWidth: 2, pointRadius: 4, tension: 0.2 },
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
      datasets: [{ label: "Kcal", data: dietMacros.map((d) => d.kcal), backgroundColor: series1, borderRadius: 4 }],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { x: { grid: { color: "transparent" } }, y: { grid: { color: gridColor } } },
    },
  });
</script>
{% endblock %}
```

- [x] **Step 4: Reescribe `app/templates/perfil.html`** (mismo formulario, envuelto en una tarjeta)

```html
{% extends "base.html" %}
{% block title %}Perfil{% endblock %}
{% block content %}
<h1>Perfil</h1>
<div class="card">
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
</div>
{% endblock %}
```

- [x] **Step 5: Reescribe `app/templates/medidas.html`** (mismo formulario y tabla, cada uno en su tarjeta)

```html
{% extends "base.html" %}
{% block title %}Medidas{% endblock %}
{% block content %}
<h1>Registrar medida del gimnasio</h1>
<div class="card">
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
</div>

<div class="card">
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
</div>
{% endblock %}
```

- [x] **Step 6: Reescribe `app/templates/macros.html`** (mantén el `id="formula-result"` y el texto "Falta completar el perfil" — los tests dependen de ellos)

```html
{% extends "base.html" %}
{% block title %}Macros objetivo{% endblock %}
{% block content %}
<h1>Macros objetivo</h1>
{% if not profile %}
<div class="card">
  <p>Falta completar el <a href="/perfil">perfil</a> antes de calcular macros.</p>
</div>
{% else %}
<div class="card-grid">
  <div class="card" id="formula-result">
    <h2>Metodo determinista ({{ formula.method_label }})</h2>
    <hr class="hr-thin">
    <div class="macro-row"><span class="label">Kcal</span><span class="value">{{ formula.kcal }}</span></div>
    <div class="macro-row"><span class="label">Proteina</span><span class="value">{{ formula.protein_g }} g</span></div>
    <div class="macro-row"><span class="label">Carbohidratos</span><span class="value">{{ formula.carbs_g }} g</span></div>
    <div class="macro-row"><span class="label">Grasa</span><span class="value">{{ formula.fat_g }} g</span></div>
  </div>
  <div class="card">
    <h2>Metodo IA (Claude Agent SDK)</h2>
    <hr class="hr-thin">
    {% include "_agent_result.html" %}
  </div>
</div>
{% endif %}
{% endblock %}
```

- [x] **Step 7: Reescribe `app/templates/_agent_result.html`** (mantén `{{ agent.explanation }}` tal cual — el test del botón busca ese texto)

```html
<div id="agent-result">
  {% if agent %}
  <div class="macro-row"><span class="label">Kcal</span><span class="value">{{ agent.kcal }}</span></div>
  <div class="macro-row"><span class="label">Proteina</span><span class="value">{{ agent.protein_g }} g</span></div>
  <div class="macro-row"><span class="label">Carbohidratos</span><span class="value">{{ agent.carbs_g }} g</span></div>
  <div class="macro-row"><span class="label">Grasa</span><span class="value">{{ agent.fat_g }} g</span></div>
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

- [x] **Step 8: Ejecuta la suite completa para verificar que nada se rompió**

Run: `python -m pytest tests/test_dashboard.py tests/test_perfil.py tests/test_medidas.py tests/test_macros_page.py tests/test_agent_macros.py -v`
Expected: los mismos tests que pasaban en el Step 1 siguen pasando, ahora con el nuevo diseño.

- [x] **Step 9: Verifica visualmente en el navegador**

Run: `docker compose up -d --build`
Abre `http://localhost:8000/`, `/perfil`, `/medidas`, `/macros`. Confirma que se ve el nuevo diseño (fondo papel, tipografía Barlow/Barlow Condensed, tarjetas, acento dorado) y que no hay errores en la consola.

- [x] **Step 10: Commit**

```bash
git add app/templates
git commit -m "Add shared design system (warm nutrition-label look) across all pages"
```

---

### Task 2: Emparejamiento de alimentos reutilizable

**Files:**
- Create: `app/food_matching.py`
- Modify: `scripts/match_foods.py` (refactor para reutilizar la función compartida, sin cambiar su comportamiento)
- Test: `tests/test_food_matching.py`

**Interfaces:**
- Produces: `app.food_matching.find_matching_food_with_cursor(cur, name: str) -> dict | None`, `app.food_matching.find_matching_food(name: str) -> dict | None` (abre su propia conexión, para llamadas puntuales fuera de un bucle).
- Consumes (sin cambios): `app.db.get_connection()`.

**Importante — no degradar el rendimiento de `match_unlinked_meals`:** esa función procesa potencialmente cientos de filas en un bucle dentro de una única conexión/transacción. Refactorízala para que siga abriendo **una sola conexión** para todo el bucle y delegue solo la consulta SQL de similitud a `find_matching_food_with_cursor(cur, ...)` — NO la cambies para que abra una conexión nueva por fila (en este entorno cada conexión a Postgres puede tardar bastante, ver `tests/conftest.py` y las notas de entornos anteriores).

- [ ] **Step 1: Escribe el test que falla**

`tests/test_food_matching.py`:
```python
from app.db import get_connection
from app.food_matching import find_matching_food


def test_find_matching_food_returns_nutritional_data_above_threshold():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM foods WHERE mercadona_product_id = 'test-avena-fm'")
            cur.execute(
                """
                INSERT INTO foods
                    (mercadona_product_id, name, category, kcal_100g, protein_100g, carbs_100g, fat_100g)
                VALUES ('test-avena-fm', 'Avena integral', 'Cereales', 350, 13, 60, 7)
                """
            )

    match = find_matching_food("avena integral")
    assert match is not None
    assert match["kcal_100g"] == 350.0
    assert match["protein_100g"] == 13.0


def test_find_matching_food_returns_none_below_threshold():
    match = find_matching_food("xyzxyzxyz alimento inexistente 12345")
    assert match is None
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_food_matching.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.food_matching'`.

- [ ] **Step 3: Implementa `app/food_matching.py`**

```python
SIMILARITY_THRESHOLD = 0.3


def find_matching_food_with_cursor(cur, name: str) -> dict | None:
    cur.execute(
        """
        SELECT id, name, kcal_100g, protein_100g, carbs_100g, fat_100g
        FROM foods
        WHERE similarity(name, %s) > %s
        ORDER BY similarity(name, %s) DESC
        LIMIT 1
        """,
        (name, SIMILARITY_THRESHOLD, name),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "kcal_100g": float(row[2] or 0),
        "protein_100g": float(row[3] or 0),
        "carbs_100g": float(row[4] or 0),
        "fat_100g": float(row[5] or 0),
    }


def find_matching_food(name: str) -> dict | None:
    from app.db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            return find_matching_food_with_cursor(cur, name)
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_food_matching.py -v`
Expected: PASS

- [ ] **Step 5: Refactoriza `scripts/match_foods.py` para reutilizar la función compartida**

```python
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402
from app.food_matching import find_matching_food_with_cursor  # noqa: E402


def _normalize(food_item: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", food_item).strip()


def match_unlinked_meals() -> int:
    matched = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, food_item FROM diet_meals WHERE matched_food_id IS NULL"
            )
            unmatched = cur.fetchall()

            for meal_id, food_item in unmatched:
                search_term = _normalize(food_item)
                match = find_matching_food_with_cursor(cur, search_term)
                if match is None:
                    continue
                cur.execute(
                    "UPDATE diet_meals SET matched_food_id = %s WHERE id = %s",
                    (match["id"], meal_id),
                )
                matched += 1
    return matched


if __name__ == "__main__":
    linked = match_unlinked_meals()
    print(f"Enlazados {linked} alimentos.")
```

- [ ] **Step 6: Ejecuta los tests existentes de `match_foods.py` para confirmar que el refactor no cambió el comportamiento**

Run: `python -m pytest tests/test_match_foods.py tests/test_food_matching.py -v`
Expected: PASS (los mismos tests que ya existían siguen pasando tal cual).

- [ ] **Step 7: Commit**

```bash
git add app/food_matching.py scripts/match_foods.py tests/test_food_matching.py
git commit -m "Extract reusable food-matching function shared by match_foods.py and the diet generator"
```

---

### Task 3: Funciones puras — margen de tolerancia y presupuesto restante

**Files:**
- Create: `app/diet_generator.py`
- Test: `tests/test_diet_generator.py`

**Interfaces:**
- Produces: `app.diet_generator.within_tolerance(real: dict, target: dict, pct: float = 0.05) -> bool`, `app.diet_generator.remaining_budget(target: dict, fixed_meals: list[dict]) -> dict`, `app.diet_generator.MACRO_KEYS`, `app.diet_generator.MEAL_NAMES`, `app.diet_generator.EXCLUDED_FOODS`.

Sin dependencias de base de datos ni del Agent SDK todavía — solo lógica pura, con datos sintéticos en los tests.

- [ ] **Step 1: Escribe el test que falla**

`tests/test_diet_generator.py`:
```python
from app.diet_generator import remaining_budget, within_tolerance

TARGET = {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0}


def test_within_tolerance_true_when_exact_match():
    assert within_tolerance(TARGET, TARGET) is True


def test_within_tolerance_true_at_edge_of_five_percent():
    real = {k: v * 1.05 for k, v in TARGET.items()}
    assert within_tolerance(real, TARGET, pct=0.05) is True


def test_within_tolerance_false_when_one_macro_exceeds_margin():
    real = dict(TARGET)
    real["protein_g"] = TARGET["protein_g"] * 1.20
    assert within_tolerance(real, TARGET, pct=0.05) is False


def test_within_tolerance_false_when_kcal_off():
    real = dict(TARGET)
    real["kcal"] = TARGET["kcal"] * 0.5
    assert within_tolerance(real, TARGET, pct=0.05) is False


def test_remaining_budget_subtracts_fixed_meals():
    fixed_meals = [
        {"kcal": 500.0, "protein_g": 40.0, "carbs_g": 50.0, "fat_g": 15.0},
        {"kcal": 700.0, "protein_g": 50.0, "carbs_g": 70.0, "fat_g": 20.0},
    ]
    budget = remaining_budget(TARGET, fixed_meals)
    assert budget == {"kcal": 800.0, "protein_g": 60.0, "carbs_g": 80.0, "fat_g": 25.0}


def test_remaining_budget_with_no_fixed_meals_equals_target():
    assert remaining_budget(TARGET, []) == TARGET
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_diet_generator.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.diet_generator'`.

- [ ] **Step 3: Implementa las funciones puras en `app/diet_generator.py`**

```python
MACRO_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g")
MEAL_NAMES = ("desayuno", "comida", "merienda", "cena")

# Misma lista que se excluyo a mano del historico en el Subsistema 1.
EXCLUDED_FOODS = ("brocoli", "vinagre", "col lombarda", "calabacin")

MAX_ATTEMPTS = 5


def within_tolerance(real: dict, target: dict, pct: float = 0.05) -> bool:
    for key in MACRO_KEYS:
        target_value = target[key]
        if target_value == 0:
            if real[key] != 0:
                return False
            continue
        deviation = abs(real[key] - target_value) / target_value
        if deviation > pct:
            return False
    return True


def remaining_budget(target: dict, fixed_meals: list) -> dict:
    consumed = {key: sum(meal[key] for meal in fixed_meals) for key in MACRO_KEYS}
    return {key: target[key] - consumed[key] for key in MACRO_KEYS}
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_diet_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/diet_generator.py tests/test_diet_generator.py
git commit -m "Add tolerance check and remaining-budget pure functions for diet generation"
```

---

### Task 4: Generación del día completo vía Agent SDK + página `/generar-dieta`

**Files:**
- Modify: `app/diet_generator.py` (añadir `_resolve_meal`, `_day_totals`, `generate_day`, llamada al Agent SDK)
- Modify: `app/main.py` (rutas `GET`/`POST /generar-dieta`)
- Create: `app/templates/generar_dieta.html`, `app/templates/_meal_card.html`
- Modify: `app/templates/base.html` (añadir el enlace "Generar dieta" al `<nav>`, ahora que la ruta existe)
- Test: `tests/test_diet_generator.py` (extender), `tests/test_generar_dieta_page.py`

**Interfaces:**
- Consumes: `app.food_matching.find_matching_food`, `app.macros.compute_real_tdee`/`mifflin_st_jeor`/`split_macros` vía `app.main.compute_formula_macro_target`, `app.main.get_latest_agent_macro_target`, `app.main.get_user_profile`.
- Produces: `app.diet_generator.generate_day(target: dict, goal: str, hints: dict) -> dict` (devuelve `{"meals": [...], "totals": {...}, "within_tolerance": bool, "attempts": int}`), ruta `GET /generar-dieta`, ruta `POST /generar-dieta`.

- [ ] **Step 1: Escribe el test que falla (`generate_day`, con Agent SDK y emparejamiento mockeados)**

Añade a `tests/test_diet_generator.py`:
```python
import json

from claude_agent_sdk import ResultMessage

from app.diet_generator import generate_day

DAY_TARGET = {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0}

GOOD_PROPOSAL = {
    "desayuno": {"food_item": "avena integral", "quantity_grams": 100},
    "comida": {"food_item": "pechuga de pollo", "quantity_grams": 200},
    "merienda": {"food_item": "yogur proteico", "quantity_grams": 125},
    "cena": {"food_item": "salmon", "quantity_grams": 150},
}

FAKE_MATCHES = {
    "avena integral": {"id": 1, "name": "Avena integral", "kcal_100g": 350, "protein_100g": 13, "carbs_100g": 60, "fat_100g": 7},
    "pechuga de pollo": {"id": 2, "name": "Pechuga de pollo", "kcal_100g": 110, "protein_100g": 23, "carbs_100g": 0, "fat_100g": 2},
    "yogur proteico": {"id": 3, "name": "Yogur proteico", "kcal_100g": 90, "protein_100g": 10, "carbs_100g": 8, "fat_100g": 2},
    "salmon": {"id": 4, "name": "Salmon", "kcal_100g": 200, "protein_100g": 20, "carbs_100g": 0, "fat_100g": 13},
}


def _fake_result(structured_output):
    return ResultMessage(
        subtype="success", duration_ms=100, duration_api_ms=90, is_error=False,
        num_turns=1, session_id="test-session",
        structured_output=structured_output, result=json.dumps(structured_output),
    )


def test_generate_day_returns_within_tolerance_on_first_good_attempt(monkeypatch):
    async def fake_query(prompt, options):
        yield _fake_result(GOOD_PROPOSAL)

    monkeypatch.setattr("app.diet_generator.query", fake_query)
    monkeypatch.setattr(
        "app.diet_generator.find_matching_food",
        lambda name: FAKE_MATCHES.get(name),
    )

    result = generate_day(DAY_TARGET, "maintenance", {})
    assert result["attempts"] == 1
    assert len(result["meals"]) == 4
    # No afirmamos aqui que de la casualidad dentro de margen; solo que la
    # estructura y el conteo de intentos son correctos con un mock fijo.


def test_generate_day_retries_until_max_attempts_when_never_within_tolerance(monkeypatch):
    bad_proposal = {
        "desayuno": {"food_item": "avena integral", "quantity_grams": 1},
        "comida": {"food_item": "pechuga de pollo", "quantity_grams": 1},
        "merienda": {"food_item": "yogur proteico", "quantity_grams": 1},
        "cena": {"food_item": "salmon", "quantity_grams": 1},
    }
    call_count = {"n": 0}

    async def fake_query(prompt, options):
        call_count["n"] += 1
        yield _fake_result(bad_proposal)

    monkeypatch.setattr("app.diet_generator.query", fake_query)
    monkeypatch.setattr(
        "app.diet_generator.find_matching_food",
        lambda name: FAKE_MATCHES.get(name),
    )

    result = generate_day(DAY_TARGET, "maintenance", {})
    assert result["within_tolerance"] is False
    assert result["attempts"] == 5
    assert call_count["n"] == 5


def test_generate_day_includes_hints_in_prompt(monkeypatch):
    captured_prompts = []

    async def fake_query(prompt, options):
        captured_prompts.append(prompt)
        yield _fake_result(GOOD_PROPOSAL)

    monkeypatch.setattr("app.diet_generator.query", fake_query)
    monkeypatch.setattr(
        "app.diet_generator.find_matching_food",
        lambda name: FAKE_MATCHES.get(name),
    )

    generate_day(DAY_TARGET, "maintenance", {"desayuno": "jamon"})
    assert "jamon" in captured_prompts[0]
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_diet_generator.py -v`
Expected: FAIL con `ImportError: cannot import name 'generate_day' from 'app.diet_generator'`.

- [ ] **Step 3: Añade a `app/diet_generator.py`**

```python
import json
import tempfile
from pathlib import Path

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from app.food_matching import find_matching_food

AGENT_CWD = Path(tempfile.gettempdir()) / "agentenutricional_diet_generator"

MEAL_PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "food_item": {"type": "string"},
        "quantity_grams": {"type": "number"},
    },
    "required": ["food_item", "quantity_grams"],
    "additionalProperties": False,
}

DAY_SCHEMA = {
    "type": "object",
    "properties": {name: MEAL_PROPOSAL_SCHEMA for name in MEAL_NAMES},
    "required": list(MEAL_NAMES),
    "additionalProperties": False,
}


def _resolve_meal(meal_name: str, proposal: dict) -> dict:
    food_item = proposal["food_item"]
    quantity_grams = proposal["quantity_grams"]
    match = find_matching_food(food_item)
    if match is None:
        return {
            "meal_name": meal_name,
            "food_item": food_item,
            "quantity_grams": quantity_grams,
            "matched_food_id": None,
            "verified": False,
            "kcal": 0.0,
            "protein_g": 0.0,
            "carbs_g": 0.0,
            "fat_g": 0.0,
        }
    factor = quantity_grams / 100.0
    return {
        "meal_name": meal_name,
        "food_item": food_item,
        "quantity_grams": quantity_grams,
        "matched_food_id": match["id"],
        "verified": True,
        "kcal": match["kcal_100g"] * factor,
        "protein_g": match["protein_100g"] * factor,
        "carbs_g": match["carbs_100g"] * factor,
        "fat_g": match["fat_100g"] * factor,
    }


def _day_totals(meals: list) -> dict:
    return {key: sum(meal[key] for meal in meals) for key in MACRO_KEYS}


def _call_agent_for_day(target: dict, goal: str, hints: dict, previous_attempt_note: str) -> dict:
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
        output_format={"type": "json_schema", "schema": DAY_SCHEMA},
    )
    hints_lines = [f"- {meal}: {hint}" for meal, hint in hints.items() if hint]
    hints_text = ("Directrices por comida (orientacion suave, no exacta):\n" + "\n".join(hints_lines) + "\n") if hints_lines else ""
    prompt = (
        f"Objetivo del dia: {json.dumps(target, ensure_ascii=False)}\n"
        f"Objetivo del usuario: {goal}\n"
        f"Alimentos a evitar: {', '.join(EXCLUDED_FOODS)}\n"
        f"{hints_text}"
        f"{previous_attempt_note}"
        "Propon desayuno, comida, merienda y cena con food_item (nombre de "
        "producto de supermercado espanol) y quantity_grams."
    )

    async def _run() -> dict:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.is_error or message.structured_output is None:
                    raise RuntimeError(f"Generacion de dieta fallida: {message.result}")
                return message.structured_output
        raise RuntimeError("Sin respuesta del agente")

    return anyio.run(_run)


def generate_day(target: dict, goal: str, hints: dict) -> dict:
    note = ""
    meals: list = []
    totals: dict = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        proposal = _call_agent_for_day(target, goal, hints, note)
        meals = [_resolve_meal(name, proposal[name]) for name in MEAL_NAMES]
        totals = _day_totals(meals)
        if within_tolerance(totals, target):
            return {"meals": meals, "totals": totals, "within_tolerance": True, "attempts": attempt}
        note = (
            f"Tu propuesta anterior dio como resultado real {json.dumps(totals, ensure_ascii=False)}, "
            f"que no cuadra con el objetivo dentro de un 5%. Ajusta las cantidades para acercarte mas.\n"
        )
    return {"meals": meals, "totals": totals, "within_tolerance": False, "attempts": MAX_ATTEMPTS}
```

(Añade estos imports/definiciones **encima** de las funciones puras ya existentes en el archivo, o reordena según prefieras — `MACRO_KEYS`, `MEAL_NAMES`, `EXCLUDED_FOODS`, `MAX_ATTEMPTS`, `within_tolerance` y `remaining_budget` de la Tarea 3 se mantienen sin cambios.)

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_diet_generator.py -v`
Expected: PASS

- [ ] **Step 5: Escribe el test que falla para la página**

`tests/test_generar_dieta_page.py`:
```python
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _seed_profile_and_metrics():
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
            cur.execute(
                "DELETE FROM body_metrics WHERE source_pdf_filename = 'test_generar_dieta.pdf'"
            )
            cur.execute(
                """
                INSERT INTO body_metrics (source_pdf_filename, measured_on, weight_kg, body_fat_pct)
                VALUES ('test_generar_dieta.pdf', '2026-01-01', 80.0, 20.0)
                """
            )


def test_get_generar_dieta_shows_form():
    _seed_profile_and_metrics()
    response = client.get("/generar-dieta")
    assert response.status_code == 200
    assert "form" in response.text.lower()


def test_post_generar_dieta_shows_generated_meals(monkeypatch):
    _seed_profile_and_metrics()

    fake_day = {
        "meals": [
            {"meal_name": "desayuno", "food_item": "Avena integral", "quantity_grams": 100, "matched_food_id": 1, "verified": True, "kcal": 350.0, "protein_g": 13.0, "carbs_g": 60.0, "fat_g": 7.0},
            {"meal_name": "comida", "food_item": "Pechuga de pollo", "quantity_grams": 200, "matched_food_id": 2, "verified": True, "kcal": 220.0, "protein_g": 46.0, "carbs_g": 0.0, "fat_g": 4.0},
            {"meal_name": "merienda", "food_item": "Yogur proteico", "quantity_grams": 125, "matched_food_id": 3, "verified": True, "kcal": 112.5, "protein_g": 12.5, "carbs_g": 10.0, "fat_g": 2.5},
            {"meal_name": "cena", "food_item": "Salmon", "quantity_grams": 150, "matched_food_id": 4, "verified": True, "kcal": 300.0, "protein_g": 30.0, "carbs_g": 0.0, "fat_g": 19.5},
        ],
        "totals": {"kcal": 982.5, "protein_g": 101.5, "carbs_g": 70.0, "fat_g": 33.0},
        "within_tolerance": True,
        "attempts": 1,
    }
    monkeypatch.setattr("app.main.generate_day", lambda target, goal, hints: fake_day)

    response = client.post(
        "/generar-dieta",
        data={"method": "formula", "hint_desayuno": "jamon", "hint_comida": "", "hint_merienda": "", "hint_cena": "salmon"},
    )
    assert response.status_code == 200
    assert "Avena integral" in response.text
    assert "Salmon" in response.text
```

- [ ] **Step 6: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_generar_dieta_page.py -v`
Expected: FAIL con `404 Not Found`.

- [ ] **Step 7: Añade a `app/main.py`**

```python
from app.diet_generator import MEAL_NAMES, generate_day


def _current_macro_target(method: str, profile: dict) -> tuple[dict, str] | None:
    if method == "formula":
        try:
            result = compute_formula_macro_target(profile)
        except ValueError:
            return None
        return result, profile["current_goal"]
    agent_result = get_latest_agent_macro_target()
    if agent_result is None:
        return None
    return agent_result, agent_result["goal"]


@app.get("/generar-dieta")
def generar_dieta_form(request: Request):
    profile = get_user_profile()
    template = templates.get_template("generar_dieta.html")
    return HTMLResponse(
        template.render({"request": request, "profile": profile, "meal_names": MEAL_NAMES, "day": None})
    )


@app.post("/generar-dieta")
def generar_dieta_generate(
    request: Request,
    method: str = Form(...),
    hint_desayuno: str = Form(""),
    hint_comida: str = Form(""),
    hint_merienda: str = Form(""),
    hint_cena: str = Form(""),
):
    profile = get_user_profile()
    template = templates.get_template("generar_dieta.html")
    if profile is None:
        return HTMLResponse(
            template.render({"request": request, "profile": None, "meal_names": MEAL_NAMES, "day": None})
        )

    target = _current_macro_target(method, profile)
    if target is None:
        return HTMLResponse(
            template.render(
                {
                    "request": request,
                    "profile": profile,
                    "meal_names": MEAL_NAMES,
                    "day": None,
                    "no_target_available": True,
                    "method": method,
                }
            )
        )

    macro_target, goal = target
    hints = {
        "desayuno": hint_desayuno,
        "comida": hint_comida,
        "merienda": hint_merienda,
        "cena": hint_cena,
    }
    day = generate_day(macro_target, goal, hints)

    return HTMLResponse(
        template.render(
            {
                "request": request,
                "profile": profile,
                "meal_names": MEAL_NAMES,
                "day": day,
                "target": macro_target,
                "goal": goal,
                "method": method,
                "hints": hints,
            }
        )
    )
```

- [ ] **Step 8: Crea `app/templates/_meal_card.html`**

```html
<div class="card">
  <h3>{{ meal.meal_name | capitalize }}</h3>
  <hr class="hr-thin">
  <p>{{ meal.food_item }} — {{ meal.quantity_grams }} g</p>
  {% if not meal.verified %}
  <p><span class="badge bad">sin verificar</span></p>
  {% endif %}
  <div class="macro-row"><span class="label">Kcal</span><span class="value">{{ "%.0f" | format(meal.kcal) }}</span></div>
  <div class="macro-row"><span class="label">Proteina</span><span class="value">{{ "%.1f" | format(meal.protein_g) }} g</span></div>
  <div class="macro-row"><span class="label">Carbohidratos</span><span class="value">{{ "%.1f" | format(meal.carbs_g) }} g</span></div>
  <div class="macro-row"><span class="label">Grasa</span><span class="value">{{ "%.1f" | format(meal.fat_g) }} g</span></div>
</div>
```

- [ ] **Step 9: Crea `app/templates/generar_dieta.html`**

```html
{% extends "base.html" %}
{% block title %}Generar dieta{% endblock %}
{% block content %}
<h1>Generar dieta</h1>
{% if not profile %}
<div class="card"><p>Falta completar el <a href="/perfil">perfil</a> antes de generar una dieta.</p></div>
{% else %}
<div class="card">
  <form method="post" action="/generar-dieta">
    <label>Fuente de macros objetivo
      <select name="method" required>
        <option value="formula" {% if method == "formula" %}selected{% endif %}>Metodo determinista</option>
        <option value="agent" {% if method == "agent" %}selected{% endif %}>Ultimo resultado de IA guardado</option>
      </select>
    </label>
    {% for name in meal_names %}
    <label>Directriz para {{ name }} (opcional)
      <input type="text" name="hint_{{ name }}" value="{{ hints[name] if hints else '' }}" placeholder="ej. jamon">
    </label>
    {% endfor %}
    <button type="submit">Generar</button>
  </form>
</div>

{% if no_target_available %}
<div class="card">
  <p>No hay ningun objetivo de macros disponible para ese metodo todavia. Ve a
     <a href="/macros">Macros</a> {% if method == "formula" %}y registra al menos una medida en <a href="/medidas">Medidas</a>{% else %}y pulsa "Recalcular con IA" al menos una vez{% endif %}.</p>
</div>
{% endif %}

{% if day %}
<div class="card">
  <h2>Objetivo del dia</h2>
  <div class="macro-row"><span class="label">Kcal</span><span class="value">{{ "%.0f" | format(target.kcal) }}</span></div>
  <div class="macro-row"><span class="label">Proteina</span><span class="value">{{ "%.1f" | format(target.protein_g) }} g</span></div>
  <div class="macro-row"><span class="label">Carbohidratos</span><span class="value">{{ "%.1f" | format(target.carbs_g) }} g</span></div>
  <div class="macro-row"><span class="label">Grasa</span><span class="value">{{ "%.1f" | format(target.fat_g) }} g</span></div>
  {% if day.within_tolerance %}
  <p><span class="badge good">dentro de margen (±5%)</span></p>
  {% else %}
  <p><span class="badge bad">fuera de margen tras {{ day.attempts }} intentos</span></p>
  {% endif %}
</div>
<div class="card-grid">
  {% for meal in day.meals %}
  {% include "_meal_card.html" %}
  {% endfor %}
</div>
{% endif %}
{% endif %}
{% endblock %}
```

- [ ] **Step 10: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_generar_dieta_page.py -v`
Expected: PASS

- [ ] **Step 11: Añade el enlace al `<nav>` de `app/templates/base.html`**

```html
<a href="/generar-dieta" {% if request.url.path == '/generar-dieta' %}class="active"{% endif %}>Generar dieta</a>
```

(Justo después del enlace a "Macros".)

- [ ] **Step 12: Verifica que la suite completa sigue en verde**

Run: `python -m pytest tests/ -v`
Expected: todos los tests pasan (los de este subsistema y los de los anteriores).

- [ ] **Step 13: Commit**

```bash
git add app/diet_generator.py app/main.py app/templates/generar_dieta.html app/templates/_meal_card.html app/templates/base.html tests/test_diet_generator.py tests/test_generar_dieta_page.py
git commit -m "Add full-day diet generation via Agent SDK with tolerance-checked retry"
```

---

### Task 5: Regenerar una sola comida

**Files:**
- Modify: `app/diet_generator.py` (añadir `generate_single_meal`)
- Modify: `app/main.py` (ruta `POST /generar-dieta/comida`)
- Modify: `app/templates/_meal_card.html` (añadir directriz + botón "Cambiar esta comida", campos ocultos)
- Modify: `app/templates/generar_dieta.html` (envolver el estado del día en `<div id="day-state">` con los campos ocultos del target)
- Create: `app/templates/_guardar_section.html` (extraído de dentro de `generar_dieta.html` para poder actualizarlo vía out-of-band swap)
- Test: `tests/test_diet_generator.py` (extender), `tests/test_generar_dieta_page.py` (extender)

**Interfaces:**
- Produces: `app.diet_generator.generate_single_meal(meal_name: str, budget: dict, goal: str, hint: str) -> dict`, ruta `POST /generar-dieta/comida`.

**Diseño de estado sin servidor (HTMX):** todo el día actual vive como inputs ocultos dentro de `<div id="day-state">` (target del día +, por cada comida, `food_item`/`quantity_grams`/`matched_food_id`/`verified`/`kcal`/`protein_g`/`carbs_g`/`fat_g`). El botón "Cambiar esta comida" de cada tarjeta usa `hx-include="#day-state"` para reenviar todo ese estado junto con su propio nuevo campo de directriz, y `hx-vals` para indicar qué comida se está regenerando. La respuesta devuelve dos fragmentos: la tarjeta de esa comida actualizada (swap normal) y la sección "Guardar" actualizada vía `hx-swap-oob="true"` (para reflejar si el día completo sigue dentro de margen tras el cambio).

- [ ] **Step 1: Escribe el test que falla (`generate_single_meal`)**

Añade a `tests/test_diet_generator.py`:
```python
from app.diet_generator import generate_single_meal

MEAL_BUDGET = {"kcal": 300.0, "protein_g": 30.0, "carbs_g": 0.0, "fat_g": 19.5}


def test_generate_single_meal_returns_resolved_meal(monkeypatch):
    async def fake_query(prompt, options):
        yield _fake_result({"food_item": "salmon", "quantity_grams": 150})

    monkeypatch.setattr("app.diet_generator.query", fake_query)
    monkeypatch.setattr(
        "app.diet_generator.find_matching_food",
        lambda name: FAKE_MATCHES.get(name),
    )

    meal = generate_single_meal("cena", MEAL_BUDGET, "maintenance", "salmon")
    assert meal["meal_name"] == "cena"
    assert meal["food_item"] == "salmon"
    assert "within_tolerance" in meal
    assert "attempts" in meal
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_diet_generator.py -v`
Expected: FAIL con `ImportError: cannot import name 'generate_single_meal'`.

- [ ] **Step 3: Añade a `app/diet_generator.py`**

```python
def _call_agent_for_meal(meal_name: str, budget: dict, goal: str, hint: str, previous_attempt_note: str) -> dict:
    AGENT_CWD.mkdir(parents=True, exist_ok=True)
    options = ClaudeAgentOptions(
        system_prompt=(
            "Eres un asistente de nutricion que propone una sola comida "
            "realista con productos de supermercado espanol, ajustando la "
            "cantidad en gramos para acercarte lo maximo posible al "
            "presupuesto de macros indicado."
        ),
        max_turns=3,
        cwd=str(AGENT_CWD),
        setting_sources=[],
        allowed_tools=[],
        output_format={"type": "json_schema", "schema": MEAL_PROPOSAL_SCHEMA},
    )
    prompt = (
        f"Comida a proponer: {meal_name}\n"
        f"Presupuesto de macros para esta comida: {json.dumps(budget, ensure_ascii=False)}\n"
        f"Objetivo del usuario: {goal}\n"
        f"Alimentos a evitar: {', '.join(EXCLUDED_FOODS)}\n"
        + (f"Directriz (orientacion suave, no exacta): {hint}\n" if hint else "")
        + previous_attempt_note
        + "Devuelve food_item (nombre de producto de supermercado espanol) y quantity_grams."
    )

    async def _run() -> dict:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.is_error or message.structured_output is None:
                    raise RuntimeError(f"Generacion de comida fallida: {message.result}")
                return message.structured_output
        raise RuntimeError("Sin respuesta del agente")

    return anyio.run(_run)


def generate_single_meal(meal_name: str, budget: dict, goal: str, hint: str) -> dict:
    note = ""
    meal: dict = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        proposal = _call_agent_for_meal(meal_name, budget, goal, hint, note)
        meal = _resolve_meal(meal_name, proposal)
        if within_tolerance({key: meal[key] for key in MACRO_KEYS}, budget):
            meal["within_tolerance"] = True
            meal["attempts"] = attempt
            return meal
        note = (
            f"Tu propuesta anterior dio como resultado real "
            f"{json.dumps({key: meal[key] for key in MACRO_KEYS}, ensure_ascii=False)}, "
            f"que no cuadra con el presupuesto dentro de un 5%. Ajusta la cantidad.\n"
        )
    meal["within_tolerance"] = False
    meal["attempts"] = MAX_ATTEMPTS
    return meal
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_diet_generator.py -v`
Expected: PASS

- [ ] **Step 5: Reescribe `app/templates/_meal_card.html`** (añade directriz + botón + campos ocultos del estado de esta comida)

```html
<div class="card" id="meal-{{ meal.meal_name }}">
  <h3>{{ meal.meal_name | capitalize }}</h3>
  <hr class="hr-thin">
  <p>{{ meal.food_item }} — {{ meal.quantity_grams }} g</p>
  {% if not meal.verified %}
  <p><span class="badge bad">sin verificar</span></p>
  {% endif %}
  <div class="macro-row"><span class="label">Kcal</span><span class="value">{{ "%.0f" | format(meal.kcal) }}</span></div>
  <div class="macro-row"><span class="label">Proteina</span><span class="value">{{ "%.1f" | format(meal.protein_g) }} g</span></div>
  <div class="macro-row"><span class="label">Carbohidratos</span><span class="value">{{ "%.1f" | format(meal.carbs_g) }} g</span></div>
  <div class="macro-row"><span class="label">Grasa</span><span class="value">{{ "%.1f" | format(meal.fat_g) }} g</span></div>

  <input type="hidden" name="meal_{{ meal.meal_name }}_food_item" value="{{ meal.food_item }}">
  <input type="hidden" name="meal_{{ meal.meal_name }}_quantity_grams" value="{{ meal.quantity_grams }}">
  <input type="hidden" name="meal_{{ meal.meal_name }}_matched_food_id" value="{{ meal.matched_food_id or '' }}">
  <input type="hidden" name="meal_{{ meal.meal_name }}_kcal" value="{{ meal.kcal }}">
  <input type="hidden" name="meal_{{ meal.meal_name }}_protein_g" value="{{ meal.protein_g }}">
  <input type="hidden" name="meal_{{ meal.meal_name }}_carbs_g" value="{{ meal.carbs_g }}">
  <input type="hidden" name="meal_{{ meal.meal_name }}_fat_g" value="{{ meal.fat_g }}">

  <label>Nueva directriz para {{ meal.meal_name }} (opcional)
    <input type="text" name="hint_{{ meal.meal_name }}_new" placeholder="ej. salmon">
  </label>
  <button
    class="secondary"
    hx-post="/generar-dieta/comida"
    hx-include="#day-state"
    hx-vals='{"meal_name": "{{ meal.meal_name }}"}'
    hx-target="#meal-{{ meal.meal_name }}"
    hx-swap="outerHTML">
    Cambiar esta comida
  </button>
</div>
```

- [ ] **Step 6: Reescribe `app/templates/generar_dieta.html`** para envolver los resultados en `#day-state` y extraer la sección "Guardar" a un partial

```html
{% extends "base.html" %}
{% block title %}Generar dieta{% endblock %}
{% block content %}
<h1>Generar dieta</h1>
{% if not profile %}
<div class="card"><p>Falta completar el <a href="/perfil">perfil</a> antes de generar una dieta.</p></div>
{% else %}
<div class="card">
  <form method="post" action="/generar-dieta">
    <label>Fuente de macros objetivo
      <select name="method" required>
        <option value="formula" {% if method == "formula" %}selected{% endif %}>Metodo determinista</option>
        <option value="agent" {% if method == "agent" %}selected{% endif %}>Ultimo resultado de IA guardado</option>
      </select>
    </label>
    {% for name in meal_names %}
    <label>Directriz para {{ name }} (opcional)
      <input type="text" name="hint_{{ name }}" value="{{ hints[name] if hints else '' }}" placeholder="ej. jamon">
    </label>
    {% endfor %}
    <button type="submit">Generar</button>
  </form>
</div>

{% if no_target_available %}
<div class="card">
  <p>No hay ningun objetivo de macros disponible para ese metodo todavia. Ve a
     <a href="/macros">Macros</a> {% if method == "formula" %}y registra al menos una medida en <a href="/medidas">Medidas</a>{% else %}y pulsa "Recalcular con IA" al menos una vez{% endif %}.</p>
</div>
{% endif %}

{% if day %}
<div id="day-state">
  <input type="hidden" name="target_kcal" value="{{ target.kcal }}">
  <input type="hidden" name="target_protein_g" value="{{ target.protein_g }}">
  <input type="hidden" name="target_carbs_g" value="{{ target.carbs_g }}">
  <input type="hidden" name="target_fat_g" value="{{ target.fat_g }}">
  <input type="hidden" name="goal" value="{{ goal }}">

  <div class="card">
    <h2>Objetivo del dia</h2>
    <div class="macro-row"><span class="label">Kcal</span><span class="value">{{ "%.0f" | format(target.kcal) }}</span></div>
    <div class="macro-row"><span class="label">Proteina</span><span class="value">{{ "%.1f" | format(target.protein_g) }} g</span></div>
    <div class="macro-row"><span class="label">Carbohidratos</span><span class="value">{{ "%.1f" | format(target.carbs_g) }} g</span></div>
    <div class="macro-row"><span class="label">Grasa</span><span class="value">{{ "%.1f" | format(target.fat_g) }} g</span></div>
  </div>

  <div class="card-grid">
    {% for meal in day.meals %}
    {% include "_meal_card.html" %}
    {% endfor %}
  </div>

  <div id="guardar-section">
    {% include "_guardar_section.html" %}
  </div>
</div>
{% endif %}
{% endif %}
{% endblock %}
```

- [ ] **Step 7: Crea `app/templates/_guardar_section.html`**

```html
<div class="card">
  {% if day.within_tolerance %}
  <p><span class="badge good">dentro de margen (±5%)</span></p>
  <button
    hx-post="/generar-dieta/guardar"
    hx-include="#day-state"
    hx-target="#guardar-section"
    hx-swap="innerHTML">
    Guardar este dia como comido
  </button>
  {% else %}
  <p><span class="badge bad">fuera de margen tras {{ day.attempts }} intentos</span> — sigue cambiando comidas hasta que cuadre.</p>
  <button disabled>Guardar este dia como comido</button>
  {% endif %}
</div>
```

- [ ] **Step 8: Añade a `app/main.py` la ruta `POST /generar-dieta/comida`**

```python
from app.diet_generator import generate_single_meal, remaining_budget


def _meal_from_form_fields(form: dict, meal_name: str) -> dict:
    return {
        "meal_name": meal_name,
        "food_item": form[f"meal_{meal_name}_food_item"],
        "quantity_grams": float(form[f"meal_{meal_name}_quantity_grams"]),
        "matched_food_id": int(form[f"meal_{meal_name}_matched_food_id"]) if form[f"meal_{meal_name}_matched_food_id"] else None,
        "verified": bool(form[f"meal_{meal_name}_matched_food_id"]),
        "kcal": float(form[f"meal_{meal_name}_kcal"]),
        "protein_g": float(form[f"meal_{meal_name}_protein_g"]),
        "carbs_g": float(form[f"meal_{meal_name}_carbs_g"]),
        "fat_g": float(form[f"meal_{meal_name}_fat_g"]),
    }


@app.post("/generar-dieta/comida")
async def generar_dieta_comida(request: Request):
    form = dict((await request.form()).items())
    meal_name = form["meal_name"]
    target = {
        "kcal": float(form["target_kcal"]),
        "protein_g": float(form["target_protein_g"]),
        "carbs_g": float(form["target_carbs_g"]),
        "fat_g": float(form["target_fat_g"]),
    }
    goal = form["goal"]
    other_meals = [_meal_from_form_fields(form, name) for name in MEAL_NAMES if name != meal_name]
    budget = remaining_budget(target, other_meals)
    hint = form.get(f"hint_{meal_name}_new", "")

    new_meal = generate_single_meal(meal_name, budget, goal, hint)
    all_meals = other_meals + [new_meal]
    day = {
        "meals": sorted(all_meals, key=lambda m: MEAL_NAMES.index(m["meal_name"])),
        "totals": _day_totals(all_meals),
        "within_tolerance": within_tolerance(_day_totals(all_meals), target),
        "attempts": new_meal["attempts"],
    }

    meal_card = templates.get_template("_meal_card.html").render({"meal": new_meal})
    guardar_section = templates.get_template("_guardar_section.html").render({"day": day})
    return HTMLResponse(
        meal_card + f'<div id="guardar-section" hx-swap-oob="true">{guardar_section}</div>'
    )
```

(Importa también `_day_totals` y `within_tolerance` desde `app.diet_generator` en la cabecera de `app/main.py` junto al resto de imports de ese módulo.)

- [ ] **Step 9: Escribe y ejecuta los tests de la ruta**

Añade a `tests/test_generar_dieta_page.py`:
```python
def test_generar_dieta_comida_regenerates_one_meal_and_updates_guardar_section(monkeypatch):
    fake_new_meal = {
        "meal_name": "cena", "food_item": "Salmon", "quantity_grams": 150,
        "matched_food_id": 4, "verified": True,
        "kcal": 300.0, "protein_g": 30.0, "carbs_g": 0.0, "fat_g": 19.5,
        "within_tolerance": True, "attempts": 1,
    }
    monkeypatch.setattr(
        "app.main.generate_single_meal",
        lambda meal_name, budget, goal, hint: fake_new_meal,
    )

    response = client.post(
        "/generar-dieta/comida",
        data={
            "meal_name": "cena",
            "target_kcal": "1000", "target_protein_g": "100",
            "target_carbs_g": "70", "target_fat_g": "33",
            "goal": "maintenance",
            "meal_desayuno_food_item": "Avena integral", "meal_desayuno_quantity_grams": "100",
            "meal_desayuno_matched_food_id": "1", "meal_desayuno_kcal": "350",
            "meal_desayuno_protein_g": "13", "meal_desayuno_carbs_g": "60", "meal_desayuno_fat_g": "7",
            "meal_comida_food_item": "Pechuga de pollo", "meal_comida_quantity_grams": "200",
            "meal_comida_matched_food_id": "2", "meal_comida_kcal": "220",
            "meal_comida_protein_g": "46", "meal_comida_carbs_g": "0", "meal_comida_fat_g": "4",
            "meal_merienda_food_item": "Yogur proteico", "meal_merienda_quantity_grams": "125",
            "meal_merienda_matched_food_id": "3", "meal_merienda_kcal": "112.5",
            "meal_merienda_protein_g": "12.5", "meal_merienda_carbs_g": "10", "meal_merienda_fat_g": "2.5",
            "meal_cena_food_item": "Salmon (anterior)", "meal_cena_quantity_grams": "100",
            "meal_cena_matched_food_id": "4", "meal_cena_kcal": "200",
            "meal_cena_protein_g": "20", "meal_cena_carbs_g": "0", "meal_cena_fat_g": "13",
            "hint_cena_new": "salmon",
        },
    )
    assert response.status_code == 200
    assert "Salmon" in response.text
    assert 'id="guardar-section"' in response.text
```

Run: `python -m pytest tests/test_generar_dieta_page.py -v`
Expected: PASS

- [ ] **Step 10: Verifica visualmente en el navegador**

Run: `docker compose up -d --build`
Abre `http://localhost:8000/generar-dieta`, genera un día, pulsa "Cambiar esta comida" en una tarjeta y confirma que solo esa tarjeta cambia (esto hace llamadas reales a la suscripción — hazlo con moderación, no en bucle).

- [ ] **Step 11: Commit**

```bash
git add app/diet_generator.py app/main.py app/templates/_meal_card.html app/templates/generar_dieta.html app/templates/_guardar_section.html tests/test_diet_generator.py tests/test_generar_dieta_page.py
git commit -m "Add single-meal regeneration keeping the other three meals fixed"
```

---

### Task 6: Guardar el día como comido

**Files:**
- Modify: `app/main.py` (ruta `POST /generar-dieta/guardar`, función `save_generated_day`)
- Test: `tests/test_generar_dieta_page.py` (extender)

**Interfaces:**
- Produces: `app.main.save_generated_day(meals: list[dict]) -> int` (devuelve `diet_version_id`), ruta `POST /generar-dieta/guardar`.

- [ ] **Step 1: Escribe el test que falla**

Añade a `tests/test_generar_dieta_page.py`:
```python
def test_guardar_dia_creates_diet_version_when_within_tolerance():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE source_pdf_filename = 'generado')"
            )
            cur.execute("DELETE FROM diet_versions WHERE source_pdf_filename = 'generado'")

    response = client.post(
        "/generar-dieta/guardar",
        data={
            "target_kcal": "982.5", "target_protein_g": "101.5",
            "target_carbs_g": "70", "target_fat_g": "33",
            "goal": "maintenance",
            "meal_desayuno_food_item": "Avena integral", "meal_desayuno_quantity_grams": "100",
            "meal_desayuno_matched_food_id": "1", "meal_desayuno_kcal": "350",
            "meal_desayuno_protein_g": "13", "meal_desayuno_carbs_g": "60", "meal_desayuno_fat_g": "7",
            "meal_comida_food_item": "Pechuga de pollo", "meal_comida_quantity_grams": "200",
            "meal_comida_matched_food_id": "2", "meal_comida_kcal": "220",
            "meal_comida_protein_g": "46", "meal_comida_carbs_g": "0", "meal_comida_fat_g": "4",
            "meal_merienda_food_item": "Yogur proteico", "meal_merienda_quantity_grams": "125",
            "meal_merienda_matched_food_id": "3", "meal_merienda_kcal": "112.5",
            "meal_merienda_protein_g": "12.5", "meal_merienda_carbs_g": "10", "meal_merienda_fat_g": "2.5",
            "meal_cena_food_item": "Salmon", "meal_cena_quantity_grams": "150",
            "meal_cena_matched_food_id": "4", "meal_cena_kcal": "300",
            "meal_cena_protein_g": "30", "meal_cena_carbs_g": "0", "meal_cena_fat_g": "19.5",
        },
    )
    assert response.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM diet_meals dm "
                "JOIN diet_versions dv ON dv.id = dm.diet_version_id "
                "WHERE dv.source_pdf_filename = 'generado'"
            )
            count = cur.fetchone()[0]
    assert count == 4


def test_guardar_dia_rejects_out_of_tolerance_data():
    response = client.post(
        "/generar-dieta/guardar",
        data={
            "target_kcal": "2000", "target_protein_g": "150",
            "target_carbs_g": "200", "target_fat_g": "60",
            "goal": "maintenance",
            "meal_desayuno_food_item": "Avena integral", "meal_desayuno_quantity_grams": "1",
            "meal_desayuno_matched_food_id": "1", "meal_desayuno_kcal": "1",
            "meal_desayuno_protein_g": "1", "meal_desayuno_carbs_g": "1", "meal_desayuno_fat_g": "1",
            "meal_comida_food_item": "Pechuga de pollo", "meal_comida_quantity_grams": "1",
            "meal_comida_matched_food_id": "2", "meal_comida_kcal": "1",
            "meal_comida_protein_g": "1", "meal_comida_carbs_g": "1", "meal_comida_fat_g": "1",
            "meal_merienda_food_item": "Yogur proteico", "meal_merienda_quantity_grams": "1",
            "meal_merienda_matched_food_id": "3", "meal_merienda_kcal": "1",
            "meal_merienda_protein_g": "1", "meal_merienda_carbs_g": "1", "meal_merienda_fat_g": "1",
            "meal_cena_food_item": "Salmon", "meal_cena_quantity_grams": "1",
            "meal_cena_matched_food_id": "4", "meal_cena_kcal": "1",
            "meal_cena_protein_g": "1", "meal_cena_carbs_g": "1", "meal_cena_fat_g": "1",
        },
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `python -m pytest tests/test_generar_dieta_page.py -v`
Expected: FAIL con `404 Not Found`.

- [ ] **Step 3: Añade a `app/main.py`**

```python
from datetime import date

from fastapi import HTTPException


def save_generated_day(meals: list) -> int:
    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO diet_versions (source_pdf_filename, valid_from, valid_to)
                VALUES ('generado', %s, %s)
                RETURNING id
                """,
                (today, today),
            )
            diet_version_id = cur.fetchone()[0]
            cur.executemany(
                """
                INSERT INTO diet_meals
                    (diet_version_id, day_label, meal_name, food_item, quantity_grams, matched_food_id)
                VALUES (%s, 'dia', %s, %s, %s, %s)
                """,
                [
                    (
                        diet_version_id,
                        meal["meal_name"],
                        meal["food_item"],
                        meal["quantity_grams"],
                        meal["matched_food_id"],
                    )
                    for meal in meals
                ],
            )
    return diet_version_id


@app.post("/generar-dieta/guardar")
async def generar_dieta_guardar(request: Request):
    form = dict((await request.form()).items())
    target = {
        "kcal": float(form["target_kcal"]),
        "protein_g": float(form["target_protein_g"]),
        "carbs_g": float(form["target_carbs_g"]),
        "fat_g": float(form["target_fat_g"]),
    }
    meals = [_meal_from_form_fields(form, name) for name in MEAL_NAMES]
    totals = _day_totals(meals)
    if not within_tolerance(totals, target):
        raise HTTPException(status_code=400, detail="El dia esta fuera de margen, no se puede guardar")

    save_generated_day(meals)
    return HTMLResponse('<div class="card"><p><span class="badge good">Guardado como comido</span></p></div>')
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `python -m pytest tests/test_generar_dieta_page.py -v`
Expected: PASS

- [ ] **Step 5: Ejecuta toda la suite del subsistema para verificar que no hay regresiones**

Run: `python -m pytest tests/ -v`
Expected: todos los tests pasan (Subsistemas 1, 2 y 3 completos).

- [ ] **Step 6: Verifica visualmente en el navegador**

Run: `docker compose up -d --build`
Abre `http://localhost:8000/generar-dieta`, genera un día, ajusta comidas hasta que quede dentro de margen, pulsa "Guardar este dia como comido" y confirma en `http://localhost:8000/` (dashboard) que aparece una nueva versión de dieta. Esto hace llamadas reales a la suscripción — hazlo una vez para confirmar, no en bucle.

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/test_generar_dieta_page.py
git commit -m "Add save-as-eaten action for generated diets, gated by macro tolerance"
```

---

## Después de este plan

Con el Subsistema 3 completo: `http://localhost:8000/generar-dieta` para generar un día de dieta variada (con directrices opcionales por comida), regenerar comidas individuales, y guardarlo como comido real cuando cuadre dentro de un ±5% — alimentando el histórico que usa el Subsistema 2 para el TDEE real. Toda la app comparte ahora un mismo sistema de diseño. El Subsistema 4 (motor de compensación/antojos) partirá de aquí.
