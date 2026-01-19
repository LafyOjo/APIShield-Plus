import { mkdir } from "node:fs/promises";
import { build } from "esbuild";

const ingestUrl = process.env.AGENT_INGEST_URL;
const define = {};
if (ingestUrl) {
  define.__AGENT_INGEST_URL__ = JSON.stringify(ingestUrl);
}

await mkdir("dist", { recursive: true });

await build({
  entryPoints: ["src/agent.js"],
  outfile: "dist/agent.js",
  bundle: true,
  minify: true,
  format: "iife",
  globalName: "APIShieldAgent",
  define,
});
