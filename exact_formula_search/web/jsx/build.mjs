import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");
const staticRoot = join(packageRoot, "static");
const outputRoot = join(staticRoot, "js");

const reactPreset = (api) =>
  api.availablePresets != null && api.availablePresets.react != null
    ? [api.availablePresets.react, { runtime: "classic" }]
    : ["@babel/preset-react", { runtime: "classic" }];

const transform = async (babel, code, sourceName) => {
  const result = await babel.transformAsync(code, {
    filename: sourceName,
    presets: [reactPreset(babel)],
    sourceMaps: false,
    comments: false,
    compact: false,
    babelrc: false,
    configFile: false,
  });
  if (!result || typeof result.code !== "string") {
    throw new Error(`transformation produced no output for ${sourceName}`);
  }
  return result.code;
};

const run = async () => {
  let babel;
  try {
    babel = await import("@babel/standalone");
  } catch {
    babel = await import("babel");
  }
  const api = babel.default ?? babel;
  await mkdir(outputRoot, { recursive: true });
  const sources = (await readdir(here)).filter((name) => name.endsWith(".jsx")).sort();
  if (sources.length === 0) {
    throw new Error("no jsx sources found");
  }
  for (const source of sources) {
    const code = await readFile(join(here, source), "utf8");
    const compiled = await transform(api, code, source);
    const target = join(outputRoot, source.replace(/\.jsx$/, ".js"));
    await writeFile(target, compiled, "utf8");
    process.stdout.write(`${source} -> ${target}\n`);
  }
};

run().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
