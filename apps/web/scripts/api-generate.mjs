/**
 * Generate the typed client under TypeScript 6 resolution.
 * openapi-ts needs a programmatic TS API; TS 7 is the typecheck gate only.
 */
import Module from "node:module";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const ts6Entry = require.resolve("typescript6");
const original = Module._resolveFilename;
Module._resolveFilename = function patched(request, parent, isMain, options) {
  if (request === "typescript") {
    return ts6Entry;
  }
  return original.call(this, request, parent, isMain, options);
};

const openapiBin = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../node_modules/@hey-api/openapi-ts/bin/run.js",
);

await import(pathToFileURL(openapiBin).href);
