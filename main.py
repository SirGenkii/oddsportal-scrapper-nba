import asyncio
from src.scraper import scrape_all_pages_for_season, scroll_to_bottom
from src.extract import extract_seasons
from src.utils import save_matches_to_csv
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from datetime import datetime

from src.config import *

today = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print(f"\U0001F4E5 Chargement de la page : {BASE_URL}")
        await page.goto(BASE_URL, wait_until="networkidle")
        await scroll_to_bottom(page)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        seasons = extract_seasons(soup)
        for label, url in seasons:
            print(f"\n\U0001F680 Scraping saison {label}")
            matches = await scrape_all_pages_for_season(page, url)
            if matches:
                save_matches_to_csv(label, matches, today_dir=today)
                
        print(f"\n\U0001F4C8 Scraping terminé, résultats sauvegardés dans le dossier '{OUTPUT_DIR}/{today}'")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
