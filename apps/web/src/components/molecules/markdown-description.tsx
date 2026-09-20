import { renderPassportDescription } from "@/lib/markdown/passport";
import { renderMarkdownOnServer } from "@/lib/markdown/render";

type MarkdownDescriptionProps = {
  source: string;
  heading?: string;
  article?: boolean;
  articleTitle?: string;
  articleCoverImage?: string | null;
  variant?: "document" | "passport";
};

/**
 * Renders description via shared server-safe pipeline only (SPEC-029).
 * Never parses unsanitized Markdown in the client.
 * `variant="passport"` applies the strict SPEC-029 profile that mirrors
 * `ai_stp_passports.markdown`; `variant="document"` (default) is the richer
 * operator-content profile (tables, heading anchors) for articles and
 * generated sections.
 */
export function MarkdownDescription({
  source,
  heading = "Description",
  article = false,
  articleTitle,
  articleCoverImage,
  variant = "document",
}: MarkdownDescriptionProps) {
  const html =
    variant === "passport"
      ? renderPassportDescription(source)
      : renderMarkdownOnServer(source, {
          article,
          ...(articleTitle === undefined ? {} : { title: articleTitle }),
          ...(articleCoverImage === undefined ? {} : { coverImage: articleCoverImage }),
        }).html;
  return (
    <section className={article ? "article-prose" : "space-y-3"} aria-label={heading}>
      {!article ? (
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-xl font-medium tracking-tight">{heading}</h2>
        </div>
      ) : null}
      <div
        className={
          article
            ? "article-prose__body"
            : "prose-sm text-muted-foreground [&_td]:border-border [&_th]:border-border [&_th]:bg-muted max-w-none space-y-3 overflow-x-auto text-sm leading-relaxed [&_a]:underline [&_code]:font-mono [&_pre]:overflow-x-auto [&_pre]:rounded-sm [&_pre]:border [&_pre]:p-3 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:p-2 [&_th]:border [&_th]:p-2 [&_th]:text-left"
        }
        // Sanitized HTML from server renderer only (SPEC-029 REQ-2905).
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </section>
  );
}
