import path from "node:path";

import { localMd } from "@fumadocs/local-md";
import { loader } from "fumadocs-core/source";

const userFacingRoot = process.env.AI_STP_USER_FACING_ROOT
  ? process.env.AI_STP_USER_FACING_ROOT
  : path.resolve(process.cwd(), "..", "..", "docs-user-facing");
const userDocs = localMd({ dir: path.join(userFacingRoot, "docs"), include: ["**/*.md"] });

export const docsSource = loader({
  baseUrl: "/docs",
  source: await userDocs.staticSource(),
});
