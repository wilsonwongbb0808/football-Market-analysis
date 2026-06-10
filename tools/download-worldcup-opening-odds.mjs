import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const htmlPath = path.join(root, "psg-arsenal-score-corner-predictor.html");
const outputPath = path.join(root, "output", "worldcup-opening-odds.json");

const args = Object.fromEntries(process.argv.slice(2).map(item => {
  const [key, ...rest] = item.replace(/^--/, "").split("=");
  return [key, rest.join("=") || "true"];
}));

const apiBaseUrl = args.baseUrl || process.env.ODDS_API_BASE_URL || "";
const apiKey = args.apiKey || process.env.ODDS_API_KEY || "";
const apiHeaderName = args.headerName || process.env.ODDS_API_HEADER_NAME || "";

function readSchedule(html) {
  const match = html.match(/const rawWorldCupSchedule = `([\s\S]*?)`;/);
  if (!match) throw new Error("Cannot find rawWorldCupSchedule in HTML.");
  return match[1].trim().split("\n").map(line => {
    const [stage, matchNo, utc, fixture, venue] = line.split("|");
    const [home = fixture, away = "待定"] = fixture.split(" vs ");
    return { stage, match: Number(matchNo), utc, fixture, home, away, venue };
  });
}

function valueAt(obj, keys) {
  for (const key of keys) {
    if (obj && obj[key] !== undefined && obj[key] !== null && obj[key] !== "") return obj[key];
  }
  return "";
}

function firstMarket(payload, names) {
  const markets = payload?.markets || payload?.odds || payload?.data?.markets || payload?.data?.odds || payload;
  for (const name of names) {
    if (markets?.[name]) return markets[name];
  }
  return {};
}

function normalizePayload(payload) {
  const europe = firstMarket(payload, ["europe", "european", "eu", "h2h", "matchWinner", "1x2"]);
  const asian = firstMarket(payload, ["asian", "asianHandicap", "handicap", "asia"]);
  const totalGoals = firstMarket(payload, ["totalGoals", "goals", "overUnder", "totals"]);
  const corners = firstMarket(payload, ["corners", "corner", "cornerTotals"]);
  return {
    europe: {
      home: valueAt(europe, ["home", "homeWin", "主胜", "1"]),
      draw: valueAt(europe, ["draw", "平局", "x", "X"]),
      away: valueAt(europe, ["away", "awayWin", "客胜", "2"])
    },
    asian: {
      line: valueAt(asian, ["line", "handicap", "盘口"]),
      homeOdds: valueAt(asian, ["homeOdds", "home", "主队"]),
      awayOdds: valueAt(asian, ["awayOdds", "away", "客队"])
    },
    totalGoals: {
      line: valueAt(totalGoals, ["line", "total", "盘口"]),
      over: valueAt(totalGoals, ["over", "大球", "overOdds"]),
      under: valueAt(totalGoals, ["under", "小球", "underOdds"])
    },
    corners: {
      line: valueAt(corners, ["line", "total", "盘口"]),
      over: valueAt(corners, ["over", "大角", "overOdds"]),
      under: valueAt(corners, ["under", "小角", "underOdds"])
    }
  };
}

function buildUrl(template, item) {
  const replacements = {
    apiKey,
    match: item.match,
    home: encodeURIComponent(item.home),
    away: encodeURIComponent(item.away),
    fixture: encodeURIComponent(item.fixture),
    date: item.utc.slice(0, 10),
    utc: encodeURIComponent(item.utc)
  };
  let urlText = template;
  for (const [key, value] of Object.entries(replacements)) {
    urlText = urlText.replaceAll(`{${key}}`, String(value));
  }
  const url = new URL(urlText);
  if (!template.includes("{apiKey}") && apiKey) url.searchParams.set("apiKey", apiKey);
  if (!template.includes("{match}")) url.searchParams.set("match", String(item.match));
  if (!template.includes("{home}")) url.searchParams.set("home", item.home);
  if (!template.includes("{away}")) url.searchParams.set("away", item.away);
  if (!template.includes("{date}")) url.searchParams.set("date", item.utc.slice(0, 10));
  return url;
}

async function fetchOpeningOdds(item) {
  const url = buildUrl(apiBaseUrl, item);
  const headers = {};
  if (apiHeaderName && apiKey) headers[apiHeaderName] = apiKey;
  else if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  const response = await fetch(url, { headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`M${item.match} ${response.status}: ${text.slice(0, 220)}`);
  }
  return response.json();
}

async function main() {
  const html = await fs.readFile(htmlPath, "utf8");
  const schedule = readSchedule(html);
  await fs.mkdir(path.dirname(outputPath), { recursive: true });

  if (!apiBaseUrl) {
    const placeholder = {
      source: "等待接口地址",
      updatedAt: new Date().toISOString(),
      matches: schedule.map(item => ({ ...item, openingOdds: {} }))
    };
    await fs.writeFile(outputPath, JSON.stringify(placeholder, null, 2), "utf8");
    console.log(`缺少 ODDS_API_BASE_URL，已生成占位文件：${outputPath}`);
    return;
  }

  const matches = [];
  for (const item of schedule) {
    try {
      const payload = await fetchOpeningOdds(item);
      matches.push({ ...item, openingOdds: normalizePayload(payload), raw: payload });
      console.log(`M${item.match} ${item.fixture} 已保存`);
    } catch (error) {
      matches.push({ ...item, openingOdds: {}, error: error.message });
      console.warn(`M${item.match} ${item.fixture} 下载失败：${error.message}`);
    }
  }

  await fs.writeFile(outputPath, JSON.stringify({
    source: apiBaseUrl.replace(apiKey, "***"),
    updatedAt: new Date().toISOString(),
    matches
  }, null, 2), "utf8");
  console.log(`已写入：${outputPath}`);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
