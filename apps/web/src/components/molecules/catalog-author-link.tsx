import { VerifiedAvatar } from "@/components/molecules/verified-avatar";
import { cn } from "@/lib/cn";
import { Link } from "@/lib/i18n/navigation";

export function ObjectAuthorRail({
  accountId,
  displayName,
  avatarUrl,
  verified,
  verifiedLabel,
  authorLabel,
  headingId = "object-author-heading",
}: {
  accountId: string;
  displayName: string | null | undefined;
  avatarUrl: string | null | undefined;
  verified: boolean;
  verifiedLabel: string;
  authorLabel: string;
  headingId?: string;
}) {
  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId} className="sr-only">
        {authorLabel}
      </h2>
      <CatalogAuthorLink
        accountId={accountId}
        displayName={displayName}
        avatarUrl={avatarUrl}
        verified={verified}
        verifiedLabel={verifiedLabel}
        authorLabel={authorLabel}
      />
    </section>
  );
}

export function CatalogAuthorLink({
  accountId,
  displayName,
  avatarUrl,
  verified,
  verifiedLabel,
  authorLabel,
}: {
  accountId: string;
  displayName: string | null | undefined;
  avatarUrl: string | null | undefined;
  verified: boolean;
  verifiedLabel: string;
  authorLabel: string;
}) {
  const name = displayName?.trim() || authorLabel;
  return (
    <Link
      href={`/publishers/${accountId}`}
      prefetch={false}
      data-ui="catalog-author-link"
      className={cn(
        "border-border bg-card hover:bg-muted/40 focus-visible:ring-ring",
        "flex min-h-11 min-w-0 items-center gap-2 rounded-lg border p-2",
        "focus-visible:ring-2 focus-visible:outline-none",
      )}
      title={name}
    >
      <VerifiedAvatar src={avatarUrl} verified={verified} verifiedLabel={verifiedLabel} size="sm" />
      <span className="min-w-0 truncate text-sm font-medium">{name}</span>
    </Link>
  );
}
