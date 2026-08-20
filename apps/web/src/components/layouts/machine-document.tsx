import { type MachineDocument } from "@/lib/projection/machine-document";
import { projectedHref } from "@/lib/projection/paths";
import { UI } from "@/lib/ui-selectors";

export function MachineDocumentView({
  document,
  locale,
}: {
  document: MachineDocument;
  locale: string;
}) {
  return (
    <div
      data-ui={UI.machine.projection}
      className="flex flex-col gap-4 p-4 font-mono text-sm whitespace-pre-wrap"
    >
      {document.map((block, i) => {
        switch (block.type) {
          case "heading": {
            const prefix = "#".repeat(block.level) + " ";
            return (
              <div key={i} className="font-bold">
                {prefix}
                {block.text}
              </div>
            );
          }
          case "paragraph":
            return <div key={i}>{block.text}</div>;
          case "link": {
            const href = block.href.startsWith("http")
              ? block.href
              : projectedHref(block.href, locale);
            return (
              <div key={i}>
                [{block.text}](
                <a href={href} className="underline">
                  {href}
                </a>
                )
              </div>
            );
          }
          case "field":
            return (
              <div key={i}>
                - {block.name}: {block.value}
              </div>
            );
          case "list":
            return (
              <div key={i} className="pl-4">
                {block.items.map((item, j) => (
                  <div key={j}>* {item}</div>
                ))}
              </div>
            );
          case "code":
            return (
              <div key={i}>
                <div>{`\`\`\`${block.language ?? ""}`}</div>
                <div className="pl-2">{block.code}</div>
                <div>{"```"}</div>
              </div>
            );
          default: {
            const _exhaustive: never = block;
            void _exhaustive;
            return null;
          }
        }
      })}
    </div>
  );
}
