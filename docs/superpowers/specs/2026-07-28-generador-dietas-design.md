# Subsistema 3: Generador de dietas variadas — Diseño

## Contexto

Programa nutricional personal (usuario único). Los Subsistemas 1 (fundamentos) y 2
(calculadora de macros objetivo) están completos: catálogo de alimentos de Mercadona,
histórico real de dietas y composición corporal, perfil de usuario, registro manual
de medidas del gimnasio, y dos formas de calcular macros objetivo (determinista y
Agent SDK bajo demanda).

Este documento cubre el Subsistema 3: generar, día a día, una propuesta de dieta
variada que se ajuste a los macros objetivo ya calculados, para no tener que
diseñar manualmente qué comer cada día.

## Alcance

- Generar **un día completo** (desayuno, comida, merienda, cena) por cada
  generación — no una semana entera.
- El usuario elige, cada vez que genera, de dónde sale el objetivo de macros a
  cuadrar: el método determinista (TDEE real, calculado al vuelo) o el último
  resultado guardado del método IA (`macro_targets`, `method='agent'`).
- El motor de generación es el **Claude Agent SDK** (mismo patrón validado de
  suscripción, no API de pago) — compone comidas realistas con productos de
  supermercado español, ajustando cantidades para acercarse a los macros
  objetivo.
- El generador evita una lista fija de alimentos ya marcados como rechazados
  por el usuario: brócoli, vinagre, col lombarda, calabacín (los mismos que se
  excluyeron a mano del histórico en el Subsistema 1). Es una constante en
  código, no una tabla nueva — no hay necesidad de gestión dinámica todavía.
- Los alimentos que el agente propone se contrastan contra el catálogo real de
  Mercadona usando el mismo emparejamiento por similitud de trigramas ya
  validado en `scripts/match_foods.py` (`similarity > 0.3`), para calcular
  macros **reales** de cada comida propuesta — no se confía en la aritmética
  del propio agente.
- El usuario puede dar, opcionalmente, una **directriz de texto libre por
  cada comida** (ej. "jamón" en desayuno, "algo con patata" en comida,
  "salmón" en cena) antes de generar. El agente las trata como orientación
  suave, no como restricción exacta — sigue ajustando cantidades y
  acompañamientos para cuadrar los macros objetivo.
- Botón **"Generar otro día"** para pedir una variante distinta completa sin
  cambiar nada más (cada pulsación es una llamada nueva a la suscripción).
- Además, el usuario puede **regenerar una sola comida** (ej. solo la cena)
  manteniendo el resto del día igual, con una directriz opcional nueva solo
  para esa comida. La comida nueva se genera para cuadrar el **presupuesto de
  macros restante** del día (el target total menos las macros reales ya
  calculadas de las otras 3 comidas que se mantienen fijas).
- La dieta generada es **efímera mientras se está generando/ajustando**
  (nada se guarda solo por pulsar "Generar" o "Generar otra"), pero el
  usuario puede pulsar **"Guardar este día como comido"** para persistirla de
  verdad: crea una `diet_version` nueva (un solo día) con sus `diet_meals`,
  usando el mismo `matched_food_id` ya resuelto durante la generación — sin
  necesidad de volver a emparejar nada. Esto es importante para que el
  cálculo de TDEE real (Subsistema 2) siga teniendo datos de dieta frescos a
  medida que el usuario deje de depender de las dietas históricas del
  nutricionista y empiece a generar las suyas — el mismo motivo por el que
  el Subsistema 2 añadió el registro manual de medidas del gimnasio.
  Guardar solo el día que el usuario confirma (no cada intento de
  "Generar otra") evita contaminar el histórico con propuestas rechazadas.

Fuera de alcance: generar una semana completa; motor de compensación por
excesos o sustitución por antojo (Subsistema 4); edición manual de la dieta
generada; gestión de la lista de alimentos rechazados desde la UI.

## Arquitectura

- Mismo stack que los Subsistemas 1-2: FastAPI + Jinja2/HTMX, Postgres
  (psycopg directo, sin ORM), Docker Compose (incluyendo el CLI de Claude Code
  ya instalado en la imagen desde el Subsistema 2 para que esto funcione tanto
  en el host como en el contenedor).
- El cálculo del macro objetivo reutiliza funciones ya existentes de
  `app/macros.py` y `app/main.py` (Subsistema 2): `compute_formula_macro_target`
  y `get_latest_agent_macro_target`.
- La llamada al Agent SDK sigue el mismo patrón validado (`setting_sources=[]`,
  `cwd` propio, `output_format` con JSON schema, `anyio.run()`), igual que
  `app/agent_macros.py`.
- El emparejamiento alimento-propuesto → catálogo reutiliza la misma consulta
  de similitud de trigramas de `scripts/match_foods.py` (se extrae a una
  función compartida si el plan de implementación lo justifica, para no
  duplicar la consulta SQL).
- **Sin estado en el servidor:** como la dieta no se persiste, el "día
  actual" (las 4 comidas ya generadas, con su alimento/gramos/macros reales)
  viaja en el propio HTML de la página, como campos ocultos de formulario —
  no hay sesión ni tabla temporal. Regenerar una sola comida reenvía por HTMX
  el estado de las otras 3 comidas (ya fijadas) junto con la directriz nueva
  para la comida a cambiar, y el servidor responde solo con el fragmento de
  esa comida actualizado.

## Flujo de datos

**Generación inicial del día:**

1. El usuario visita `/generar-dieta`, elige el método de macros objetivo
   (determinista o IA guardada), y opcionalmente escribe una directriz de
   texto libre por comida (desayuno/comida/merienda/cena — cualquiera puede
   quedar vacía), y pulsa "Generar".
2. El backend calcula el target de macros con el método elegido (reutilizando
   Subsistema 2). Si no hay ningún target disponible (perfil incompleto para
   el determinista, o nunca se ha pulsado "Recalcular con IA" para el de IA),
   la página lo indica y enlaza a `/perfil` o `/macros` según corresponda, sin
   generar nada.
3. El backend llama al Agent SDK con: los macros objetivo totales del día, el
   objetivo actual del usuario (déficit/mantenimiento/superávit), la lista
   fija de alimentos a evitar, y las directrices por comida si las hay —
   pidiendo, vía `output_format` con JSON schema, las 4 comidas (desayuno,
   comida, merienda, cena), cada una con `food_item` (nombre libre, tipo
   producto de supermercado español) y `quantity_grams`.
4. El backend intenta emparejar cada `food_item` propuesto contra la tabla
   `foods` (misma similitud de trigramas, umbral 0.3). Para los que emparejan,
   calcula kcal/macros reales a partir de los datos nutricionales del
   catálogo. Para los que no emparejan, se muestran igual pero marcados como
   "sin verificar" y se excluyen de la suma de macros reales (para no falsear
   el total).
5. La página muestra las 4 comidas propuestas (cada una como su propia
   tarjeta, con un campo oculto con sus datos para poder reenviarlos después),
   con los macros reales calculados (sumados) junto al target, y cualquier
   aviso de alimentos sin verificar.

**Regenerar el día completo:** el botón "Generar otro día" repite los pasos
3-5 con el mismo target y las mismas directrices por comida (nueva llamada al
Agent SDK, propuesta nueva de las 4 comidas).

**Regenerar una sola comida (ej. solo la cena):**

1. El usuario edita (o deja igual) la directriz de esa comida y pulsa
   "Cambiar esta comida". La petición HTMX incluye los datos ya fijados de
   las otras 3 comidas (vía los campos ocultos del paso 5 anterior) y la
   directriz nueva para la comida a cambiar.
2. El backend calcula el **presupuesto restante**: el target total del día
   menos la suma de las macros reales ya calculadas de las 3 comidas fijas.
3. El backend llama al Agent SDK igual que en la generación inicial, pero
   pidiendo solo esa comida, con el presupuesto restante como objetivo y la
   directriz nueva.
4. Se empareja el alimento propuesto contra el catálogo igual que antes, y se
   devuelve solo el fragmento HTML de esa comida actualizada (HTMX reemplaza
   únicamente esa tarjeta, las otras 3 no se tocan).

**Guardar el día como comido:**

1. El usuario pulsa "Guardar este día como comido". La petición incluye los
   datos ya fijados de las 4 comidas actuales (campos ocultos: `food_item`,
   `quantity_grams`, `matched_food_id` — este último puede ser `null` si esa
   comida quedó "sin verificar").
2. El backend crea una fila en `diet_versions` (`valid_from` = fecha de hoy,
   `valid_to` = la misma fecha — es un día suelto, no un plan de varias
   semanas) y una fila en `diet_meals` por cada una de las 4 comidas,
   reutilizando el `matched_food_id` ya resuelto (sin volver a emparejar). El
   `day_label` es el mismo para las 4 (ej. el nombre del día de la semana),
   para que el cálculo de kcal media diaria de `get_diet_versions_daily_kcal`
   (Subsistema 2) las cuente como un solo día.
3. Confirmación visual de que se guardó; el usuario puede seguir generando
   otros días después sin que eso afecte a lo ya guardado.

## Manejo de errores

- Sin macro target disponible → la página no genera nada, pide completar el
  paso previo correspondiente (perfil+medidas, o pulsar "Recalcular con IA"
  al menos una vez).
- Fallo en la llamada al Agent SDK → mensaje de error en esa sección, sin
  romper el resto de la página.
- Alimento propuesto sin match en el catálogo → se muestra marcado como "no
  verificado", excluido de la suma de macros reales; si el usuario guarda el
  día igualmente, esa comida se guarda con `matched_food_id = NULL` (igual
  que ya permite el esquema desde el Subsistema 1 para comidas históricas sin
  emparejar).

## Pruebas

- Emparejamiento alimento→catálogo: tests con datos sintéticos (reutilizando
  o extendiendo los ya existentes de `match_foods.py`).
- Cálculo del presupuesto restante (target total menos 3 comidas fijas):
  función pura, tests con datos sintéticos conocidos.
- Llamada al Agent SDK (generación de día completo y de una sola comida):
  test con cliente mockeado (mismo patrón que `tests/test_agent_macros.py` y
  `tests/test_ingest_diet_pdfs.py`), sin llamada real en los tests
  automáticos. Verificar que las directrices por comida se incluyen en el
  prompt cuando existen.
- Ruta de generación inicial y ruta de regenerar una sola comida: tests
  end-to-end vía `TestClient` con el Agent SDK y el emparejamiento
  mockeados.
- Ruta de guardar el día: test end-to-end vía `TestClient` que verifica que
  se crea una `diet_version` y sus `diet_meals` con los `matched_food_id`
  correctos (incluyendo el caso de una comida con `matched_food_id = NULL`).
