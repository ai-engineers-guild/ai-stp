import type { ReactNode } from "react";

import { UI } from "@/lib/ui-selectors";

export function ObjectDetailFrame({
  description,
  media,
  main,
  rail,
  passport,
}: {
  description: ReactNode;
  media?: ReactNode;
  main: ReactNode;
  rail: ReactNode;
  passport?: ReactNode;
}) {
  return (
    <div
      data-ui={UI.component.detailLower}
      className="grid min-w-0 items-start gap-8 overflow-x-clip lg:grid-cols-[minmax(0,1fr)_22rem]"
    >
      <div className="order-2 min-w-0 space-y-8 lg:order-1">
        <div
          data-ui={UI.component.descriptionMedia}
          className={
            media
              ? "grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_16rem]"
              : "grid items-start gap-8"
          }
        >
          <div className="min-w-0">{description}</div>
          {media ? <div className="min-w-0 lg:max-w-64">{media}</div> : null}
        </div>
        <div data-ui={UI.component.detailMain} className="min-w-0 space-y-6">
          {passport}
          {main}
        </div>
      </div>
      <aside
        data-ui={UI.component.detailRail}
        className="order-1 min-w-0 space-y-4 self-start lg:sticky lg:top-24 lg:order-2"
      >
        {rail}
      </aside>
    </div>
  );
}
