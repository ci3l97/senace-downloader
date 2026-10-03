# Seguridad

Este repositorio no necesita claves de API, contraseñas ni tokens para descargar documentos públicos de SENACE.

- No guardes credenciales en el código, manifiestos ni archivos de configuración.
- Usa variables de entorno o el almacén de secretos de GitHub si una integración futura necesita autenticación.
- `tools/scan_secrets.py` se ejecuta localmente y en GitHub Actions para detectar formatos comunes de secretos.
- Si una credencial llega a publicarse, revócala primero y luego elimínala del historial; borrar solamente el archivo no invalida la credencial.

Los enlaces públicos `DownloadByGet?docId=...` incluidos en los ejemplos son identificadores públicos de documentos del portal SENACE, no credenciales.
