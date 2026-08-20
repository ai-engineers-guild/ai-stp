import {
  field,
  heading,
  link,
  paragraph,
  type MachineDocument,
} from "@/lib/projection/machine-document";
import type { ContentEntry } from "@/lib/content/source";

export function presentContentIndex(entries: ContentEntry[]): MachineDocument {
  const doc: MachineDocument = [heading(1, "Content hub"), link("Home", "/")];
  for (const entry of entries) {
    doc.push(
      link(entry.title, `/content/${entry.type}/${entry.slug}`),
      field("type", entry.type),
      field("published_at", entry.published_at),
      paragraph(entry.description),
    );
  }
  return doc;
}

export function presentContentEntry(entry: ContentEntry): MachineDocument {
  return [
    heading(1, entry.title),
    link("Content hub", "/content"),
    field("type", entry.type),
    field("published_at", entry.published_at),
    field("tags", entry.tags.join(", ")),
    paragraph(entry.description),
    heading(2, "Content"),
    paragraph(entry.body),
  ];
}
