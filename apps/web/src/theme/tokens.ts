/**
 * Typed view over portable design tokens (src/theme/tokens.json).
 * Change tokens.json when rebranding or porting to Open Design; keep CSS vars in sync.
 */

import raw from "./tokens.json";

export type ColorRole =
  | "background"
  | "foreground"
  | "card"
  | "card-foreground"
  | "popover"
  | "popover-foreground"
  | "primary"
  | "primary-foreground"
  | "primary-hover"
  | "secondary"
  | "secondary-foreground"
  | "muted"
  | "muted-foreground"
  | "accent"
  | "accent-foreground"
  | "destructive"
  | "destructive-foreground"
  | "border"
  | "input"
  | "ring"
  | "success"
  | "success-foreground"
  | "warning"
  | "warning-foreground";

export type ThemeMode = "light" | "dark";

type ColorEntry = { light: { $value: string }; dark: { $value: string } };

const colorMap = raw.color as Record<ColorRole, ColorEntry>;

/** Semantic color roles used by the UI kit (REQ-2214). */
export const COLOR_ROLES: readonly ColorRole[] = Object.keys(colorMap) as ColorRole[];

export function colorChannels(role: ColorRole, mode: ThemeMode): string {
  return colorMap[role][mode].$value;
}

export function hsl(role: ColorRole, mode: ThemeMode = "light"): string {
  return `hsl(${colorChannels(role, mode)})`;
}

export const spacing = Object.fromEntries(
  Object.entries(raw.space).map(([key, entry]) => [key, entry.$value]),
) as Record<string, string>;

export const radii = Object.fromEntries(
  Object.entries(raw.radius).map(([key, entry]) => [key, entry.$value]),
) as Record<string, string>;

export const fontSizes = Object.fromEntries(
  Object.entries(raw.font.size).map(([key, entry]) => [key, entry.$value]),
) as Record<string, string>;

export const fontWeights = Object.fromEntries(
  Object.entries(raw.font.weight).map(([key, entry]) => [key, entry.$value]),
) as Record<string, string>;

export const iconSizes = Object.fromEntries(
  Object.entries(raw.icon.size).map(([key, entry]) => [key, entry.$value]),
) as Record<"sm" | "md" | "lg", string>;

export const fontFamilySans = raw.font.family.sans.$value.join(", ");
export const fontFamilyMono = raw.font.family.mono.$value.join(", ");

export const motion = {
  durationFast: raw.motion.duration.fast.$value,
  durationNormal: raw.motion.duration.normal.$value,
} as const;

export const shadows = {
  sm: raw.shadow.sm.$value,
  md: raw.shadow.md.$value,
} as const;

/** Token file path relative to apps/web — Open Design import entry. */
export const TOKENS_PATH = "src/theme/tokens.json";
