"""Captura semanal de escaneos Revuzee por tarjeta y reseñas Google de Santorino.

Corre en GitHub Actions. Variables de entorno (secretos del repositorio):
  REVUZEE_USER, REVUZEE_PASS  -> login de Revuzee
  GOOGLE_PLACES_KEY           -> clave de la API de Google Places (New)
Escribe datos/historial.csv, datos/google.csv y datos/estado.json.
Solo lectura en Revuzee y Google: no edita nada.
"""
import csv
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


LIST_URL = os.environ.get("REVUZEE_LIST_URL", "https://revuzee.link/revuzeeCardsList.php")
PLACE_ID = os.environ.get("PLACE_ID", "ChIJQQ1RKQDhro4R7oT2ljBEgaE")
DATOS = Path(__file__).parent / "datos"
DEBUG = Path(__file__).parent / "debug"
HOY = datetime.now(ZoneInfo("America/Santo_Domingo")).strftime("%Y-%m-%d")

LABELS = {
    "semana_pasada": r"semana\s+pasada",
    "mes_pasado": r"mes\s+pasado",
    "anio_pasado": r"a\S{1,2}o\s+pasado",
    "total": r"de\s+todos\s+los\s+tiempos",
}

# JS: devuelve el texto del elemento visible más pequeño que contenga ambas etiquetas.
JS_ANALITICA = """() => {
  let best = null;
  for (const el of document.querySelectorAll('body *')) {
    const t = el.innerText || '';
    if (!/semana\\s+pasada/i.test(t) || !/de\\s+todos/i.test(t)) continue;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || st.visibility === 'hidden' || st.display === 'none') continue;
    if (!best || t.length < best.length) best = t;
  }
  return best;
}"""


def parse_analitica(texto):
    """Extrae los 4 contadores. Prueba 'etiqueta → número' y luego 'número → etiqueta'."""
    t = re.sub(r"\s+", " ", texto)
    for patron in (r"{lab}\D{{0,40}}?(\d[\d.,]*)", r"(\d[\d.,]*)\D{{0,40}}?{lab}"):
        vals = {}
        for k, lab in LABELS.items():
            m = re.search(patron.format(lab=lab), t, re.I)
            if not m:
                break
            vals[k] = int(re.sub(r"[.,]", "", m.group(1)))
        if len(vals) == 4 and vals["semana_pasada"] <= vals["mes_pasado"] <= vals["anio_pasado"] <= vals["total"]:
            return vals
    raise ValueError(f"No pude leer la analítica: {t[:300]!r}")


def guardar_debug(page, nombre):
    try:
        DEBUG.mkdir(exist_ok=True)
        page.screenshot(path=str(DEBUG / f"{nombre}.png"), full_page=True)
        (DEBUG / f"{nombre}.html").write_text(page.content(), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print("debug no guardado:", e)


def login_si_hace_falta(page):
    pwd = page.locator("input[type=password]")
    if pwd.count() == 0 or not pwd.first.is_visible():
        return
    user, clave = os.environ.get("REVUZEE_USER"), os.environ.get("REVUZEE_PASS")
    if not user or not clave:
        raise RuntimeError("Faltan los secretos REVUZEE_USER / REVUZEE_PASS")
    campo = page.locator(
        "input[type=email], input[name*=mail i], input[name*=user i], input[id*=mail i], input[id*=user i], input[type=text]"
    ).first
    campo.fill(user)
    pwd.first.fill(clave)
    boton = page.locator("button[type=submit], input[type=submit], button:has-text('Iniciar'), button:has-text('Entrar'), button:has-text('Login')")
    if boton.count():
        boton.first.click()
    else:
        pwd.first.press("Enter")
    page.wait_for_load_state("networkidle")
    page.goto(LIST_URL, wait_until="networkidle")
    if page.locator("input[type=password]").count() and page.locator("input[type=password]").first.is_visible():
        guardar_debug(page, "login_fallido")
        raise RuntimeError("El login de Revuzee no funcionó (¿usuario/clave correctos?)")


def leer_revuzee():
    from playwright.sync_api import sync_playwright

    filas = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="es-ES", viewport={"width": 1400, "height": 1000})
        try:
            page.goto(LIST_URL, wait_until="networkidle")
            login_si_hace_falta(page)
            guardar_debug(page, "lista")

            # Índices de columnas por encabezado
            headers = [h.strip().lower() for h in page.locator("table thead th, table tr:first-child th").all_inner_texts()]
            def idx(*claves):
                for i, h in enumerate(headers):
                    if any(c in h for c in claves):
                        return i
                return None
            i_id, i_apodo, i_estado = idx("id"), idx("apodo", "nombre"), idx("estado")

            rows = page.locator("table tbody tr")
            n = rows.count()
            print(f"{n} filas en la tabla; encabezados: {headers}")
            previo = None
            for r in range(n):
                row = rows.nth(r)
                celdas = [c.strip() for c in row.locator("td").all_inner_texts()]
                texto_fila = " | ".join(celdas)
                estado = celdas[i_estado] if i_estado is not None and i_estado < len(celdas) else texto_fila
                if not re.search(r"\bactiv[oa]\b", estado, re.I) or re.search(r"inactiv", estado, re.I):
                    continue
                id_t = celdas[i_id] if i_id is not None and i_id < len(celdas) else ""
                if not re.fullmatch(r"[A-Z0-9]{6,12}", id_t or ""):
                    m = re.search(r"\b[A-Z0-9]{8}\b", texto_fila)
                    id_t = m.group(0) if m else ""
                apodo = celdas[i_apodo] if i_apodo is not None and i_apodo < len(celdas) else ""
                if not id_t:
                    raise RuntimeError(f"Fila activa sin ID reconocible: {texto_fila}")

                row.get_by_text(re.compile(r"anal\S{1,2}tica", re.I)).first.click()
                texto = None
                for _ in range(20):  # hasta ~5 s, esperando contenido nuevo
                    page.wait_for_timeout(250)
                    texto = page.evaluate(JS_ANALITICA)
                    if texto and (texto != previo or _ >= 8):
                        break
                if not texto:
                    guardar_debug(page, f"analitica_{id_t}")
                    raise RuntimeError(f"No apareció la ventana Analítica de {id_t}")
                vals = parse_analitica(texto)
                previo = texto
                # El repositorio es público: no se publica el nombre del mesero (Claude lo completa desde el Project).
                filas.append({"fecha_captura": HOY, "id_tarjeta": id_t, "apodo": "", **vals})
                print(id_t, vals)
                # cerrar la ventana
                cerrar = page.locator(".modal.show .close, .modal.show [data-dismiss=modal], .modal.show [data-bs-dismiss=modal], .modal.show .btn-close")
                if cerrar.count():
                    cerrar.first.click()
                else:
                    page.keyboard.press("Escape")
                page.wait_for_timeout(500)
        except Exception:
            guardar_debug(page, "error")
            raise
        finally:
            browser.close()
    if not filas:
        raise RuntimeError("No encontré tarjetas activas en Revuzee")
    return filas


def leer_google():
    key = os.environ.get("GOOGLE_PLACES_KEY")
    if not key:
        raise RuntimeError("Falta el secreto GOOGLE_PLACES_KEY")
    req = urllib.request.Request(
        f"https://places.googleapis.com/v1/places/{PLACE_ID}",
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "displayName,rating,userRatingCount"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.load(resp)
    nombre = d.get("displayName", {}).get("text", "")
    if "santorino" not in nombre.lower():
        raise RuntimeError(f"La ficha de Google no es Santorino: {nombre!r}")
    return {"fecha_captura": HOY, "calificacion": d["rating"], "total_resenas": d["userRatingCount"]}


def escribir(path, campos, nuevas):
    filas = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            filas = [r for r in csv.DictReader(f) if r["fecha_captura"] != HOY]
    filas += nuevas
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def main():
    estado = {"fecha": HOY, "hora": datetime.now(ZoneInfo("America/Santo_Domingo")).strftime("%H:%M"), "revuzee": "pendiente", "google": "pendiente"}
    errores = []
    # Revuzee tiene verificación de Cloudflare en el login: no se captura desde GitHub.
    # La tarea programada de Claude lo lee desde el Chrome de David y actualiza datos/historial.csv.
    if os.environ.get("REVUZEE_DESDE_GITHUB") == "1":
        try:
            tarjetas = leer_revuzee()
            escribir(DATOS / "historial.csv", ["fecha_captura", "id_tarjeta", "apodo", "semana_pasada", "mes_pasado", "anio_pasado", "total"], tarjetas)
            estado["revuzee"] = f"ok ({len(tarjetas)} tarjetas activas)"
        except Exception as e:  # noqa: BLE001
            estado["revuzee"] = f"error: {e}"
            errores.append(e)
    else:
        estado["revuzee"] = "se captura desde Chrome (tarea de Claude)"
    try:
        g = leer_google()
        escribir(DATOS / "google.csv", ["fecha_captura", "calificacion", "total_resenas"], [g])
        estado["google"] = f"ok ({g['calificacion']}, {g['total_resenas']} reseñas)"
    except Exception as e:  # noqa: BLE001
        estado["google"] = f"error: {e}"
        errores.append(e)
    (DATOS / "estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(estado, ensure_ascii=False))
    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
