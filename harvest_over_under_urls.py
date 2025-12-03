import argparse
import asyncio
import contextlib
import csv
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from main import load_tournaments
from src.config import DEFAULT_SPORT, OUTPUT_DIR, get_sport_config
from src.extract import extract_matches, extract_seasons
from src.scraper import dismiss_overlays, scroll_to_bottom
from src.utils import build_output_path, slugify


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Étape 1: collecte des URLs over/under sans ouvrir les pages détail."
    )
    parser.add_argument(
        "--sport",
        default=DEFAULT_SPORT,
        choices=list(get_sport_config(s) and s for s in ["nba", "atp"]),
        help="Sport à scraper (par défaut: nba)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Lance le navigateur Playwright en mode headless",
    )
    return parser.parse_args()


async def scrape_all_pages_urls(page, base_url: str) -> list[dict]:
    all_matches = []

    await page.goto(base_url, wait_until="networkidle")
    await dismiss_overlays(page)
    await scroll_to_bottom(page)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    all_matches.extend(extract_matches(soup, base_url=page.url, with_links=True))

    page_num = 1
    while True:
        def pagination_locator():
            return page.locator("div.pagination").locator("a.pagination-link")

        try:
            await pagination_locator().first.wait_for(state="visible", timeout=2000)
        except Exception:
            break

        next_button = pagination_locator().last
        try:
            next_text = await next_button.text_content()
        except Exception:
            break
        if not next_text or "next" not in next_text.lower():
            break

        await dismiss_overlays(page)
        try:
            await next_button.wait_for(state="attached", timeout=2000)
            await next_button.scroll_into_view_if_needed()
            await next_button.click(force=True)
        except Exception:
            break

        await page.wait_for_load_state("networkidle")
        with contextlib.suppress(Exception):
            await page.wait_for_selector("div.eventRow", timeout=4000)
        await page.wait_for_timeout(500)
        await scroll_to_bottom(page)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        all_matches.extend(extract_matches(soup, base_url=page.url, with_links=True))
        page_num += 1

    # Normalize match_url -> url key
    normalized = []
    for match in all_matches:
        data = {k: v for k, v in match.items() if k != "match_url"}
        data["url"] = match.get("match_url", "")
        normalized.append(data)
    return normalized


def save_urls_csv(matches: list[dict], *, sport: str, tournament: str, season_label: str, today_dir: str):
    if not matches:
        return
    output_path = build_output_path(today_dir, sport, tournament)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = output_path / f"{slugify(season_label)}.csv"
    fieldnames = [
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "home_odds",
        "away_odds",
        "url",
        "sport",
        "tournament",
        "season",
    ]
    with filename.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)
    print(f"✅ URLs sauvegardées → {filename}")


async def main():
    args = parse_args()
    sport = args.sport
    config = get_sport_config(sport)
    tournaments = load_tournaments(config)
    if not tournaments:
        raise ValueError("Aucun tournoi configuré.")

    today_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        page = await browser.new_page()

        for tournament in tournaments:
            print(f"\n🏀 Harvest URLs – {tournament['name']}")
            await page.goto(tournament["results_url"], wait_until="networkidle")
            await scroll_to_bottom(page)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            seasons = extract_seasons(soup, tournament["results_url"])
            for season_label, season_url in seasons:
                print(f"   ➜ Saison {season_label}")
                matches = await scrape_all_pages_urls(page, season_url)
                enriched = [
                    {
                        **m,
                        "sport": sport,
                        "tournament": tournament["name"],
                        "season": season_label,
                    }
                    for m in matches
                ]
                save_urls_csv(
                    enriched,
                    sport=sport,
                    tournament=tournament["name"],
                    season_label=season_label,
                    today_dir=today_dir,
                )

        await browser.close()
    print(f"\n🏁 Harvest terminé. Dossier: {OUTPUT_DIR / today_dir}")


if __name__ == "__main__":
    asyncio.run(main())
