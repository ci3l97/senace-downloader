# -*- coding: utf-8 -*-
"""SENACE Downloader (no oficial).

Descarga documentos públicos expuestos por Consulta Ciudadana de SENACE a partir
 de un manifiesto JSON. El manifiesto puede incluir la ruta jerárquica de cada
 documento o puede combinarse con un archivo de estructura por rangos.

Solo usa la biblioteca estándar de Python.
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
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

VERSION = "0.2.0-alpha"
DEFAULT_REFERER = "https://consultaciudadana.senace.gob.pe/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)
DEFAULT_ALLOWED_HOSTS = {"eva.senace.gob.pe"}
CHUNK = 1024 * 1024
INVALID_WINDOWS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

KNOWN_EXTS = {
    ".csv", ".pdf", ".zip", ".kmz", ".kml", ".shp", ".dbf", ".shx",
    ".prj", ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt", ".txt",
    ".jpg", ".jpeg", ".png", ".rar", ".7z", ".xml", ".geojson", ".gpkg",
}
CONTAINER_EXTS = {".kmz", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}


def clean_name(name: str) -> str:
    name = INVALID_WINDOWS.sub("_", str(name)).rstrip(" .")
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", name, re.I):
        name = "_" + name
    if len(name) > 120:
        name = name[:100].rstrip(" .") + "_" + hashlib.sha256(name.encode()).hexdigest()[:12]
    return name or "sin_nombre"


def visible_extension(name: str) -> str:
    m = re.search(r"(\.[A-Za-z0-9]{2,8})$", name)
    if not m:
        return ""
    ext = m.group(1).lower()
    return ext if ext in KNOWN_EXTS else ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def parse_content_disposition(headers: Any) -> Optional[str]:
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
        return Path(urllib.parse.unquote(raw)).name
    return None


def office_or_kmz_from_zip(path: Path, display_name: str) -> Optional[str]:
    if "kmz" in display_name.lower():
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


def extension_from_magic(path: Path, content_type: str, display_name: str) -> str:
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
    if head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return office_or_kmz_from_zip(path, display_name) or ".zip"

    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    mapping = {
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
    if ctype in mapping:
        return mapping[ctype]
    guessed = mimetypes.guess_extension(ctype) if ctype else None
    return guessed or ""


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    with zipfile.ZipFile(zip_path) as z:
        seen = set()
        for member in z.infolist():
            rel = Path(member.filename.replace("\\", "/"))
            if (rel.is_absolute() or rel.drive or ".." in rel.parts
                    or any(clean_name(p) != p for p in rel.parts)
                    or (member.external_attr >> 16) & 0o170000 == 0o120000):
                raise RuntimeError(f"Ruta insegura dentro del ZIP: {member.filename}")
            key = str(rel).casefold()
            if key in seen:
                raise RuntimeError(f"Ruta duplicada dentro del ZIP: {member.filename}")
            seen.add(key)
            out = (destination / rel).resolve()
            try:
                out.relative_to(base)
            except ValueError:
                raise RuntimeError(f"Ruta insegura dentro del ZIP: {member.filename}")
        z.extractall(destination)


def normalize_manifest(raw: Any) -> Dict[str, Any]:
    """Admite el formato nuevo o la lista plana usada en el caso Romina."""
    if isinstance(raw, list):
        docs = raw
        title = "Expediente SENACE"
        metadata = {"schema_version": 0, "source": "legacy-flat-list"}
    elif isinstance(raw, dict) and isinstance(raw.get("documents"), list):
        if raw.get("schema_version", 1) != 1:
            raise ValueError("schema_version no soportada; se requiere 1.")
        docs = raw["documents"]
        title = raw.get("project_title") or raw.get("title") or "Expediente SENACE"
        metadata = dict(raw)
    else:
        raise ValueError("El manifiesto debe ser una lista o un objeto con 'documents'.")

    normalized: List[Dict[str, Any]] = []
    for i, d in enumerate(docs, start=1):
        if not isinstance(d, dict):
            raise ValueError(f"Documento #{i}: se esperaba un objeto JSON.")
        number = d.get("numero", i)
        if type(number) is not int or number <= 0:
            raise ValueError(f"Documento #{i}: numero debe ser un entero positivo.")
        name = str(d.get("nombre") or d.get("name") or f"Documento {number}").strip()
        url = str(d.get("url") or "").strip()
        docid = str(d.get("docId") or d.get("docid") or "").strip()
        route = d.get("ruta") or d.get("path") or []
        if isinstance(route, str):
            route = [p for p in re.split(r"[\\/]", route) if p]
        if not isinstance(route, list):
            raise ValueError(f"Documento {number}: 'ruta' debe ser lista o texto.")
        normalized.append({
            "numero": number,
            "nombre": name,
            "url": url,
            "docId": docid,
            "ruta": [str(p).strip() for p in route if str(p).strip()],
            "tipo": str(d.get("tipo") or "auto").lower(),
        })

    return {
        **metadata,
        "schema_version": metadata.get("schema_version", 1),
        "project_title": str(title),
        "source": metadata.get("source", "senace-consulta-ciudadana"),
        "documents": normalized,
    }


def load_structure(path: Optional[Path]) -> List[Dict[str, Any]]:
    if not path:
        return []
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        raw = raw.get("ranges") or raw.get("rangos") or []
    if not isinstance(raw, list):
        raise ValueError("La estructura debe ser una lista de rangos.")
    result = []
    for r in raw:
        start = int(r.get("desde") if "desde" in r else r.get("start"))
        end = int(r.get("hasta") if "hasta" in r else r.get("end"))
        route = r.get("ruta") or r.get("path") or []
        if isinstance(route, str):
            route = [p for p in re.split(r"[\\/]", route) if p]
        result.append({"desde": start, "hasta": end, "ruta": [str(x) for x in route]})
    return result


def apply_structure(manifest: Dict[str, Any], ranges: List[Dict[str, Any]]) -> None:
    if not ranges:
        return
    for doc in manifest["documents"]:
        if doc.get("ruta"):
            continue
        n = int(doc["numero"])
        matches = [r for r in ranges if r["desde"] <= n <= r["hasta"]]
        if len(matches) > 1:
            raise ValueError(f"El documento {n} cae en más de un rango de estructura.")
        if matches:
            doc["ruta"] = list(matches[0]["ruta"])


def validate_manifest(manifest: Dict[str, Any], allow_other_hosts: bool = False) -> List[str]:
    docs = manifest["documents"]
    if not docs:
        raise ValueError("El manifiesto no contiene documentos.")

    numbers = [int(d["numero"]) for d in docs]
    if len(set(numbers)) != len(numbers):
        dup = sorted(n for n in set(numbers) if numbers.count(n) > 1)
        raise ValueError(f"Hay números repetidos: {dup}")

    docids = [d["docId"] for d in docs if d.get("docId")]
    if len(docids) != len(set(docids)):
        raise ValueError("Hay docId repetidos en el manifiesto.")

    warnings: List[str] = []
    destinations = []
    for d in docs:
        dest = (route_for(d) / clean_name(d["nombre"])).as_posix().casefold()
        for previous in destinations:
            if dest == previous or dest.startswith(previous + "/") or previous.startswith(dest + "/") or dest.startswith(previous + ".") or previous.startswith(dest + "."):
                raise ValueError(f"Destinos que colisionan en Windows: {d['nombre']}")
        destinations.append(dest)
        if d["tipo"] not in {"auto", "file", "archivo", "package", "zip-package"}:
            raise ValueError(f"Tipo desconocido: {d['tipo']}")
    sorted_nums = sorted(numbers)
    expected = list(range(sorted_nums[0], sorted_nums[-1] + 1))
    missing = sorted(set(expected) - set(sorted_nums))
    if missing:
        warnings.append(f"Numeración con huecos: {missing}")

    for d in docs:
        url = d.get("url", "")
        if not url:
            raise ValueError(f"Documento {d['numero']} sin URL.")
        parsed = urllib.parse.urlparse(url)
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"Documento {d['numero']}: URL inválida.")
        query_id = urllib.parse.parse_qs(parsed.query).get("docId", [""])[0]
        if query_id and d["docId"] and query_id != d["docId"]:
            raise ValueError(f"Documento {d['numero']}: docId no coincide con la URL.")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Documento {d['numero']}: URL no HTTP(S).")
        if not allow_other_hosts and parsed.hostname not in DEFAULT_ALLOWED_HOSTS:
            raise ValueError(
                f"Documento {d['numero']}: host no permitido ({parsed.hostname}). "
                "Use --allow-other-hosts solo para pruebas controladas."
            )
        if parsed.hostname == "eva.senace.gob.pe" and "DownloadByGet" not in parsed.path:
            warnings.append(f"Documento {d['numero']}: URL SENACE con endpoint inesperado.")
    return warnings


def route_for(doc: Dict[str, Any]) -> Path:
    route = doc.get("ruta") or ["Documentos"]
    return Path(*(clean_name(p) for p in route))


def existing_element(directory: Path, doc: Dict[str, Any]) -> Optional[Path]:
    receipt = directory / (clean_name(doc["nombre"]) + ".senace.json")
    try:
        record = json.loads(receipt.read_text(encoding="utf-8"))
        if record["identity"] != document_identity(doc):
            return None
        final = directory / record["name"]
        final.resolve().relative_to(directory.resolve())
        if inventory(final) == record["files"]:
            return final
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def document_identity(doc: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def inventory(path: Path) -> Dict[str, str]:
    if path.is_file():
        return {".": sha256_file(path)}
    if not path.is_dir():
        raise ValueError("Salida inexistente")
    return {str(p.relative_to(path)): sha256_file(p) for p in sorted(path.rglob("*")) if p.is_file()}


def finalize_download(
    temp_path: Path,
    target_dir: Path,
    doc: Dict[str, Any],
    server_filename: Optional[str],
    content_type: str,
    no_extract: bool,
    keep_zip: bool,
) -> Tuple[Path, str]:
    display = clean_name(doc["nombre"])
    visible_ext = visible_extension(display)
    server_ext = Path(server_filename).suffix.lower() if server_filename else ""
    magic_ext = extension_from_magic(temp_path, content_type, display)
    ext = visible_ext or server_ext or magic_ext

    if magic_ext == ".zip":
        special = office_or_kmz_from_zip(temp_path, display)
        if special:
            ext = visible_ext or server_ext or special

    is_zip = zipfile.is_zipfile(temp_path)
    declared = str(doc.get("tipo") or "auto").lower()
    lower_display = display.lower()
    shp_package = "shp" in lower_display and is_zip

    should_extract = (
        is_zip
        and not no_extract
        and ext not in CONTAINER_EXTS
        and (
            declared == "package"
            or declared == "zip-package"
            or ext == ".zip"
            or shp_package
        )
    )

    if declared in {"file", "archivo"}:
        should_extract = False

    if should_extract:
        final_dir = target_dir / display
        # Extrae primero a staging. Así una interrupción no deja una carpeta final
        # a medio extraer que en la siguiente ejecución parezca completa.
        staging = target_dir / (display + ".__senace_extracting__")
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            safe_extract_zip(temp_path, staging)
            if final_dir.exists():
                if final_dir.is_dir():
                    shutil.rmtree(final_dir)
                else:
                    final_dir.unlink()
            staging.rename(final_dir)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        if keep_zip:
            zip_copy = target_dir / (display + ".zip")
            shutil.copy2(temp_path, zip_copy)
        temp_path.unlink(missing_ok=True)
        return final_dir, "extraido"

    final_name = display if visible_ext else display + (ext or ".bin")
    final_path = target_dir / final_name
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_path, final_path)
    return final_path, "archivo"


def request_headers(range_start: int = 0) -> Dict[str, str]:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": DEFAULT_REFERER,
        "Accept": "*/*",
        "Accept-Language": "es-ES,es;q=0.9",
        "Connection": "keep-alive",
    }
    if range_start > 0:
        headers["Range"] = f"bytes={range_start}-"
    return headers


def download_one(
    doc: Dict[str, Any],
    root: Path,
    temp_dir: Path,
    ssl_context: ssl.SSLContext,
    retries: int,
    timeout: int,
    no_extract: bool,
    keep_zip: bool,
) -> Dict[str, Any]:
    number = int(doc["numero"])
    target_dir = root / route_for(doc)
    target_dir.mkdir(parents=True, exist_ok=True)

    existing = existing_element(target_dir, doc)
    if existing:
        return {
            "numero": number, "nombre": doc["nombre"], "estado": "YA EXISTIA",
            "ruta": str(existing.relative_to(root)),
            "tamano_bytes": existing.stat().st_size if existing.is_file() else "",
            "sha256": sha256_file(existing) if existing.is_file() else "",
            "server_filename": "", "detalle": "",
        }

    part = temp_dir / f"{document_identity(doc)}.part"
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            resume_from = part.stat().st_size if part.exists() else 0
            req = urllib.request.Request(
                doc["url"], headers=request_headers(resume_from), method="GET"
            )
            print(f"[{number}] {doc['nombre']} (intento {attempt}/{retries})")
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
                status = getattr(resp, "status", 200)
                content_type = resp.headers.get("Content-Type", "") or ""
                server_filename = parse_content_disposition(resp.headers)

                if "text/html" in content_type.lower() or "application/json" in content_type.lower():
                    preview = resp.read(500)
                    raise RuntimeError(f"Respuesta inesperada {content_type}: {preview[:180]!r}")

                # Si el servidor ignoró Range y respondió 200, reinicia el archivo parcial.
                append = resume_from > 0 and status == 206
                if resume_from > 0 and status == 200:
                    append = False
                    resume_from = 0
                if status not in (200, 206):
                    raise RuntimeError(f"HTTP {status}")

                if status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", resp.headers.get("Content-Range", ""))
                    if not match or int(match[1]) != resume_from or int(match[2]) + 1 != int(match[3]):
                        part.unlink(missing_ok=True)
                        raise RuntimeError("Content-Range inválido; se reiniciará la descarga.")

                length = resp.headers.get("Content-Length")
                remaining = int(length) if length and length.isdigit() else None
                total = (resume_from + remaining) if remaining is not None else None
                if status == 206:
                    total = int(match[3])
                mode = "ab" if append else "wb"
                written = resume_from

                with part.open(mode) as f:
                    while True:
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        written += len(chunk)
                        if total:
                            pct = min(100, int(written * 100 / total))
                            print(
                                f"\r    {written/(1024**2):.1f} / {total/(1024**2):.1f} MB ({pct}%)",
                                end="", flush=True,
                            )
                        else:
                            print(f"\r    {written/(1024**2):.1f} MB", end="", flush=True)
                print()
                if total is not None and written != total:
                    raise RuntimeError(
                        f"Descarga incompleta: {written} de {total} bytes. "
                        "Se conservará el parcial para reanudar."
                    )

            if not part.exists() or part.stat().st_size == 0:
                raise RuntimeError("Archivo vacío.")

            final, mode = finalize_download(
                part, target_dir, doc, server_filename, content_type,
                no_extract=no_extract, keep_zip=keep_zip,
            )
            size = final.stat().st_size if final.is_file() else ""
            digest = sha256_file(final) if final.is_file() else ""
            receipt = target_dir / (clean_name(doc["nombre"]) + ".senace.json")
            pending = receipt.with_suffix(".tmp")
            pending.write_text(json.dumps({"identity": document_identity(doc), "name": final.name,
                                           "files": inventory(final)}, ensure_ascii=False), encoding="utf-8")
            os.replace(pending, receipt)
            print(f"    OK -> {final.relative_to(root)}")
            return {
                "numero": number, "nombre": doc["nombre"], "estado": "OK",
                "ruta": str(final.relative_to(root)), "tamano_bytes": size,
                "sha256": digest, "server_filename": server_filename or "", "detalle": mode,
            }

        except urllib.error.HTTPError as e:
            last_error = e
            # Un 416 suele significar que el parcial ya tiene el tamaño completo. Para no
            # adivinar el tipo, reiniciamos una sola vez de forma segura.
            if e.code == 416 and part.exists():
                part.unlink(missing_ok=True)
            print(f"    ERROR HTTP {e.code}: {e.reason}")
        except Exception as e:
            last_error = e
            print(f"    ERROR: {e}")

        if attempt < retries:
            wait = min(30, 2 ** (attempt - 1) * 2)
            print(f"    Reintentando en {wait} s...")
            time.sleep(wait)

    return {
        "numero": number, "nombre": doc["nombre"], "estado": "ERROR",
        "ruta": "", "tamano_bytes": "", "sha256": "", "server_filename": "",
        "detalle": repr(last_error),
    }


def write_manifest_csv(root: Path, results: List[Dict[str, Any]]) -> None:
    fields = [
        "numero", "nombre", "estado", "ruta", "tamano_bytes", "sha256",
        "server_filename", "detalle",
    ]
    with (root / "_MANIFIESTO_DESCARGA.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)


def verify(root: Path, docs: Iterable[Dict[str, Any]]) -> Tuple[List[int], List[str]]:
    missing: List[int] = []
    lines: List[str] = []
    for doc in docs:
        n = int(doc["numero"])
        directory = root / route_for(doc)
        p = existing_element(directory, doc)
        if p:
            lines.append(f"OK    {n:04d}  {doc['nombre']}  ->  {p.relative_to(root)}")
        else:
            missing.append(n)
            lines.append(f"FALTA {n:04d}  {doc['nombre']}")
    return missing, lines


def select_documents(manifest: Dict[str, Any], start: Optional[int], end: Optional[int]) -> List[Dict[str, Any]]:
    docs = sorted(manifest["documents"], key=lambda d: int(d["numero"]))
    if start is not None:
        docs = [d for d in docs if int(d["numero"]) >= start]
    if end is not None:
        docs = [d for d in docs if int(d["numero"]) <= end]
    return docs


def dry_run(docs: Iterable[Dict[str, Any]]) -> None:
    for d in docs:
        route = route_for(d)
        print(f"{d['numero']:>4} | {route} | {d['nombre']}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Descargador no oficial para Consulta Ciudadana de SENACE.")
    p.add_argument("manifest", help="Manifiesto JSON exportado desde Consulta Ciudadana.")
    p.add_argument("--estructura", help="JSON opcional con rangos -> rutas jerárquicas.")
    p.add_argument("--destino", help="Carpeta raíz de salida.")
    p.add_argument("--desde", type=int, help="Primer número a procesar.")
    p.add_argument("--hasta", type=int, help="Último número a procesar.")
    p.add_argument("--reintentos", type=int, default=4)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--pausa", type=float, default=0.35, help="Pausa entre elementos (segundos).")
    p.add_argument("--dry-run", action="store_true", help="Valida y muestra la estructura sin descargar.")
    p.add_argument("--no-extraer", action="store_true", help="No extrae paquetes ZIP.")
    p.add_argument("--conservar-zip", action="store_true", help="Conserva además el ZIP al extraer un paquete.")
    p.add_argument("--inseguro", action="store_true", help="Desactiva validación TLS (solo diagnóstico).")
    p.add_argument("--allow-other-hosts", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    manifest_path = Path(args.manifest).expanduser().resolve()
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = normalize_manifest(json.load(f))

    ranges = load_structure(Path(args.estructura).expanduser().resolve() if args.estructura else None)
    apply_structure(manifest, ranges)
    warnings = validate_manifest(manifest, allow_other_hosts=args.allow_other_hosts)

    print("=" * 72)
    print(f" SENACE DOWNLOADER {VERSION} — herramienta no oficial")
    print("=" * 72)
    print(f"Proyecto: {manifest['project_title']}")
    print(f"Documentos: {len(manifest['documents'])}")
    for w in warnings:
        print(f"ADVERTENCIA: {w}")

    docs = select_documents(manifest, args.desde, args.hasta)
    if not docs:
        print("ERROR: el rango indicado no selecciona ningún documento.")
        return 2
    print(f"Selección: {len(docs)} de {len(manifest['documents'])} documentos")

    if args.dry_run:
        print()
        dry_run(docs)
        return 0

    default_root = manifest_path.parent / "descargas" / clean_name(manifest["project_title"])
    root = Path(args.destino).expanduser().resolve() if args.destino else default_root
    root.mkdir(parents=True, exist_ok=True)
    temp_dir = root / ".senace_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    with (root / "_MANIFIESTO_ORIGINAL_NORMALIZADO.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    ssl_context = ssl._create_unverified_context() if args.inseguro else ssl.create_default_context()
    results: List[Dict[str, Any]] = []
    try:
        for idx, doc in enumerate(docs):
            result = download_one(
                doc, root, temp_dir, ssl_context, retries=max(1, args.reintentos),
                timeout=max(1, args.timeout), no_extract=args.no_extraer,
                keep_zip=args.conservar_zip,
            )
            results.append(result)
            write_manifest_csv(root, results)
            if idx < len(docs) - 1 and args.pausa > 0:
                time.sleep(args.pausa)
    except KeyboardInterrupt:
        print("\nInterrumpido. Los archivos parciales se conservan para reanudar.")
        write_manifest_csv(root, results)

    missing, lines = verify(root, docs)
    verification = root / "_VERIFICACION.txt"
    with verification.open("w", encoding="utf-8") as f:
        f.write(f"SENACE Downloader {VERSION}\n")
        f.write("=" * 72 + "\n\n")
        f.write("\n".join(lines))
        f.write("\n\n" + "=" * 72 + "\n")
        if missing:
            f.write(f"FALTAN {len(missing)}: {', '.join(map(str, missing))}\n")
        else:
            f.write(f"COMPLETO: {len(docs)}/{len(docs)} elementos seleccionados presentes.\n")

    if not missing:
        try:
            if temp_dir.exists() and not any(temp_dir.iterdir()):
                temp_dir.rmdir()
        except Exception:
            pass

    print("\n" + "=" * 72)
    if missing:
        print(f"Verificación: faltan {len(missing)} elementos.")
        print("Números:", ", ".join(map(str, missing)))
    else:
        print(f"Verificación: {len(docs)}/{len(docs)} elementos seleccionados presentes.")
    print(f"Detalle: {verification}")
    print("=" * 72)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
