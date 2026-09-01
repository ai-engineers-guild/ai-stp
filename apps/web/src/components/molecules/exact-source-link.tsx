import type { GitSource } from "@/lib/api/generated/types.gen";
import { sourceLinksFor, type PublicSourceLink } from "@/lib/source-url";
import { Icon } from "@/theme/icons";

export function ExactSourceLink({
  source,
  facts,
  links,
  label,
}: {
  source: GitSource | null;
  facts?: { source_links?: { value: unknown } } | null;
  links?: readonly (PublicSourceLink & { label: string })[];
  label: string;
}) {
  const resolved = links ?? sourceLinksFor(source, facts).map((item) => ({ ...item, label }));
  if (!resolved.length) return null;

  return (
    <span className="inline-flex flex-wrap items-center gap-3">
      {resolved.map((item) => (
        <a
          key={item.href}
          href={item.href}
          target="_blank"
          rel="noreferrer"
          className="focus-visible:ring-ring inline-flex items-center gap-2 font-medium underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
        >
          <Icon name={item.provider === "GitHub" ? "github" : "link"} size="sm" /> {item.label}
        </a>
      ))}
    </span>
  );
}
