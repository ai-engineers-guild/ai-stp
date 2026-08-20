import { localMd } from "@fumadocs/local-md";
import { loader } from "fumadocs-core/source";

const userDocs = localMd({ dir: "content/user-docs", include: ["**/*.md"] });

export const docsSource = loader({
  baseUrl: "/docs",
  source: await userDocs.staticSource(),
});
