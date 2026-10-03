# Changelog

## Próxima versión

- Detección automática de capítulo y subcapítulo desde la tabla de SENACE.
- Detección más precisa del título del expediente.
- Verificación limitada al rango indicado con `--desde` y `--hasta`.
- Licencia MIT y preparación del repositorio para uso público.
- Escaneo automático de secretos en GitHub Actions.

## 0.2.0-alpha

- Primera arquitectura genérica.
- Manifiesto v1 con rutas por documento.
- Estructura externa por rangos para compatibilidad con exportaciones planas.
- Reanudación HTTP Range y staging de ZIP.
- Tests unitarios e integración offline.
- GitHub Actions preparado para Windows y Ubuntu.

## 0.1-romina

- Descargador específico creado para el EIA-d Romina.
- Prueba real completada en Windows con 205/205 elementos descargados desde SENACE.
