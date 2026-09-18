import type { ReactNode } from "react";

import { UI } from "@/lib/ui-selectors";

export function EntityDetailHeader({
  icon,
  title,
  meta,
  stats,
  menu,
}: {
  icon: ReactNode;
  title: string;
  meta?: ReactNode;
  stats?: ReactNode;
  menu?: ReactNode;
}) {
  return (
    <header
      data-ui={UI.component.detailHeader}
      className="border-border relative min-w-0 overflow-x-clip border-b pb-8"
    >
      {menu ? <div className="absolute top-0 right-0 z-10">{menu}</div> : null}
      <div className="flex min-w-0 items-start gap-3 pr-12 sm:gap-4">
        <div className="shrink-0">{icon}</div>
        <div className="min-w-0 flex-1 lg:pr-[42%]">
          <h1 className="max-w-4xl text-xl leading-tight font-semibold tracking-tight [overflow-wrap:anywhere] break-words sm:text-2xl lg:text-3xl">
            {title}
          </h1>
          {meta ? <div className="mt-3 min-w-0">{meta}</div> : null}
          {stats ? (
            <div
              data-ui={UI.component.actions}
              className="mt-5 flex min-w-0 flex-wrap items-center gap-2 lg:absolute lg:right-12 lg:bottom-8 lg:max-w-[40%] lg:justify-end"
            >
              {stats}
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
