# Subsistema 1: Fundamentos — Diseño

## Contexto

Programa nutricional personal (usuario único) para sustituir el seguimiento con
nutricionista tras una fase de definición (16kg perdidos). El proyecto se
decompuso en 4 subsistemas secuenciales:

1. **Fundamentos** (este documento) — datos de alimentos + histórico + esqueleto web
2. Calculadora de macros objetivo (analiza el histórico → macros de definición)
3. Generador de dietas variadas
4. Motor de ajuste (compensación tras excesos + sustitución por antojo)

Este documento cubre solo el subsistema 1.

## Alcance

- Base de datos de alimentos (catálogo Mercadona)
- Carga única e inicial de PDFs históricos (dietas + análisis corporales) —
  no es una funcionalidad de subida continua, es una importación de una vez
- Esqueleto mínimo de la aplicación web

Fuera de alcance: cálculo de macros objetivo, generación de dietas, ajustes
por exceso/antojo, cualquier uso del Agent SDK como agente conversacional.

## Arquitectura

- **Hosting**: Docker Compose en el portátil del usuario (server local), dos
  servicios: `postgres` y `app` (FastAPI).
- **Acceso remoto**: Tailscale (VPN privada, plan Personal gratuito) — no se
  expone nada públicamente. No hay login propio; la red privada de Tailscale
  es el único perímetro de seguridad, adecuado para un usuario único.
- **Frontend**: FastAPI sirve páginas Jinja2 + HTMX. Sin build de Node, sin
  SPA separada.
- **Backend**: Python + FastAPI.
- **Base de datos**: Postgres.
- **Motor IA**: extracción de datos de PDFs (ver más abajo) vía el Claude
  Agent SDK, autenticado con la suscripción del usuario — no se usa la API de
  pago por token en este subsistema (decisión revisada tras la implementación
  inicial: el usuario no dispone de saldo de API, así que toda llamada a
  Claude en este proyecto usa la suscripción).

## Modelo de datos (Postgres)

- `foods` — catálogo de alimentos sincronizado desde `mercaapi`
  (macros por 100g, categoría, nombre, id de producto Mercadona,
  fecha de última sincronización)
- `diet_versions` — una fila por cada versión de dieta del nutricionista
  (fecha de inicio, fecha de fin, nombre de archivo PDF origen)
- `diet_meals` — comidas concretas de cada versión (día, tipo de comida,
  texto del alimento, gramos, referencia opcional a `foods` si hubo match)
- `body_metrics` — una fila por análisis corporal (fecha, peso, % grasa,
  masa muscular, nombre de archivo PDF origen)

## Flujo de datos

1. **Sincronización de alimentos**: script puntual que descarga el catálogo
   de `mercaapi` (con fallback al dump de `datania/mercadona-catalog` si
   `mercaapi` no responde) y puebla `foods`.
2. **Ingesta inicial de PDFs** (una sola vez, por lotes): todos los PDFs de
   dietas y análisis corporales existentes se procesan en un único script de
   importación. No hay flujo de subida recurrente — una vez importados,
   quedan en la base de datos de forma permanente.
3. **Parseo de PDFs**: cada PDF se procesa con el Claude Agent SDK
   (`claude_agent_sdk.query`, autenticado con la suscripción, herramienta
   `Read` para leer el PDF, `output_format` con JSON schema fijo: comidas +
   gramos + fecha, o métricas corporales + fecha) para extraer los datos
   estructurados. Se elige esto en vez de un parser regex porque el formato
   de los PDFs del nutricionista varía entre versiones.
4. **Enlace con `foods`**: los alimentos extraídos del texto se intentan
   emparejar por nombre contra `foods`. Lo que no cuadre queda sin enlazar
   para revisión manual posterior.
5. **Dashboard de evolución**: página que muestra peso/grasa corporal en el
   tiempo y las macros reales de cada versión de dieta — es la base de datos
   que consumirá el subsistema 2 (calculadora de macros objetivo).

## Requisito no negociable para todo uso del Agent SDK en este proyecto

Validado en esta sesión: el Claude Agent SDK puede autenticarse contra la
suscripción de Claude (Pro/Max/Code) en vez de una API key de pago por token.
Sin embargo, por defecto hereda toda la configuración de Claude Code de este
proyecto (hooks, skills, plugins), lo que añade ~26.000 tokens de overhead
por llamada. Con `setting_sources=[]`, un `cwd` propio (fuera de este
proyecto) y un `system_prompt` explícito, el overhead baja a ~2.900 tokens
(~9x menos). **Todo uso del Agent SDK en este proyecto debe configurarse
así** — incluida la extracción de PDFs de este subsistema (Tareas 4 y 5),
que originalmente se implementó con la API de pago y se migró después al
Agent SDK por decisión del usuario (sin saldo de API disponible). Para leer
el contenido del PDF se usa la herramienta `Read` del propio agente
(`allowed_tools=["Read"]`), en vez de mandar el PDF en base64 como bloque de
documento — el Agent SDK no expone ese mecanismo de la API de Mensajes
directamente, pero `Read` ya soporta PDFs de forma nativa.

## Manejo de errores

- Si `mercaapi` no responde durante la sincronización, se usa el dump de
  `datania/mercadona-catalog` como respaldo.
- Alimentos de un PDF que no encuentran match en `foods`: se guardan sin
  enlazar (no bloquea la ingesta) para revisión manual.
- Fallos de parseo de un PDF concreto no deben abortar la ingesta del resto
  de PDFs del lote.

## Pruebas

- Comprobación mínima tras la ingesta: cada `diet_version` y `body_metrics`
  importado corresponde a un PDF de entrada (conteo de archivos vs filas).
- Verificación manual puntual de que las macros calculadas para una versión
  de dieta conocida coinciden con lo que recuerda el usuario.
