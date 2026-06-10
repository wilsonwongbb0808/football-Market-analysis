import json
import os
import re
import sys
import time
from http.client import IncompleteRead
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "psg-arsenal-score-corner-predictor.html"
OUTPUT_PATH = ROOT / "output" / "worldcup-opening-odds.json"
EVENT_CACHE_PATH = ROOT / "output" / "odds-api-worldcup-events.json"
BASE_URL = "https://api.odds-api.io/v3"


class BudgetReached(RuntimeError):
    pass


request_budget = 95
request_count = 0

ZH_TO_EN = {
    "墨西哥": "Mexico", "南非": "South Africa", "韩国": "South Korea", "捷克": "Czech Republic",
    "加拿大": "Canada", "波黑": "Bosnia and Herzegovina", "美国": "United States", "巴拉圭": "Paraguay",
    "卡塔尔": "Qatar", "瑞士": "Switzerland", "巴西": "Brazil", "摩洛哥": "Morocco",
    "海地": "Haiti", "苏格兰": "Scotland", "澳大利亚": "Australia", "土耳其": "Turkey",
    "德国": "Germany", "库拉索": "Curaçao", "荷兰": "Netherlands", "日本": "Japan",
    "科特迪瓦": "Ivory Coast", "厄瓜多尔": "Ecuador", "瑞典": "Sweden", "突尼斯": "Tunisia",
    "西班牙": "Spain", "佛得角": "Cape Verde", "比利时": "Belgium", "埃及": "Egypt",
    "沙特阿拉伯": "Saudi Arabia", "乌拉圭": "Uruguay", "伊朗": "Iran", "新西兰": "New Zealand",
    "法国": "France", "塞内加尔": "Senegal", "伊拉克": "Iraq", "挪威": "Norway",
    "阿根廷": "Argentina", "阿尔及利亚": "Algeria", "奥地利": "Austria", "约旦": "Jordan",
    "葡萄牙": "Portugal", "民主刚果": "DR Congo", "英格兰": "England", "克罗地亚": "Croatia",
    "加纳": "Ghana", "巴拿马": "Panama", "乌兹别克斯坦": "Uzbekistan", "哥伦比亚": "Colombia",
}


def read_schedule():
    html = HTML_PATH.read_text(encoding="utf-8")
    match = re.search(r"const rawWorldCupSchedule = `([\s\S]*?)`;", html)
    if not match:
        raise RuntimeError("Cannot find rawWorldCupSchedule.")
    items = []
    for line in match.group(1).strip().splitlines():
        stage, match_no, utc, fixture, venue = line.split("|")
        home, away = fixture.split(" vs ", 1)
        items.append({
            "stage": stage,
            "match": int(match_no),
            "utc": utc,
            "fixture": fixture,
            "home": home,
            "away": away,
            "homeEn": ZH_TO_EN.get(home, home),
            "awayEn": ZH_TO_EN.get(away, away),
            "venue": venue,
        })
    return items


def get_json(path, params):
    global request_count
    if request_count >= request_budget:
        raise BudgetReached(f"本次请求预算已用完：{request_count}/{request_budget}")
    request_count += 1
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    for attempt in range(3):
        req = Request(url, headers={"User-Agent": "worldcup-odds-downloader/1.0"})
        try:
            with urlopen(req, timeout=35) as response:
                return json.loads(response.read().decode("utf-8"))
        except IncompleteRead:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{exc.code} {body}") from exc


def read_existing():
    if not OUTPUT_PATH.exists():
        return {}
    try:
        data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        return {int(item["match"]): item for item in data.get("matches", [])}
    except Exception:
        return {}


def write_output(matches, bookmaker):
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    data = {
        "source": "Odds-API.io",
        "bookmaker": bookmaker,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "matches": matches,
    }
    OUTPUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_html_embedded_odds(data)


def sync_html_embedded_odds(data):
    html = HTML_PATH.read_text(encoding="utf-8")
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    updated = re.sub(
        r"const embeddedWorldCupOpeningOddsData = \{[\s\S]*?\};",
        f"const embeddedWorldCupOpeningOddsData = {compact};",
        html,
        count=1,
    )
    if updated != html:
        HTML_PATH.write_text(updated, encoding="utf-8")


def load_worldcup_events(api_key):
    if EVENT_CACHE_PATH.exists():
        try:
            cached = json.loads(EVENT_CACHE_PATH.read_text(encoding="utf-8"))
            if cached.get("events"):
                return cached["events"]
        except Exception:
            pass
    windows = [
        ("2026-06-11T00:00:00Z", "2026-06-15T23:59:59Z"),
        ("2026-06-16T00:00:00Z", "2026-06-20T23:59:59Z"),
        ("2026-06-21T00:00:00Z", "2026-06-24T23:59:59Z"),
        ("2026-06-25T00:00:00Z", "2026-06-28T23:59:59Z"),
    ]
    events = []
    for start, end in windows:
        chunk = get_json("/events", {
            "apiKey": api_key,
            "sport": "football",
            "status": "pending",
            "from": start,
            "to": end,
        })
        if isinstance(chunk, dict):
            chunk = [chunk]
        events.extend(chunk)
    events = [
        event for event in events
        if event.get("league", {}).get("slug") == "international-fifa-world-cup"
        or "World Cup" in event.get("league", {}).get("name", "")
    ]
    if not events:
        raise RuntimeError("Odds-API.io events returned no World Cup matches; refusing to overwrite local odds with an empty event set.")
    EVENT_CACHE_PATH.write_text(json.dumps({
        "source": "Odds-API.io",
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "events": events,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return events


def norm_name(value):
    normalized = value.lower()
    aliases = {
        "usa": "united states",
        "u.s.a.": "united states",
        "czechia": "czech republic",
        "korea republic": "south korea",
        "republic of korea": "south korea",
        "dr congo": "democratic republic of the congo",
        "d.r. congo": "democratic republic of the congo",
        "congo dr": "democratic republic of the congo",
        "turkiye": "turkey",
        "curacao": "curaçao",
    }
    for src, dst in aliases.items():
        normalized = normalized.replace(src, dst)
    return re.sub(r"[^a-z0-9]+", "", normalized)


def event_key(home, away):
    return f"{norm_name(home)}|{norm_name(away)}"


def market(markets, *names):
    name_set = {name.lower() for name in names}
    for item in markets or []:
        if str(item.get("name", "")).lower() in name_set:
            odds = item.get("odds") or []
            return item, odds[0] if odds else {}
    return {}, {}


def num(value):
    if value in ("", None):
        return ""
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def market_has_values(data):
    if not isinstance(data, dict):
        return False
    return any(value not in ("", None) for value in data.values())


def has_all_four_markets(record):
    odds = record.get("openingOdds") or {}
    return all(market_has_values(odds.get(name)) for name in ("europe", "asian", "totalGoals", "corners"))


def has_all_openings(record):
    sources = record.get("openingSources") or {}
    return all(sources.get(name) == "opening" for name in ("europe", "asian", "totalGoals", "corners"))


def has_latest_snapshot(record):
    return bool(record.get("bookmaker") and record.get("openingOdds"))


def pick_bookmaker(bookmakers, preferred):
    if preferred in bookmakers:
        return preferred, bookmakers[preferred]
    for key in bookmakers:
        if key.lower().startswith(preferred.lower()):
            return key, bookmakers[key]
    return next(iter(bookmakers.items()), ("", []))


def movement(api_key, event_id, bookmaker, market_name, market_line=""):
    params = {"apiKey": api_key, "eventId": event_id, "bookmaker": bookmaker, "market": market_name}
    if market_line not in ("", None):
        params["marketLine"] = str(market_line)
    return get_json("/odds/movements", params).get("opening") or {}


def with_opening(api_key, event_id, bookmaker, latest, market_name, line_key, mapper, allow_movement=True):
    line = latest.get(line_key) if line_key else ""
    if not allow_movement:
        return mapper(latest), "latest"
    try:
        opening = movement(api_key, event_id, bookmaker, market_name, line)
        return mapper(opening), "opening"
    except Exception as exc:
        return mapper(latest), f"latest-fallback: {exc}"


def download():
    global request_budget
    api_key = os.environ.get("ODDS_API_KEY") or (sys.argv[1] if len(sys.argv) > 1 else "")
    bookmaker = os.environ.get("ODDS_BOOKMAKER", "Bet365")
    mode = os.environ.get("ODDS_MODE", "latest").lower()
    max_matches = int(os.environ.get("ODDS_MAX_MATCHES", "104"))
    request_budget = int(os.environ.get("ODDS_REQUEST_BUDGET", "95"))
    allow_movement = mode in {"hybrid", "opening"}
    if not api_key:
        raise RuntimeError("Set ODDS_API_KEY or pass it as the first argument.")

    schedule = read_schedule()
    existing = read_existing()
    events = load_worldcup_events(api_key)
    events_by_pair = {event_key(event.get("home", ""), event.get("away", "")): event for event in events}

    saved_by_match = dict(existing)
    schedule = sorted(schedule, key=lambda item: (item["utc"], item["match"]))
    for item in schedule:
        previous = existing.get(item["match"], {})
        if mode in {"latest", "current"} and has_latest_snapshot(previous):
            saved_by_match[item["match"]] = previous
            continue
        if mode in {"opening", "hybrid"} and has_all_openings(previous):
            saved_by_match[item["match"]] = previous
            continue
        event = events_by_pair.get(event_key(item["homeEn"], item["awayEn"]))
        record = {key: item[key] for key in ("stage", "match", "utc", "fixture", "venue")}
        record["openingOdds"] = previous.get("openingOdds", {})
        if not event:
            record["error"] = "未在 Odds-API.io 找到 eventId，通常是淘汰赛对阵尚未确定。"
            if previous.get("openingOdds"):
                record = {**previous, **record, "openingOdds": previous.get("openingOdds", {})}
            saved_by_match[item["match"]] = record
            continue

        record["eventId"] = event.get("id")
        record["apiHome"] = event.get("home")
        record["apiAway"] = event.get("away")
        record["apiLeague"] = event.get("league", {}).get("name")
        try:
            if item["match"] > max_matches:
                merged = {**previous, **record}
                saved_by_match[item["match"]] = merged
                continue
            odds = get_json("/odds", {"apiKey": api_key, "eventId": event["id"], "bookmakers": bookmaker})
            picked_name, markets = pick_bookmaker(odds.get("bookmakers", {}), bookmaker)
            record["bookmaker"] = picked_name
            ml_meta, ml = market(markets, "ML")
            spread_meta, spread = market(markets, "Spread")
            totals_meta, totals = market(markets, "Totals")
            corner_meta, corners = market(markets, "Corners Totals")

            europe, europe_source = with_opening(api_key, event["id"], picked_name, ml, "ML", "", lambda data: {
                "home": num(data.get("home")),
                "draw": num(data.get("draw")),
                "away": num(data.get("away")),
            }, allow_movement)
            asian, asian_source = with_opening(api_key, event["id"], picked_name, spread, "Spread", "hdp", lambda data: {
                "line": num(data.get("hdp")),
                "homeOdds": num(data.get("home")),
                "awayOdds": num(data.get("away")),
            }, allow_movement)
            total_goals, total_source = with_opening(api_key, event["id"], picked_name, totals, "Totals", "hdp", lambda data: {
                "line": num(data.get("hdp")),
                "over": num(data.get("over", data.get("home"))),
                "under": num(data.get("under", data.get("away"))),
            }, allow_movement)
            corners_odds, corner_source = with_opening(api_key, event["id"], picked_name, corners, "Corners Totals", "hdp", lambda data: {
                "line": num(data.get("hdp")),
                "over": num(data.get("over", data.get("home"))),
                "under": num(data.get("under", data.get("away"))),
            }, allow_movement)

            record["openingOdds"] = {
                "europe": europe,
                "asian": asian,
                "totalGoals": total_goals,
                "corners": corners_odds,
            }
            record["fetchMode"] = mode
            record["fetchedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            record["openingSources"] = {
                "europe": europe_source,
                "asian": asian_source,
                "totalGoals": total_source,
                "corners": corner_source,
            }
            record["marketUpdatedAt"] = {
                "europe": ml_meta.get("updatedAt", ""),
                "asian": spread_meta.get("updatedAt", ""),
                "totalGoals": totals_meta.get("updatedAt", ""),
                "corners": corner_meta.get("updatedAt", ""),
            }
            print(f"M{item['match']} {item['fixture']} ok")
        except BudgetReached as exc:
            record["error"] = str(exc)
            saved_by_match[item["match"]] = {**previous, **record}
            print(str(exc))
            break
        except Exception as exc:
            record["error"] = str(exc)
            print(f"M{item['match']} {item['fixture']} failed: {exc}")
            if "429" in str(exc):
                saved_by_match[item["match"]] = record
                print("检测到接口限流，立即停止，保留已保存盘口。")
                break
        saved_by_match[item["match"]] = record
        write_output([saved_by_match.get(item["match"]) or existing.get(item["match"]) or {**item, "openingOdds": {}} for item in schedule], bookmaker)
        time.sleep(0.08)

    saved = [saved_by_match.get(item["match"]) or existing.get(item["match"]) or {**item, "openingOdds": {}} for item in schedule]
    write_output(saved, bookmaker)
    print(f"written {OUTPUT_PATH}; requests used {request_count}/{request_budget}; mode={mode}")


if __name__ == "__main__":
    download()
