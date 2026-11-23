import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import main, tablero as T


@pytest.fixture
def client(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(main, "engine", eng)
    main.sala.conexiones.clear()
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def sesion():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


def recibir_hasta(ws, tipo):
    while True:
        m = ws.receive_json()
        if m["tipo"] == tipo:
            return m


# ---------- lógica del tablero ----------
def test_crear_asigna_posiciones_al_final(sesion):
    a = T.crear(sesion, "demo", T.DatosTarjeta(titulo="A"), "Ana")
    b = T.crear(sesion, "demo", T.DatosTarjeta(titulo="B"), "Ana")
    assert (a.posicion, b.posicion) == (0, 1)


def test_mover_entre_columnas_reordena_ambas(sesion):
    ids = [T.crear(sesion, "demo", T.DatosTarjeta(titulo=t), "Ana").id for t in "ABC"]
    hecho = T.crear(sesion, "demo", T.DatosTarjeta(titulo="X", columna="hecho"), "Ana")
    T.mover(sesion, "demo", ids[0], "hecho", 0)
    assert [t.titulo for t in T.de_columna(sesion, "demo", "por_hacer")] == ["B", "C"]
    assert [t.posicion for t in T.de_columna(sesion, "demo", "por_hacer")] == [0, 1]
    assert [t.titulo for t in T.de_columna(sesion, "demo", "hecho")] == ["A", "X"]
    assert hecho.id in [t.id for t in T.de_columna(sesion, "demo", "hecho")]


def test_mover_dentro_de_la_misma_columna(sesion):
    ids = [T.crear(sesion, "demo", T.DatosTarjeta(titulo=t), "Ana").id for t in "ABCD"]
    T.mover(sesion, "demo", ids[0], "por_hacer", 2)
    assert [t.titulo for t in T.de_columna(sesion, "demo", "por_hacer")] == ["B", "C", "A", "D"]
    T.mover(sesion, "demo", ids[3], "por_hacer", 99)   # posiciones fuera de rango se ajustan
    assert [t.titulo for t in T.de_columna(sesion, "demo", "por_hacer")][-1] == "D"


def test_borrar_cierra_el_hueco(sesion):
    ids = [T.crear(sesion, "demo", T.DatosTarjeta(titulo=t), "Ana").id for t in "ABC"]
    T.borrar(sesion, "demo", ids[1])
    assert [(t.titulo, t.posicion) for t in T.de_columna(sesion, "demo", "por_hacer")] == [("A", 0), ("C", 1)]


def test_tableros_aislados(sesion):
    t = T.crear(sesion, "uno", T.DatosTarjeta(titulo="A"), "Ana")
    with pytest.raises(T.ErrorTablero):
        T.borrar(sesion, "otro", t.id)


def test_validaciones():
    with pytest.raises(ValueError):
        T.DatosTarjeta(titulo="   ")
    with pytest.raises(ValueError):
        T.DatosTarjeta(titulo="A", etiqueta="inventada")
    with pytest.raises(ValueError):
        T.DatosTarjeta(titulo="A", columna="archivado")


# ---------- API y tiempo real ----------
def test_pagina_y_slug_invalido(client):
    assert client.get("/t/equipo-demo").status_code == 200
    assert client.get("/api/tableros/NO_VALIDO").status_code == 400


def test_dos_clientes_reciben_los_cambios_en_vivo(client):
    with client.websocket_connect("/ws/sala-1?nombre=Ana") as ana:
        recibir_hasta(ana, "presencia")
        with client.websocket_connect("/ws/sala-1?nombre=Beto") as beto:
            assert recibir_hasta(ana, "presencia")["personas"] == ["Ana", "Beto"]
            recibir_hasta(beto, "presencia")

            ana.send_json({"accion": "crear", "datos": {"titulo": "Diseñar logo", "etiqueta": "diseno"}})
            ev = recibir_hasta(beto, "creada")
            assert ev["tarjeta"]["titulo"] == "Diseñar logo" and ev["por"] == "Ana"
            recibir_hasta(ana, "creada")
            tid = ev["tarjeta"]["id"]

            beto.send_json({"accion": "mover", "id": tid, "columna": "en_progreso", "posicion": 0})
            mov = recibir_hasta(ana, "movida")
            assert mov["tarjetas"][0]["columna"] == "en_progreso"
            recibir_hasta(beto, "movida")

            beto.send_json({"accion": "borrar", "id": tid})
            assert recibir_hasta(ana, "borrada")["id"] == tid
        assert recibir_hasta(ana, "presencia")["personas"] == ["Ana"]

    estado = client.get("/api/tableros/sala-1").json()
    assert estado["tarjetas"] == [] and estado["personas"] == []


def test_errores_solo_llegan_a_quien_los_causo(client):
    with client.websocket_connect("/ws/sala-2?nombre=Ana") as ana:
        recibir_hasta(ana, "presencia")
        ana.send_json({"accion": "crear", "datos": {"titulo": ""}, "ref": 7})
        err = recibir_hasta(ana, "error")
        assert err["ref"] == 7
        ana.send_json({"accion": "volar"})
        assert "desconocida" in recibir_hasta(ana, "error")["mensaje"]
        ana.send_json({"accion": "borrar", "id": 999})
        assert recibir_hasta(ana, "error")["mensaje"] == "La tarjeta no existe"


def test_demo_siembra_solo_con_variable_y_tablero_vacio(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        monkeypatch.delenv("SEMBRAR_DEMO", raising=False)
        assert T.sembrar_demo(s) == 0
        monkeypatch.setenv("SEMBRAR_DEMO", "1")
        assert T.sembrar_demo(s) == len(T.EJEMPLOS_DEMO)
        assert T.sembrar_demo(s) == 0
        assert {t.columna for t in T.tarjetas(s, "equipo-demo")} == set(T.COLUMNAS)
