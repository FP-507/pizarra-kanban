// Cliente del tablero: estado local + WebSocket. El servidor es la fuente de verdad.
const NOMBRES_COL = { por_hacer: "Por hacer", en_progreso: "En progreso", revision: "Revisión", hecho: "Hecho" };
const NOMBRES_ETQ = { ninguna: "Sin etiqueta", diseno: "Diseño", backend: "Backend", frontend: "Frontend", bug: "Bug", urgente: "Urgente" };
const COLORES_PERSONA = ["#3554d1", "#c2412d", "#1f8a4c", "#9b4dca", "#b7791f", "#0e7c86"];

const $ = (s, r = document) => r.querySelector(s);
const slug = location.pathname.split("/").pop();
const estado = { columnas: [], etiquetas: [], tarjetas: new Map(), personas: [] };
let ws, nombre, intentos = 0, arrastrada = null;

// ---------- utilidades ----------
function aviso(texto, error = false) {
  const el = document.createElement("div");
  el.className = "aviso" + (error ? " error" : "");
  el.textContent = texto;
  $("#avisos").append(el);
  setTimeout(() => el.remove(), 3200);
}
const iniciales = (n) => n.split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
const colorDe = (n) => COLORES_PERSONA[[...n].reduce((a, c) => a + c.charCodeAt(0), 0) % COLORES_PERSONA.length];

function conexion(clase, texto) {
  const el = $("#estado");
  el.className = "estado " + clase;
  el.lastElementChild.textContent = texto;
}

function enviar(accion) {
  if (ws?.readyState !== WebSocket.OPEN) return aviso("Sin conexión: reintentando…", true);
  ws.send(JSON.stringify(accion));
}

// ---------- render ----------
function tarjetasDe(col) {
  return [...estado.tarjetas.values()].filter((t) => t.columna === col).sort((a, b) => a.posicion - b.posicion);
}

function fichaHTML(t) {
  const el = document.createElement("article");
  el.className = "ficha";
  el.draggable = true;
  el.tabIndex = 0;
  el.dataset.id = t.id;
  el.style.setProperty("--cinta", `var(--t-${t.etiqueta})`);
  el.setAttribute("aria-label", `${t.titulo}. ${NOMBRES_ETQ[t.etiqueta]}. Enter para editar`);
  el.innerHTML = `<h3></h3><p></p><div class="pie"><span class="etq"></span><span class="autor"></span></div>`;
  $("h3", el).textContent = t.titulo;
  $("p", el).textContent = t.descripcion;
  $(".etq", el).textContent = t.etiqueta === "ninguna" ? "" : NOMBRES_ETQ[t.etiqueta];
  $(".autor", el).textContent = t.autor;
  el.addEventListener("click", () => abrirEditor(t.id));
  el.addEventListener("keydown", (e) => { if (e.key === "Enter") abrirEditor(t.id); });
  el.addEventListener("dragstart", (e) => { arrastrada = t.id; el.classList.add("arrastrando"); e.dataTransfer.effectAllowed = "move"; });
  el.addEventListener("dragend", () => { el.classList.remove("arrastrando"); limpiarMarcador(); });
  return el;
}

function render(resaltar = new Set()) {
  for (const col of estado.columnas) {
    const lista = $(`[data-col="${col}"] .lista`);
    const fichas = tarjetasDe(col);
    lista.replaceChildren(...fichas.map((t) => {
      const el = fichaHTML(t);
      if (resaltar.has(t.id)) el.classList.add("destello");
      return el;
    }));
    $(`[data-col="${col}"] .cuenta`).textContent = fichas.length;
  }
}

function renderPersonas() {
  $("#personas").replaceChildren(...estado.personas.map((p) => {
    const li = document.createElement("li");
    li.textContent = iniciales(p);
    li.title = p;
    li.style.background = colorDe(p);
    return li;
  }));
}

function construirTablero() {
  $("#tablero").replaceChildren(...estado.columnas.map((col) => {
    const sec = document.createElement("section");
    sec.className = "carril";
    sec.dataset.col = col;
    sec.innerHTML = `<header><h2>${NOMBRES_COL[col]}</h2><span class="cuenta">0</span></header>
      <div class="lista"></div>
      <form class="agregar"><input name="titulo" maxlength="120" placeholder="+ Agregar tarjeta" aria-label="Nueva tarjeta en ${NOMBRES_COL[col]}"></form>`;
    const lista = $(".lista", sec);
    lista.addEventListener("dragover", (e) => { e.preventDefault(); mostrarMarcador(lista, e.clientY); });
    lista.addEventListener("dragleave", (e) => { if (!lista.contains(e.relatedTarget)) limpiarMarcador(); });
    lista.addEventListener("drop", (e) => { e.preventDefault(); soltar(col, lista, e.clientY); });
    $("form", sec).addEventListener("submit", (e) => {
      e.preventDefault();
      const input = e.target.titulo;
      if (!input.value.trim()) return;
      enviar({ accion: "crear", datos: { titulo: input.value, columna: col } });
      input.value = "";
    });
    return sec;
  }));
}

// ---------- arrastrar y soltar ----------
function indiceEn(lista, y) {
  const fichas = [...lista.querySelectorAll(".ficha:not(.arrastrando)")];
  const i = fichas.findIndex((f) => y < f.getBoundingClientRect().top + f.offsetHeight / 2);
  return i === -1 ? fichas.length : i;
}

function mostrarMarcador(lista, y) {
  limpiarMarcador();
  lista.classList.add("sobre");
  const marca = document.createElement("div");
  marca.className = "marcador";
  const fichas = [...lista.querySelectorAll(".ficha:not(.arrastrando)")];
  const i = indiceEn(lista, y);
  i < fichas.length ? lista.insertBefore(marca, fichas[i]) : lista.append(marca);
}

function limpiarMarcador() {
  document.querySelectorAll(".marcador").forEach((m) => m.remove());
  document.querySelectorAll(".lista.sobre").forEach((l) => l.classList.remove("sobre"));
}

function soltar(col, lista, y) {
  const id = arrastrada;
  const posicion = indiceEn(lista, y);
  limpiarMarcador();
  if (id == null) return;
  const t = estado.tarjetas.get(id);
  if (t.columna === col && (t.posicion === posicion)) return;
  enviar({ accion: "mover", id, columna: col, posicion });
}

// ---------- editor ----------
let editando = null;
function abrirEditor(id) {
  const t = estado.tarjetas.get(id);
  editando = id;
  const f = $("#form-tarjeta");
  f.titulo.value = t.titulo;
  f.descripcion.value = t.descripcion;
  f.etiqueta.innerHTML = estado.etiquetas.map((e) => `<option value="${e}">${NOMBRES_ETQ[e]}</option>`).join("");
  f.columna.innerHTML = estado.columnas.map((c) => `<option value="${c}">${NOMBRES_COL[c]}</option>`).join("");
  f.etiqueta.value = t.etiqueta;
  f.columna.value = t.columna;
  $("#dlg-meta").textContent = `Creada por ${t.autor} · última edición ${new Date(t.actualizada).toLocaleString("es-PA")}`;
  $("#dlg-tarjeta").showModal();
  f.titulo.focus();
}

$("#form-tarjeta").addEventListener("submit", () => {
  const f = $("#form-tarjeta"), t = estado.tarjetas.get(editando);
  if (!t) return;
  enviar({ accion: "editar", id: t.id, datos: { titulo: f.titulo.value, descripcion: f.descripcion.value, etiqueta: f.etiqueta.value } });
  if (f.columna.value !== t.columna) enviar({ accion: "mover", id: t.id, columna: f.columna.value, posicion: tarjetasDe(f.columna.value).length });
});
$("#cancelar").addEventListener("click", () => $("#dlg-tarjeta").close());
$("#borrar").addEventListener("click", () => {
  const t = estado.tarjetas.get(editando);
  if (t && confirm(`¿Borrar «${t.titulo}»?`)) {
    enviar({ accion: "borrar", id: t.id });
    $("#dlg-tarjeta").close();
  }
});

// ---------- eventos del servidor ----------
function aplicar(ev) {
  const mio = ev.por === nombre;
  switch (ev.tipo) {
    case "presencia":
      estado.personas = ev.personas;
      renderPersonas();
      return;
    case "creada":
      estado.tarjetas.set(ev.tarjeta.id, ev.tarjeta);
      render(new Set([ev.tarjeta.id]));
      if (!mio) aviso(`${ev.por} creó «${ev.tarjeta.titulo}»`);
      return;
    case "editada":
      estado.tarjetas.set(ev.tarjeta.id, ev.tarjeta);
      render(new Set(mio ? [] : [ev.tarjeta.id]));
      if (!mio) aviso(`${ev.por} editó «${ev.tarjeta.titulo}»`);
      return;
    case "movida":
      ev.tarjetas.forEach((t) => estado.tarjetas.set(t.id, t));
      render(new Set(mio ? [] : [ev.id]));
      if (!mio) aviso(`${ev.por} movió «${estado.tarjetas.get(ev.id).titulo}» a ${NOMBRES_COL[estado.tarjetas.get(ev.id).columna]}`);
      return;
    case "borrada": {
      const titulo = estado.tarjetas.get(ev.id)?.titulo;
      estado.tarjetas.delete(ev.id);
      ev.tarjetas.forEach((t) => estado.tarjetas.set(t.id, t));
      render();
      if (!mio) aviso(`${ev.por} borró «${titulo}»`);
      return;
    }
    case "error":
      aviso(ev.mensaje, true);
  }
}

async function cargarEstado() {
  const r = await fetch(`/api/tableros/${slug}`);
  const datos = await r.json();
  estado.columnas = datos.columnas;
  estado.etiquetas = datos.etiquetas;
  estado.tarjetas = new Map(datos.tarjetas.map((t) => [t.id, t]));
  if (!$("#tablero").children.length) construirTablero();
  render();
}

function conectar() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${slug}?nombre=${encodeURIComponent(nombre)}`);
  ws.onopen = async () => {
    intentos = 0;
    conexion("ok", "En vivo");
    await cargarEstado();   // por si hubo cambios mientras estábamos desconectados
  };
  ws.onmessage = (m) => aplicar(JSON.parse(m.data));
  ws.onclose = () => {
    conexion("caido", "Reconectando…");
    const espera = Math.min(10000, 500 * 2 ** intentos++);   // backoff exponencial
    setTimeout(conectar, espera);
  };
}

// ---------- inicio ----------
$("#slug").textContent = `tablero / ${slug}`;
$("#invitar").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(location.href); aviso("Enlace copiado: compártelo para colaborar"); }
  catch { aviso(location.href); }
});

function entrar(n) {
  nombre = n.trim().slice(0, 30) || "Anónimo";
  try { localStorage.setItem("pizarra.nombre", nombre); } catch {}
  cargarEstado().then(conectar);
}

let guardado = null;
try { guardado = localStorage.getItem("pizarra.nombre"); } catch {}
if (guardado) entrar(guardado);
else {
  $("#dlg-nombre").showModal();
  $("#form-nombre").addEventListener("submit", () => entrar($("#form-nombre").nombre.value));
}
