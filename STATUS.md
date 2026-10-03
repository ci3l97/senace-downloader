# Estado de verificación — v0.2.0-alpha

## Verificado

- El caso Romina incluido contiene 205 documentos, numeración 1–205 continua y 205 `docId` únicos.
- Todos los documentos de Romina tienen una ruta jerárquica en el manifiesto v1.
- El descargador genérico no contiene rangos ni un total de 205 hardcodeado.
- Acepta lista plana heredada + `estructura.json` y manifiesto v1 con `ruta`.
- Tests offline pasan para:
  - nombres inválidos de Windows;
  - validación de manifiesto;
  - rechazo de `docId` duplicados;
  - ZIP traversal (`../`);
  - distinción KMZ/ZIP;
  - PDF directo;
  - CSV directo;
  - ZIP de paquete y preservación de subcarpetas;
  - KMZ sin extracción accidental;
  - reanudación desde archivo `.part` mediante HTTP Range;
  - segunda ejecución sin redescargar elementos completos.
- La versión histórica `legacy/romina-v0.1` es la que se usó como base del experimento real que terminó con 205/205 en Windows.
- El descargador genérico procesó correctamente los primeros 5 documentos de un segundo expediente real de 504 elementos en Windows, sin modificar `senace_downloader.py`.
- El DOM del segundo expediente se inspeccionó en el portal: el exportador detecta 22 encabezados y asigna capítulo/subcapítulo a los 504 documentos.
- Una ejecución limitada con `--desde`/`--hasta` verifica solamente el rango seleccionado.

## No verificado todavía

- Descarga completa de los 504 documentos del segundo expediente.
- GitHub Actions real hasta que el repositorio exista y se haga push.
- Comportamiento ante todos los formatos posibles que pueda contener un expediente SENACE (p. ej. RAR/7z se conservan, no se extraen con biblioteca estándar).

## Próxima prueba decisiva

Volver a exportar el segundo expediente con el exportador actualizado, comprobar las rutas con `--dry-run` y continuar la descarga completa sin editar `senace_downloader.py`.

## Revisión local del 3 de octubre de 2026

Windows: 16 pruebas locales pasan con el Python incluido en el entorno de Codex. CI configurada solo para Windows; aún sin ejecutar en GitHub. El exportador fue contrastado con el DOM real del expediente Ruta PE-34C: 504/504 enlaces recibieron ruta. Los primeros 5 documentos se descargaron desde SENACE correctamente.
