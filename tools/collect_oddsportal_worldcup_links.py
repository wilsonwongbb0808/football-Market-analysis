import asyncio
import csv
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
THREE_MARKETS = ROOT / "data" / "world_cup_2022_three_markets.csv"
OUT_PATH = ROOT / "data" / "oddsportal_worldcup2022_links.json"
BASE_URL = "https://www.oddsportal.com/football/world/world-cup-2022/results/"


def norm(value):
    return "".join(ch for ch in value.lower() if ch.isalnum())


def slug_team(segment):
    segment = segment.strip("/")
    if not segment:
        return ""
    # OddsPortal team URL segments look like cameroon-zk1uVG2D.
    name = segment.rsplit("-", 1)[0]
    return norm(name)


def read_matches():
    with THREE_MARKETS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def match_url_to_row(url, rows):
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    try:
        idx = parts.index("h2h")
        home_slug = slug_team(parts[idx + 1])
        away_slug = slug_team(parts[idx + 2])
    except (ValueError, IndexError):
        return None
    if {home_slug, away_slug} == {"croatia", "morocco"}:
        wanted = "Croatia - Morocco" if parsed.fragment == "U7jo7z91" else "Morocco - Croatia"
        return next((row for row in rows if row["match"] == wanted), None)
    for row in rows:
        home = norm(row["home"])
        away = norm(row["away"])
        if home == home_slug and away == away_slug:
            return row
        if home in home_slug and away in away_slug:
            return row
        if home == away_slug and away == home_slug:
            return row
        if home in away_slug and away in home_slug:
            return row
    return None


async def collect_page(page, page_no):
    if page_no == 1:
        print(f"打开 {BASE_URL}", flush=True)
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.get_by_role("button", name=re.compile("accept|agree|allow", re.I)).click(timeout=4000)
        except Exception:
            pass
    else:
        print(f"点击第 {page_no} 页", flush=True)
        await page.get_by_text(str(page_no), exact=True).last.click(timeout=15000)
    await page.wait_for_timeout(3500)
    for _ in range(5):
        await page.mouse.wheel(0, 2400)
        await page.wait_for_timeout(350)
    hrefs = await page.eval_on_selector_all(
        "a[href*='/football/h2h/']",
        """els => els.map(a => a.href).filter(Boolean)""",
    )
    return sorted(set(urljoin(BASE_URL, href.split("?")[0]) for href in hrefs))


async def main():
    rows = read_matches()
    by_match = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": 1366, "height": 1600},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
        )
        for page_no in range(1, 4):
            try:
                for url in await collect_page(page, page_no):
                    row = match_url_to_row(url, rows)
                    if row:
                        key = f"{norm(row['match'])}-{row['date_utc']}"
                        by_match[key] = {
                            "match": row["match"],
                            "home": row["home"],
                            "away": row["away"],
                            "date_utc": row["date_utc"],
                            "url": url,
                        }
            except Exception as exc:
                print(f"第 {page_no} 页失败: {exc}", flush=True)
        await browser.close()

    items = sorted(by_match.values(), key=lambda x: x["date_utc"])
    OUT_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"保存 {len(items)} 条链接 -> {OUT_PATH}", flush=True)
    missing = [r["match"] for r in rows if f"{norm(r['match'])}-{r['date_utc']}" not in by_match]
    if missing:
        print("缺失比赛:", " | ".join(missing[:20]), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
