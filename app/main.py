"""Servidor del tablero Kanban: REST para leer y WebSocket para colaborar en tiempo real."""

import os
import re
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine

from . import tablero as T

ESTATICOS = Path(__file__).resolve().parent.parent / "web"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pizarra.db")
SLUG = re.compile(r"^[a-z0-9-]{3,40}$")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class Sala:
    """Conexiones activas por tablero, con el nombre de cada participante."""

    def __init__(self):
        self.conexiones: dict[str, dict[WebSocket, str]] = defaultdict(dict)

    def presentes(self, tablero: str) -> list[str]:
        return sorted(self.conexiones[tablero].values())

    async def unir(self, tablero: str, ws: WebSocket, nombre: str):
        self.conexiones[tablero][ws] = nombre
        await self.difundir(tablero, {"tipo": "presencia", "personas": self.presentes(tablero)})

    async def salir(self, tablero: str, ws: WebSocket):
        self.conexiones[tablero].pop(ws, None)
        if self.conexiones[tablero]:
            await self.difundir(tablero, {"tipo": "presencia", "personas": self.presentes(tablero)})
        else:
            del self.conexiones[tablero]

    async def difundir(self, tablero: str, mensaje: dict):
        caidas = []
        for ws in list(self.conexiones.get(tablero, {})):
            try:
                await ws.send_json(mensaje)
            except Exception:  # conexión cerrada a mitad de camino
                caidas.append(ws)
        for ws in caidas:
            self.conexiones[tablero].pop(ws, None)


sala = Sala()


@asynccontextmanager
async def lifespan(_: FastAPI):
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        T.sembrar_demo(s)
    yield


app = FastAPI(title="Pizarra · Kanban en tiempo real", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")


def validar_slug(slug: str) -> str:
    if not SLUG.match(slug):
        raise HTTPException(400, "El nombre del tablero usa solo minúsculas, números y guiones (3 a 40)")
    return slug


def a_dict(t: T.Tarjeta) -> dict:
    return t.model_dump()


@app.get("/", include_in_schema=False)
def inicio():
    return RedirectResponse("/t/equipo-demo")


@app.get("/t/{slug}", include_in_schema=False)
def pagina(slug: str):
    validar_slug(slug)
    return FileResponse(ESTATICOS / "index.html")


@app.get("/api/tableros/{slug}")
def estado(slug: str) -> dict:
    validar_slug(slug)
    with Session(engine) as s:
        return {"columnas": T.COLUMNAS, "etiquetas": T.ETIQUETAS,
                "tarjetas": [a_dict(t) for t in T.tarjetas(s, slug)], "personas": sala.presentes(slug)}


async def procesar(slug: str, nombre: str, msg: dict) -> dict:
    """Aplica una acción del cliente y devuelve el evento a difundir."""
    accion = msg.get("accion")
    with Session(engine) as s:
        if accion == "crear":
            t = T.crear(s, slug, T.DatosTarjeta(**msg.get("datos", {})), nombre)
            return {"tipo": "creada", "tarjeta": a_dict(t), "por": nombre}
        if accion == "editar":
            t = T.editar(s, slug, int(msg["id"]), T.DatosTarjeta(**msg.get("datos", {})))
            return {"tipo": "editada", "tarjeta": a_dict(t), "por": nombre}
        if accion == "mover":
            cambiadas = T.mover(s, slug, int(msg["id"]), msg["columna"], int(msg.get("posicion", 0)))
            return {"tipo": "movida", "id": int(msg["id"]), "tarjetas": [a_dict(t) for t in cambiadas], "por": nombre}
        if accion == "borrar":
            resto = T.borrar(s, slug, int(msg["id"]))
            return {"tipo": "borrada", "id": int(msg["id"]), "tarjetas": [a_dict(t) for t in resto], "por": nombre}
    raise T.ErrorTablero(f"Acción desconocida: {accion}")


@app.websocket("/ws/{slug}")
async def socket(ws: WebSocket, slug: str, nombre: str = "Anónimo"):
    if not SLUG.match(slug):
        await ws.close(code=1008)
        return
    nombre = (nombre.strip() or "Anónimo")[:30]
    await ws.accept()
    await sala.unir(slug, ws, nombre)
    try:
        while True:
            msg = await ws.receive_json()
            try:
                evento = await procesar(slug, nombre, msg)
            except (T.ErrorTablero, ValidationError, KeyError, ValueError, TypeError) as e:
                detalle = e.errors()[0]["msg"] if isinstance(e, ValidationError) else str(e)
                await ws.send_json({"tipo": "error", "mensaje": detalle, "ref": msg.get("ref")})
                continue
            evento["ref"] = msg.get("ref")
            await sala.difundir(slug, evento)
    except WebSocketDisconnect:
        pass
    finally:
        await sala.salir(slug, ws)
