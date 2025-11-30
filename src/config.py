"""Centralised configuration for the OddsPortal scraper."""

from pathlib import Path


OUTPUT_DIR = Path("output")

NBA_BASE_URL = "https://www.oddsportal.com/basketball/usa/nba/results/"

ATP_TOURNAMENTS_CSV = Path("data/tennis/oddsportal_atp_results_urls.csv")


SPORTS_CONFIG: dict[str, dict] = {
    "nba": {
        "label": "NBA",
        "emoji": "🏀",
        "tournaments": [
            {
                "name": "NBA",
                "results_url": NBA_BASE_URL,
            }
        ],
    },
    "atp": {
        "label": "ATP",
        "emoji": "🎾",
        "tournaments_csv": ATP_TOURNAMENTS_CSV,
    },
}


def get_sport_config(sport: str) -> dict:
    try:
        return SPORTS_CONFIG[sport]
    except KeyError as exc:
        available = ", ".join(sorted(SPORTS_CONFIG))
        raise ValueError(
            f"Sport inconnu '{sport}'. Sports disponibles: {available}"
        ) from exc


DEFAULT_SPORT = "nba"
