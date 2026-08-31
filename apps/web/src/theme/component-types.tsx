import {
  Bot,
  Braces,
  Cable,
  Command,
  FileText,
  Plug,
  Settings2,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import type { ComponentType } from "@/lib/api/generated/types.gen";
import { cn } from "@/lib/cn";

type ComponentTypeDefinition = {
  icon: LucideIcon;
  labelKey: string;
};

/**
 * Client-owned presentation registry. Keep the exhaustive list, icon mapping,
 * and localization together until ADR-0054 moves catalog media to metadata.
 */
export const COMPONENT_TYPE_PRESENTATION: Record<ComponentType, ComponentTypeDefinition> = {
  instruction: { icon: FileText, labelKey: "componentTypes.instruction" },
  skill: { icon: Sparkles, labelKey: "componentTypes.skill" },
  mcp: { icon: Cable, labelKey: "componentTypes.mcp" },
  hook: { icon: Plug, labelKey: "componentTypes.hook" },
  command: { icon: Command, labelKey: "componentTypes.command" },
  agent: { icon: Bot, labelKey: "componentTypes.agent" },
  plugin: { icon: Braces, labelKey: "componentTypes.plugin" },
  setting: { icon: Settings2, labelKey: "componentTypes.setting" },
};

export function ComponentTypeIcon({
  type,
  compact = false,
  className,
}: {
  type: ComponentType;
  compact?: boolean;
  className?: string;
}) {
  const Glyph = COMPONENT_TYPE_PRESENTATION[type].icon;
  return (
    <span
      data-component-type={type}
      className={cn(
        "bg-muted border-border text-foreground inline-flex shrink-0 items-center justify-center rounded-sm border",
        compact ? "h-10 w-10" : "h-16 w-16",
        className,
      )}
      aria-hidden="true"
    >
      <Glyph strokeWidth={1.7} className={compact ? "h-5 w-5" : "h-8 w-8"} />
    </span>
  );
}
