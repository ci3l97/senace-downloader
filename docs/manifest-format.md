# Formato del manifiesto

El descargador acepta dos formatos.

## 1. Formato v1 recomendado

```json
{
  "schema_version": 1,
  "source": "senace-consulta-ciudadana",
  "project_title": "Nombre del expediente",
  "documents": [
    {
      "numero": 1,
      "nombre": "1. Documento",
      "url": "https://eva.senace.gob.pe:8443/.../DownloadByGet?docId=...",
      "docId": "...",
      "ruta": ["01. Capítulo", "02. Subcapítulo"],
      "tipo": "auto"
    }
  ]
}
```

`ruta` es opcional. Si está vacía, el documento se guarda en `Documentos/`.

`tipo` admite:

- `auto`: decisión por encabezados, extensión y firma del archivo.
- `file`: nunca extraer aunque sea un ZIP.
- `package` o `zip-package`: extraer si el contenido es ZIP y no es KMZ/Office.

## 2. Lista plana heredada

También se admite una lista JSON como la obtenida originalmente para Romina:

```json
[
  {
    "numero": 1,
    "nombre": "1. AUM3.csv",
    "url": "https://eva.senace.gob.pe:8443/...",
    "docId": "..."
  }
]
```

Puede combinarse con `--estructura estructura.json` para añadir la jerarquía sin modificar el código.

## estructura.json

```json
{
  "ranges": [
    {
      "desde": 1,
      "hasta": 9,
      "ruta": ["01. Capítulo", "02. Subcapítulo"]
    }
  ]
}
```

Los rangos no deben superponerse. Si un documento ya trae `ruta`, esa ruta tiene prioridad.
