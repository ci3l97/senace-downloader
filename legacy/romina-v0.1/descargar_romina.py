# -*- coding: utf-8 -*-
"""
Descargador y organizador del EIA-d del proyecto Romina (SENACE).

- Lee Romina_SENACE_205_documentos.json.
- Descarga los 205 elementos individuales desde SENACE.
- Los ubica en la misma jerarquía mostrada por Consulta Ciudadana.
- Si un elemento descargado es un ZIP "paquete", crea una carpeta con el
  nombre exacto del elemento (p. ej. "45. Anexo 2.10.10a") y extrae todo
  su contenido preservando la estructura interna.
- No descomprime KMZ ni formatos Office basados en ZIP.
- Reintenta descargas fallidas.
- Puede incorporar elementos ya descargados desde una carpeta plana.
- Genera manifiesto con SHA-256 y verificación final 1-205.

No requiere librerías externas: usa solo Python estándar.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import re
import shutil
import ssl
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)
REFERER = "https://consultaciudadana.senace.gob.pe/"
CHUNK = 1024 * 1024
MAX_REINTENTOS = 4

# Jerarquía exacta entregada por SENACE para los números 1-205.
RANGOS = [
    (1, 9, [
        "01. Ficha Resumen",
        "02. Ubicación y extensión del proyecto",
    ]),
    (10, 23, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "01. Resumen Ejecutivo",
    ]),
    (24, 69, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "02. Descripción del Proyecto",
    ]),
    (70, 126, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "03. Estudio de la Línea Base Ambiental",
    ]),
    (127, 155, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "04. Plan de Participación Ciudadana",
    ]),
    (156, 169, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "05. Caracterización del Impacto Ambiental",
    ]),
    (170, 179, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "06. Estrategia de Manejo Ambiental",
    ]),
    (180, 182, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "07. Valoración Económica del Impacto Ambiental",
    ]),
    (183, 186, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "08. Empresa Consultora",
    ]),
    (187, 189, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "09. Otras consideraciones técnicas que determine la autoridad competente",
    ]),
    (190, 191, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "10. Opiniones técnicas",
    ]),
    (192, 193, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "11. Bibliografía",
    ]),
    (194, 195, [
        "02. Contenido de Estudio en Cumplimiento de Tdr",
        "12. Anexos",
    ]),
    (196, 205, [
        "04. Pagos y otros requisitos TUPA",
        "02. Documentos Adjuntos",
    ]),
]

INVALID_WINDOWS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def limpiar_nombre(nombre: str) -> str:
    """Limpia caracteres que Windows no permite, conservando el texto visible."""
    nombre = INVALID_WINDOWS.sub("_", nombre).rstrip(" .")
    return nombre or "sin_nombre"


def ruta_relativa(numero: int) -> Path:
    for inicio, fin, partes in RANGOS:
        if inicio <= numero <= fin:
            return Path(*partes)
    raise ValueError(f"Número fuera de rango: {numero}")


def nombre_sin_numero(nombre: str) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", nombre, count=1)


def extension_visible(nombre: str) -> str:
    # Solo acepta extensiones cortas reales; evita interpretar "3.2.14a" como extensión.
    m = re.search(r"(\.[A-Za-z0-9]{2,6})$", nombre)
    if not m:
        return ""
    ext = m.group(1).lower()
    conocidas = {
        ".csv", ".pdf", ".zip", ".kmz", ".kml", ".shp", ".dbf", ".shx",
        ".prj", ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt",
        ".txt", ".jpg", ".jpeg", ".png", ".rar", ".7z"
    }
    return ext if ext in conocidas else ""


def parse_filename(headers) -> Optional[str]:
    cd = headers.get("Content-Disposition", "") or ""

    m = re.search(r"filename\*\s*=\s*([^']*)''([^;]+)", cd, flags=re.I)
    if m:
        charset = (m.group(1) or "utf-8").strip()
        raw = m.group(2).strip()
        try:
            return Path(urllib.parse.unquote(raw, encoding=charset, errors="replace")).name
        except Exception:
            return Path(urllib.parse.unquote(raw)).name

    m = re.search(r'filename\s*=\s*"([^"]+)"', cd, flags=re.I)
    if not m:
        m = re.search(r"filename\s*=\s*([^;]+)", cd, flags=re.I)
    if m:
        raw = m.group(1).strip().strip('"').strip("'")
        raw = urllib.parse.unquote(raw)
        return Path(raw).name
    return None


def office_o_kmz_desde_zip(path: Path, nombre_mostrado: str) -> Optional[str]:
    """Distingue contenedores ZIP que NO deben extraerse."""
    low = nombre_mostrado.lower()
    if "kmz" in low:
        return ".kmz"

    try:
        with zipfile.ZipFile(path) as z:
            names = {n.lower() for n in z.namelist()}
            if "doc.kml" in names:
                return ".kmz"
            if "[content_types].xml" in names:
                if any(n.startswith("word/") for n in names):
                    return ".docx"
                if any(n.startswith("xl/") for n in names):
                    return ".xlsx"
                if any(n.startswith("ppt/") for n in names):
                    return ".pptx"
    except Exception:
        return None
    return None


def extension_por_magic(path: Path, content_type: str, nombre_mostrado: str) -> str:
    try:
        with path.open("rb") as f:
            head = f.read(16)
    except Exception:
        head = b""

    if head.startswith(b"%PDF"):
        return ".pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06") or head.startswith(b"PK\x07\x08"):
        nested = office_o_kmz_desde_zip(path, nombre_mostrado)
        return nested or ".zip"

    ctype = (content_type or "").split(";")[0].strip().lower()
    mapa = {
        "application/pdf": ".pdf",
        "text/csv": ".csv",
        "application/zip": ".zip",
        "application/vnd.google-earth.kmz": ".kmz",
        "application/vnd.google-earth.kml+xml": ".kml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "text/plain": ".txt",
    }
    if ctype in mapa:
        return mapa[ctype]

    guessed = mimetypes.guess_extension(ctype) if ctype else None
    return guessed or ""


def sha256_archivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def safe_extract_zip(zip_path: Path, destino: Path) -> None:
    """Extrae ZIP evitando rutas ../ o absolutas."""
    destino.mkdir(parents=True, exist_ok=True)
    base_resolved = destino.resolve()

    with zipfile.ZipFile(zip_path) as z:
        for member in z.infolist():
            # Normaliza barras y evita drive letters/rutas absolutas.
            rel = Path(member.filename.replace("\\", "/"))
            if rel.is_absolute() or ".." in rel.parts:
                raise RuntimeError(f"Ruta insegura dentro del ZIP: {member.filename}")

            out = (destino / rel).resolve()
            try:
                out.relative_to(base_resolved)
            except ValueError:
                raise RuntimeError(f"Ruta insegura dentro del ZIP: {member.filename}")

        z.extractall(destino)


def elemento_existente(carpeta: Path, item: Dict) -> Optional[Path]:
    nombre = limpiar_nombre(item["nombre"])

    exact_dir = carpeta / nombre
    if exact_dir.is_dir() and any(exact_dir.iterdir()):
        return exact_dir

    exact_file = carpeta / nombre
    if exact_file.is_file() and exact_file.stat().st_size > 0:
        return exact_file

    # Directos guardados como "Nombre.pdf", "Nombre.zip", etc.
    for p in carpeta.glob(nombre + ".*"):
        if p.is_file() and p.stat().st_size > 0:
            return p

    return None


def archivo_final_desde_temp(
    temp_path: Path,
    target_dir: Path,
    item: Dict,
    server_filename: Optional[str],
    content_type: str,
) -> Tuple[Path, str]:
    """
    Devuelve (ruta_final, modo):
      modo='extraido' o 'archivo'
    """
    display = limpiar_nombre(item["nombre"])
    visible_ext = extension_visible(display)
    server_ext = Path(server_filename).suffix.lower() if server_filename else ""
    magic_ext = extension_por_magic(temp_path, content_type, display)

    # La etiqueta visible tiene prioridad cuando ya incluye extensión real (ej. .csv).
    ext = visible_ext or server_ext or magic_ext

    # Un ZIP puede ser KMZ/Office. Nunca extraer esos contenedores.
    if magic_ext == ".zip":
        special = office_o_kmz_desde_zip(temp_path, display)
        if special:
            ext = visible_ext or server_ext or special

    is_zip = zipfile.is_zipfile(temp_path)
    lower_display = display.lower()

    # SHP suele venir como paquete ZIP y el usuario pidió que estos paquetes
    # se conviertan en carpetas con el nombre visible de SENACE.
    parece_paquete_shp = "shp" in lower_display and is_zip

    # Extraer solo un ZIP de paquete real, no KMZ/Office.
    container_exts = {".kmz", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
    extraer = is_zip and (ext == ".zip" or parece_paquete_shp) and ext not in container_exts

    if extraer:
        final_dir = target_dir / display
        if final_dir.exists():
            if final_dir.is_file():
                final_dir.unlink()
            elif any(final_dir.iterdir()):
                return final_dir, "extraido"
        final_dir.mkdir(parents=True, exist_ok=True)
        safe_extract_zip(temp_path, final_dir)
        return final_dir, "extraido"

    # Si el display ya termina en extensión válida, no la duplica.
    if visible_ext:
        final_name = display
    else:
        final_name = display + (ext or ".bin")

    final_path = target_dir / final_name
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_path, final_path)
    return final_path, "archivo"


def descargar_uno(
    item: Dict,
    raiz: Path,
    tmp_dir: Path,
    ssl_context,
) -> Dict:
    numero = int(item["numero"])
    target_dir = raiz / ruta_relativa(numero)
    target_dir.mkdir(parents=True, exist_ok=True)

    existente = elemento_existente(target_dir, item)
    if existente:
        return {
            "numero": numero,
            "nombre": item["nombre"],
            "estado": "YA EXISTIA",
            "ruta": str(existente.relative_to(raiz)),
            "tamano_bytes": existente.stat().st_size if existente.is_file() else "",
            "sha256": sha256_archivo(existente) if existente.is_file() else "",
            "server_filename": "",
            "detalle": "",
        }

    temp = tmp_dir / f"{numero:03d}.download"
    last_error = None

    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            if temp.exists():
                temp.unlink()

            req = urllib.request.Request(
                item["url"],
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": REFERER,
                    "Accept": "*/*",
                    "Accept-Language": "es-ES,es;q=0.9",
                },
                method="GET",
            )

            print(f"[{numero:03d}/205] Descargando: {item['nombre']}  (intento {intento})")
            with urllib.request.urlopen(req, timeout=120, context=ssl_context) as resp:
                status = getattr(resp, "status", 200)
                if status < 200 or status >= 300:
                    raise RuntimeError(f"HTTP {status}")

                server_filename = parse_filename(resp.headers)
                content_type = resp.headers.get("Content-Type", "") or ""

                # Evita guardar páginas de error como si fueran documentos.
                if "text/html" in content_type.lower() or "application/json" in content_type.lower():
                    preview = resp.read(500)
                    raise RuntimeError(
                        f"Respuesta inesperada ({content_type}): "
                        f"{preview[:200]!r}"
                    )

                total = resp.headers.get("Content-Length")
                total = int(total) if total and total.isdigit() else None

                leidos = 0
                with temp.open("wb") as f:
                    while True:
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        leidos += len(chunk)

                        if total and total > 0:
                            pct = min(100, (leidos * 100) // total)
                            print(
                                f"\r    {leidos / (1024**2):.1f} MB / "
                                f"{total / (1024**2):.1f} MB ({pct}%)",
                                end="",
                                flush=True,
                            )
                        else:
                            print(
                                f"\r    {leidos / (1024**2):.1f} MB",
                                end="",
                                flush=True,
                            )
                print()

            if not temp.exists() or temp.stat().st_size == 0:
                raise RuntimeError("SENACE devolvió un archivo vacío.")

            # Descarga completa. Procesar / renombrar.
            final, modo = archivo_final_desde_temp(
                temp, target_dir, item, server_filename, content_type
            )

            # Si se extrajo, el temp no fue movido.
            if temp.exists():
                temp.unlink()

            if final.is_file():
                size = final.stat().st_size
                digest = sha256_archivo(final)
            else:
                size = ""
                digest = ""

            print(f"    OK -> {final.relative_to(raiz)}")
            return {
                "numero": numero,
                "nombre": item["nombre"],
                "estado": "OK",
                "ruta": str(final.relative_to(raiz)),
                "tamano_bytes": size,
                "sha256": digest,
                "server_filename": server_filename or "",
                "detalle": modo,
            }

        except Exception as e:
            last_error = e
            print(f"    ERROR: {e}")
            if temp.exists():
                try:
                    temp.unlink()
                except Exception:
                    pass

            if intento < MAX_REINTENTOS:
                espera = 3 * intento
                print(f"    Reintentando en {espera} s...")
                time.sleep(espera)

    return {
        "numero": numero,
        "nombre": item["nombre"],
        "estado": "ERROR",
        "ruta": "",
        "tamano_bytes": "",
        "sha256": "",
        "server_filename": "",
        "detalle": repr(last_error),
    }


def incorporar_existentes(origen: Path, raiz: Path, items_by_num: Dict[int, Dict]) -> None:
    """
    Incorpora SOLO hijos directos de una carpeta plana.
    No escanea recursivamente para evitar confundir archivos internos.
    """
    if not origen.exists() or not origen.is_dir():
        print(f"No existe la carpeta de existentes: {origen}")
        return

    print(f"\nIncorporando elementos ya descargados desde:\n  {origen}\n")
    candidatos = list(origen.iterdir())

    for src in candidatos:
        m = re.match(r"^\s*(\d{1,3})\.", src.name)
        if not m:
            continue
        numero = int(m.group(1))
        item = items_by_num.get(numero)
        if not item:
            continue

        target_dir = raiz / ruta_relativa(numero)
        target_dir.mkdir(parents=True, exist_ok=True)

        if elemento_existente(target_dir, item):
            print(f"[{numero:03d}] Ya existe en destino; dejo el original sin tocar.")
            continue

        display = limpiar_nombre(item["nombre"])

        try:
            if src.is_dir():
                dst = target_dir / display
                print(f"[{numero:03d}] Moviendo carpeta -> {dst.relative_to(raiz)}")
                shutil.move(str(src), str(dst))
                continue

            # Si ya es ZIP de paquete, extraer y luego eliminar el ZIP original.
            if src.is_file() and zipfile.is_zipfile(src):
                special = office_o_kmz_desde_zip(src, display)
                low = display.lower()
                if not special and ("shp" in low or src.suffix.lower() == ".zip"):
                    dst = target_dir / display
                    print(f"[{numero:03d}] Extrayendo existente -> {dst.relative_to(raiz)}")
                    safe_extract_zip(src, dst)
                    src.unlink()
                    continue

            # Archivo directo: renombrar con el nombre visible + extensión original.
            visible_ext = extension_visible(display)
            ext = visible_ext or src.suffix
            dst = target_dir / (display if visible_ext else display + ext)
            print(f"[{numero:03d}] Moviendo archivo -> {dst.relative_to(raiz)}")
            shutil.move(str(src), str(dst))

        except Exception as e:
            print(f"[{numero:03d}] No pude incorporar {src.name}: {e}")


def escribir_manifest(raiz: Path, resultados: List[Dict]) -> None:
    manifest = raiz / "_MANIFIESTO_SENACE.csv"
    fields = [
        "numero", "nombre", "estado", "ruta", "tamano_bytes",
        "sha256", "server_filename", "detalle"
    ]
    with manifest.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(resultados)


def verificar(raiz: Path, items: List[Dict]) -> Tuple[List[int], List[str]]:
    faltantes: List[int] = []
    lineas: List[str] = []

    for item in items:
        numero = int(item["numero"])
        target_dir = raiz / ruta_relativa(numero)
        p = elemento_existente(target_dir, item)
        if p:
            lineas.append(f"OK    {numero:03d}  {item['nombre']}  ->  {p.relative_to(raiz)}")
        else:
            faltantes.append(numero)
            lineas.append(f"FALTA {numero:03d}  {item['nombre']}")

    return faltantes, lineas


def validar_json(items: List[Dict]) -> None:
    if len(items) != 205:
        raise RuntimeError(f"El JSON contiene {len(items)} elementos; se esperaban 205.")

    nums = [int(x["numero"]) for x in items]
    if sorted(nums) != list(range(1, 206)):
        faltan = sorted(set(range(1, 206)) - set(nums))
        repetidos = sorted(n for n in set(nums) if nums.count(n) > 1)
        raise RuntimeError(f"Numeración inválida. Faltan={faltan}; repetidos={repetidos}")

    docids = [x.get("docId", "") for x in items]
    if len(set(docids)) != len(docids):
        raise RuntimeError("Hay docId repetidos en el JSON.")

    for x in items:
        if not str(x.get("url", "")).startswith(
            "https://eva.senace.gob.pe:8443/AppIntegracionCMIS/rest/WebServiceECM/DownloadByGet?docId="
        ):
            raise RuntimeError(f"URL inesperada en el elemento {x.get('numero')}: {x.get('url')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Descarga y organiza los 205 documentos del EIA-d Romina desde SENACE."
    )
    parser.add_argument("--json", dest="json_path", help="Ruta al JSON de 205 documentos.")
    parser.add_argument("--destino", help="Carpeta raíz de salida.")
    parser.add_argument(
        "--existentes",
        help="Carpeta PLANA con descargas existentes numeradas (se moverán al destino).",
    )
    parser.add_argument(
        "--inseguro",
        action="store_true",
        help="Desactiva validación TLS. Usar solo si Python reporta error de certificado.",
    )
    parser.add_argument("--desde", type=int, default=1, help="Primer número a procesar.")
    parser.add_argument("--hasta", type=int, default=205, help="Último número a procesar.")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    json_path = Path(args.json_path).expanduser() if args.json_path else here / "Romina_SENACE_205_documentos.json"

    if not json_path.exists():
        print(f"No encuentro el JSON:\n  {json_path}")
        return 2

    with json_path.open("r", encoding="utf-8") as f:
        items = json.load(f)

    validar_json(items)
    items.sort(key=lambda x: int(x["numero"]))
    items_by_num = {int(x["numero"]): x for x in items}

    print("=" * 72)
    print(" EIA-d ROMINA — DESCARGADOR/ORGANIZADOR SENACE")
    print("=" * 72)
    print("JSON verificado: 205/205 elementos, numeración continua y docId únicos.\n")

    if args.destino:
        raiz = Path(args.destino).expanduser()
    else:
        defecto = here / "EIA-d Romina"
        entrada = input(f"Carpeta de destino [Enter = {defecto}]: ").strip().strip('"')
        raiz = Path(entrada).expanduser() if entrada else defecto

    raiz.mkdir(parents=True, exist_ok=True)
    tmp_dir = raiz / ".senace_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Guarda una copia del índice original dentro del expediente.
    try:
        shutil.copy2(json_path, raiz / "_INDICE_ORIGINAL_205.json")
    except Exception:
        pass

    existentes = args.existentes
    if existentes is None:
        respuesta = input(
            "\n¿Tienes una carpeta PLANA con archivos ya descargados (por ejemplo 70-97, 103)?\n"
            "Pega su ruta o deja Enter para omitir: "
        ).strip().strip('"')
        existentes = respuesta or None

    if existentes:
        incorporar_existentes(Path(existentes).expanduser(), raiz, items_by_num)

    desde = max(1, args.desde)
    hasta = min(205, args.hasta)
    if desde > hasta:
        print("Rango inválido.")
        return 2

    if args.inseguro:
        ssl_context = ssl._create_unverified_context()
        print("\nADVERTENCIA: validación TLS desactivada (--inseguro).\n")
    else:
        ssl_context = ssl.create_default_context()

    resultados: List[Dict] = []

    print("\nComenzando. Puedes volver a ejecutar el programa si se interrumpe:")
    print("lo que ya esté completo se saltará automáticamente.\n")

    try:
        for item in items:
            numero = int(item["numero"])
            if numero < desde or numero > hasta:
                continue
            resultado = descargar_uno(item, raiz, tmp_dir, ssl_context)
            resultados.append(resultado)
            escribir_manifest(raiz, resultados)

    except KeyboardInterrupt:
        print("\n\nInterrumpido por el usuario. No se pierde lo ya completado.")
        escribir_manifest(raiz, resultados)

    faltantes, lineas = verificar(raiz, items)
    verif = raiz / "_VERIFICACION_1-205.txt"
    with verif.open("w", encoding="utf-8") as f:
        f.write("VERIFICACIÓN EIA-d ROMINA — SENACE\n")
        f.write("=" * 72 + "\n\n")
        f.write("\n".join(lineas))
        f.write("\n\n" + "=" * 72 + "\n")
        if faltantes:
            f.write(f"FALTAN {len(faltantes)} elementos: {', '.join(map(str, faltantes))}\n")
        else:
            f.write("COMPLETO: 205/205 elementos presentes.\n")

    # Elimina temp si quedó vacío.
    try:
        if tmp_dir.exists() and not any(tmp_dir.iterdir()):
            tmp_dir.rmdir()
    except Exception:
        pass

    print("\n" + "=" * 72)
    if faltantes:
        print(f"VERIFICACIÓN: faltan {len(faltantes)} elementos.")
        print("Números:", ", ".join(map(str, faltantes)))
        print("Vuelve a ejecutar el programa: reintentará solo los faltantes.")
    else:
        print("VERIFICACIÓN FINAL: 205/205 elementos presentes.")
    print(f"Detalle: {verif}")
    print(f"Manifiesto: {raiz / '_MANIFIESTO_SENACE.csv'}")
    print("=" * 72)

    return 0 if not faltantes else 1


if __name__ == "__main__":
    raise SystemExit(main())
