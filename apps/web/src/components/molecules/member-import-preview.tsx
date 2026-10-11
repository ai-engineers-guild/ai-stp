"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
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
      <Table>
        <caption className="sr-only">{t("importPreview")}</caption>
        <THead className="bg-muted sticky top-0">
          <Tr>
            {["importRow", "email", "nameColumn", "status"].map((key) => (
              <Th key={key} className="py-3">
                {t(key)}
              </Th>
            ))}
          </Tr>
        </THead>
        <TBody>
          {loading || !rows.length ? (
            <Tr>
              <Td colSpan={4} className="text-muted-foreground p-6 text-center">
                <p role="status">{t(loading ? "readingFile" : "emptyImportPreview")}</p>
              </Td>
            </Tr>
          ) : (
            rows.map((row) => (
              <Tr key={row.rowNumber} className="align-top">
                <Td className="text-muted-foreground py-3 tabular-nums">{row.rowNumber}</Td>
                <Td className="max-w-56 py-3 [overflow-wrap:anywhere] break-words">
                  {row.email || "—"}
                </Td>
                <Td className="max-w-56 py-3 [overflow-wrap:anywhere] break-words">
                  {row.displayName || "—"}
                </Td>
                <Td className="py-3">
                  <Badge variant={row.error ? "destructive" : "success"} className="font-sans">
                    {t(row.error ?? "importReady")}
                  </Badge>
                </Td>
              </Tr>
            ))
          )}
        </TBody>
      </Table>
    </div>
  );
}
