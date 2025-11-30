from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.utils import clean_score, normalize_date


def extract_seasons(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    seen = set()
    seasons: list[tuple[str, str]] = []

    for a in soup.select("div.flex.flex-wrap a.cursor-pointer"):
        label = a.text.strip()
        url = a.get("href")
        if not url:
            continue
        absolute_url = urljoin(base_url, url)
        if absolute_url in seen:
            continue
        seasons.append((label, absolute_url))
        seen.add(absolute_url)

    return seasons

def extract_matches(soup: BeautifulSoup) -> list[dict]:
    matches = []
    rows = soup.select("div.eventRow")
    current_date = None

    for row in rows:
        header = row.select_one("div[data-testid='date-header']")
        if header:
            current_date = header.text.strip().split(" - ")[0]

        game_block = row.select_one("div[data-testid='game-row']")
        if not game_block:
            continue

        teams = row.select("p.participant-name")
        scores = row.select("div.font-bold")

        # Cotes (2 blocs successifs)
        odd_blocks = row.select("div.flex-center.border-black-main")
        home_odds = away_odds = ""

        if len(odd_blocks) >= 2:
            home_p = odd_blocks[0].select_one("p")
            away_p = odd_blocks[1].select_one("p")
            home_odds = home_p.text.strip() if home_p else ""
            away_odds = away_p.text.strip() if away_p else ""

        if len(teams) >= 2:
            home = teams[0].text.strip()
            away = teams[1].text.strip()
            home_score = scores[0].text.strip() if len(scores) >= 1 else ""
            away_score = scores[1].text.strip() if len(scores) >= 2 else ""

            matches.append({
                "date": normalize_date(current_date),
                "home_team": home,
                "away_team": away,
                "home_score": clean_score(home_score),
                "away_score": clean_score(away_score),
                "home_odds": home_odds,
                "away_odds": away_odds,
            })

    return matches
