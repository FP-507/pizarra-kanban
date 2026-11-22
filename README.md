# Pizarra · Kanban colaborativo en tiempo real

Tablero Kanban donde varias personas trabajan al mismo tiempo: cada tarjeta que alguien crea, edita, mueve o borra **aparece al instante en las pantallas de los demás**, con indicador de quién está conectado. Backend en **FastAPI con WebSockets y SQLite**; frontend en **JavaScript puro**, sin frameworks.

![tests](https://github.com/FP-507/pizarra-kanban/actions/workflows/tests.yml/badge.svg)

## Funciones

- **Tiempo real**: los cambios se difunden por WebSocket a todos los conectados al mismo tablero, con avisos del tipo «Ana movió *Conectar API de pagos* a Revisión».
- **Presencia**: iniciales de cada persona conectada, que se actualizan al entrar y salir.
- **Arrastrar y soltar** entre columnas y dentro de una columna, con marcador de posición.
- **Editor** de tarjetas: título, descripción, etiqueta de color (diseño, backend, frontend, bug, urgente) y columna.
- **Tableros independientes por URL**: `/t/mi-equipo`. Se comparten copiando el enlace.
- **Reconexión automática** con backoff exponencial; al volver, recarga el estado para no perder cambios.
- **Accesible**: tarjetas enfocables con teclado (Enter para editar), etiquetas ARIA y movimiento reducido.

## Arquitectura

```
navegador ──WebSocket──► FastAPI /ws/{tablero} ──► tablero.py (reglas) ──► SQLite
    ▲                         │
    └──── evento difundido ◄──┘  (a todas las conexiones del tablero)
```

- **El servidor es la fuente de verdad**: el cliente envía acciones (`crear`, `editar`, `mover`, `borrar`), el servidor las valida con Pydantic, las guarda, renumera posiciones y difunde el evento resultante.
- **Los errores solo vuelven a quien los causó**; los eventos válidos van a todo el tablero.
- **Lógica separada de la red**: [`app/tablero.py`](app/tablero.py) contiene las operaciones y se prueba sin servidor.

### Protocolo

| Cliente → servidor | Servidor → clientes |
|---|---|
| `{"accion": "crear", "datos": {...}}` | `{"tipo": "creada", "tarjeta": {...}, "por": "Ana"}` |
| `{"accion": "mover", "id", "columna", "posicion"}` | `{"tipo": "movida", "tarjetas": [...]}` |
| `{"accion": "editar", "id", "datos"}` | `{"tipo": "editada", "tarjeta": {...}}` |
| `{"accion": "borrar", "id"}` | `{"tipo": "borrada", "id", "tarjetas": [...]}` |
| | `{"tipo": "presencia", "personas": [...]}` |
| | `{"tipo": "error", "mensaje", "ref"}` (solo al emisor) |

## Cómo ejecutarlo

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Abre <http://127.0.0.1:8000> en dos ventanas (o en dos dispositivos de la misma red) y mueve tarjetas en una para verlas cambiar en la otra.

```bash
docker build -t pizarra . && docker run -p 8000:8000 pizarra
```

## Tests

```bash
pytest -v
```

Incluyen la lógica de ordenamiento (mover dentro de una columna y entre columnas, borrar cerrando huecos, aislamiento entre tableros) y pruebas de **WebSocket con dos clientes simultáneos** que verifican la difusión y la presencia.

## Estructura

```
app/    main.py (HTTP + WebSocket + sala de conexiones) · tablero.py (modelo y operaciones)
web/    index.html · app.js · estilo.css
tests/
```
