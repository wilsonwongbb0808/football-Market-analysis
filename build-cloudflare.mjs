import { cpSync, mkdirSync, rmSync, copyFileSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const root = process.cwd();
const dist = join(root, "dist-cloudflare");

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

copyFileSync(join(root, "football-odds-analyzer.html"), join(dist, "index.html"));
copyFileSync(join(root, "football-odds-analyzer.html"), join(dist, "football-odds-analyzer.html"));
copyFileSync(join(root, "psg-arsenal-score-corner-predictor.html"), join(dist, "psg-arsenal-score-corner-predictor.html"));
copyFileSync(join(root, "_routes.json"), join(dist, "_routes.json"));

cpSync(join(root, "assets"), join(dist, "assets"), { recursive: true });
cpSync(join(root, "functions"), join(dist, "functions"), { recursive: true });
const sharedSource = readFileSync(join(root, "functions", "_shared", "license.js"), "utf8")
  .replaceAll(/^export\s+/gm, "");
for (const folder of readdirSync(join(dist, "functions", "api"), { withFileTypes: true })) {
  if (!folder.isDirectory() || folder.name === "_shared") continue;
  const folderPath = join(dist, "functions", "api", folder.name);
  for (const file of readdirSync(folderPath, { withFileTypes: true })) {
    if (!file.isFile() || !file.name.endsWith(".js")) continue;
    const filePath = join(folderPath, file.name);
    const source = readFileSync(filePath, "utf8").replace(/^import\s+\{[\s\S]*?\}\s+from\s+["']\.\.\/\.\.\/_shared\/license\.js["'];\s*/, `${sharedSource}\n`);
    writeFileSync(filePath, source, "utf8");
  }
}
mkdirSync(join(dist, "output"), { recursive: true });
copyFileSync(
  join(root, "output", "worldcup-opening-odds.json"),
  join(dist, "output", "worldcup-opening-odds.json")
);

console.log("Cloudflare Pages output:", dist);
