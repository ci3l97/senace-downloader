#!/usr/bin/env python3
"""Combina un manifiesto plano con estructura.json y escribe un manifiesto con rutas."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import senace_downloader as sd

p = argparse.ArgumentParser()
p.add_argument("manifest")
p.add_argument("estructura")
p.add_argument("salida")
p.add_argument("--titulo")
args = p.parse_args()

with Path(args.manifest).open("r", encoding="utf-8") as f:
    manifest = sd.normalize_manifest(json.load(f))
if args.titulo:
    manifest["project_title"] = args.titulo
ranges = sd.load_structure(Path(args.estructura))
sd.apply_structure(manifest, ranges)
Path(args.salida).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK: {len(manifest['documents'])} documentos -> {args.salida}")
