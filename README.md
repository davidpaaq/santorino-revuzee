# santorino-revuzee

Captura semanal automática para Santorino, sin depender de una PC encendida:

- **Revuzee:** escaneos por tarjeta activa (semana, mes, año y total).
- **Google:** calificación y total de reseñas, con la API de Places.

Corre en GitHub Actions todos los lunes a las 6:23 a.m. (hora RD) y guarda los datos en `datos/`. Más tarde, la tarea programada de Claude toma esos datos y arma el PDF, actualiza el Panel y carga la app Anfitrión.

Este repositorio es **público** porque Claude lo lee sin contraseña. Por eso **no contiene nombres de meseros**, solo los ID de las tarjetas y los números. Usuario y clave están guardados como *secrets* cifrados de GitHub, y nadie puede verlos, ni siquiera en un repositorio público.

## Instalación (una sola vez)

1. **Crear el repositorio.** En GitHub, entra a *New repository*, ponle el nombre `santorino-revuzee` y elige *Public*. Créalo vacío.
2. **Subir los archivos.** Usa *Add file → Upload files* y arrastra `captura.py`, `README.md`, `.gitignore` y la carpeta `datos`.
3. **Crear el flujo automático.** Usa *Add file → Create new file*. En el nombre escribe exactamente `.github/workflows/captura.yml`. Pega el contenido del archivo `captura.yml` y guarda con *Commit*.
4. **Guardar los secretos.** Ve a *Settings → Secrets and variables → Actions → New repository secret* y crea estos tres:
   - `REVUZEE_USER`: correo o usuario de Revuzee.
   - `REVUZEE_PASS`: clave de Revuzee.
   - `GOOGLE_PLACES_KEY`: clave de la API de Google (paso siguiente).
5. **Obtener la clave de Google:**
   1. En console.cloud.google.com, crea un proyecto (por ejemplo, "Santorino").
   2. Activa *Places API (New)*.
   3. Ve a *Credenciales → Crear credenciales → Clave de API*.
   4. Por seguridad, restringe la clave solo a "Places API (New)".
   5. Google pide una tarjeta, pero 4 consultas al mes quedan muy por debajo del uso gratuito.
6. **Probar.** En la pestaña *Actions*, abre "Captura Revuzee y Google" y pulsa *Run workflow*. Al terminar, `datos/estado.json` debe mostrar `ok` en Revuzee y en Google.

Si algo falla, el *run* deja un archivo **diagnostico** con capturas de pantalla durante 3 días, para poder ajustar el script.

## Archivos

- `datos/historial.csv`: `fecha_captura,id_tarjeta,apodo(vacío),semana_pasada,mes_pasado,anio_pasado,total`
- `datos/google.csv`: `fecha_captura,calificacion,total_resenas`
- `datos/estado.json`: resultado de la última captura.

En Revuzee y Google todo es de solo lectura: el script no modifica nada.
