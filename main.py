import argparse
import asyncio
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from src.config import DEFAULT_SPORT, OUTPUT_DIR, SPORTS_CONFIG, get_sport_config
from src.extract import extract_seasons
from src.scraper import scrape_all_pages_for_season, scroll_to_bottom
from src.utils import save_matches_to_csv, slugify


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scraper OddsPortal multi-sports")
    available_sports = get_available_sports()
    parser.add_argument(
        "--sport",
        default=DEFAULT_SPORT,
        choices=available_sports,
        help="Sport à scraper (par défaut: %(default)s)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Lance le navigateur Playwright en mode headless",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Reprend le dernier scraping inachevé (écrit dans le dernier dossier d'output).",
    )
    parser.add_argument(
        "--over_under",
        action="store_true",
        help="Active le scraping des over/under (NBA uniquement pour l'instant).",
    )
    parser.add_argument(
        "--over_under_same_window",
        action="store_true",
        help="Ouvre les onglets over/under dans la même fenêtre (peut prendre le focus). Par défaut ils s'ouvrent en arrière-plan headless.",
    )
    parser.add_argument(
        "--start_minimized",
        action="store_true",
        help="Lance la fenêtre navigateur minimisée (évite de prendre le focus en mode non-headless).",
    )
    return parser.parse_args()


def get_available_sports() -> list[str]:
    return sorted(SPORTS_CONFIG.keys())


def load_tournaments(config: dict) -> list[dict[str, str]]:
    if "tournaments" in config:
        return config["tournaments"]

    if "tournaments_csv" in config:
        csv_path = Path(config["tournaments_csv"])

        if not csv_path.exists():
            raise FileNotFoundError(f"Fichier CSV introuvable: {csv_path}")
        with csv_path.open(newline="", encoding="utf-8") as f:
            filtered_lines = (line for line in f if line.strip())
            reader = csv.DictReader(filtered_lines)
            tournaments = []
            seen_urls: set[str] = set()
            for row in reader:
                results_url = (row.get("results_url") or "").strip()
                if not results_url or results_url in seen_urls:
                    continue
                seen_urls.add(results_url)

                name = (row.get("tournament_name") or "").strip()
                if not name:
                    parts = results_url.rstrip("/").split("/")
                    slug = parts[-2] if len(parts) >= 2 else parts[-1]
                    name = slug.replace("-", " ").title()

                tournaments.append({"name": name, "results_url": results_url})

            return tournaments

    raise ValueError("Configuration sport invalide: aucun tournoi défini")


@dataclass
class RepairPlan:
    today_dir: str
    last_tournament_slug: str
    last_season_slug: str
    existing_season_slugs: dict[str, set[str]]


def prepare_repair_plan(sport: str) -> RepairPlan:
    sport_slug = slugify(sport)
    if not OUTPUT_DIR.exists():
        raise ValueError("Impossible d'activer --repair : aucun dossier output.")

    run_dirs = sorted(
        (path for path in OUTPUT_DIR.iterdir() if path.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for run_dir in run_dirs:
        sport_dir = run_dir / sport_slug
        if not sport_dir.is_dir():
            continue

        existing: dict[str, set[str]] = {}
        last_file: Path | None = None
        last_mtime = float("-inf")

        for tournament_dir in sport_dir.iterdir():
            if not tournament_dir.is_dir():
                continue
            csv_files = [
                csv_file for csv_file in tournament_dir.glob("*.csv") if csv_file.is_file()
            ]
            if not csv_files:
                continue

            slug = tournament_dir.name
            existing[slug] = {csv_file.stem for csv_file in csv_files}

            latest_csv = max(csv_files, key=lambda f: f.stat().st_mtime)
            mtime = latest_csv.stat().st_mtime
            if mtime > last_mtime:
                last_mtime = mtime
                last_file = latest_csv

        if last_file:
            return RepairPlan(
                today_dir=run_dir.name,
                last_tournament_slug=last_file.parent.name,
                last_season_slug=last_file.stem,
                existing_season_slugs=existing,
            )

    raise ValueError(
        "Impossible d'activer --repair : aucun CSV existant pour déterminer le dernier scrap."
    )


async def scrape_tournament(
    page,
    *,
    sport: str,
    tournament_name: str,
    results_url: str,
    today_dir: str,
    emoji: str,
    skip_existing_season_slugs: set[str] | None = None,
    over_under: bool = False,
    over_under_config: dict | None = None,
    over_under_context=None,
):
    print(f"\n{emoji} Scraping {sport.upper()} – {tournament_name}")

    await page.goto(results_url, wait_until="networkidle")
    await scroll_to_bottom(page)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    seasons = extract_seasons(soup, results_url)
    if not seasons:
        print("⚠️ Aucun onglet de saison détecté pour ce tournoi.")
        return

    skipped_slugs = set(skip_existing_season_slugs or set())
    scraped_any = False

    for season_label, season_url in seasons:
        season_slug = slugify(season_label)
        if season_slug in skipped_slugs:
            print(f"   ⏭️ Saison {season_label} déjà sauvegardée, on passe.")
            continue

        print(f"\n🚀 Scraping saison {season_label}")
        matches = await scrape_all_pages_for_season(
            page,
            season_url,
            over_under=over_under,
            over_under_config=over_under_config,
            over_under_context=over_under_context,
        )
        if not matches:
            print(f"   ➜ Aucune rencontre trouvée pour {season_label}")
            continue

        enriched_matches = [
            {
                **match,
                "sport": sport,
                "tournament": tournament_name,
                "season": season_label,
            }
            for match in matches
        ]

        save_matches_to_csv(
            sport=sport,
            tournament=tournament_name,
            season_label=season_label,
            matches=enriched_matches,
            today_dir=today_dir,
        )
        scraped_any = True

    if skipped_slugs and not scraped_any:
        print("ℹ️ Rien à réparer pour ce tournoi, toutes les saisons présentes.")


async def main():
    args = parse_args()
    sport = args.sport
    config = get_sport_config(sport)
    over_under_enabled = bool(args.over_under)
    sport_supports_over_under = config.get("supports_over_under", False)
    if over_under_enabled and not sport_supports_over_under:
        print("⚠️ Option --over_under ignorée : sport non supporté.")
        over_under_enabled = False
    over_under_same_window = bool(args.over_under_same_window)

    tournaments = load_tournaments(config)
    slug_to_name = {slugify(t["name"]): t["name"] for t in tournaments}

    sport_emoji = config.get("emoji", "🏟️")

    if not tournaments:
        raise ValueError(f"Aucun tournoi configuré pour le sport '{sport}'")

    repair_plan: RepairPlan | None = None
    today_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if args.repair:
        repair_plan = prepare_repair_plan(sport)
        today_dir = repair_plan.today_dir
        last_tournament_name = slug_to_name.get(
            repair_plan.last_tournament_slug, repair_plan.last_tournament_slug
        )
        print(
            f"🔁 Mode repair → dossier '{today_dir}', reprise après "
            f"{last_tournament_name} / {repair_plan.last_season_slug}"
        )

    resume_reached = not (repair_plan and repair_plan.last_tournament_slug)
    if repair_plan and repair_plan.last_tournament_slug not in slug_to_name:
        print(
            "⚠️ Dernier tournoi trouvé dans l'output introuvable dans la configuration. "
            "Reprise depuis le début."
        )
        resume_reached = True

    async with async_playwright() as p:
        launch_args = ["--start-minimized"] if args.start_minimized else None
        browser = await p.chromium.launch(headless=args.headless, args=launch_args)
        context = await browser.new_context()
        page = await context.new_page()
        over_under_context = None
        bg_browser = None
        if over_under_enabled and not args.headless and not over_under_same_window:
            bg_browser = await p.chromium.launch(headless=True)
            over_under_context = await bg_browser.new_context()

        for tournament in tournaments:
            tournament_slug = slugify(tournament["name"])

            if repair_plan and not resume_reached:
                if tournament_slug == repair_plan.last_tournament_slug:
                    resume_reached = True
                else:
                    print(
                        f"⏭️ {tournament['name']} déjà scrapé lors de la dernière exécution."
                    )
                    continue

            skip_seasons = (
                set(repair_plan.existing_season_slugs.get(tournament_slug, set()))
                if repair_plan
                else None
            )

            await scrape_tournament(
                page,
                sport=sport,
                tournament_name=tournament["name"],
                results_url=tournament["results_url"],
                today_dir=today_dir,
                emoji=sport_emoji,
                skip_existing_season_slugs=skip_seasons,
                over_under=over_under_enabled,
                over_under_config=config.get("over_under_config"),
                over_under_context=over_under_context,
            )

        print(
            f"\n📈 Scraping terminé, résultats sauvegardés dans le dossier '{OUTPUT_DIR / today_dir}'"
        )

        if over_under_context:
            await over_under_context.close()
        if bg_browser:
            await bg_browser.close()
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
