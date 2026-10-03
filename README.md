# SENACE Downloader

Herramienta **no oficial** para descargar y reconstruir localmente expedientes públicos disponibles en **Consulta Ciudadana de SENACE**.

Plataforma objetivo: **Windows 10/11, Python 3.11 o superior**. Sin dependencias externas.

Estado actual: **v0.2.0-alpha pública para pruebas**.

## Qué problema resuelve

En Consulta Ciudadana, cada documento visible puede descargarse mediante un enlace público del tipo `DownloadByGet?docId=...`. En expedientes grandes, descargar capítulos completos puede ser poco práctico. Este proyecto exporta los enlaces individuales y los descarga de forma ordenada, verificable y reanudable.

## Prueba real que originó el proyecto

La primera versión se construyó para el **EIA-d del proyecto Romina**. En una PC con Windows se ejecutó contra el portal real y completó **205/205 elementos**. Esa versión se conserva intacta en `legacy/romina-v0.1/`.

La v0.2 elimina del descargador la estructura hardcodeada de Romina. La jerarquía ahora viene del manifiesto o de un `estructura.json` externo.

## Flujo actual

1. Abrir el expediente en Consulta Ciudadana.
2. Abrir `F12 > Console`.
3. Ejecutar `exportar.js`.
4. Guardar `manifest.json`.
5. Comprobar que `ruta` contiene el capítulo y subcapítulo detectados.
6. Ejecutar:

```powershell
py -3 senace_downloader.py manifest.json --estructura estructura.json
```

Si el manifiesto ya contiene `ruta` en cada documento:

```powershell
py -3 senace_downloader.py manifest.json
```

## Solo comprobar antes de descargar

```powershell
py -3 senace_downloader.py manifest.json --estructura estructura.json --dry-run
```

Muestra cada número, ruta y nombre sin hacer solicitudes de descarga.

## Características de v0.2-alpha

- no depende de que existan exactamente 205 documentos;
- soporta cualquier manifiesto con URLs públicas válidas de `eva.senace.gob.pe`;
- estructura jerárquica fuera del código;
- descargas secuenciales con pausa configurable;
- reintentos con backoff;
- reanudación de `.part` mediante HTTP `Range` cuando el servidor lo admite;
- evita cargar archivos grandes completos en RAM;
- conserva el nombre visible del portal y detecta extensión real;
- extrae ZIP de paquetes preservando estructura interna;
- no descomprime por error KMZ ni archivos Office basados en ZIP;
- extracción ZIP segura contra `../` y rutas absolutas;
- extracción mediante carpeta de staging para no aceptar anexos a medio extraer;
- SHA-256 de archivos directos;
- `_MANIFIESTO_DESCARGA.csv` y `_VERIFICACION.txt` al terminar;
- segunda ejecución salta elementos ya completos;
- cero dependencias externas: biblioteca estándar de Python.

## Jerarquía automática

`exportar.js` recorre en orden las filas de capítulo, subcapítulo y documento de la tabla de SENACE. La detección se validó en el segundo expediente de prueba: encontró 504 documentos y asignó una ruta a los 504 sin modificar el Python.

Para avanzar sin adivinar se incluye:

```text
browser/diagnosticar_estructura.js
```

Ese script genera un JSON pequeño con el contexto DOM de varios enlaces y sirve para diagnosticar futuros cambios del portal.

`estructura.json` sigue disponible como mecanismo manual de compatibilidad.

## Caso Romina incluido

```text
examples/romina/
├─ manifest.json
└─ estructura.json
```

El ejemplo contiene los 205 enlaces públicos y su jerarquía. Sirve para validar que la arquitectura genérica representa exactamente el caso que ya funcionó.

También se guarda la versión inicial:

```text
legacy/romina-v0.1/
```

para no perder el código que fue probado contra el expediente completo.

## Tests

No descargan nada de SENACE. Levantan un servidor HTTP local y simulan PDF, CSV, ZIP de paquete, KMZ, descarga parcial/reanudación y segunda ejecución.

```powershell
py -3 -m unittest discover -s tests -v
```

GitHub Actions está configurado exclusivamente con `windows-latest` (Python 3.11 y 3.14).

## Salida típica

```text
Expediente
├─ Capítulo
│  └─ Subcapítulo
│     ├─ 1. Documento.pdf
│     ├─ 2. datos.csv
│     └─ 3. Anexo paquete
│        ├─ archivo-original-1.pdf
│        └─ carpeta-interna/
├─ _MANIFIESTO_DESCARGA.csv
├─ _MANIFIESTO_ORIGINAL_NORMALIZADO.json
└─ _VERIFICACION.txt
```

## Opciones útiles

```text
--desde N              primer número a procesar
--hasta N              último número a procesar
--reintentos N         reintentos por documento
--timeout N            timeout de red en segundos
--pausa S              pausa entre documentos
--no-extraer           conserva ZIP sin extraer paquetes
--conservar-zip        conserva ZIP además de extraerlo
--inseguro             desactiva TLS; solo diagnóstico de certificados
--dry-run              valida y muestra estructura sin descargar
```

## Política de uso prevista

El proyecto está pensado para trabajar únicamente con documentación que el propio portal de Consulta Ciudadana expone públicamente. No intenta saltarse autenticación, permisos ni controles de acceso. La descarga es secuencial y por defecto introduce una pausa entre documentos para evitar carga innecesaria sobre el servicio.

Antes de publicar una versión 1.0 se revisarán las condiciones aplicables del portal y se documentará el uso responsable.

## Seguridad

No introduzcas manifiestos de fuentes no confiables. Por defecto el programa rechaza hosts distintos de `eva.senace.gob.pe`. La opción interna para otros hosts existe únicamente para los tests locales.

Los ZIP se validan antes de extraerse para impedir rutas `../` o absolutas.

## Licencia

Publicado bajo la [licencia MIT](LICENSE). Se permite usar, copiar, modificar y redistribuir el código conservando el aviso de copyright y la licencia.

## Estado antes de v1.0

Consulta `docs/ROADMAP.md`. El hito principal es probar **un segundo expediente real** sin editar `senace_downloader.py`.

---

**SENACE Downloader no es una herramienta oficial de SENACE ni está afiliada a la entidad.**

## Verificación y reanudación

La salida predeterminada es `descargas/<proyecto>/`, excluida de Git. Cada documento completado tiene un recibo `.senace.json` con su identidad y SHA-256 de sus archivos. Al repetir el comando se verifican esos hashes; un archivo alterado o un paquete incompleto se descarga nuevamente. Los archivos de versiones anteriores sin recibo también se descargan nuevamente. La comprobación detecta cambios locales; no certifica que el servidor haya entregado todo el expediente.

Los parciales se identifican por documento y se valida `Content-Range`. Ejecuta una sola instancia por carpeta de destino. Usa una ruta corta, por ejemplo `--destino C:\SENACE\Estudio`, si el expediente tiene rutas profundas que superan el límite de Windows.

El exportador elimina enlaces duplicados, numera los nombres y obtiene las rutas de las filas visibles de capítulo y subcapítulo. Solo exporta enlaces cargados en el DOM: espera a que la tabla termine de cargar y revisa cualquier paginación antes de ejecutarlo. Si un diseño futuro del portal impide detectar una ruta, ese documento se guarda en `Documentos` y puede organizarse con `estructura.json`.

Cuando se usa `--desde` o `--hasta`, `_VERIFICACION.txt` comprueba únicamente los documentos seleccionados. Por ejemplo, `--hasta 5` termina con `5/5 elementos seleccionados presentes`; los demás siguen disponibles para una ejecución posterior.
