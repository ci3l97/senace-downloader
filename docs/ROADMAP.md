# Roadmap antes de hacerlo público

## Ya hecho en esta alpha

- Descargador separado del caso Romina.
- Cualquier cantidad de documentos; no existe un `205` hardcodeado.
- Jerarquía en el manifiesto o en `estructura.json`.
- Descarga secuencial con pausa configurable.
- Reintentos con espera exponencial.
- Reanudación mediante HTTP `Range` cuando existe un `.part`.
- Detección por `Content-Disposition`, Content-Type y firma de archivo.
- Extracción segura de ZIP de paquete mediante staging.
- KMZ y DOCX/XLSX/PPTX no se descomprimen por error.
- SHA-256 para archivos directos.
- Verificación y manifiesto CSV.
- Tests offline con servidor HTTP local.
- Caso Romina conservado como versión histórica y ejemplo de 205 documentos.
- Jerarquía automática validada contra un segundo expediente de 504 documentos.
- Prueba real de los primeros 5 documentos del segundo expediente en Windows.

## Pendiente ideal para Codex

1. Completar la descarga del segundo expediente sin modificar `senace_downloader.py`.
2. Añadir tests con más variantes de `Content-Disposition` y respuestas HTTP anómalas.
3. Evaluar si conviene una interfaz sencilla para Windows sin scripts bloqueados por Smart App Control.
4. Seguir revisando cambios en las condiciones y el funcionamiento del portal antes de cada versión estable.

## Criterio para v1.0

La herramienta se considera genérica cuando un segundo expediente de Consulta Ciudadana puede exportarse, descargarse y reconstruirse sin editar el código Python ni crear reglas específicas dentro de él.
