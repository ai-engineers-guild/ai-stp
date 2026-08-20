import type { ReactNode } from "react";

import { AvatarImage } from "@/components/atoms/avatar-image";
import { cn } from "@/lib/cn";
import { Icon } from "@/theme";

const sizes = {
  sm: { image: 24, marker: "size-3", icon: "size-2" },
  md: { image: 36, marker: "size-4", icon: "size-3" },
  lg: { image: 68, marker: "size-5", icon: "size-4" },
} as const;

export function VerifiedAvatar({
  src,
  verified,
  verifiedLabel,
  size = "md",
  fallback,
  className,
}: {
  src: string | null | undefined;
  verified: boolean;
  verifiedLabel: string;
  size?: keyof typeof sizes;
  fallback?: ReactNode;
  className?: string;
}) {
  const styles = sizes[size];
  return (
    <span
      className={cn("relative inline-flex shrink-0 overflow-visible", className)}
      style={{ width: styles.image, height: styles.image }}
    >
      <span className="absolute top-0 left-0" style={{ width: styles.image, height: styles.image }}>
        <AvatarImage
          src={src}
          width={styles.image}
          height={styles.image}
          className="border-border bg-muted block size-full max-w-none rounded-full border object-cover"
          fallback={
            <span
              className="border-border bg-muted text-foreground grid size-full place-items-center rounded-full border text-[0.65em] font-medium"
              style={{ width: styles.image, height: styles.image }}
            >
              {fallback ?? <Icon name="user" size={size === "lg" ? "md" : "sm"} />}
            </span>
          }
        />
      </span>
      {verified ? (
        <span
          className={cn(
            "border-background bg-primary text-primary-foreground absolute bottom-0 left-0 grid -translate-x-1/4 translate-y-1/4 place-items-center rounded-full border-2",
            styles.marker,
          )}
          title={verifiedLabel}
          aria-label={verifiedLabel}
        >
          <Icon name="verified" className={styles.icon} strokeWidth={2} />
        </span>
      ) : null}
    </span>
  );
}
