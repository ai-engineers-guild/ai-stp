import type { ReactNode } from "react";

import { DetailAccordion } from "@/components/molecules/detail-accordion";

export function CollapsibleSection({
  title,
  summary,
  children,
}: {
  title: string;
  summary?: string;
  children: ReactNode;
}) {
  return (
    <DetailAccordion title={title} summary={summary}>
      {children}
    </DetailAccordion>
  );
}
