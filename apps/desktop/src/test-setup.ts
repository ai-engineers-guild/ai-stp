import { beforeAll } from "vitest";
import { loadCatalog } from "./i18n";

// Component tests use the same packaged messages as the installed application.
beforeAll(async () => {
  await loadCatalog("en");
});
