# NBA over/under scraping roadmap

## Goal and scope
- Keep the existing season and pagination workflow for NBA result pages.
- For each match row on a results page, capture the base metadata before leaving the list: date, home_team (bold), away_team (regular), home_score, away_score, home_odds, away_odds.
- Follow the match link (anchor `.w-full` under the row `.group`) to its detail page, then load the over/under tab via the fragment `#over-under;1`.
- Extract all valid over/under lines whose handicap pivot ends with `.5` (ignore integer pivots). Default any `-` odds value to `1.73`.
- Store the collected markets in a new CSV column `handicap` as JSON mapping pivot -> odds.

## DOM targets on the match page
- Table container: `.event-container`.
- Table content wrapper: `.event-container > div:nth-child(2)`.
- Row selector: `.event-container > div:nth-child(2) > div > [data-testid='over-under-collapsed-row']`.
- Pivot label within a row: first `<p>` inside `[data-testid='over-under-collapsed-option-box']`. Extract only the numeric pivot ending with `.5`, strip the leading `+`.
- Odds:
  - Over: `div.flex.h-9 > div:nth-child(1) p`.
  - Under: `div.flex.h-9 > div:nth-child(2) p`.

## Output shape for the new column
- Column name: `handicap`.
- Value: JSON string (stable key order) mapping each pivot to its odds, e.g.:
  ```json
  {
    "199.5": {"label": 199.5, "odds_over": 1.20, "odds_under": 4.00},
    "200.5": {"label": 200.5, "odds_over": 1.21, "odds_under": 3.90}
  }
  ```
- Skip rows whose pivot does not end with `.5`. If no valid `.5` pivot exists, store an empty object `{}`.
- Use `.` decimal separator; serialize numbers, not strings, for odds and label.

## Flow changes to implement
- Extend the match extraction on result pages to also capture the match detail URL (href of the anchor under the row `.group a.w-full`).
- While iterating matches for a page:
  - Reuse the current `page` for list navigation and pagination.
  - Open a dedicated `detail_page` (or temporarily navigate and then go back) to fetch over/under data without losing pagination state; reapply `dismiss_overlays` if needed.
  - Build the over/under URL by replacing the fragment with `#over-under;1` (or appending it if absent).
  - Wait for the over/under table to render; if missing or timed out, keep `handicap` empty.
  - Parse rows, filter `.5` pivots, normalize odds with fallback `1.73` only if all pivots have `-` odds.
  - Attach the serialized `handicap` JSON to the match dict before saving.
- Preserve the existing CSV structure and add the new column; ensure `save_matches_to_csv` writes the new field order consistently.
- Keep `--repair` behavior compatible: when resuming, skip already scraped seasons based on filenames as today; no format migration needed for older CSVs.

## Edge cases and safeguards
- Overlays/cookie banners may appear on detail pages: reuse `dismiss_overlays`.
- Some matches may have no over/under tab or empty table: decide how to represent (empty JSON) vs. skipping the match entirely.
- Odds strings may contain commas or spacing; trim and replace comma with dot before float conversion. Use only the first `<p>` from the pivot box to avoid concatenated digits (e.g., `+2122`).
- Duplicate pivots: choose first occurrence or last consistently; prefer deterministic overwrite.
- Rate limiting: keep one detail page at a time; add small waits if the site throttles after rapid navigation.

## Decisions confirmed
- Scope: implement for NBA now, but code should remain reusable for other sports later.
- Column: `handicap` always present in NBA over/under export.
- Empty data handling: always store JSON. If no `.5` pivots, store `{}`.
- Payout: ignore.
- URL fragment: default to `<match_url>#over-under;1`; add a config flag to change this behavior later (no need to preserve other params by default).
- Navigation: allowed to open a new tab per match and close it after scraping to keep the main pagination state intact.

## Over/under odds rules (updated)
- Keep only pivots ending in `.5`; ignore integer duplicates and strip the leading `+`.
- If at least one pivot has real odds (not `-`), keep only rows where both over/under are real; discard rows with `-`.
- If pivots exist but all odds are `-`, include those pivots and set both odds to the default (1.73).
- If no valid `.5` pivot or the page fails to load, return an empty JSON.

## Proposed two-step pipeline (simpler and faster)
- Step 1: URL harvesting — iterate seasons/pages, collect base match data plus the over/under URL (fragment applied), without opening detail pages. Save to CSV with columns `date,home_team,away_team,home_score,away_score,home_odds,away_odds,url,sport,tournament,season`.
- Step 2: Odds enrichment — read the harvested CSVs, fetch each URL headless, apply the over/under rules above, and write out CSVs with the additional `handicap` column.
- Benefits: avoids opening tabs during pagination, less focus-stealing, easier to re-run enrichment without re-scraping schedules, and allows targeted repair by reprocessing specific CSVs.
