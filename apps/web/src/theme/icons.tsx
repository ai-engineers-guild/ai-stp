/**
 * UI kit icon layer. All product icons go through this registry so Open Design /
 * rebrand can swap the set without hunting lucide imports in every file.
 */
import {
  AlertCircle,
  ArrowLeft,
  Camera,
  Clock3,
  CheckCircle2,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleHelp,
  Copy,
  Download,
  Filter,
  Flag,
  Eye,
  Github,
  Heart,
  Inbox,
  KeyRound,
  LayoutGrid,
  LayoutList,
  Loader2,
  LogOut,
  Mail,
  Link2,
  Monitor,
  MoreHorizontal,
  MoreVertical,
  Boxes,
  SlidersHorizontal,
  SortAsc,
  Sparkles,
  Star,
  Pencil,
  type LucideIcon,
  type LucideProps,
  Moon,
  Search,
  Sun,
  UserRound,
  X,
} from "lucide-react";

import { cn } from "@/lib/cn";
import { iconSizes } from "@/theme/tokens";

export type IconName =
  | "search"
  | "sun"
  | "moon"
  | "copy"
  | "check"
  | "verified"
  | "alert"
  | "empty"
  | "loader"
  | "close"
  | "chevronRight"
  | "chevronUp"
  | "chevronLeft"
  | "help"
  | "camera"
  | "cards"
  | "list"
  | "filter"
  | "sort"
  | "controls"
  | "chevronDown"
  | "user"
  | "mail"
  | "arrowLeft"
  | "flag"
  | "github"
  | "google"
  | "heart"
  | "link"
  | "more"
  | "moreVertical"
  | "clock"
  | "sparkles"
  | "star"
  | "eye"
  | "download"
  | "edit"
  | "logout"
  | "objects"
  | "devices"
  | "access";

export type IconSize = keyof typeof iconSizes;

const REGISTRY: Record<IconName, LucideIcon> = {
  search: Search,
  sun: Sun,
  moon: Moon,
  copy: Copy,
  check: CheckCircle2,
  verified: Check,
  alert: AlertCircle,
  empty: Inbox,
  loader: Loader2,
  close: X,
  chevronRight: ChevronRight,
  chevronUp: ChevronUp,
  chevronLeft: ChevronLeft,
  help: CircleHelp,
  camera: Camera,
  cards: LayoutGrid,
  list: LayoutList,
  filter: Filter,
  sort: SortAsc,
  controls: SlidersHorizontal,
  chevronDown: ChevronDown,
  user: UserRound,
  mail: Mail,
  arrowLeft: ArrowLeft,
  flag: Flag,
  github: Github,
  google: ((props: LucideProps) => (
    <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M21.6 12.23c0-.71-.06-1.4-.18-2.07H12v3.92h5.38a4.6 4.6 0 0 1-2 3.02v2.55h3.24c1.9-1.75 2.98-4.33 2.98-7.42Z" />
      <path d="M12 22c2.7 0 4.98-.9 6.63-2.43l-3.24-2.55c-.9.6-2.05.96-3.39.96-2.6 0-4.81-1.76-5.6-4.13H3.06v2.63A10 10 0 0 0 12 22Z" />
      <path d="M6.4 13.85A6 6 0 0 1 6.08 12c0-.64.11-1.27.32-1.85V7.52H3.06A10 10 0 0 0 2 12c0 1.61.39 3.14 1.06 4.48l3.34-2.63Z" />
      <path d="M12 6.02c1.47 0 2.79.5 3.82 1.49l2.87-2.87A9.64 9.64 0 0 0 12 2a10 10 0 0 0-8.94 5.52l3.34 2.63C7.19 7.78 9.4 6.02 12 6.02Z" />
    </svg>
  )) as LucideIcon,
  heart: Heart,
  link: Link2,
  more: MoreHorizontal,
  moreVertical: MoreVertical,
  clock: Clock3,
  sparkles: Sparkles,
  star: Star,
  eye: Eye,
  download: Download,
  edit: Pencil,
  logout: LogOut,
  objects: Boxes,
  devices: Monitor,
  access: KeyRound,
};

export type IconProps = Omit<LucideProps, "size"> & {
  name: IconName;
  size?: IconSize;
};

export function Icon({
  name,
  size = "md",
  className,
  "aria-label": ariaLabel,
  ...props
}: IconProps) {
  const Comp = REGISTRY[name];
  const decorative = ariaLabel === undefined;
  return (
    <Comp
      className={cn("shrink-0", className)}
      style={{ width: iconSizes[size], height: iconSizes[size] }}
      aria-hidden={decorative ? true : undefined}
      aria-label={ariaLabel}
      {...props}
    />
  );
}

export const iconNames = Object.keys(REGISTRY) as IconName[];
