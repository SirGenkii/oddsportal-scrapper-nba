import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import csv
import os
import datetime



BASE_URL = "https://www.oddsportal.com/basketball/usa/nba/results/"
OUTPUT_DIR = "output"



def save_matches_to_csv(season_label: str, matches: list[dict]):
    
    today = datetime.date.today().strftime("%Y-%m-%d_%H-%M-%S")
    
    output_path = os.path.join(OUTPUT_DIR, today)
    
    os.makedirs(output_path, exist_ok=True)
    filename =  os.path.join(output_path, f"nba_{season_label.replace('/', '_').replace('-', '_')}.csv")

    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(matches[0].keys()))
        writer.writeheader()
        writer.writerows(matches)

    print(f"✅ Sauvegardé {len(matches)} matchs → {filename}")

async def get_page_html(page, url: str) -> str:
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(3000)

    # Refuse la redirection JS si elle est visible
    # (Souvent déclenchée en cas de cookies non acceptés)
    current_url = page.url
    
    print(f"🔗 Chargement de {current_url}")
    
    # Scroll jusqu'en bas pour forcer le chargement de tous les matchs
    await scroll_to_bottom(page)

    return await page.content()



# N'oublie pas de déclarer ces fonctions au-dessus
def extract_seasons(soup: BeautifulSoup) -> list[tuple[str, str]]:
    seen = set()
    seasons = []


    for a in soup.select("div.flex.flex-wrap a.cursor-pointer"):
        label = a.text.strip()
        url = a.get("href")
        if url and url.startswith("http") and url not in seen:
            seasons.append((label, url))
            seen.add(url)

    return seasons[:4]

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
            home_score = scores[0].text.strip() if len(scores) > 1 else ""
            away_score = scores[1].text.strip() if len(scores) > 1 else ""

            matches.append({
                "date": current_date,
                "home_team": home,
                "away_team": away,
                "home_score": home_score,
                "away_score": away_score,
                "home_odds": home_odds,
                "away_odds": away_odds,
            })

    return matches


async def scroll_to_bottom(page, step: int = 1000, delay: int = 500):
    """
    Scrolls until no more height is added to the page.
    """
    prev_height = await page.evaluate("() => document.body.scrollHeight")
    while True:
        await page.evaluate(f"window.scrollBy(0, {step})")
        await page.wait_for_timeout(delay)
        new_height = await page.evaluate("() => document.body.scrollHeight")
        if new_height == prev_height:
            break
        prev_height = new_height

async def scrape_all_pages_for_season(page, base_url: str) -> list[dict]:
    all_matches = []

    await page.goto(base_url, wait_until="networkidle")
    await scroll_to_bottom(page)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    all_matches.extend(extract_matches(soup))

    page_num = 1
    while True:
        
        pagination_block = page.locator("div.pagination")   
        
        #last a.pagination-link in pagination_block
        
        next_button = pagination_block.locator("a.pagination-link").last
        
        # find the text of the next button
        next_button_text = await next_button.text_content()
        if not next_button_text or "next" not in next_button_text.lower():
            print("🔚 Aucune page suivante détectée, fin du scraping.")
            break
        

        print(f"📄 Page suivante détectée → chargement page {page_num + 1}")
        await next_button.click()
        await page.wait_for_timeout(3000)
        await scroll_to_bottom(page)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        all_matches.extend(extract_matches(soup))

        page_num += 1

    return all_matches


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print(f"📥 Chargement de la page : {BASE_URL}")
        await page.goto(BASE_URL, wait_until="networkidle")
        await scroll_to_bottom(page)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        seasons = extract_seasons(soup)
        for label, url in seasons:
            print(f"\n🚀 Scraping saison {label}")
            matches = await scrape_all_pages_for_season(page, url)
            if matches:
                save_matches_to_csv(label, matches)

        await browser.close()




if __name__ == "__main__":
    asyncio.run(main())
