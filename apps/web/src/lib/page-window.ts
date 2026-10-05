/** Allowed audit journal page sizes; shared by the server reader and the client panel. */
export const AUDIT_PAGE_SIZES = [10, 25, 50] as const;

/** Compact page list: edges, current neighbourhood, gaps. */
export function pageWindow(current: number, total: number, radius = 2): Array<number | "gap"> {
  if (total < 1) return [];
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const pages = new Set<number>([1, total]);
  const start = Math.max(1, current - radius);
  const end = Math.min(total, current + radius);
  for (let page = start; page <= end; page += 1) pages.add(page);
  const ordered = [...pages].sort((left, right) => left - right);
  const window: Array<number | "gap"> = [];
  for (const page of ordered) {
    const previous = window[window.length - 1];
    if (typeof previous === "number" && page - previous > 1) window.push("gap");
    window.push(page);
  }
  return window;
}
