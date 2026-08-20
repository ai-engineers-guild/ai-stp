import { Icon } from "@/theme";

export function CatalogEngagement({
  likes,
  stars,
  likesLabel,
  starsLabel,
}: {
  likes: number;
  stars: number | null | undefined;
  likesLabel: string | undefined;
  starsLabel: string | undefined;
}) {
  const showStars = stars !== null && stars !== undefined;
  return (
    <div className="text-muted-foreground flex min-w-0 flex-wrap items-center gap-3 text-xs">
      <span
        className="inline-flex items-center gap-1"
        aria-label={`${likesLabel ?? "Likes"}: ${likes}`}
      >
        <Icon name="heart" size="sm" />
        <span className="font-mono">{likes}</span>
      </span>
      {showStars ? (
        <span
          className="inline-flex items-center gap-1"
          aria-label={`${starsLabel || "GitHub stars"}: ${stars}`}
        >
          <Icon name="star" size="sm" />
          <span className="font-mono">{stars}</span>
        </span>
      ) : null}
    </div>
  );
}
