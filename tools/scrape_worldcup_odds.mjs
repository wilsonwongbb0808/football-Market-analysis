import fs from "node:fs/promises";
import path from "node:path";

const ROOT = "C:/Users/Administrator/Documents/世界杯";
const OUT_DIR = path.join(ROOT, "data");
const SOURCE = "https://checkbestodds.com";
const ARCHIVE_URL = `${SOURCE}/football-odds/archive-world-cup-2022`;
const RESULTS_URL = "https://fixturedownload.com/feed/json/fifa-world-cup-2022";
const MORE_MARKETS = "99,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,24,25,26,27,28,29,30,31,32,33,34,35,36";

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const num = value => {
  const found = String(value ?? "").replace("%", "").match(/[+-]?\d+(?:\.\d+)?/);
  const n = found ? Number(found[0]) : NaN;
  return Number.isFinite(n) ? n : null;
};
const strip = html => String(html || "")
  .replace(/<script[\s\S]*?<\/script>/gi, "")
  .replace(/<style[\s\S]*?<\/style>/gi, "")
  .replace(/<[^>]+>/g, " ")
  .replace(/&nbsp;/g, " ")
  .replace(/&amp;/g, "&")
  .replace(/\s+/g, " ")
  .trim();
const uniq = rows => [...new Set(rows)];

async function getText(url, options = {}) {
  let lastError;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          "user-agent": "Mozilla/5.0 football-odds-research",
          "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          ...(options.headers || {})
        }
      });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${url}`);
      return response.text();
    } catch (error) {
      lastError = error;
      await sleep(500 + attempt * 500);
    }
  }
  throw lastError;
}

function parseArchiveLinks(html) {
  const matches = [...html.matchAll(/href="(\/football-odds\/world-cup-2022\/[^"]+\/\d+)"/g)];
  return uniq(matches.map(match => `${SOURCE}${match[1]}`));
}

function parseMatchPage(html) {
  const home = html.match(/<span id="homeName">([^<]+)<\/span>/)?.[1]?.trim();
  const away = html.match(/<span id="awayName">([^<]+)<\/span>/)?.[1]?.trim();
  const matchTime = html.match(/id="matchTime" ts="(\d+)"/)?.[1];
  const matchHash = html.match(/id="matchHash" value="([^"]+)"/)?.[1];
  const finalSection = html.match(/<div id="1" class="tblehead"[\s\S]*?<div id="moreOdds"/)?.[0] || "";
  const h2h = parseTable(finalSection, "Final result odds");
  return { home, away, matchTime, matchHash, h2h };
}

async function getMoreOdds(url, match) {
  const body = [
    ["xjxcls", "fx"],
    ["xjxmthd", "moreOddsFootball"],
    ["xjxr", String(Date.now())],
    ["xjxargs[]", `S${MORE_MARKETS}`],
    ["xjxargs[]", `S${match.matchTime}`],
    ["xjxargs[]", `S${match.home}`],
    ["xjxargs[]", `S${match.away}`],
    ["xjxargs[]", `S${match.matchHash}`]
  ].map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`).join("&");
  const xml = await getText(url, {
    method: "POST",
    body,
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      "accept": "text/xml,application/xml,*/*"
    }
  });
  const cdata = xml.match(/<cmd cmd="as" id="moreOdds" prop="innerHTML"><!\[CDATA\[S([\s\S]*?)\]\]><\/cmd>/)?.[1] || "";
  return { xml, html: cdata };
}

function parseTable(section, name) {
  const table = section.match(/<table[\s\S]*?<\/table>/)?.[0];
  if (!table) return null;
  const header = [...table.matchAll(/<th[^>]*>([\s\S]*?)<\/th>/g)].map(m => strip(m[1]));
  const rows = [...table.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)].map(row => {
    const cells = [...row[1].matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/g)].map(m => strip(m[1]));
    return cells;
  }).filter(cells => cells.length > 1 && !/^Bookmaker$/i.test(cells[0]));
  const best = rows.find(cells => /Best odds/i.test(cells[0]));
  const books = rows.filter(cells => !/Best odds/i.test(cells[0]));
  return { name, header, books, best };
}

function sectionByTitle(html, title) {
  const pattern = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "\\s+");
  const index = html.search(new RegExp(`<i>\\s*${pattern}\\s*<\\/i>`, "i"));
  if (index < 0) return "";
  const start = html.lastIndexOf("<div", index);
  const rest = html.slice(index + title.length);
  const nextRelative = rest.search(/<div id="[^"]+" class="tblehead"/);
  const next = nextRelative >= 0 ? index + title.length + nextRelative : html.length;
  return html.slice(start, next > start ? next : html.length);
}

function parseTotals(html) {
  const titles = [...html.matchAll(/<i>\s*Under\/Over\s+([0-9]+(?:\.[0-9]+)?)\s+odds\s*<\/i>/gi)];
  const seen = new Set();
  return titles.map(match => {
    const line = Number(match[1]);
    if (seen.has(line)) return null;
    seen.add(line);
    const title = `Under/Over ${line} odds`;
    const table = parseTable(sectionByTitle(html, title), title);
    if (!table?.best) return null;
    return {
      line,
      under: num(table.best[1]),
      over: num(table.best[2]),
      margin: num(table.best[3]),
      table
    };
  }).filter(Boolean);
}

function parseAsian(html) {
  const blocks = [...html.matchAll(/<div id="8[^"]*" class="tblehead"[\s\S]*?(?=<div id="8[^"]*" class="tblehead"|<div id="9"|$)/g)];
  return blocks.map(block => {
    const title = strip(block[0].match(/<i>(Asian Handicap[^<]+)<\/i>/)?.[1] || "");
    const homeLine = num(block[0].match(/class="homeLine" value="([^"]+)"/)?.[1]);
    const awayLine = num(block[0].match(/class="awayLine" value="([^"]+)"/)?.[1]);
    const table = parseTable(block[0], title);
    if (!table?.best || homeLine === null || awayLine === null) return null;
    return {
      homeLine,
      awayLine,
      homeOdds: num(table.best[1]),
      awayOdds: num(table.best[2]),
      margin: num(table.best[3]),
      table
    };
  }).filter(row => row && row.homeOdds && row.awayOdds);
}

function resultKey(home, away) {
  const fix = s => String(s || "").toLowerCase().replace(/\butd\b/g, "united").replace(/[^a-z]/g, "");
  return `${fix(home)}-${fix(away)}`;
}

function settleAsian(scoreDiff, line, odds) {
  const adjusted = scoreDiff + line;
  if (adjusted > 0) return odds - 1;
  if (adjusted === 0) return 0;
  if (adjusted < 0) return -1;
  return 0;
}

function settleTotal(goals, side, line, odds) {
  if (side === "over") {
    if (goals > line) return odds - 1;
    if (goals === line) return 0;
    return -1;
  }
  if (goals < line) return odds - 1;
  if (goals === line) return 0;
  return -1;
}

function implied(h, d, a) {
  const raw = [1 / h, 1 / d, 1 / a];
  const sum = raw.reduce((x, y) => x + y, 0);
  return raw.map(x => x / sum);
}

function pickMainAsian(lines) {
  return lines
    .filter(line => line.margin !== null)
    .sort((a, b) => {
      const aBalance = Math.abs(a.homeOdds - a.awayOdds);
      const bBalance = Math.abs(b.homeOdds - b.awayOdds);
      return aBalance - bBalance || Math.abs(a.margin) - Math.abs(b.margin);
    })[0] || null;
}

function pickMainTotal(totals) {
  return totals
    .filter(row => row.under && row.over)
    .sort((a, b) => {
      const aBalance = Math.abs(a.under - a.over);
      const bBalance = Math.abs(b.under - b.over);
      return aBalance - bBalance || Math.abs(a.margin ?? 99) - Math.abs(b.margin ?? 99);
    })[0] || null;
}

function buildFlatRow(match, result) {
  const h2hBest = match.h2h?.best || [];
  const probs = h2hBest.length ? implied(num(h2hBest[1]), num(h2hBest[2]), num(h2hBest[3])) : [null, null, null];
  const asian = pickMainAsian(match.asian || []);
  const total = pickMainTotal(match.totals || []);
  return {
    source: "checkbestodds",
    match: `${match.home} - ${match.away}`,
    date_utc: result?.DateUtc || "",
    home: match.home,
    away: match.away,
    home_score: result?.HomeTeamScore ?? "",
    away_score: result?.AwayTeamScore ?? "",
    h2h_home: num(h2hBest[1]),
    h2h_draw: num(h2hBest[2]),
    h2h_away: num(h2hBest[3]),
    p_home: probs[0],
    p_draw: probs[1],
    p_away: probs[2],
    ah_home_line: asian?.homeLine ?? "",
    ah_away_line: asian?.awayLine ?? "",
    ah_home_odds: asian?.homeOdds ?? "",
    ah_away_odds: asian?.awayOdds ?? "",
    total_line: total?.line ?? "",
    total_under: total?.under ?? "",
    total_over: total?.over ?? "",
    total_lines_available: (match.totals || []).map(row => `${row.line}:${row.under}/${row.over}`).join(";"),
    url: match.url
  };
}

function backtest(rows) {
  const tests = [];
  const add = (name, picks) => {
    const settled = picks.filter(p => Number.isFinite(p.pnl));
    const profit = settled.reduce((sum, pick) => sum + pick.pnl, 0);
    tests.push({
      name,
      bets: settled.length,
      wins: settled.filter(p => p.pnl > 0).length,
      pushes: settled.filter(p => p.pnl === 0).length,
      losses: settled.filter(p => p.pnl < 0).length,
      profit: Number(profit.toFixed(2)),
      roi: settled.length ? Number((profit / settled.length).toFixed(4)) : 0
    });
  };

  const withScores = rows.filter(r => r.home_score !== "" && r.away_score !== "");
  add("1X2: highest implied probability, odds >= 1.65", withScores.map(r => {
    const sides = [
      ["home", r.p_home, r.h2h_home],
      ["draw", r.p_draw, r.h2h_draw],
      ["away", r.p_away, r.h2h_away]
    ].sort((a, b) => b[1] - a[1]);
    const [side, , odd] = sides[0];
    if (!odd || odd < 1.65) return { pnl: NaN };
    const outcome = r.home_score > r.away_score ? "home" : r.home_score < r.away_score ? "away" : "draw";
    return { pnl: outcome === side ? odd - 1 : -1 };
  }));

  add("Asian: balanced main line, take lower odds side", withScores.map(r => {
    if (!r.ah_home_odds || !r.ah_away_odds) return { pnl: NaN };
    const scoreDiff = Number(r.home_score) - Number(r.away_score);
    if (r.ah_home_odds <= r.ah_away_odds) return { pnl: settleAsian(scoreDiff, Number(r.ah_home_line), Number(r.ah_home_odds)) };
    return { pnl: settleAsian(-scoreDiff, Number(r.ah_away_line), Number(r.ah_away_odds)) };
  }));

  add("Total: 2.5/main line, take lower odds side", withScores.map(r => {
    if (!r.total_line || !r.total_under || !r.total_over) return { pnl: NaN };
    const goals = Number(r.home_score) + Number(r.away_score);
    const side = r.total_under <= r.total_over ? "under" : "over";
    const odd = side === "under" ? Number(r.total_under) : Number(r.total_over);
    return { pnl: settleTotal(goals, side, Number(r.total_line), odd) };
  }));

  return tests;
}

function toCsv(rows) {
  const headers = Object.keys(rows[0] || {});
  const esc = value => {
    const s = String(value ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [headers.join(","), ...rows.map(row => headers.map(h => esc(row[h])).join(","))].join("\n");
}

async function main() {
  await fs.mkdir(OUT_DIR, { recursive: true });
  const [archiveHtml, results] = await Promise.all([
    getText(ARCHIVE_URL),
    getText(RESULTS_URL).then(JSON.parse)
  ]);
  await fs.writeFile(path.join(OUT_DIR, "world_cup_2022_results.json"), JSON.stringify(results, null, 2), "utf8");
  const links = parseArchiveLinks(archiveHtml);
  const resultMap = new Map(results.map(row => [resultKey(row.HomeTeam, row.AwayTeam), row]));
  const raw = [];

  for (const [index, url] of links.entries()) {
    const html = await getText(url);
    const match = { ...parseMatchPage(html), url };
    if (!match.home || !match.away || !match.matchTime || !match.matchHash) {
      console.warn(`skip ${url}`);
      continue;
    }
    const more = await getMoreOdds(url, match);
    match.totals = parseTotals(more.html);
    match.asian = parseAsian(more.html);
    raw.push(match);
    console.log(`${index + 1}/${links.length} ${match.home} - ${match.away}: totals=${match.totals.length} asian=${match.asian.length}`);
    await sleep(120);
  }

  const rows = raw.map(match => buildFlatRow(match, resultMap.get(resultKey(match.home, match.away))))
    .filter(row => row.h2h_home && row.h2h_draw && row.h2h_away && row.ah_home_line !== "" && row.total_line !== "");
  const summary = {
    source_urls: [ARCHIVE_URL, RESULTS_URL],
    scraped_matches: raw.length,
    three_market_matches: rows.length,
    backtest: backtest(rows),
    note: "CheckBestOdds provides last available odds, not a full open-to-close odds history. Use this for closing-line calibration, not live line-movement calibration."
  };

  await fs.writeFile(path.join(OUT_DIR, "checkbestodds_world_cup_2022_raw.json"), JSON.stringify(raw, null, 2), "utf8");
  await fs.writeFile(path.join(OUT_DIR, "world_cup_2022_three_markets.csv"), toCsv(rows), "utf8");
  await fs.writeFile(path.join(OUT_DIR, "world_cup_2022_backtest_summary.json"), JSON.stringify(summary, null, 2), "utf8");
  console.log(JSON.stringify(summary, null, 2));
}

await main().catch(error => {
  console.error(error);
});
