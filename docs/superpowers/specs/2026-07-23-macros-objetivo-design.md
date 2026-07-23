# Subsistema 2: Calculadora de macros objetivo — Diseño

## Contexto

Programa nutricional personal (usuario único). El Subsistema 1 (fundamentos)
está completo: catálogo de alimentos de Mercadona, histórico real de 5
versiones de dieta y 5 análisis de composición corporal cargados con 100% de
cobertura de macros, y un dashboard de evolución.

Este documento cubre el Subsistema 2: a partir de ese histórico, calcular qué
macros objetivo debería seguir el usuario de aquí en adelante.

## Alcance

- Perfil de usuario básico (edad, sexo, altura, nivel de actividad, objetivo
  actual).
- Dos métodos de cálculo de macros objetivo, mostrados en comparación:
  1. Determinista — TDEE real calculado a partir del histórico de energía
     (kcal comidas vs cambio real de masa grasa observado).
  2. Agente de IA (Claude Agent SDK, suscripción del usuario) — razona sobre
     el mismo histórico y da una recomendación con explicación.
- Tres objetivos soportados: déficit (definición), mantenimiento, superávit
  (volumen). El usuario elige cuál quiere en cada momento.

Fuera de alcance: generación de dietas variadas, motor de compensación por
excesos o sustitución por antojo (subsistemas 3 y 4).

## Arquitectura

- Mismo stack que el Subsistema 1: FastAPI + Jinja2/HTMX + Postgres (psycopg
  directo, sin ORM), Docker Compose local.
- El cálculo determinista es Python puro (sin llamadas externas), instantáneo,
  se recalcula en cada visita a la página.
- El cálculo con IA usa el Claude Agent SDK con el patrón ya validado en el
  Subsistema 1: `setting_sources=[]`, `cwd` propio fuera del proyecto,
  `system_prompt` explícito, `output_format` con JSON schema. **No se
  recalcula automáticamente** en cada carga de página (evita gastar cuota de
  la suscripción sin necesidad) — solo cuando el usuario pulsa un botón
  "recalcular con IA". El resultado se persiste en `macro_targets`.

## Modelo de datos (Postgres, nuevas tablas)

- `user_profile` — fila única (un solo usuario):
  `age`, `sex` ('M'/'F'), `height_cm`, `activity_level` (uno de:
  'sedentario', 'ligero', 'moderado', 'intenso' — multiplicador de Mifflin-St
  Jeor 1.2/1.375/1.55/1.725 respectivamente, solo usado en el respaldo),
  `current_goal` ('deficit'/'maintenance'/'surplus'), `updated_at`.
- `macro_targets` — histórico de resultados calculados:
  `method` ('formula'/'agent'), `goal`, `kcal`, `protein_g`, `carbs_g`,
  `fat_g`, `explanation` (nullable, solo para el método agente),
  `computed_at`.

## Cálculo determinista (TDEE real)

1. Ordenar `body_metrics` por `measured_on`.
2. Para cada par consecutivo de mediciones (m1, m2):
   - masa grasa en cada punto = `weight_kg * body_fat_pct / 100`.
   - kcal medias diarias en ese intervalo = media de las kcal totales de las
     `diet_versions` cuyo `valid_from` cae dentro de `[m1.measured_on,
     m2.measured_on)`.
   - cambio de energía por grasa = `(masa_grasa_m1 - masa_grasa_m2) * 9300`
     kcal (positivo si se perdió grasa).
   - TDEE implícito del tramo = kcal medias diarias + cambio de energía por
     grasa / días del tramo.
3. TDEE real = media de los TDEE implícitos de todos los tramos válidos.
4. Ajuste según objetivo: déficit −20%, mantenimiento +0%, superávit +10%
   sobre el TDEE real.
5. Reparto de macros, usando el peso corporal de la medición más reciente:
   - Proteína: 2.2 g/kg en déficit (proteger músculo), 1.8 g/kg en
     mantenimiento y superávit.
   - Grasa: 25% de las kcal totales del objetivo, en todos los casos.
   - Carbohidratos: el resto de kcal tras proteína y grasa.

**Respaldo**: si hay menos de 2 `body_metrics`, no se puede calcular energía
real — se usa Mifflin-St Jeor con los datos del perfil (edad, sexo, altura,
peso más reciente) más un multiplicador de actividad como TDEE de partida.

## Cálculo con IA (Agent SDK)

Se construye un resumen compacto del histórico (TDEE real ya calculado si
existe, evolución de peso/grasa, perfil, objetivo elegido) y se envía al
Agent SDK pidiendo, vía `output_format` con JSON schema: `kcal`,
`protein_g`, `carbs_g`, `fat_g`, `explanation` (texto breve justificando la
recomendación). Se guarda el resultado en `macro_targets` con
`method='agent'`.

## Flujo de datos

1. El usuario rellena/actualiza su perfil y elige objetivo en un formulario
   web (`user_profile`).
2. Al visitar la página de macros objetivo, se calcula al vuelo el método
   determinista y se muestra junto al último resultado guardado del método
   IA (si existe).
3. Un botón "Recalcular con IA" dispara una nueva llamada al Agent SDK y
   guarda el resultado nuevo en `macro_targets`.
4. Ambos resultados se muestran en una vista de comparación (kcal y macros
   lado a lado).

## Manejo de errores

- Menos de 2 `body_metrics` → cae a Mifflin-St Jeor (ver respaldo arriba),
  no bloquea la página.
- Fallo en la llamada al Agent SDK → se muestra un error en esa sección de
  la página, sin afectar al resultado determinista (que es instantáneo e
  independiente).
- Perfil incompleto (sin rellenar) → la página de macros objetivo pide
  rellenarlo primero antes de calcular nada.

## Pruebas

- Función de TDEE real: datos sintéticos con valores conocidos, verificar el
  resultado exacto del cálculo (masa grasa, energía, promedio de tramos).
- Función de reparto de macros por objetivo: verificar proteína/grasa/carbos
  para cada uno de los tres objetivos con un TDEE de ejemplo.
- Respaldo Mifflin-St Jeor: verificar resultado con menos de 2
  `body_metrics`.
- Llamada al Agent SDK: test con el cliente mockeado (mismo patrón que las
  Tareas 4 y 5 del Subsistema 1), sin llamada real en los tests automáticos.
- Formulario de perfil: test de guardado/carga vía `TestClient`.
