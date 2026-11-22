"""Modelo y operaciones del tablero, independientes de la capa web."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, col, select

COLUMNAS = ["por_hacer", "en_progreso", "revision", "hecho"]
ETIQUETAS = ["ninguna", "diseno", "backend", "frontend", "bug", "urgente"]


class Tarjeta(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    tablero: str = SQLField(index=True, max_length=40)
    titulo: str = SQLField(max_length=120)
    descripcion: str = SQLField(default="", max_length=1000)
    columna: str = "por_hacer"
    posicion: int = 0
    etiqueta: str = "ninguna"
    autor: str = SQLField(default="Anónimo", max_length=30)
    actualizada: str = SQLField(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DatosTarjeta(BaseModel):
    titulo: str = Field(min_length=1, max_length=120)
    descripcion: str = Field(default="", max_length=1000)
    etiqueta: str = "ninguna"
    columna: str = "por_hacer"

    @field_validator("titulo")
    @classmethod
    def sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El título no puede estar vacío")
        return v

    @field_validator("etiqueta")
    @classmethod
    def etiqueta_valida(cls, v: str) -> str:
        if v not in ETIQUETAS:
            raise ValueError(f"Etiqueta inválida: {v}")
        return v

    @field_validator("columna")
    @classmethod
    def columna_valida(cls, v: str) -> str:
        if v not in COLUMNAS:
            raise ValueError(f"Columna inválida: {v}")
        return v


class ErrorTablero(ValueError):
    pass


def tarjetas(s: Session, tablero: str) -> list[Tarjeta]:
    q = select(Tarjeta).where(Tarjeta.tablero == tablero).order_by(col(Tarjeta.columna), col(Tarjeta.posicion))
    return list(s.exec(q).all())


def de_columna(s: Session, tablero: str, columna: str) -> list[Tarjeta]:
    q = select(Tarjeta).where(Tarjeta.tablero == tablero, Tarjeta.columna == columna).order_by(col(Tarjeta.posicion))
    return list(s.exec(q).all())


def obtener(s: Session, tablero: str, tarjeta_id: int) -> Tarjeta:
    t = s.get(Tarjeta, tarjeta_id)
    if t is None or t.tablero != tablero:
        raise ErrorTablero("La tarjeta no existe")
    return t


def _renumerar(lista: list[Tarjeta]) -> None:
    for i, t in enumerate(lista):
        t.posicion = i


def crear(s: Session, tablero: str, datos: DatosTarjeta, autor: str) -> Tarjeta:
    if len(tarjetas(s, tablero)) >= 300:
        raise ErrorTablero("El tablero llegó al máximo de 300 tarjetas")
    t = Tarjeta(tablero=tablero, autor=autor[:30] or "Anónimo", posicion=len(de_columna(s, tablero, datos.columna)),
                **datos.model_dump())
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def editar(s: Session, tablero: str, tarjeta_id: int, datos: DatosTarjeta) -> Tarjeta:
    t = obtener(s, tablero, tarjeta_id)
    t.titulo, t.descripcion, t.etiqueta = datos.titulo, datos.descripcion, datos.etiqueta
    t.actualizada = datetime.now(timezone.utc).isoformat()
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def mover(s: Session, tablero: str, tarjeta_id: int, columna: str, posicion: int) -> list[Tarjeta]:
    """Mueve una tarjeta y reordena las columnas afectadas. Devuelve las tarjetas que cambiaron."""
    if columna not in COLUMNAS:
        raise ErrorTablero(f"Columna inválida: {columna}")
    t = obtener(s, tablero, tarjeta_id)
    origen = [x for x in de_columna(s, tablero, t.columna) if x.id != t.id]
    destino = origen if columna == t.columna else de_columna(s, tablero, columna)
    posicion = max(0, min(int(posicion), len(destino)))
    destino.insert(posicion, t)
    t.columna = columna
    t.actualizada = datetime.now(timezone.utc).isoformat()
    _renumerar(destino)
    if destino is not origen:
        _renumerar(origen)
    cambiadas = {x.id: x for x in origen + destino}
    for x in cambiadas.values():
        s.add(x)
    s.commit()
    return [s.get(Tarjeta, i) for i in cambiadas]


def borrar(s: Session, tablero: str, tarjeta_id: int) -> list[Tarjeta]:
    t = obtener(s, tablero, tarjeta_id)
    resto = [x for x in de_columna(s, tablero, t.columna) if x.id != t.id]
    s.delete(t)
    _renumerar(resto)
    for x in resto:
        s.add(x)
    s.commit()
    return resto
