
import json
import os
import unicodedata
import re

def slugify(s):
    if not s:
        return "general"
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower())
    return s.strip("_") or "general"

def process_json_file(path):
    print(f"Processing {path}")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        return

    items = data if isinstance(data, list) else [data]
    print(f"Found {len(items)} items")

    for item in items:
        carreras = item.get("carreras", [])
        if not isinstance(carreras, list):
            continue
        
        for car in carreras:
            short_code = str(car.get("carrera") or "").strip()
            
            # Logic from chunking.py
            nombre_carrera = ""
            datos_especiales = car.get("datos_especiales", [])
            for de in datos_especiales:
                titulo = str(de.get("titulo") or "").strip()
                contenido = str(de.get("contenido") or "").strip()
                if "nombre de la carrera" in titulo.lower():
                    nombre_carrera = contenido
            
            if not nombre_carrera:
                nombre_carrera = short_code or "Desconocida"

            slugs = [slugify(nombre_carrera)]
            if short_code and short_code not in slugs:
                slugs.append(short_code)
            
            carrera_slug = slugs
            
            if short_code == "software" or "software" in nombre_carrera.lower():
                print(f"--- Found Software ---")
                print(f"Short code: {short_code}")
                print(f"Nombre: {nombre_carrera}")
                print(f"Slugs: {slugs}")
                print(f"Carrera Slug (Metadata): {carrera_slug}")
                print("----------------------")

path = "/home/franpercivaldi/personalProyects/chatbot-ucc/data/xlsx/public-admisiones/datos_generales_carreras.json"
process_json_file(path)
