import io
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import senace_downloader as sd


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class CoreTests(unittest.TestCase):
    def test_clean_name_windows(self):
        self.assertEqual(sd.clean_name('A:B<C>"D/\\E|F?G*.'), 'A_B_C__D__E_F_G_')

    def test_reserved_names(self):
        for name in ["CON", "nul.txt", "LPT1.csv", "COM¹"]:
            self.assertTrue(sd.clean_name(name).startswith("_"))

    def test_collision_after_windows_normalization(self):
        m = sd.normalize_manifest([
            {"nombre": "A:B", "url": "https://eva.senace.gob.pe/x"},
            {"nombre": "a?b", "url": "https://eva.senace.gob.pe/y"},
        ])
        with self.assertRaises(ValueError):
            sd.validate_manifest(m)

    def test_invalid_schema_and_number(self):
        for raw in [{"schema_version": 2, "documents": []}, [{"numero": 1.5}]]:
            with self.assertRaises(ValueError):
                sd.normalize_manifest(raw)

    def test_zip_windows_unsafe_names(self):
        for name in ["C:/escape.txt", "file:stream", "NUL.txt", "a./file"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                p = Path(td) / "bad.zip"
                p.write_bytes(make_zip({name: "bad"}))
                with self.assertRaises(RuntimeError):
                    sd.safe_extract_zip(p, Path(td) / "out")

    def test_manifest_legacy_and_structure(self):
        raw = [
            {"numero": 1, "nombre": "1. Uno", "url": "https://eva.senace.gob.pe:8443/x/DownloadByGet?docId=a", "docId": "a"},
            {"numero": 2, "nombre": "2. Dos", "url": "https://eva.senace.gob.pe:8443/x/DownloadByGet?docId=b", "docId": "b"},
        ]
        m = sd.normalize_manifest(raw)
        sd.apply_structure(m, [{"desde": 1, "hasta": 2, "ruta": ["Capítulo", "Sub"]}])
        self.assertEqual(m["documents"][0]["ruta"], ["Capítulo", "Sub"])
        self.assertFalse(sd.validate_manifest(m))

    def test_duplicate_docid_rejected(self):
        m = sd.normalize_manifest([
            {"numero": 1, "nombre": "A", "url": "https://eva.senace.gob.pe/x/DownloadByGet?docId=x", "docId": "x"},
            {"numero": 2, "nombre": "B", "url": "https://eva.senace.gob.pe/x/DownloadByGet?docId=x", "docId": "x"},
        ])
        with self.assertRaises(ValueError):
            sd.validate_manifest(m)

    def test_safe_zip_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            z = td / "bad.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("../escape.txt", "x")
            with self.assertRaises(RuntimeError):
                sd.safe_extract_zip(z, td / "out")

    def test_kmz_not_confused_with_package(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.tmp"
            p.write_bytes(make_zip({"doc.kml": "<kml/>"}))
            self.assertEqual(sd.office_or_kmz_from_zip(p, "Mapa KMZ"), ".kmz")
            self.assertEqual(sd.extension_from_magic(p, "application/zip", "Mapa KMZ"), ".kmz")


class TestHandler(BaseHTTPRequestHandler):
    payloads = {}
    counts = {}

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        cls = type(self)
        cls.counts[self.path] = cls.counts.get(self.path, 0) + 1
        if self.path not in cls.payloads:
            self.send_error(404)
            return

        data, ctype, filename = cls.payloads[self.path]
        range_header = self.headers.get("Range")
        start = 0
        status = 200
        if range_header and range_header.startswith("bytes="):
            start = int(range_header.split("=", 1)[1].split("-", 1)[0])
            if start >= len(data):
                self.send_response(416)
                self.end_headers()
                return
            status = 206

        body = data[start:]
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{len(data)-1}/{len(data)}")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = b"%PDF-1.4\nsynthetic\n%%EOF\n"
        cls.csv = b"x,y\n1,2\n"
        cls.package = make_zip({"sub/a.txt": "hola", "b.csv": "a,b\n1,2\n"})
        cls.kmz = make_zip({"doc.kml": "<kml><Document/></kml>"})
        cls.resume = (b"0123456789abcdef" * 8192)  # 128 KiB
        TestHandler.payloads = {
            "/pdf": (cls.pdf, "application/pdf", "original.pdf"),
            "/csv": (cls.csv, "text/csv", "original.csv"),
            "/package": (cls.package, "application/zip", "anexo.zip"),
            "/kmz": (cls.kmz, "application/zip", "mapa.kmz"),
            "/resume": (cls.resume, "application/octet-stream", "resume.bin"),
        }
        TestHandler.counts = {}
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_end_to_end_and_resume_and_skip(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            manifest = {
                "schema_version": 1,
                "project_title": "Prueba",
                "documents": [
                    {"numero": 1, "nombre": "1. Texto", "url": self.base + "/pdf", "docId": "a", "ruta": ["A"]},
                    {"numero": 2, "nombre": "2. datos.csv", "url": self.base + "/csv", "docId": "b", "ruta": ["A"]},
                    {"numero": 3, "nombre": "3. Anexo paquete", "url": self.base + "/package", "docId": "c", "ruta": ["B"]},
                    {"numero": 4, "nombre": "4. Mapa KMZ", "url": self.base + "/kmz", "docId": "d", "ruta": ["B"]},
                    {"numero": 5, "nombre": "5. Resume", "url": self.base + "/resume", "docId": "e", "ruta": ["C"]},
                ],
            }
            mf = td / "manifest.json"
            mf.write_text(json.dumps(manifest), encoding="utf-8")
            out = td / "out"
            temp = out / ".senace_tmp"
            temp.mkdir(parents=True)
            # Simula una sesión anterior interrumpida a mitad del documento 5.
            partial = self.resume[:32768]
            normalized = sd.normalize_manifest(manifest)
            (temp / (sd.document_identity(normalized["documents"][4]) + ".part")).write_bytes(partial)

            rc = sd.main([
                str(mf), "--destino", str(out), "--allow-other-hosts",
                "--pausa", "0", "--reintentos", "2", "--timeout", "10",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual((out / "A" / "1. Texto.pdf").read_bytes(), self.pdf)
            self.assertEqual((out / "A" / "2. datos.csv").read_bytes(), self.csv)
            self.assertTrue((out / "B" / "3. Anexo paquete" / "sub" / "a.txt").exists())
            self.assertEqual((out / "B" / "4. Mapa KMZ.kmz").read_bytes(), self.kmz)
            self.assertEqual((out / "C" / "5. Resume.bin").read_bytes(), self.resume)
            self.assertIn("COMPLETO: 5/5", (out / "_VERIFICACION.txt").read_text(encoding="utf-8"))

            counts_before = dict(TestHandler.counts)
            rc2 = sd.main([
                str(mf), "--destino", str(out), "--allow-other-hosts", "--pausa", "0"
            ])
            self.assertEqual(rc2, 0)
            self.assertEqual(counts_before, TestHandler.counts, "La segunda ejecución no debería volver a descargar.")
            (out / "A" / "1. Texto.pdf").write_bytes(b"corrupto")
            (out / "B" / "3. Anexo paquete" / "sub" / "a.txt").unlink()
            self.assertEqual(sd.main([str(mf), "--destino", str(out),
                                     "--allow-other-hosts", "--pausa", "0"]), 0)
            self.assertEqual((out / "A" / "1. Texto.pdf").read_bytes(), self.pdf)
            self.assertEqual((out / "B" / "3. Anexo paquete" / "sub" / "a.txt").read_text(), "hola")
            self.assertEqual(TestHandler.counts["/pdf"], counts_before["/pdf"] + 1)
            self.assertEqual(TestHandler.counts["/package"], counts_before["/package"] + 1)

    def test_partial_range_verifies_only_selected_documents(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            manifest = {
                "schema_version": 1,
                "project_title": "Rango parcial",
                "documents": [
                    {"numero": 1, "nombre": "1. Uno", "url": self.base + "/pdf", "docId": "range-a", "ruta": ["A"]},
                    {"numero": 2, "nombre": "2. Dos", "url": self.base + "/csv", "docId": "range-b", "ruta": ["A"]},
                    {"numero": 3, "nombre": "3. Tres", "url": self.base + "/package", "docId": "range-c", "ruta": ["B"]},
                ],
            }
            mf = td / "manifest.json"
            mf.write_text(json.dumps(manifest), encoding="utf-8")
            out = td / "out"
            counts_before = dict(TestHandler.counts)

            rc = sd.main([
                str(mf), "--destino", str(out), "--allow-other-hosts",
                "--hasta", "2", "--pausa", "0",
            ])

            self.assertEqual(rc, 0)
            report = (out / "_VERIFICACION.txt").read_text(encoding="utf-8")
            self.assertIn("COMPLETO: 2/2 elementos seleccionados presentes.", report)
            self.assertNotIn("FALTA 0003", report)
            self.assertEqual(TestHandler.counts.get("/package", 0), counts_before.get("/package", 0))



if __name__ == "__main__":
    unittest.main()
