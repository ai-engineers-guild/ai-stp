import { publicOrigin } from "@/lib/site";
import { getEnv } from "@/lib/env";
import { isFeatureEnabled } from "@/lib/features/gate";

export function GET() {
  const origin = publicOrigin();
  const docsHref = getEnv().AI_STP_USER_DOCS_URL;
  const absolute = (path: string) => new URL(path, origin).toString();
  const body = `# ai_stp

> The AI setup registry for skills, MCP, hooks, and subagents — not another skills.sh. The web is the catalog; the agent installs through the CLI.

## Primary resources
- [Catalog](${absolute("/en/catalog")}): public components and setups
- [Human documentation](${docsHref}): product, CLI, catalog, trust and troubleshooting guides
- [OpenAPI](${absolute("/openapi.json")}): HTTP contract served by the deployed API
- [Provider-info schema](${absolute("/schemas/provider-protocol/v3/provider-info.json")}): JSON Schema for protocol v3 provider-info
- [Agent instructions](${absolute("/agents.md")}): safe machine onboarding
- [Extended context](${absolute("/llms-full.txt")}): terminology, trust model and supported harnesses
- [Catalog manifest](${absolute("/llms/catalog.ndjson")}): paginated active subjects
${isFeatureEnabled("content_hub") ? `- [Content](${absolute("/en/content")}): articles, product news, changelog and release notes\n` : ""}

## Rules
- Public catalog metadata is readable without an account.
- author_verified is not proof that component content is safe.
- Experimental objects require explicit request-scoped consent and are not auto-installed.
- Never infer private object existence from public responses.
- Use stable ids and exact versions; version numbers may be non-contiguous.
`;
  return new Response(body, {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "public, max-age=3600",
    },
  });
}
