import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lock = JSON.parse(await readFile(path.join(desktop, "package-lock.json"), "utf8"));
const output = path.join(desktop, "resources", "npm-licenses");
await mkdir(output, { recursive: true });

const packages = Object.entries(lock.packages || {})
  .filter(([location, metadata]) => location.startsWith("node_modules/") && metadata.dev !== true)
  .sort(([left], [right]) => left.localeCompare(right));
const inventory = ["SUGAR Desktop production npm dependency licenses", "", "Retain these notices when redistributing SUGAR Desktop.", ""];
const namePattern = /^(license|licence|copying|notice|third.?party)([-_.].*)?$/i;

for (const [location, metadata] of packages) {
  const packageRoot = path.resolve(desktop, location);
  if (!packageRoot.startsWith(path.join(desktop, "node_modules") + path.sep)) continue;
  let packageInfo;
  try { packageInfo = JSON.parse(await readFile(path.join(packageRoot, "package.json"), "utf8")); }
  catch { continue; }
  const packageName = packageInfo.name || location.slice("node_modules/".length);
  const version = packageInfo.version || metadata.version || "unknown";
  const license = typeof packageInfo.license === "string" ? packageInfo.license : "License metadata not declared";
  const folder = path.join(output, `${packageName.replaceAll("/", "_").replaceAll("@", "")}-${version}`);
  await mkdir(folder, { recursive: true });
  let names = [];
  try { names = await readdir(packageRoot); } catch { continue; }
  const licenses = names.filter((name) => namePattern.test(name));
  inventory.push(`${packageName}@${version} — ${license}${licenses.length ? "" : " (no top-level license file found)"}`);
  for (const name of licenses) {
    await copyFile(path.join(packageRoot, name), path.join(folder, name));
  }
}

await mkdir(path.join(output, "_inventory"), { recursive: true });
await writeFile(path.join(output, "_inventory", "LICENSES.txt"), inventory.join("\n"), "utf8");
console.log(`Collected license texts for ${packages.length} resolved production npm dependencies.`);
