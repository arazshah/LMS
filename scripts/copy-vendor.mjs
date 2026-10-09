// Copies self-hosted frontend assets into static/dist (no external CDNs; users are in Iran).
import { cpSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

// Source maps are not shipped; drop the reference so collectstatic's manifest
// storage does not fail looking for them.
function copyScript(from, to) {
  const code = readFileSync(from, "utf8").replace(/\n\/\/# sourceMappingURL=.*\s*$/, "\n");
  writeFileSync(to, code);
}

mkdirSync("static/dist/fonts", { recursive: true });
copyScript("node_modules/htmx.org/dist/htmx.min.js", "static/dist/htmx.min.js");
copyScript("node_modules/hls.js/dist/hls.light.min.js", "static/dist/hls.min.js");
cpSync(
  "node_modules/vazirmatn/fonts/webfonts/Vazirmatn[wght].woff2",
  "static/dist/fonts/Vazirmatn-Variable.woff2",
);
