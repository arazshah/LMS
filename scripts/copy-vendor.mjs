// Copies self-hosted frontend assets into static/dist (no external CDNs; users are in Iran).
import { cpSync, mkdirSync } from "node:fs";

mkdirSync("static/dist/fonts", { recursive: true });
cpSync("node_modules/htmx.org/dist/htmx.min.js", "static/dist/htmx.min.js");
cpSync(
  "node_modules/vazirmatn/fonts/webfonts/Vazirmatn[wght].woff2",
  "static/dist/fonts/Vazirmatn-Variable.woff2",
);
