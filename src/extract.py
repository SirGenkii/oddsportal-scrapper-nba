import re
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

def extract_matches(
    soup: BeautifulSoup, *, base_url: str | None = None, with_links: bool = False
) -> list[dict]:
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

            match_data = {
                "date": normalize_date(current_date),
                "home_team": home,
                "away_team": away,
                "home_score": clean_score(home_score),
                "away_score": clean_score(away_score),
                "home_odds": home_odds,
                "away_odds": away_odds,
            }

            if with_links:
                link = row.select_one(".group a.w-full")
                href = link.get("href") if link else None
                if href and base_url:
                    match_data["match_url"] = urljoin(base_url, href)

            matches.append(match_data)

    return matches


def _extract_pivot_from_box(box) -> tuple[str | None, float | None]:
    """
    Extract pivot from the first <p> inside the option box, preferring values ending with '.5'.
    Returns (string_key, float_value) or (None, None).
    """
    if not box:
        return None, None
    p = box.select_one("p")
    text = p.get_text(strip=True) if p else box.get_text(strip=True)
    if not text:
        return None, None

    matches = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if not matches:
        return None, None

    pivot_str = next((m for m in matches if m.endswith(".5")), None)
    if not pivot_str:
        return None, None

    try:
        pivot_float = float(pivot_str)
    except ValueError:
        return None, None

    # Remove leading '+' for the JSON key
    key = pivot_str.lstrip("+")
    return key, pivot_float


def _parse_odds(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip().replace(",", ".")
    if text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def extract_over_under(
    soup: BeautifulSoup, *, default_odds: float = 1.73
) -> dict[str, dict]:
    """
    Parse over/under odds from a match page soup.

    Returns a mapping pivot -> {label, odds_over, odds_under}.
    """
    rows = soup.select(
        ".event-container > div:nth-child(2) > div > [data-testid='over-under-collapsed-row']"
    )
    if not rows:
        return {}

    parsed_rows: list[tuple[str, float | None, float | None]] = []

    for row in rows:
        pivot_box = row.select_one("[data-testid='over-under-collapsed-option-box']")
        pivot_str, pivot_float = _extract_pivot_from_box(pivot_box)
        if pivot_str is None or pivot_float is None:
            continue

        # Odds: grab the p inside odd-container-default (excludes payout / labels).
        price_cells = row.select("div[data-testid='odd-container-default'] p.height-content")
        odds_over = _parse_odds(price_cells[0].text if len(price_cells) >= 1 else None)
        odds_under = _parse_odds(price_cells[1].text if len(price_cells) >= 2 else None)

        parsed_rows.append((pivot_str, odds_over, odds_under))

    if not parsed_rows:
        return {}

    # Keep only .5 pivots (already filtered), decide odds fallback.
    valid_rows = [row for row in parsed_rows if row[0].endswith(".5")]
    if not valid_rows:
        return {}

    any_real_odds = any(
        (o is not None and u is not None) for _, o, u in valid_rows
    )

    result = {}
    for pivot_str, odds_over, odds_under in sorted(
        valid_rows, key=lambda item: float(item[0])
    ):
        # If we have at least one real odds, skip rows with missing odds ('-').
        if any_real_odds and (odds_over is None or odds_under is None):
            continue

        odds_over_final = odds_over if odds_over is not None else default_odds
        odds_under_final = odds_under if odds_under is not None else default_odds
        if pivot_str in result:
            continue  # keep first occurrence deterministically
        result[pivot_str] = {
            "label": float(pivot_str),
            "odds_over": odds_over_final,
            "odds_under": odds_under_final,
        }

    return result
