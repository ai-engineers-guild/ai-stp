import { listPublishedContent } from "@/lib/api/content";
import { machineDocumentToText } from "@/lib/projection/document-text";
import { presentLanding, presentPlatformContext } from "@/lib/projection/presenters";
import { INSTALL_CLI } from "@/lib/cli-copy";
import { getEnv } from "@/lib/env";
import { presentContentIndex } from "@/lib/content/presenter";
import { isFeatureEnabled } from "@/lib/features/gate";

/**
 * Expanded machine context assembled from the same presenters as machine HTML
 * pages (REQ-3608). Content-type remains text/plain; address is unchanged.
 */
export async function GET() {
  const locale = "en";
  const docsHref = getEnv().AI_STP_USER_DOCS_URL;
  const platform = presentPlatformContext({ docsHref });
  const landing = presentLanding({
    title: "The AI setup registry, not just a skill catalog",
    subtitle: "Find, verify, install, and earn on AI components.",
    browseCatalog: "Browse catalog",
    installCommand: INSTALL_CLI,
    installHeading: "Install the CLI",
    docsHref,
  });

  const published = isFeatureEnabled("content_hub")
    ? await listPublishedContent(locale).catch(() => [])
    : [];
  const content = published.length
    ? "\n" + machineDocumentToText(presentContentIndex(published), locale)
    : "";
  const body =
    machineDocumentToText(platform, locale) +
    "\n" +
    machineDocumentToText(landing, locale) +
    content;

  return new Response(body, {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "public, max-age=3600",
    },
  });
}
