import asyncio
from src.extract import extract_matches
from bs4 import BeautifulSoup


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

