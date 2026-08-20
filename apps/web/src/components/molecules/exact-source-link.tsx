import type { GitSource } from "@/lib/api/generated/types.gen";
import { exactSourceUrl } from "@/lib/source-url";
import { Icon } from "@/theme/icons";

export function ExactSourceLink({ source, label }: { source: GitSource | null; label: string }) {
  const href = exactSourceUrl(source);
  if (!href) return null;

  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="focus-visible:ring-ring inline-flex items-center gap-2 font-medium underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
    >
      <Icon name="github" size="sm" /> {label}
    </a>
  );
}
