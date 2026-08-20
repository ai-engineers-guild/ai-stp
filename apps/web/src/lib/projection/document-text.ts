import type { MachineDocument } from "@/lib/projection/machine-document";
import { projectedHref } from "@/lib/projection/paths";

/** Serialize a machine document to plain text (shared with /llms-full.txt). */
export function machineDocumentToText(document: MachineDocument, locale: string): string {
  const lines: string[] = [];

  for (const block of document) {
    switch (block.type) {
      case "heading":
        lines.push(`${"#".repeat(block.level)} ${block.text}`);
        break;
      case "paragraph":
        lines.push(block.text);
        break;
      case "link": {
        const href = projectedHref(block.href, locale);
        lines.push(`[${block.text}](${href})`);
        break;
      }
      case "field":
        lines.push(`- ${block.name}: ${block.value}`);
        break;
      case "list":
        for (const item of block.items) {
          lines.push(`* ${item}`);
        }
        break;
      case "code":
        lines.push(`\`\`\`${block.language ?? ""}`);
        lines.push(block.code);
        lines.push("```");
        break;
      default: {
        const _exhaustive: never = block;
        void _exhaustive;
      }
    }
    lines.push("");
  }

  return lines.join("\n").trimEnd() + "\n";
}
