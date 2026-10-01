"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import type { MemberImportRow } from "@/lib/member-import";

/** Reusable recipient review for file and pasted-list imports. No mutations. */
export function MemberImportPreview({
  rows,
  loading = false,
}: {
  rows: readonly MemberImportRow[];
  loading?: boolean;
}) {
  const t = useTranslations("people");
  return (
    <div
      role="region"
      aria-label={t("importPreview")}
      aria-busy={loading}
      className="border-border focus-visible:ring-ring max-h-64 min-w-0 overflow-auto rounded-sm border focus-visible:ring-2 focus-visible:outline-none"
      // The region provides keyboard scrolling for long previews.
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
    >
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{t("importPreview")}</caption>
        <thead className="bg-muted sticky top-0">
          <tr>
            {["importRow", "email", "nameColumn", "status"].map((key) => (
              <th key={key} scope="col" className="px-3 py-3 text-left text-xs font-medium">
                {t(key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading || !rows.length ? (
            <tr>
              <td colSpan={4} className="text-muted-foreground p-6 text-center">
                <p role="status">{t(loading ? "readingFile" : "emptyImportPreview")}</p>
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.rowNumber} className="border-border border-t align-top">
                <td className="text-muted-foreground px-3 py-3 tabular-nums">{row.rowNumber}</td>
                <td className="max-w-56 px-3 py-3 [overflow-wrap:anywhere] break-words">
                  {row.email || "—"}
                </td>
                <td className="max-w-56 px-3 py-3 [overflow-wrap:anywhere] break-words">
                  {row.displayName || "—"}
                </td>
                <td className="px-3 py-3">
                  <Badge variant={row.error ? "destructive" : "success"} className="font-sans">
                    {t(row.error ?? "importReady")}
                  </Badge>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
