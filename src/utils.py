
import csv
import os
from datetime import datetime
import re
import unicodedata
import dateparser

from src.config import OUTPUT_DIR


def clean_score(value: str) -> str:
    """Extrait le dernier nombre si format du type '100–106' """
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)  # Convertit ‘–’ en '-'
    parts = re.findall(r"\d+", value)
    if parts:
        return parts[-1]  # On prend le dernier nombre, donc le score away
    return ""

def normalize_date(raw_date: str) -> str:
    parsed = dateparser.parse(raw_date)
    if not parsed:
        return None
    return parsed.strftime("%Y-%m-%d")

def save_matches_to_csv(season_label: str, matches: list[dict], today_dir):
    
    #today = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    output_path = os.path.join(OUTPUT_DIR, today_dir)
    
    os.makedirs(output_path, exist_ok=True)
    filename =  os.path.join(output_path, f"nba_{season_label.replace('/', '_').replace('-', '_')}.csv")

    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(matches[0].keys()))
        writer.writeheader()
        writer.writerows(matches)

    print(f"✅ Sauvegardé {len(matches)} matchs → {filename}")
