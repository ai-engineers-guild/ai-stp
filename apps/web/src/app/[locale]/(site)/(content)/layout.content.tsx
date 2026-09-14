import type { ReactNode } from "react";

import { requireFeature } from "@/lib/features/gate";

export default function ContentLayout({ children }: { children: ReactNode }) {
  requireFeature("content_hub");
  return children;
}
