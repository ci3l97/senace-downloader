import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import senace_downloader as sd


class RominaFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = ROOT / "examples" / "romina" / "manifest.json"
        cls.manifest = sd.normalize_manifest(json.loads(p.read_text(encoding="utf-8")))

    def test_has_exact_205_contiguous_documents(self):
        docs = self.manifest["documents"]
        self.assertEqual(len(docs), 205)
        self.assertEqual(sorted(d["numero"] for d in docs), list(range(1, 206)))

    def test_docids_unique(self):
        ids = [d["docId"] for d in self.manifest["documents"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_have_hierarchy(self):
        self.assertTrue(all(d["ruta"] for d in self.manifest["documents"]))

    def test_known_boundaries(self):
        by_n = {d["numero"]: d for d in self.manifest["documents"]}
        self.assertEqual(by_n[1]["ruta"], ["01. Ficha Resumen", "02. Ubicación y extensión del proyecto"])
        self.assertEqual(by_n[70]["ruta"][-1], "03. Estudio de la Línea Base Ambiental")
        self.assertEqual(by_n[196]["ruta"], ["04. Pagos y otros requisitos TUPA", "02. Documentos Adjuntos"])
        self.assertEqual(by_n[205]["nombre"], "205. Carta, cargo y matriz (Información complementaria) 231024")

    def test_manifest_validates(self):
        self.assertEqual(sd.validate_manifest(self.manifest), [])


if __name__ == "__main__":
    unittest.main()
