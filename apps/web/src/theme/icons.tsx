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
  Globe2,
  Eye,
  Heart,
  Inbox,
  KeyRound,
  LayoutGrid,
  LayoutList,
  Loader2,
  LogOut,
  Mail,
  Send,
  Upload,
  Link2,
  LockKeyhole,
  Monitor,
  MoreHorizontal,
  MoreVertical,
  Boxes,
  UsersRound,
  Box,
  Database,
  Settings,
  Code,
  SlidersHorizontal,
  SortAsc,
  Sparkles,
  Star,
  Pencil,
  Play,
  Plus,
  createLucideIcon,
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

// Lucide 1.0 dropped brand marks. This is the outline its 0.x `Github` icon
// drew (ISC), kept so the GitHub entry looks the same as before.
const Github = createLucideIcon("github", [
  [
    "path",
    {
      d: "M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4",
      key: "tonef",
    },
  ],
  ["path", { d: "M9 18c-4.51 2-5-2-7-2", key: "9comsn" }],
]);

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
  | "send"
  | "upload"
  | "arrowLeft"
  | "flag"
  | "globe"
  | "github"
  | "google"
  | "heart"
  | "link"
  | "lock"
  | "more"
  | "moreVertical"
  | "clock"
  | "sparkles"
  | "star"
  | "eye"
  | "download"
  | "edit"
  | "play"
  | "plus"
  | "logout"
  | "objects"
  | "devices"
  | "access"
  | "team"
  | "component"
  | "technology"
  | "setup"
  | "code";

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
  send: Send,
  upload: Upload,
  arrowLeft: ArrowLeft,
  flag: Flag,
  globe: Globe2,
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
  lock: LockKeyhole,
  more: MoreHorizontal,
  moreVertical: MoreVertical,
  clock: Clock3,
  sparkles: Sparkles,
  star: Star,
  eye: Eye,
  download: Download,
  edit: Pencil,
  play: Play,
  plus: Plus,
  logout: LogOut,
  objects: Boxes,
  devices: Monitor,
  access: KeyRound,
  team: UsersRound,
  component: Box,
  technology: Database,
  setup: Settings,
  code: Code,
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
