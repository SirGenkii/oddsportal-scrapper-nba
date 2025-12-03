import asyncio
import contextlib
import json

from bs4 import BeautifulSoup
from playwright.async_api import Error, TimeoutError

from src.extract import extract_matches, extract_over_under
from src.utils import build_over_under_url


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


async def dismiss_overlays(page):
    """Best-effort removal of top banners / cookie dialogs that block clicks."""

    # Try clicking common consent buttons
    selectors = [
        "#onetrust-accept-btn-handler",
        "button#onetrust-accept-btn-handler",
        "button[id*='accept']",
        "button:has-text('Accept All')",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        if await locator.count():
            with contextlib.suppress(Exception):
                await locator.first.click(timeout=2000)
                await page.wait_for_timeout(250)

    # Hide sticky legal banners / overlays intercepting pointer events
    await page.evaluate(
        """
        () => {
            const ids = ["onetrust-consent-sdk", "onetrust-banner-sdk"];
            ids.forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.remove();
            });
            document
                .querySelectorAll("div[data-testid='banner-legal-text']")
                .forEach((el) => {
                    const parent = el.closest("div");
                    if (parent) parent.style.display = "none";
                    el.style.display = "none";
                });
        }
        """
    )


async def scrape_over_under_for_match(
    context, match_url: str, config: dict, over_under_url: str | None = None
) -> dict:
    """Open a new tab, navigate to over/under tab, and extract odds."""
    tab = await context.new_page()
    try:
        url = (
            over_under_url
            or build_over_under_url(
                match_url,
                fragment=config.get("fragment", "over-under;1"),
                preserve_query=config.get("preserve_query", False),
                preserve_existing_fragment=config.get("preserve_existing_fragment", False),
            )
        )
        await tab.goto(url, wait_until="networkidle")
        await dismiss_overlays(tab)
        with contextlib.suppress(TimeoutError):
            await tab.wait_for_selector(".event-container", timeout=4000)
        html = await tab.content()
        soup = BeautifulSoup(html, "html.parser")
        return extract_over_under(
            soup, default_odds=config.get("default_odds_value", 1.73)
        )
    except Exception as exc:  # noqa: BLE001 - best-effort scraping
        print(f"⚠️ Impossible de récupérer l'over/under pour {match_url}: {exc}")
        return {}
    finally:
        with contextlib.suppress(Exception):
            await tab.close()


async def enrich_matches_with_over_under(
    page,
    matches: list[dict],
    config: dict,
    *,
    over_under_context=None,
) -> list[dict]:
    context = over_under_context or page.context
    enriched: list[dict] = []
    for match in matches:
        match_url = match.get("match_url")
        handicap_data = {}
        over_under_url = ""
        if match_url:
            over_under_url = build_over_under_url(
                match_url,
                fragment=config.get("fragment", "over-under;1"),
                preserve_query=config.get("preserve_query", False),
                preserve_existing_fragment=config.get("preserve_existing_fragment", False),
            )
            handicap_data = await scrape_over_under_for_match(
                context, match_url, config, over_under_url=over_under_url
            )

        cleaned_match = {k: v for k, v in match.items() if k != "match_url"}
        cleaned_match["handicap"] = json.dumps(
            handicap_data, ensure_ascii=False, sort_keys=True
        )
        cleaned_match["url"] = over_under_url
        enriched.append(cleaned_match)

    return enriched


async def scrape_all_pages_for_season(
    page,
    base_url: str,
    *,
    over_under: bool = False,
    over_under_config: dict | None = None,
    over_under_context=None,
    with_links: bool = False,
) -> list[dict]:
    all_matches = []

    await page.goto(base_url, wait_until="networkidle")
    await dismiss_overlays(page)
    await scroll_to_bottom(page)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    page_matches = extract_matches(
        soup, base_url=page.url, with_links=over_under or with_links
    )
    if over_under and page_matches:
        page_matches = await enrich_matches_with_over_under(
            page,
            page_matches,
            over_under_config or {},
            over_under_context=over_under_context,
        )
    all_matches.extend(page_matches)

    page_num = 1
    while True:
        
        
        def pagination_locator():
            return page.locator("div.pagination").locator("a.pagination-link")

        try:
            await pagination_locator().first.wait_for(state="visible", timeout=2000)
        except TimeoutError:
            print("🔚 Aucune pagination détectée après le délai, fin du scraping.")
            break

        next_button = pagination_locator().last
        # find the text of the next button, retrying if the node is refreshed
        for attempt in range(3):
            try:
                next_button_text = await next_button.text_content()
                break
            except Error:
                if attempt == 2:
                    raise
                await page.wait_for_timeout(200)
                next_button = pagination_locator().last
        else:
            next_button_text = ""
        
        if not next_button_text or "next" not in next_button_text.lower():
            print("🔚 Aucune page suivante détectée, fin du scraping.")
            break
        

        print(f"📄 Page suivante détectée → chargement page {page_num + 1}")
        await dismiss_overlays(page)
        
        # Clicking while the pager re-renders can detach the element; retry if needed
        for attempt in range(3):
            try:
                await next_button.wait_for(state="attached", timeout=2000)
                await next_button.scroll_into_view_if_needed()
                await next_button.click(force=True)
                break
            except Error:
                if attempt == 2:
                    raise
                await page.wait_for_timeout(200)
                next_button = pagination_locator().last        

        await page.wait_for_load_state("networkidle")
        with contextlib.suppress(Exception):
            await page.wait_for_selector("div.eventRow", timeout=4000)
        await page.wait_for_timeout(500)
        await scroll_to_bottom(page)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        page_matches = extract_matches(
            soup, base_url=page.url, with_links=over_under or with_links
        )
        if over_under and page_matches:
            page_matches = await enrich_matches_with_over_under(
                page,
                page_matches,
                over_under_config or {},
                over_under_context=over_under_context,
            )
        all_matches.extend(page_matches)

        page_num += 1

    return all_matches
