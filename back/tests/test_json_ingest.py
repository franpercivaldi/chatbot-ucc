import os
import json
import tempfile
import unittest
import sys

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.chunking import process_json_file

class TestJsonIngest(unittest.TestCase):
    def test_process_json_file(self):
        # Create a dummy JSON file
        data = [
            {
                "unidad": "Ingeniería",
                "carreras": [
                    {
                        "carrera": "ingenieria-sistemas",
                        "codigoSiucc": "ING-SIS",
                        "datos_especiales": [
                            {"titulo": "nombre de la carrera", "contenido": "Ingeniería en Sistemas"},
                            {"titulo": "perfil", "contenido": "El ingeniero..."}
                        ]
                    }
                ]
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            json.dump(data, tmp)
            tmp_path = tmp.name
            
        try:
            records = process_json_file(tmp_path, "test-bot")
            
            self.assertEqual(len(records), 1)
            rec = records[0]
            
            # Check metadata
            self.assertEqual(rec["metadata"]["domain"], "carreras")
            self.assertEqual(rec["metadata"]["carrera"], "Ingeniería en Sistemas")
            self.assertEqual(rec["metadata"]["carrera_id"], "ING-SIS")
            self.assertEqual(rec["metadata"]["periodo"], "general")
            self.assertEqual(rec["metadata"]["facultad"], "Ingeniería")
            self.assertEqual(rec["metadata"]["bot_id"], "test-bot")
            
            # Check text
            self.assertIn("UNIDAD ACADÉMICA: Ingeniería", rec["texto"])
            self.assertIn("NOMBRE DE LA CARRERA: Ingeniería en Sistemas", rec["texto"])
            self.assertIn("PERFIL: El ingeniero...", rec["texto"])
            
        finally:
            os.remove(tmp_path)

if __name__ == '__main__':
    unittest.main()
