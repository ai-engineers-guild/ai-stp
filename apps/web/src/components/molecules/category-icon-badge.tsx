import { AvatarImage } from "@/components/atoms/avatar-image";
import {
  CATEGORY_ICON_NAMES,
  CategoryIcon,
  defaultCategoryIcon,
  type CategoryIconName,
} from "@/theme/category-icons";

/** Prefix the contract's TechnologyCategoryMetadata.icon uses for registry glyphs. */
export const CATEGORY_LUCIDE_PREFIX = "lucide:";

export function categoryLucideName(icon: string | null | undefined): CategoryIconName | null {
  const name = icon?.startsWith(CATEGORY_LUCIDE_PREFIX)
    ? icon.slice(CATEGORY_LUCIDE_PREFIX.length)
    : null;
  return name && (CATEGORY_ICON_NAMES as readonly string[]).includes(name)
    ? (name as CategoryIconName)
    : null;
}

/** Framed category mark: an uploaded image fills the box; a lucide glyph sits inside. */
export function CategoryIconBadge({
  icon,
  seed,
  size,
}: {
  /** Persisted icon value, or null/"" for the deterministic fallback. */
  icon: string | null | undefined;
  /** Stable id used to derive the fallback glyph. */
  seed: string;
  size: 8 | 16;
}) {
  const box = size === 8 ? "size-8 rounded-md" : "size-16 rounded-lg";
  const glyph = (
    <CategoryIcon
      name={categoryLucideName(icon) ?? defaultCategoryIcon(seed)}
      className={size === 8 ? "size-4" : "size-8"}
    />
  );
  const frame = (
    <span className={`bg-muted text-foreground grid shrink-0 place-items-center ${box}`}>
      {glyph}
    </span>
  );
  if (!icon || categoryLucideName(icon)) return frame;
  return (
    <AvatarImage
      src={icon}
      width={size * 4}
      height={size * 4}
      className={`${box} object-cover`}
      fallback={frame}
    />
  );
}
