import {
  field,
  heading,
  link,
  list,
  paragraph,
  type MachineDocument,
} from "@/lib/projection/machine-document";

export function presentServicesIndex(input: {
  title: string;
  subtitle: string;
  emptyMessage: string;
  services: ReadonlyArray<{ name: string; domain: string }>;
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.title),
    paragraph(input.subtitle),
    link("Catalog", "/catalog"),
  ];
  if (input.services.length === 0) {
    doc.push(paragraph(input.emptyMessage));
    return doc;
  }
  for (const item of input.services) {
    doc.push(link(item.name, `/services/${item.domain}`));
    doc.push(field("domain", item.domain));
  }
  return doc;
}

export function presentCountry(input: {
  title: string;
  code: string;
  services: ReadonlyArray<{ name: string; domain: string }>;
  objects: ReadonlyArray<{ name: string }>;
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.title),
    field("code", input.code),
    link("Services", "/services"),
    link("Catalog", "/catalog"),
  ];
  if (input.services.length > 0) {
    doc.push(heading(2, "Services"));
    for (const item of input.services) {
      doc.push(link(item.name, `/services/${item.domain}`));
    }
  }
  if (input.objects.length > 0) {
    doc.push(heading(2, "Automations"));
    doc.push(list(input.objects.map((item) => item.name)));
  }
  return doc;
}

export function presentService(input: {
  name: string;
  domain: string;
  primaryUrl: string;
  countryCodes: readonly string[];
  objects: ReadonlyArray<{ name: string; kind: string; stableId: string }>;
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.name),
    field("domain", input.domain),
    link(input.domain, input.primaryUrl),
    link("Services", "/services"),
    link("Catalog", "/catalog"),
  ];
  if (input.countryCodes.length > 0) {
    for (const code of input.countryCodes) {
      doc.push(link(code, `/countries/${code}`));
    }
  }
  if (input.objects.length > 0) {
    doc.push(heading(2, "Automations"));
    for (const item of input.objects) {
      const href =
        item.kind === "setup"
          ? `/catalog/setups/${item.stableId}`
          : `/catalog/components/${item.stableId}`;
      doc.push(link(item.name, href));
    }
  }
  return doc;
}
