export type MachineBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "link"; text: string; href: string }
  | { type: "field"; name: string; value: string }
  | { type: "list"; items: string[] }
  | { type: "code"; code: string; language?: string };

export type MachineDocument = MachineBlock[];

export function heading(level: number, text: string): MachineBlock {
  return { type: "heading", level, text };
}

export function paragraph(text: string): MachineBlock {
  return { type: "paragraph", text };
}

export function link(text: string, href: string): MachineBlock {
  return { type: "link", text, href };
}

export function field(name: string, value: string): MachineBlock {
  return { type: "field", name, value };
}

export function list(items: string[]): MachineBlock {
  return { type: "list", items };
}

export function code(codeText: string, language?: string): MachineBlock {
  return language === undefined
    ? { type: "code", code: codeText }
    : { type: "code", code: codeText, language };
}
