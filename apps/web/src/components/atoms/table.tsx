import * as React from "react";

import { cn } from "@/lib/cn";

/**
 * Table primitives — the only owner of table/head/row markup styling.
 * Consumers compose `Table`, `THead`, `TBody`, `Tr`, `Th`, `Td` and pass
 * layout extras (min-width, alignment, col widths) through `className`.
 */
export const tableClass = "w-full border-collapse text-sm";
export const tableHeadCellClass =
  "text-muted-foreground h-12 px-3 text-left text-xs font-medium whitespace-nowrap";
export const tableCellClass = "px-3 py-2 text-sm";

export const Table = React.forwardRef<
  HTMLTableElement,
  React.TableHTMLAttributes<HTMLTableElement>
>(({ className, ...props }, ref) => (
  <table ref={ref} data-ui="ui-table" className={cn(tableClass, className)} {...props} />
));
Table.displayName = "Table";

export const THead = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => <thead ref={ref} className={cn(className)} {...props} />);
THead.displayName = "THead";

export const TBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => <tbody ref={ref} className={cn(className)} {...props} />);
TBody.displayName = "TBody";

export const Tr = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr ref={ref} className={cn("border-border border-b last:border-0", className)} {...props} />
  ),
);
Tr.displayName = "Tr";

export const Th = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, scope = "col", ...props }, ref) => (
  <th ref={ref} scope={scope} className={cn(tableHeadCellClass, className)} {...props} />
));
Th.displayName = "Th";

export const Td = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <td ref={ref} className={cn(tableCellClass, className)} {...props} />
));
Td.displayName = "Td";
