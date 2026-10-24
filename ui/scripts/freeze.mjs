import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { join, resolve, relative } from "node:path";
const target = resolve(process.argv[2]);
if (existsSync(target))
  throw new Error("Preserve an existing frozen candidate; choose a new path.");
cpSync("dist", target, { recursive: true });
const walk = (directory) =>
  readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) =>
      entry.isDirectory()
        ? walk(join(directory, entry.name))
        : [join(directory, entry.name)],
    )
    .sort();
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const files = Object.fromEntries(
  walk(target).map((file) => {
    const bytes = readFileSync(file);
    return [
      relative(target, file),
      { sha256: hash(bytes), bytes: bytes.length },
    ];
  }),
);
// Match Python json.dumps(sort_keys=True,separators=(',',':')) used by earlier manifests.
const canonical = Object.fromEntries(
  Object.entries(files).map(([file, value]) => [
    file,
    { bytes: value.bytes, sha256: value.sha256 },
  ]),
);
const manifest = {
  format: "career-agent.ui-build/1",
  sha256: hash(JSON.stringify(canonical)),
  path: target,
  status: "awaiting-independent-final-review",
  files,
};
const name = process.argv[2].split("/").at(-1);
writeFileSync(
  `evidence/${name}-manifest.json`,
  JSON.stringify(manifest, null, 2) + "\n",
);
console.log(
  JSON.stringify({
    sha256: manifest.sha256,
    path: target,
    files: Object.keys(files),
    bytes: Object.values(files).reduce((n, file) => n + file.bytes, 0),
  }),
);
