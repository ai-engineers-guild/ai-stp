import { renderMarkdownOnServer } from "@/lib/markdown/render";

type MarkdownDescriptionProps = {
  source: string;
  heading?: string;
  article?: boolean;
  articleTitle?: string;
  articleCoverImage?: string | null;
};

/**
 * Renders description via shared server-safe pipeline only (SPEC-029).
 * Never parses unsanitized Markdown in the client.
 */
export function MarkdownDescription({
  source,
  heading = "Description",
  article = false,
  articleTitle,
  articleCoverImage,
}: MarkdownDescriptionProps) {
  const rendered = renderMarkdownOnServer(source, {
    article,
    ...(articleTitle === undefined ? {} : { title: articleTitle }),
    ...(articleCoverImage === undefined ? {} : { coverImage: articleCoverImage }),
  });
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
            : "prose-sm text-muted-foreground max-w-none space-y-3 text-sm leading-relaxed [&_a]:underline [&_code]:font-mono [&_pre]:overflow-x-auto [&_pre]:rounded-sm [&_pre]:border [&_pre]:p-3"
        }
        // Sanitized HTML from server renderer only (SPEC-029 REQ-2905).
        dangerouslySetInnerHTML={{ __html: rendered.html }}
      />
    </section>
  );
}
