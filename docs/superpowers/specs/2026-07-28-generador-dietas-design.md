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
- Botón "Generar otra" para pedir una variante distinta del mismo día sin
  cambiar nada más (cada pulsación es una llamada nueva a la suscripción).
- La dieta generada **no se persiste** en la base de datos: es una sugerencia
  efímera que se muestra en pantalla y desaparece si el usuario navega fuera o
  recarga. Si el usuario decide seguirla de verdad, registrar que la siguió es
  una decisión de un subsistema futuro (fuera de alcance aquí).

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

## Flujo de datos

1. El usuario visita `/generar-dieta`, elige el método de macros objetivo
   (determinista o IA guardada) en un formulario simple, y pulsa "Generar".
2. El backend calcula el target de macros con el método elegido (reutilizando
   Subsistema 2). Si no hay ningún target disponible (perfil incompleto para
   el determinista, o nunca se ha pulsado "Recalcular con IA" para el de IA),
   la página lo indica y enlaza a `/perfil` o `/macros` según corresponda, sin
   generar nada.
3. El backend llama al Agent SDK con: los macros objetivo, el objetivo actual
   del usuario (déficit/mantenimiento/superávit), y la lista fija de
   alimentos a evitar — pidiendo, vía `output_format` con JSON schema, una
   propuesta de 4 comidas (desayuno, comida, merienda, cena), cada una con
   `food_item` (nombre libre, tipo producto de supermercado español) y
   `quantity_grams`.
4. El backend intenta emparejar cada `food_item` propuesto contra la tabla
   `foods` (misma similitud de trigramas, umbral 0.3). Para los que emparejan,
   calcula kcal/macros reales a partir de los datos nutricionales del
   catálogo. Para los que no emparejan, se muestran igual pero marcados como
   "sin verificar" y se excluyen de la suma de macros reales (para no falsear
   el total).
5. La página muestra las 4 comidas propuestas, con los macros reales
   calculados (sumados) junto al target, y cualquier aviso de alimentos sin
   verificar.
6. El botón "Generar otra" repite los pasos 3-5 sin recargar la elección de
   método (nueva llamada al Agent SDK, nueva propuesta).

## Manejo de errores

- Sin macro target disponible → la página no genera nada, pide completar el
  paso previo correspondiente (perfil+medidas, o pulsar "Recalcular con IA"
  al menos una vez).
- Fallo en la llamada al Agent SDK → mensaje de error en esa sección, sin
  romper el resto de la página.
- Alimento propuesto sin match en el catálogo → se muestra marcado como "no
  verificado", excluido de la suma de macros reales.

## Pruebas

- Emparejamiento alimento→catálogo: tests con datos sintéticos (reutilizando
  o extendiendo los ya existentes de `match_foods.py`).
- Llamada al Agent SDK: test con cliente mockeado (mismo patrón que
  `tests/test_agent_macros.py` y `tests/test_ingest_diet_pdfs.py`), sin
  llamada real en los tests automáticos.
- Ruta de generación: test end-to-end vía `TestClient` con el Agent SDK y el
  emparejamiento mockeados.
