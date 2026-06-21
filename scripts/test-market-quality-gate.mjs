import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const root = nodeRepl.cwd;
const html = fs.readFileSync(path.join(root, "football-odds-analyzer.html"), "utf8");
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]).join("\n");

function extractFunction(name) {
  const start = script.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `Missing function ${name}`);
  let parenDepth = 0;
  let braceStart = -1;
  for (let index = script.indexOf("(", start); index < script.length; index += 1) {
    const char = script[index];
    if (char === "(") parenDepth += 1;
    if (char === ")") parenDepth -= 1;
    if (parenDepth === 0) {
      braceStart = script.indexOf("{", index);
      break;
    }
  }
  assert.notEqual(braceStart, -1, `Missing body for function ${name}`);
  let depth = 0;
  for (let index = braceStart; index < script.length; index += 1) {
    const char = script[index];
    if (char === "{") depth += 1;
    if (char === "}") depth -= 1;
    if (depth === 0) return script.slice(start, index + 1);
  }
  throw new Error(`Could not extract function ${name}`);
}

const context = vm.createContext({
  Number,
  Math,
  String,
  Array,
  Object,
  RegExp,
  allocationGroup(row) {
    const name = row.name || "";
    if (name.includes("主胜") || name.includes("亚盘主队")) return "home";
    if (name.includes("客胜") || name.includes("亚盘客队")) return "away";
    if (name.includes("平局")) return "draw";
    if (name.includes("大球")) return "over";
    if (name.includes("小球")) return "under";
    return name;
  },
  valueGrade(score) {
    if (score >= 4) return ["偏有价值", "strong", "可下注"];
    if (score >= 2) return ["有一定价值", "ok", "轻仓"];
    if (score >= 0) return ["中性", "neutral", "观察"];
    return ["谨慎", "warn", "过滤"];
  }
});

vm.runInContext([
  extractFunction("marketStrengthProfile"),
  extractFunction("marketAdjustedResultLean"),
  extractFunction("marketQualityGateForRow"),
  extractFunction("applyMarketQualityGate")
].join("\n"), context);

const obvious = context.marketStrengthProfile({
  e1: [1.44, 4.33, 7],
  p1: { home: 0.64, draw: 0.21, away: 0.15 },
  ah1: -1.25,
  goalLine1: 2.25,
  over1: 0.82,
  under1: 1.02
});
assert.equal(obvious.tier, "obvious");
assert.equal(obvious.favorite, "home");

const balancedRows = context.applyMarketQualityGate([
  { name: "竞彩主胜", score: 4, grade: "偏有价值", cls: "strong", action: "可下注", reason: "原始主胜" },
  { name: "竞彩平局", score: 3, grade: "有一定价值", cls: "ok", action: "轻仓", reason: "原始平局" }
], {
  e1: [2.62, 3.1, 2.7],
  p1: { home: 0.34, draw: 0.29, away: 0.33 },
  ah1: 0,
  goalLine1: 2.25,
  over1: 1,
  under1: 0.85
});
assert.ok(balancedRows.find(row => row.name === "竞彩主胜").score < 2, "均势盘应压低硬选胜负");
assert.ok(balancedRows.find(row => row.name === "竞彩平局").score >= 3, "均势盘应保留平局防范");

const superTrap = context.applyMarketQualityGate([
  { name: "竞彩主胜", score: 4, grade: "偏有价值", cls: "strong", action: "可下注", reason: "原始主胜" },
  { name: "亚盘主队 -2.5", score: 4, grade: "偏有价值", cls: "strong", action: "可下注", reason: "原始深让" }
], {
  e1: [1.09, 9.5, 23],
  p1: { home: 0.84, draw: 0.10, away: 0.04 },
  ah1: -2.5,
  goalLine1: 3.5,
  over1: 0.925,
  under1: 0.925
});
assert.ok(superTrap.every(row => row.score < 4), "超级低赔且平局保护不够高时应降权");

const drawLean = context.marketAdjustedResultLean("home", {
  e1: [1.65, 3.75, 5.5],
  p1: { home: 0.55, draw: 0.25, away: 0.2 },
  ah1: -0.75,
  goalLine1: 2.25,
  over1: 0.8,
  under1: 1.05
});
assert.equal(drawLean, "draw", "中等强弱且存在防平结构时，比分方向应转为平局保护");

const mediumRows = context.applyMarketQualityGate([
  { name: "竞彩主胜", score: 4.2, grade: "偏有价值", cls: "strong", action: "可下注", reason: "原始主胜" },
  { name: "小球 2.25", score: 4.5, grade: "偏有价值", cls: "strong", action: "可下注", reason: "原始小球" }
], {
  e1: [1.65, 3.75, 5.5],
  p1: { home: 0.55, draw: 0.25, away: 0.2 },
  ah1: -0.75,
  goalLine1: 2.25,
  over1: 0.8,
  under1: 1.05
});
assert.ok(mediumRows.every(row => row.score < 2), "非明显强弱层应整体降为观察，不进入下注池");

const obviousRows = context.applyMarketQualityGate([
  { name: "竞彩主胜", score: 4.2, grade: "偏有价值", cls: "strong", action: "可下注", reason: "原始主胜" }
], {
  e1: [1.44, 4.33, 7],
  p1: { home: 0.64, draw: 0.21, away: 0.15 },
  ah1: -1.25,
  goalLine1: 2.25,
  over1: 0.82,
  under1: 1.02
});
assert.ok(obviousRows[0].score >= 2, "明显强弱层应保留可下注方向");

console.log("market quality gate tests passed");
