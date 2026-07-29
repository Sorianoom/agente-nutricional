# Subsistema 4: Motor de compensación y antojos — Diseño

## Contexto

Programa nutricional personal (usuario único). Los Subsistemas 1-3 están completos:
fundamentos (catálogo, histórico, dashboard), calculadora de macros objetivo (determinista +
IA bajo demanda), y generador de dietas variadas (día completo + regenerar una comida +
guardar como comido, todo con verificación de margen ±5%).

Este documento cubre el Subsistema 4, la última pieza del alcance original: qué pasa cuando la
realidad se desvía del plan — ya sea porque el usuario come algo no planificado, se desvía de
un día ya guardado, o le apetece algo concreto y quiere encajarlo sin salirse del objetivo.

## Alcance

- **Registrar algo comido fuera de plan** (ej. "me he comido medio campero y dos yogures a
  mediodía", el caso real que motivó este subsistema): el usuario introduce alimento(s) +
  cantidad, se emparejan contra el catálogo (reutilizando `app.food_matching.find_matching_food`),
  y se guardan como comidas reales del día de hoy — creando la `diet_version` de hoy si no
  existe todavía, o añadiéndose a ella si ya existe (por ejemplo, porque ya se generó y guardó
  algo con el Subsistema 3). Se puede registrar varias veces a lo largo del día (desayuno,
  luego una comida suelta a media tarde, etc.) sin disparar nada más por sí solo — ver más
  abajo cuándo se dispara realmente la compensación.
- **Corregir una desviación de un día ya guardado**: si una comida de un día ya guardado
  (Subsistema 3) no se siguió tal cual, el usuario puede editar esa comida concreta
  (`diet_meals`) para que refleje lo que realmente comió.
- **Antojo que se encaja ajustando el resto del día**: el usuario indica un alimento y cantidad
  que le apetece (no una directriz suave como en el Subsistema 3 — esto es un alimento fijo,
  real, que sí o sí se va a comer). El sistema lo trata como una comida ya fija del día, calcula
  el presupuesto de macros restante (reutilizando `app.diet_generator.remaining_budget`), y
  regenera las comidas del día que aún no se han fijado (reutilizando
  `app.diet_generator.generate_day`/`generate_single_meal` con reintento hasta ±5%) para que el
  antojo quepa sin salirse del objetivo total del día.
- **Compensación repartida en varios días**: cuando el día se cierra (se guarda, o se marca
  como terminado) con un desvío neto respecto al objetivo — de más o de menos, en kcal — ese
  desvío no se pierde ni se ignora: se reparte suavizado entre los siguientes 3 días, ajustando
  el objetivo de esos días para compensar (si hoy te pasaste 300 kcal, los próximos 3 días el
  objetivo baja 100 kcal cada uno; si comiste de menos, sube). Esto afecta a
  `compute_formula_macro_target`/`compute_agent_macro_target` (Subsistema 2) y a la generación
  de dietas (Subsistema 3): mientras haya compensación pendiente, el target que usan se ajusta
  antes de calcular macros/generar el día.

Fuera de alcance: sustituir un alimento por otro dentro de una comida ya fija sin recalcular
nada más (edición simple, cubierta por la corrección de desviación de arriba); compensación
repartida en más de 3 días o con una curva no lineal; deshacer o cancelar manualmente una
compensación pendiente antes de que termine de aplicarse (si hace falta, se puede añadir
después).

## Arquitectura

- Mismo stack que los Subsistemas 1-3: FastAPI + Jinja2/HTMX, Postgres (psycopg directo, sin
  ORM), Docker Compose, sistema de diseño compartido ya existente.
- Reutiliza extensivamente el Subsistema 3: `app.food_matching.find_matching_food`,
  `app.diet_generator.remaining_budget`, `app.diet_generator.generate_day`/`generate_single_meal`,
  `app.diet_generator.within_tolerance`. El "antojo que ajusta el resto del día" es, en esencia,
  una generación de día con una comida ya fija de entrada en vez de generada — no un motor
  nuevo.
- La compensación multi-día es el único mecanismo genuinamente nuevo: una tabla pequeña que
  registra un desvío pendiente y cuántos días le quedan por repartirse, consultada por el
  Subsistema 2 al calcular el target y por el Subsistema 3 al generar un día.

## Modelo de datos (Postgres, tabla nueva)

- `pending_compensation` — a lo sumo una fila activa a la vez (fila única mientras haya algo
  pendiente, se borra al terminar de aplicarse):
  `id`, `kcal_delta` (positivo = hay que comer menos los próximos días, negativo = hay que
  comer más), `protein_g_delta`, `carbs_g_delta`, `fat_g_delta`, `days_total` (fijo en 3),
  `created_at` (fecha en la que se creó/actualizó por última vez).

  **Nota de diseño importante:** no se guarda un contador de "días ya aplicados" que se
  incremente cada vez que se calcula un target — `/macros` recalcula el método determinista en
  **cada visita a la página** (por diseño del Subsistema 2), así que un contador atado a
  "número de cálculos" agotaría la ventana de 3 días en minutos con solo refrescar la página
  varias veces el mismo día. En su lugar, los días transcurridos se derivan de la fecha:
  `dias_transcurridos = (hoy - created_at).days`. Mientras `dias_transcurridos < days_total`,
  la compensación sigue activa y se aplica (el mismo ajuste todo el día, sin importar cuántas
  veces se recalculen macros ese día); en cuanto `dias_transcurridos >= days_total`, se
  considera terminada y se borra la fila.

## Algoritmo de compensación

**Importante — la compensación se calcula UNA sola vez por día, al cerrarlo, no cada vez que
se registra una comida suelta.** Si se recalculara en cada registro ad-hoc a lo largo del día,
el mismo exceso se contaría varias veces (una vez por cada comida registrada ese día). El
"cierre" de un día es uno de estos dos momentos, según cómo se haya llegado a ese día:

- **Guardar un día generado** (Subsistema 3, `POST /generar-dieta/guardar`) — el cierre ya
  existe, es ese mismo guardado.
- **Cerrar el día de hoy** (acción nueva de este subsistema, un botón explícito) — para un día
  construido solo con registros ad-hoc fuera de plan, sin pasar por el generador. El usuario lo
  pulsa cuando considera que ya ha terminado de comer por hoy.

Al cerrar un día (cualquiera de los dos caminos):

1. Se compara el total real acumulado del día (suma de sus `diet_meals`) contra el target del
   momento (mismo método usado para generarlo si se generó, o el determinista si no):
   `delta = real_totals - target` en las 4 magnitudes.
2. Si `delta` está ya dentro del ±5% (el mismo margen del Subsistema 3), no se crea ninguna
   compensación — un desvío tan pequeño no merece repartirse.
3. Si no, y no había ninguna compensación pendiente activa (o la que había ya expiró,
   `dias_transcurridos >= days_total`): se crea una fila en `pending_compensation` con ese
   `delta`, `days_total = 3`, `created_at = hoy`.
4. Si ya había una compensación pendiente **todavía activa** (`dias_transcurridos < days_total`
   respecto a su propio `created_at`): se calcula cuánto quedaba realmente por compensar de
   ella — `restante = delta_anterior * (days_total - dias_transcurridos) / days_total` (la
   parte proporcional a los días que le quedaban, ya que los días ya transcurridos de esa
   ventana no se recuperan) — se **suma** al nuevo desvío de hoy, y se **reinicia** la ventana:
   `days_total = 3`, `created_at = hoy`, con `delta = restante + delta_de_hoy`. Simplifica el
   caso de desvíos consecutivos, a costa de alargar un poco la ventana de compensación si se
   encadenan varios días seguidos fuera de margen.
5. Cada vez que se calcula un target (determinista o IA) o se genera un día, se comprueba si hay
   una fila en `pending_compensation` con `dias_transcurridos = (hoy - created_at).days <
   days_total`; si la hay, el target de **hoy** (no de "el próximo cálculo", sino de la fecha
   real de hoy) se ajusta restando `delta / days_total` (redondeado) en cada magnitud. El mismo
   ajuste se aplica sin importar cuántas veces se recalcule ese mismo día — depende de la fecha,
   no de un contador de llamadas.
6. En cuanto `dias_transcurridos >= days_total`, la compensación se considera terminada; la fila
   se borra la próxima vez que se consulta (o mediante una limpieza perezosa al calcular
   cualquier target).

**Corregir una comida de un día ya cerrado:** si el día ya se cerró y generó una compensación
que sigue activa (`dias_transcurridos < days_total`), y el usuario corrige una comida de ese
día, se recalcula el `delta` de ese día con el dato corregido y se **reemplaza** el `delta` de
la fila `pending_compensation` por el nuevo valor (sin tocar `created_at`, que sigue marcando
cuándo empezó la ventana de 3 días) — los días de compensación ya transcurridos no se
recuperan retroactivamente, solo se ajusta el tamaño del desvío que queda por compensar en los
días restantes de la ventana.

**Ejemplo:** te pasaste 300 kcal hoy → `kcal_delta = 300` → los próximos 3 días el target baja
100 kcal cada uno, hasta que se agoten los 3 días.

## Flujo de datos

**Registrar algo comido fuera de plan:**
1. Formulario simple: lista de (alimento, cantidad) para hoy.
2. Se emparejan contra el catálogo, se calculan macros reales, se guardan como `diet_meals` de
   la `diet_version` de hoy (creándola si no existe). **No** dispara la compensación por sí
   solo — se puede repetir varias veces a lo largo del día.
3. Cuando el usuario decide que ya ha terminado de comer por hoy, pulsa "Cerrar el día de hoy",
   que ejecuta el algoritmo de compensación descrito arriba contra el total acumulado del día.

**Corregir una comida de un día ya cerrado (guardado o cerrado ad-hoc):**
1. El usuario ve las comidas de ese día (reutilizando datos ya existentes de `diet_meals`) y
   edita una: nuevo alimento y/o cantidad.
2. Se re-empareja y se actualiza esa fila de `diet_meals`.
3. Si ese día ya había generado una compensación pendiente que sigue activa, se recalcula y se
   reemplaza el `delta` tal como describe el algoritmo (sin reiniciar `created_at`).

**Antojo que ajusta el resto del día:**
1. El usuario, desde una pantalla de antojo, indica el alimento fijo + cantidad que le apetece,
   y qué comidas del día ya están fijas (ya comidas) frente a las que quedan por decidir.
2. Se calcula el presupuesto restante (target del día menos las comidas ya fijas, incluido el
   antojo) y se generan las comidas que faltan con el Agent SDK, con el mismo reintento hasta
   ±5% del Subsistema 3.
3. El resultado se puede guardar como el resto de generaciones del Subsistema 3 (dispara
   también el chequeo de compensación al guardar).

## Manejo de errores

- Sin macro target disponible → igual que el Subsistema 3, pide completar el paso previo.
- El antojo por sí solo ya excede el target del día (ej. pides comer 2000 kcal de golosinas y
  el target total es 1800) → se avisa claramente que no cabe, sin intentar generar nada
  imposible, y se sugiere reducirlo.
- Alimento sin match en el catálogo (tanto en registro ad-hoc como en antojo) → mismo
  tratamiento que el Subsistema 3: se marca "sin verificar", no cuenta en el total real.

## Pruebas

- Algoritmo de compensación (crear, acumular, aplicar, agotar los 3 días): funciones puras,
  tests con datos sintéticos.
- Registro de alimento fuera de plan: test end-to-end vía `TestClient`.
- Corrección de una comida de un día guardado: test end-to-end.
- Antojo con ajuste del resto del día: test con Agent SDK mockeado (mismo patrón que el
  Subsistema 3).
- Integración: verificar que un target calculado (Subsistema 2) o un día generado (Subsistema
  3) refleja el ajuste de una compensación pendiente cuando la hay, y que deja de aplicarse tras
  3 días.
