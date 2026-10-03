#!/usr/bin/env python3
"""Valida un manifiesto SENACE sin descargar nada."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import senace_downloader as sd

p = argparse.ArgumentParser()
p.add_argument("manifest")
p.add_argument("--estructura")
args = p.parse_args()

with Path(args.manifest).open("r", encoding="utf-8") as f:
    m = sd.normalize_manifest(json.load(f))
if args.estructura:
    sd.apply_structure(m, sd.load_structure(Path(args.estructura)))
warnings = sd.validate_manifest(m)
print(f"OK: {len(m['documents'])} documentos; docId únicos; URLs válidas.")
for w in warnings:
    print("ADVERTENCIA:", w)
missing_routes = [d['numero'] for d in m['documents'] if not d.get('ruta')]
if missing_routes:
    print(f"RUTAS VACÍAS: {len(missing_routes)} documentos (se guardarán en 'Documentos').")
else:
    print("RUTAS: todos los documentos tienen jerarquía.")
