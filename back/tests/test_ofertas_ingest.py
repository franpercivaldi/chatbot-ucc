import os
import csv
import tempfile
import unittest

from app.rag.chunking import load_xlsx_dir


class TestOfertasIngest(unittest.TestCase):
    def test_load_ofertas_enriches_carrera_and_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            carreras_path = os.path.join(tmp, "carreras.csv")
            ofertas_path = os.path.join(tmp, "ofertas_carreras.csv")

            # carreras.csv con nombre legible
            with open(carreras_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["carrera_id", "carrera_nombre", "titulo", "area_estudio", "nivel_estudio"])
                writer.writerow(["0601", "ABOGACIA", "Abogado", "Derecho", "GRADO"])

            # ofertas_carreras.csv solo trae el ID y fechas
            with open(ofertas_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["carrera_id", "anio_ingreso", "periodo", "cursos_ingreso", "inicio_actividad", "fuente"])
                writer.writerow(["0601", "2025", "2025", "FEB-2025", "11-03-2025", "datos_carreras_ofertas"])

            records = load_xlsx_dir(tmp, bot_id="test-bot")
            self.assertEqual(len(records), 1)
            rec = records[0]
            md = rec["metadata"]

            self.assertEqual(md["domain"], "oferta")
            self.assertEqual(md["tipo"], "fechas_ingreso")
            self.assertEqual(md["carrera_id"], "0601")
            self.assertEqual(md["carrera"], "ABOGACIA")
            self.assertIn("Curso de ingreso ABOGACIA", rec["texto"])
            self.assertEqual(md["periodo"], "2025")


if __name__ == "__main__":
    unittest.main()
