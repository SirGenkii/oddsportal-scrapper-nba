
import csv
import re
import unicodedata
from pathlib import Path

import dateparser

from src.config import OUTPUT_DIR


def clean_score(value: str) -> str:
    """Extrait le dernier nombre si format du type '100–106'."""

    if not value:
        return ""

    value = unicodedata.normalize("NFKD", value)  # Convertit ‘–’ en '-'
    parts = re.findall(r"\d+", value)
    if parts:
        return parts[-1]  # On prend le dernier nombre, donc le score away
    return ""


def normalize_date(raw_date: str) -> str | None:
    parsed = dateparser.parse(raw_date)
    if not parsed:
        return None
    return parsed.strftime("%Y-%m-%d")


def slugify(value: str) -> str:
    """Simplifie une chaîne pour être utilisée dans un nom de fichier."""

    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    return value.strip("_").lower() or "untitled"


def build_output_path(today_dir: str, sport: str, tournament: str) -> Path:
    return OUTPUT_DIR / today_dir / slugify(sport) / slugify(tournament)


def save_matches_to_csv(
    *,
    sport: str,
    tournament: str,
    season_label: str,
    matches: list[dict],
    today_dir: str,
):
    if not matches:
        return

    output_path = build_output_path(today_dir, sport, tournament)
    output_path.mkdir(parents=True, exist_ok=True)

    filename = output_path / f"{slugify(season_label)}.csv"

    fieldnames = list(matches[0].keys())
    with filename.open(mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)

    print(f"✅ Sauvegardé {len(matches)} matchs → {filename}")
