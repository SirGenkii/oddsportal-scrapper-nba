import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from src.config import OUTPUT_DIR, get_sport_config
from src.extract import extract_over_under
from src.scraper import dismiss_overlays
from src.utils import build_over_under_url, slugify


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Répare les handicaps over/under vides en relançant la récupération depuis les URLs stockées."
    )
    parser.add_argument("--sport", default="nba", help="Sport à traiter (par défaut: nba).")
    parser.add_argument(
        "--run_dir",
        help="Dossier d'output à réparer (par défaut: le plus récent contenant le sport ciblé).",
    )
    return parser.parse_args()


def find_latest_run_dir(sport_slug: str) -> Path:
    if not OUTPUT_DIR.exists():
        raise FileNotFoundError("Aucun dossier output trouvé.")

    run_dirs = sorted(
        (p for p in OUTPUT_DIR.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for run_dir in run_dirs:
        sport_dir = run_dir / sport_slug
        if sport_dir.is_dir():
            return run_dir
    raise FileNotFoundError(f"Aucun dossier contenant le sport '{sport_slug}' trouvé.")


def list_csv_files(run_dir: Path, sport_slug: str) -> Iterable[Path]:
    sport_dir = run_dir / sport_slug
    if not sport_dir.exists():
        return []
    return sorted(sport_dir.rglob("*.csv"))


def handicap_is_empty(value: str | None) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    try:
        parsed = json.loads(text)
    except Exception:
        return False
    return parsed == {} or parsed == [] or parsed is None


async def fetch_handicap(page, url: str, config: dict) -> dict:
    target_url = build_over_under_url(
        url,
        fragment=config.get("fragment", "over-under;1"),
        preserve_query=config.get("preserve_query", False),
        preserve_existing_fragment=config.get("preserve_existing_fragment", False),
    )
    await page.goto(target_url, wait_until="networkidle")
    await dismiss_overlays(page)
    await page.wait_for_timeout(500)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    return extract_over_under(
        soup, default_odds=config.get("default_odds_value", 1.73)
    )


async def repair_csv_file(page, csv_path: Path, over_under_config: dict, log_entries: list[str]):
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    if "handicap" not in fieldnames or "url" not in fieldnames:
        return False  # skip files that don't support over/under

    updated = False
    for idx, row in enumerate(rows, start=2):  # header is line 1
        if not handicap_is_empty(row.get("handicap")):
            continue
        url = (row.get("url") or "").strip()
        if not url:
            continue
        home = row.get("home_team", "?")
        away = row.get("away_team", "?")
        print(f"🔎 {csv_path.name} ligne {idx}: {home} vs {away} → {url}")
        try:
            data = await fetch_handicap(page, url, over_under_config)
        except Exception as exc:  # noqa: BLE001
            log_entries.append(f"{csv_path}: ligne {idx} - erreur fetch: {exc}")
            continue

        if not data:
            print(f"   ⚠️ Aucune donnée trouvée")
            log_entries.append(f"{csv_path}: ligne {idx} - aucune donnée trouvée ({row.get('home_team','?')} vs {row.get('away_team','?')})")
            continue

        row["handicap"] = json.dumps(data, ensure_ascii=False, sort_keys=True)
        updated = True
        print(f"   ✅ Mis à jour avec {len(data)} pivots: {', '.join(data.keys())}")
        log_entries.append(
            f"{csv_path}: ligne {idx} mis à jour ({row.get('home_team','?')} vs {row.get('away_team','?')})"
        )

    if updated:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return updated


async def main():
    args = parse_args()
    sport = args.sport
    sport_slug = slugify(sport)
    config = get_sport_config(sport)
    over_under_config = config.get("over_under_config") or {}

    run_dir = Path(args.run_dir) if args.run_dir else find_latest_run_dir(sport_slug)
    csv_files = list(list_csv_files(run_dir, sport_slug))
    if not csv_files:
        raise FileNotFoundError(f"Aucun CSV trouvé pour le sport '{sport}' dans {run_dir}")

    log_entries: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for csv_file in csv_files:
            await repair_csv_file(page, csv_file, over_under_config, log_entries)

        await context.close()
        await browser.close()

    log_path = run_dir / "over_under_repair.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"=== Run {timestamp} ===\n")
        if log_entries:
            for entry in log_entries:
                log_file.write(entry + "\n")
        else:
            log_file.write("Aucune mise à jour effectuée.\n")
    print(f"📝 Log écrit dans {log_path}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
