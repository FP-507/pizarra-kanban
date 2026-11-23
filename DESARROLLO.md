# Notas de desarrollo · Pizarra (Kanban en tiempo real)

Guía para retomar el proyecto: cómo está armado, por qué y cómo cambiarlo.

## Puesta en marcha

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload       # http://127.0.0.1:8000 → redirige a /t/equipo-demo
pytest -q
```

Para probar la colaboración: abrir la misma URL en dos ventanas. Variable opcional `DATABASE_URL` (por defecto `sqlite:///./pizarra.db`).

## Piezas

| Archivo | Responsabilidad |
|---|---|
| `app/tablero.py` | Tabla `Tarjeta`, esquema de entrada `DatosTarjeta` (validado con Pydantic), constantes `COLUMNAS` y `ETIQUETAS`, y operaciones `crear`, `editar`, `mover`, `borrar`. No sabe nada de HTTP ni de WebSocket |
| `app/main.py` | Clase `Sala` (conexiones por tablero y presencia), rutas HTTP (`/`, `/t/{slug}`, `/api/tableros/{slug}`), `procesar()` (acción → evento) y el endpoint `/ws/{slug}` |
| `web/app.js` | Estado local (`Map` de tarjetas), render del tablero, arrastrar y soltar, editor en `<dialog>`, `aplicar(evento)` y reconexión |
| `web/index.html`, `web/estilo.css` | Estructura y estilos (servidos en `/static`) |

## Flujo de una acción

1. El cliente envía por WebSocket `{"accion": "mover", "id": 7, "columna": "revision", "posicion": 0, "ref": "..."}`.
2. `socket()` llama a `procesar()`, que valida, ejecuta la operación de `tablero.py` en una sesión nueva y arma el evento (`{"tipo": "movida", "tarjetas": [...], "por": "Ana"}`).
3. Si todo sale bien, `sala.difundir()` envía el evento a **todas** las conexiones del tablero (incluida la que lo originó). Si falla, solo el emisor recibe `{"tipo": "error", "mensaje", "ref"}`.
4. Cada cliente aplica el evento a su estado local en `aplicar()` y vuelve a dibujar, resaltando las tarjetas que cambiaron.

El campo `ref` lo genera el cliente y vuelve en la respuesta; sirve para saber qué acción propia falló.

## Decisiones

- **El servidor es la fuente de verdad.** El cliente no modifica su estado al arrastrar: espera el evento del servidor. Así todos ven exactamente el mismo orden aunque dos personas muevan tarjetas a la vez.
- **Posiciones densas (0, 1, 2…)** que se renumeran en cada movimiento o borrado. `mover()` devuelve todas las tarjetas que cambiaron para que los clientes actualicen sus posiciones sin recargar.
- **Lógica separada de la red:** `tablero.py` se prueba con una sesión de SQLite en memoria, sin levantar el servidor.
- **Tableros por URL** (slug de 3 a 40 caracteres: minúsculas, números y guiones) sin cuentas: compartir el enlace es compartir el tablero. El nombre del participante llega como parámetro `?nombre=` y se recorta a 30 caracteres.
- **Límite de 300 tarjetas por tablero** para que un tablero abierto no crezca sin control.
- **Conexiones caídas:** `difundir()` descarta los sockets que fallan al enviar; el cliente se reconecta con backoff exponencial y vuelve a pedir el estado completo (`cargarEstado()`).
- **Sala en memoria:** la presencia vive en el proceso. Con un solo proceso de uvicorn es suficiente.

## Tests

`tests/test_pizarra.py`: posiciones al crear, mover entre columnas y dentro de la misma, borrar cerrando huecos, aislamiento entre tableros, validaciones, slug inválido, y dos pruebas de WebSocket con **dos clientes a la vez** (difusión en vivo y presencia; errores que solo recibe el emisor). Usan `TestClient` con una base en memoria.

## Despliegue (demo pública en Render)

- `render.yaml` define el servicio (Docker, plan gratuito). En Render: **New > Blueprint**, elegir este repositorio y confirmar. Cada `push` a `main` vuelve a desplegar.
- El `Dockerfile` escucha en `$PORT` (lo pone Render; en local, 8000) y corre como usuario sin privilegios.
- `SEMBRAR_DEMO=1` carga datos de ejemplo al arrancar si la base está vacía (`sembrar_demo()` en `app/tablero.py`, tablero `equipo-demo`).
- Plan gratuito: el servicio se duerme tras 15 minutos sin uso (el primer pedido tarda cerca de un minuto) y el disco no es persistente, así que la demo vuelve a los datos de ejemplo en cada reinicio. Para guardar datos de verdad haría falta un disco persistente o una base externa (cambiar `DATABASE_URL`).

## Cómo extenderlo

- **Nueva acción** (por ejemplo, `archivar`): función en `tablero.py`, rama en `procesar()` que devuelva un evento con `tipo` nuevo, y un caso en `aplicar()` de `web/app.js`. Agregar un test de lógica y uno de WebSocket.
- **Nueva columna o etiqueta:** sumarla a `COLUMNAS` o `ETIQUETAS` en `tablero.py` y su nombre visible en `NOMBRES_COL` o `NOMBRES_ETQ` en `app.js` (y su color en el CSS, si es etiqueta).
- **Varios procesos o servidores:** la `Sala` en memoria no se comparte entre procesos; habría que difundir con Redis pub/sub o similar.

## Pendientes

- Autenticación y permisos por tablero (hoy cualquiera con el enlace puede editar).
- Historial de cambios o deshacer.
- La edición simultánea de la misma tarjeta la resuelve "el último que guarda gana".
