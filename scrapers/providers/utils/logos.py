import os
import json
import re
import unicodedata

# Ruta al archivo JSON con logos
CURRENT_DIR = os.path.dirname(__file__)
LOGOS_JSON = os.path.join(CURRENT_DIR, "football_logos.json")

# Cargar el archivo JSON
try:
    with open(LOGOS_JSON, "r", encoding="utf-8") as f:
        logos_data = json.load(f)
except Exception as e:
    print(f"❌ Error cargando football_logos.json: {e}")
    logos_data = []

# ------------------------------
# Normalización y utilidades
# ------------------------------

def normalize(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^a-z0-9\s\-]", "", text)
    text = text.replace(" fc", "").replace(" cf", "")
    text = re.sub(r"[-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def tokenize(text: str) -> set:
    return set(normalize(text).split())

# ------------------------------
# Búsqueda por coincidencia
# ------------------------------

def get_team_logo(name: str) -> str | None:
    input_tokens = tokenize(name)
    best_score = 0
    best_logo = None

    for entry in logos_data:
        logo_tokens = tokenize(entry["name"])
        common = input_tokens & logo_tokens
        score = len(common)

        if score > best_score:
            best_score = score
            best_logo = entry["img_url"]

    return best_logo