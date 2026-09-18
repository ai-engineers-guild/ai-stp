import { getTranslations } from "next-intl/server";

import { searchComponents } from "@/lib/api/catalog";
import { presentPage } from "@/lib/projection/presenters";
import type { MachineRoute } from "@/lib/projection/route-table";

export const CORPORATE_ROUTES: MachineRoute[] = [
  {
    pattern: "corporate/components",
    resolve: async () => {
      const t = await getTranslations("hub");
      const result = await searchComponents({ page_size: 100, include_experimental: true }).catch(
        () => null,
      );
      return presentPage({
        title: t("components"),
        links:
          result === null
            ? []
            : [...result.items, ...result.experimental].map((item) => [
                item.latest_name,
                `/catalog/components/${encodeURIComponent(item.stable_id)}`,
              ]),
      });
    },
  },
];
